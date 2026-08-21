"""
In-memory GraphAdapter implementation for workload/runner unit tests.

a lightweight fake that satisfies the real contract (GraphAdapter,
here structurally rather than via ABC inheritance) with no I/O, plus
inspection hooks and controllable failure/latency injection so the
runner's warm-up/discard logic and the mixed-workload concurrency path
can be exercised deterministically.

Unlike FakePostingRepo, this fake needs to be *scriptable* rather than
purely observational -- a test asserting "the Nth call during warm-up
is discarded" needs to control exactly what the Nth call returns and
how long it appears to take.
"""

import asyncio
from dataclasses import dataclass

from graphparity.adapters.protocol import LoadResult, QueryResult
from graphparity.errors import BenchmarkError, ErrorCode


@dataclass
class _ScriptedQuery:
    """One pre-programmed response for a single run_query call."""

    result: QueryResult | None = None
    error: BenchmarkError | None = None
    delay_seconds: float = 0.0


class FakeGraphAdapter:
    """In-memory GraphAdapter for unit tests -- no network, no driver.

    Satisfies the GraphAdapter Protocol structurally (no inheritance
    required). Responses are consumed from a queue in FIFO order per
    method, so a test can script exactly what the Nth call returns --
    essential for asserting warm-up/discard boundaries precisely,
    which a fixed always-the-same-result fake could not do.

    Attributes:
        name: Fake platform identifier, defaults to "fake".
        connect_calls: Count of connect() invocations.
        disconnect_calls: Count of disconnect() invocations.
        query_calls: Every (query, params) pair passed to run_query,
            in call order.
        load_calls: Every (nodes, relationships) pair passed to
            load_batch, in call order.
        concurrent_query_count: Current number of in-flight run_query
            calls -- lets a mixed-workload test assert calls actually
            overlapped rather than ran serially.
        max_observed_concurrency: High-water mark of
            concurrent_query_count, useful for asserting a concurrency
            sweep actually achieved parallelism.
    """

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.query_calls: list[tuple[str, dict]] = []
        self.load_calls: list[tuple[list[dict], list[dict]]] = []
        self.concurrent_query_count = 0
        self.max_observed_concurrency = 0

        self._connected = False
        self._query_queue: list[_ScriptedQuery] = []
        self._default_query_result = QueryResult(rows=[], latency_ms=0.0)
        self._load_queue: list[LoadResult | BenchmarkError] = []
        self._default_load_result = LoadResult(
            nodes_loaded=0, relationships_loaded=0, wall_clock_seconds=0.0
        )
        self._connect_error: BenchmarkError | None = None

    # --- Scripting API (test setup, not part of the Protocol) --------

    def queue_query_result(
        self,
        rows: list[dict] | None = None,
        latency_ms: float = 0.0,
        delay_seconds: float = 0.0,
    ) -> None:
        """Queue a successful run_query response for the next call.

        Args:
            rows: Rows the next run_query call should return. Defaults
                to an empty list.
            latency_ms: The latency value the next call should report
                -- lets a test assert p50/p95 math against a known
                input without depending on real timing.
            delay_seconds: If set, the call actually awaits this long
                before returning -- use only when a test needs a real
                elapsed-time assertion; use latency_ms for everything
                else.
        """
        self._query_queue.append(
            _ScriptedQuery(
                result=QueryResult(rows=rows or [], latency_ms=latency_ms),
                delay_seconds=delay_seconds,
            )
        )

    def queue_query_error(self, code: ErrorCode, delay_seconds: float = 0.0) -> None:
        """Queue a BenchmarkError for the next run_query call.

        Args:
            code: The error code the next call should raise.
            delay_seconds: Optional artificial delay before raising.
        """
        self._query_queue.append(
            _ScriptedQuery(error=BenchmarkError(code=code), delay_seconds=delay_seconds)
        )

    def queue_load_result(self, result: LoadResult) -> None:
        """Queue a successful load_batch response for the next call."""
        self._load_queue.append(result)

    def queue_load_error(self, code: ErrorCode) -> None:
        """Queue a BenchmarkError for the next load_batch call."""
        self._load_queue.append(BenchmarkError(code=code))

    def fail_next_connect(self, code: ErrorCode) -> None:
        """Make the next connect() call raise BenchmarkError(code)."""
        self._connect_error = BenchmarkError(code=code)

    # --- GraphAdapter Protocol implementation -------------------------

    async def connect(self) -> None:
        self.connect_calls += 1
        if self._connect_error is not None:
            error, self._connect_error = self._connect_error, None
            raise error
        self._connected = True

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    async def run_query(self, query: str, params: dict) -> QueryResult:
        self.query_calls.append((query, params))

        scripted = self._query_queue.pop(0) if self._query_queue else _ScriptedQuery()

        self.concurrent_query_count += 1
        self.max_observed_concurrency = max(
            self.max_observed_concurrency, self.concurrent_query_count
        )
        try:
            if scripted.delay_seconds:
                await asyncio.sleep(scripted.delay_seconds)

            if scripted.error is not None:
                raise scripted.error

            return scripted.result or self._default_query_result
        finally:
            self.concurrent_query_count -= 1

    async def load_batch(
        self, nodes: list[dict], relationships: list[dict]
    ) -> LoadResult:
        self.load_calls.append((list(nodes), list(relationships)))

        outcome = (
            self._load_queue.pop(0) if self._load_queue else self._default_load_result
        )

        if isinstance(outcome, BenchmarkError):
            raise outcome

        return outcome
