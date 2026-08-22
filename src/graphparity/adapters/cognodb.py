"""
CognoDB Cloud adapter -- Bolt+Cypher via the official `neo4j` async driver.

CognoDB is a managed graph database cloud that speaks openCypher over
Bolt, so this adapter needs no CognoDB-specific SDK -- it is a thin
wrapper around `neo4j.AsyncGraphDatabase` that satisfies the
GraphAdapter Protocol and translates every `neo4j`-raised exception
into a BenchmarkError before it can cross the adapter boundary.

Platform-specific behavior this adapter is responsible for surfacing
correctly:

- CognoDB's free `c0` tier caps query results at 50,000 rows. The
    driver itself does not raise a distinct exception for this -- it
    surfaces as a ClientError with a specific error code in the
    exception's `.code` attribute, so `_translate_query_error` inspects
    that code specifically rather than bucketing every ClientError into
    QUERY_FAILED.
- Every write in `load_batch` uses Cypher `MERGE`, never `CREATE`, so a
    rerun after a partial load failure does not duplicate nodes or
    relationships (see GraphAdapter's own idempotency contract in
    protocol.py).
"""

import time
from typing import LiteralString, cast

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import ClientError, ServiceUnavailable, TransientError

from graphparity.errors import BenchmarkError, ErrorCode

from .protocol import LoadResult, QueryResult

# The specific neo4j ClientError code CognoDB's free c0 tier raises when
# a query's result set exceeds its 50,000-row cap. Kept as a module-level
# constant, not inlined in the except clause, so the platform-specific
# magic string has exactly one place to update if CognoDB's error code
# ever changes.
_RESULT_LIMIT_ERROR_CODE = "Neo.ClientError.Statement.ResultLimitExceeded"

# Batched MERGE queries. UNWIND lets one query load an entire batch in
# one round trip rather than one query per record, which matters at
# real dataset sizes -- a naive per-node query would turn a 200k-node
# load into 200k separate round trips.
_MERGE_NODES_QUERY = """
UNWIND $nodes AS node
MERGE (n:Node {id: node.id})
SET n.category = node.category
"""

_MERGE_RELATIONSHIPS_QUERY = """
UNWIND $relationships AS rel
MATCH (source:Node {id: rel.source})
MATCH (target:Node {id: rel.target})
MERGE (source)-[:CONNECTS_TO]->(target)
"""


def _translate_query_error(exc: Exception) -> BenchmarkError:
    """Map a neo4j-driver exception raised during a query to a BenchmarkError.

    Args:
        exc: The exception the neo4j driver raised.

    Returns:
        The corresponding BenchmarkError, with `exc` preserved as
        `cause` for debugging -- never included in equality comparisons
        (see BenchmarkError's own docstring).
    """
    if isinstance(exc, ServiceUnavailable):
        return BenchmarkError(code=ErrorCode.CONNECTION_FAILED, cause=exc)

    if isinstance(exc, TransientError):
        return BenchmarkError(code=ErrorCode.QUERY_TIMEOUT, cause=exc)

    if isinstance(exc, ClientError):
        if getattr(exc, "code", None) == _RESULT_LIMIT_ERROR_CODE:
            return BenchmarkError(code=ErrorCode.RESULT_LIMIT_EXCEEDED, cause=exc)
        return BenchmarkError(code=ErrorCode.QUERY_FAILED, cause=exc)

    return BenchmarkError(code=ErrorCode.QUERY_FAILED, cause=exc)


