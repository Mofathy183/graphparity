"""
Adapter contract for GraphParity.

GraphAdapter is the structural (Protocol) equivalent of PostingRepo in
PyLedger: it defines the boundary every platform-specific client must
satisfy, without any of them inheriting from a shared base class. The
workload runner and aggregate.py depend only on this module, never on
a concrete adapter -- that's what keeps five platforms' numbers
comparable in one table instead of five ad hoc scripts.

Implementations must:

- Remain asynchronous.
- Translate their own client library's exceptions into BenchmarkError
    before returning -- never let a neo4j.exceptions.* or
    arango.exceptions.* type cross this boundary.
- Perform load_batch idempotently (MERGE/upsert, never CREATE), so a
    rerun after a partial failure doesn't duplicate data.
- Avoid any workload-shape knowledge (1-hop vs 3-hop, etc.) -- that
    belongs in workloads/, not here.
"""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class QueryResult(BaseModel):
    """Outcome of a single timed query against a platform.

    Attributes:
        rows: The raw result rows, as returned by the platform's
            driver, converted to plain dicts.
        latency_ms: Wall-clock time from call to full materialization
            of the result set, in milliseconds. Never partial timing
            (e.g. time-to-first-row) -- every adapter must measure the
            same thing so latencies are comparable across platforms.
    """

    rows: list[dict]
    latency_ms: float = Field(ge=0)


class LoadResult(BaseModel):
    """Outcome of a single batch load call.

    Attributes:
        nodes_loaded: Count of nodes created or merged in this batch.
        relationships_loaded: Count of relationships created or merged
            in this batch.
        wall_clock_seconds: Total time for the batch, including any
            driver-side batching/retries -- this is what ingest
            throughput (nodes/sec, rels/sec) is computed from.
    """

    nodes_loaded: int = Field(ge=0)
    relationships_loaded: int = Field(ge=0)
    wall_clock_seconds: float = Field(ge=0)


@runtime_checkable
class GraphAdapter(Protocol):
    """Persistence/query contract every platform adapter must satisfy.

    Structurally typed rather than an ABC, since GraphParity has no
    inheritance hierarchy to enforce -- five unrelated client libraries
    (neo4j driver, python-arango, ...) each produce a class that
    happens to match this shape. `runtime_checkable` lets tests assert
    `isinstance(adapter, GraphAdapter)` as a cheap conformance check.

    Attributes:
        name: Short, stable platform identifier used in logs and the
            results matrix (e.g. "cognodb", "aura", "self_hosted_neo4j").
    """

    name: str

    async def connect(self) -> None:
        """Establish the connection/session for this platform.

        Raises:
            BenchmarkError: CONNECTION_FAILED if the platform cannot
                be reached or authentication fails.
        """
        ...

    async def disconnect(self) -> None:
        """Release the connection/session for this platform.

        Must be safe to call even if `connect()` was never called or
        already failed.
        """
        ...

    async def run_query(self, query: str, params: dict) -> QueryResult:
        """Run one query (Cypher or AQL, depending on the platform), timed.

        Args:
            query: The query string, in whichever language this
                platform speaks. Callers (workloads/*.py) are
                responsible for supplying the right dialect per adapter.
            params: Query parameters, passed through to the driver
                unchanged.

        Returns:
            The result rows plus end-to-end latency.

        Raises:
            BenchmarkError: QUERY_TIMEOUT if the driver's own timeout fires.
            BenchmarkError: QUERY_FAILED for any other driver-raised error.
            BenchmarkError: RESULT_LIMIT_EXCEEDED if the platform's own
                row cap is hit (e.g. CognoDB Free's 50,000-row limit).
        """
        ...

    async def load_batch(
        self, nodes: list[dict], relationships: list[dict]
    ) -> LoadResult:
        """Idempotently load a batch of nodes and relationships.

        Args:
            nodes: Node records to merge, in whatever shape the
                loader's dataset module produces.
            relationships: Relationship records to merge, referencing
                the same node identifiers as `nodes`.

        Returns:
            Counts and wall-clock time for this batch.

        Raises:
            BenchmarkError: LOAD_FAILED if the batch fails partway
                through or entirely.
        """
        ...
