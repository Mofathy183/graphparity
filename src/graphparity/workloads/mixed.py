"""
Mixed read/write workload at a stated concurrency level.

Runs `concurrency` worker coroutines concurrently for a fixed wall-
clock duration, each repeatedly issuing either a read or a write query
according to `read_write_ratio`, and reports sustained throughput
(queries/sec) alongside every individual latency observed. This is the
one workload shape measuring throughput under concurrent load rather
than per-call latency in isolation -- the other four workloads run
serially, one call at a time.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field

from graphparity.adapters.protocol import GraphAdapter

from .common import Protocol, QueryTemplate

READ_TEMPLATE = QueryTemplate(
    cypher="MATCH (n {id: $id}) RETURN n LIMIT 1",
    aql="RETURN DOCUMENT(CONCAT('nodes/', @id))",
)

WRITE_TEMPLATE = QueryTemplate(
    cypher="MATCH (n {id: $id}) SET n.touched_at = $touched_at RETURN n",
    aql="UPDATE @id WITH {touched_at: @touched_at} IN nodes RETURN NEW",
)


@dataclass
class MixedWorkloadResult:
    """Outcome of one mixed read/write run at a stated concurrency.

    Attributes:
        concurrency: The number of concurrent workers that ran.
        queries_completed: Total queries executed across every worker.
        elapsed_seconds: Actual wall-clock duration of the run.
        throughput_qps: `queries_completed / elapsed_seconds`.
        read_latencies_ms: Latency of every completed read query.
        write_latencies_ms: Latency of every completed write query.
    """

    concurrency: int
    queries_completed: int
    elapsed_seconds: float
    throughput_qps: float
    read_latencies_ms: list[float] = field(default_factory=list)
    write_latencies_ms: list[float] = field(default_factory=list)


async def run_mixed_workload(
    adapter: GraphAdapter,
    protocol: Protocol,
    node_ids: list[str],
    concurrency: int,
    duration_seconds: float = 5.0,
    read_write_ratio: float = 0.8,
    rng: random.Random | None = None,
) -> MixedWorkloadResult:
    """Run concurrent read/write queries for a fixed duration.

    Spawns `concurrency` worker coroutines, each looping for
    `duration_seconds` of wall-clock time, choosing a read query with
    probability `read_write_ratio` and a write query otherwise on every
    iteration. All workers run concurrently via `asyncio.gather`, so
    genuine overlap depends on the adapter's own connection handling
    supporting concurrent calls -- a serialized adapter would still
    complete correctly, just without any real throughput gain.

    Args:
        adapter: The connected GraphAdapter to run queries against.
        protocol: "bolt" for Cypher platforms, "http" for ArangoDB.
        node_ids: Candidate node identifiers for both the read and
            write query. Must be non-empty.
        concurrency: Number of concurrent workers. Must be >= 1.
        duration_seconds: Wall-clock duration each worker runs for.
            Must be > 0.
        read_write_ratio: Probability that a given iteration issues a
            read rather than a write. Must be in [0, 1].
        rng: Optional Random instance for deterministic query-type and
            node-id selection in tests.

    Returns:
        The aggregated outcome across every worker.

    Raises:
        ValueError: If `node_ids` is empty, `concurrency` < 1,
            `duration_seconds` <= 0, or `read_write_ratio` is outside
            [0, 1].
    """
    if not node_ids:
        raise ValueError("node_ids must be non-empty")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")
    if not 0 <= read_write_ratio <= 1:
        raise ValueError("read_write_ratio must be within [0, 1]")

    chooser = rng.choice if rng is not None else random.choice
    roll = rng.random if rng is not None else random.random

    read_query = READ_TEMPLATE.for_protocol(protocol)
    write_query = WRITE_TEMPLATE.for_protocol(protocol)

    read_latencies: list[float] = []
    write_latencies: list[float] = []

    async def worker() -> None:
        end_at = time.monotonic() + duration_seconds
        while time.monotonic() < end_at:
            node_id = chooser(node_ids)
            if roll() < read_write_ratio:
                result = await adapter.run_query(read_query, {"id": node_id})
                read_latencies.append(result.latency_ms)
            else:
                result = await adapter.run_query(
                    write_query,
                    {"id": node_id, "touched_at": time.time()},
                )
                write_latencies.append(result.latency_ms)

    start = time.monotonic()
    await asyncio.gather(*(worker() for _ in range(concurrency)))
    elapsed = time.monotonic() - start

    completed = len(read_latencies) + len(write_latencies)

    return MixedWorkloadResult(
        concurrency=concurrency,
        queries_completed=completed,
        elapsed_seconds=elapsed,
        throughput_qps=completed / elapsed if elapsed > 0 else 0.0,
        read_latencies_ms=read_latencies,
        write_latencies_ms=write_latencies,
    )