class CognoDBAdapter:
    """GraphAdapter implementation for CognoDB Cloud.

    Satisfies the GraphAdapter Protocol structurally -- see
    adapters/protocol.py for the full contract this class must uphold.
    Holds one `neo4j.AsyncDriver` for the lifetime of a single
    connect()/disconnect() pair; `run_query` and `load_batch` both
    require `connect()` to have been called first.

    Attributes:
        name: Always "cognodb" -- the stable identifier used in logs
            and the results matrix.
    """

    name = "cognodb"

    def __init__(self, uri: str, username: str, password: str) -> None:
        """Store connection parameters without opening a connection.

        No I/O happens here -- constructing this adapter is always
        safe, even with no CognoDB instance reachable. The actual
        connection is opened by `connect()`.

        Args:
            uri: The `bolt+s://` connection URI for the CognoDB
                instance.
            username: Auth username, typically "cognodb".
            password: Auth credential.
        """
        self._uri = uri
        self._username = username
        self._password = password
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Open the driver and verify connectivity with a ping.

        Raises:
            BenchmarkError: CONNECTION_FAILED if the instance cannot be
                reached or authentication fails.
        """
        driver = AsyncGraphDatabase.driver(
            self._uri, auth=(self._username, self._password)
        )
        try:
            await driver.verify_connectivity()
        except ServiceUnavailable as exc:
            await driver.close()
            raise BenchmarkError(code=ErrorCode.CONNECTION_FAILED, cause=exc) from exc
        except Exception as exc:
            await driver.close()
            raise BenchmarkError(code=ErrorCode.CONNECTION_FAILED, cause=exc) from exc

        self._driver = driver

    async def disconnect(self) -> None:
        """Close the driver.

        Safe to call even if `connect()` was never called or already
        failed -- matches every other adapter's disconnect contract.
        """
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def run_query(self, query: str, params: dict) -> QueryResult:
        """Run one Cypher query, timed end-to-end.

        Latency is measured from call to full materialization of the
        result set (every row consumed), never time-to-first-row --
        every adapter in this project must measure the same thing so
        latencies are comparable across platforms.

        Args:
            query: A Cypher query string.
            params: Query parameters, passed through to the driver
                unchanged.

        Returns:
            The result rows plus end-to-end latency in milliseconds.

        Raises:
            BenchmarkError: CONNECTION_FAILED if the driver was never
                connected, or if the connection is lost mid-query.
            BenchmarkError: QUERY_TIMEOUT if the query is aborted as
                transient (e.g. a leader election, lock contention).
            BenchmarkError: QUERY_FAILED for any other query error
                (invalid Cypher, constraint violation).
            BenchmarkError: RESULT_LIMIT_EXCEEDED if CognoDB's free-tier
                50,000-row cap is hit.
        """
        if self._driver is None:
            raise BenchmarkError(code=ErrorCode.CONNECTION_FAILED)

        start = time.monotonic()
        try:
            async with self._driver.session() as session:
                result = await session.run(cast(LiteralString, query), params)
                rows = [record.data() async for record in result]
        except BenchmarkError:
            raise
        except Exception as exc:
            raise _translate_query_error(exc) from exc

        latency_ms = (time.monotonic() - start) * 1000
        return QueryResult(rows=rows, latency_ms=latency_ms)

    async def load_batch(
        self, nodes: list[dict], relationships: list[dict]
    ) -> LoadResult:
        """Idempotently MERGE a batch of nodes and/or relationships.

        Either `nodes` or `relationships` may be empty -- the batch
        loader (loader/batch_loader.py) always loads every node batch
        before any relationship batch, so a caller passing one empty
        list here is the expected, common case, not an error.

        Args:
            nodes: Node records, each with `id` and `category` keys.
            relationships: Relationship records, each with `source` and
                `target` keys referencing node ids.

        Returns:
            Counts of nodes/relationships merged plus wall-clock time
            for this batch.

        Raises:
            BenchmarkError: CONNECTION_FAILED if the driver was never
                connected.
            BenchmarkError: LOAD_FAILED if the batch fails partway
                through or entirely.
        """
        if self._driver is None:
            raise BenchmarkError(code=ErrorCode.CONNECTION_FAILED)

        start = time.monotonic()
        try:
            async with self._driver.session() as session:
                if nodes:
                    await session.run(_MERGE_NODES_QUERY, {"nodes": nodes})
                if relationships:
                    await session.run(
                        _MERGE_RELATIONSHIPS_QUERY, {"relationships": relationships}
                    )
        except Exception as exc:
            raise BenchmarkError(code=ErrorCode.LOAD_FAILED, cause=exc) from exc

        wall_clock_seconds = time.monotonic() - start
        return LoadResult(
            nodes_loaded=len(nodes),
            relationships_loaded=len(relationships),
            wall_clock_seconds=wall_clock_seconds,
        )
