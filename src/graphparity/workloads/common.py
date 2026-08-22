"""
Shared execution helpers for GraphParity's read-workload shapes.

Every read workload (1/2/3-hop traversal, point lookup, indexed
lookup, aggregation) follows the same execution pattern: run a fixed
number of warm-up iterations against the adapter and discard their
latencies, then run a fixed number of timed iterations and keep every
latency. This module owns that shared pattern once, so each
workload-shape module only has to supply its own query text and
per-iteration parameters.

Nothing here knows which platform it's talking to -- callers already
resolved that by picking the right entry from a QueryTemplate before
calling run_timed_workload.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from graphparity.adapters.protocol import GraphAdapter

Protocol = Literal["bolt", "http"]


@dataclass(frozen=True)
class QueryTemplate:
    """One workload shape, expressed in both query languages GraphParity speaks.

    Every platform GraphParity benchmarks maps onto exactly one of
    these two families (matching PlatformConfig's own `protocol`
    field): `cypher` for every Bolt+Cypher platform (CognoDB, AuraDB,
    self-hosted Neo4j, Memgraph) and `aql` for ArangoDB. Both variants
    must express the same workload shape -- e.g. both must be a 2-hop
    outbound traversal -- so the two languages remain a translation of
    each other, not two different benchmarks.

    Attributes:
        cypher: The query text for every Bolt+Cypher platform.
        aql: The query text for ArangoDB.
    """

    cypher: str
    aql: str

    def for_protocol(self, protocol: Protocol) -> str:
        """Return the query text matching a platform's protocol family.

        Args:
            protocol: "bolt" for Cypher platforms, "http" for AQL
                (ArangoDB).

        Returns:
            The matching query text.
        """
        return self.cypher if protocol == "bolt" else self.aql


async def run_timed_workload(
    adapter: GraphAdapter,
    query: str,
    params_factory: Callable[[], dict],
    warmup_iterations: int = 10,
    timed_iterations: int = 100,
) -> list[float]:
    """Run one query shape against an adapter, warm-up then timed.

    Executes `warmup_iterations` calls first and discards every
    latency they report -- this absorbs connection/cache warm-up cost
    so it never contaminates the numbers that actually get reported.
    Only the `timed_iterations` calls that follow contribute to the
    returned sample list.

    Args:
        adapter: The connected GraphAdapter to run queries against.
        query: The query text to execute on every iteration, already
            resolved to the adapter's own protocol (e.g. via
            `QueryTemplate.for_protocol`).
        params_factory: Called once per iteration (including warm-up
            iterations) to produce that iteration's query parameters --
            e.g. a fresh random start-node id per call, so every
            iteration exercises a different part of the graph rather
            than benefiting from a single cached lookup.
        warmup_iterations: Number of discarded iterations before timing
            starts. Must be >= 0.
        timed_iterations: Number of iterations whose latency is kept.
            Must be >= 1.

    Returns:
        One latency value (milliseconds) per timed iteration, in the
        order the calls completed.

    Raises:
        ValueError: If `warmup_iterations` is negative or
            `timed_iterations` is less than 1.
        BenchmarkError: Whatever `adapter.run_query` raises on the
            first failed call -- this function makes no attempt to
            retry or swallow adapter failures; that policy belongs to
            the caller orchestrating the full run.
    """
    if warmup_iterations < 0:
        raise ValueError("warmup_iterations must be >= 0")
    if timed_iterations < 1:
        raise ValueError("timed_iterations must be >= 1")

    for _ in range(warmup_iterations):
        await adapter.run_query(query, params_factory())

    latencies: list[float] = []
    for _ in range(timed_iterations):
        result = await adapter.run_query(query, params_factory())
        latencies.append(result.latency_ms)

    return latencies
