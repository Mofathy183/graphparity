"""
Aggregation workload: a count/group-by query over one label or
relationship type.

Unlike traversal and lookup, aggregation has no meaningful per-
iteration parameter to randomize -- a count-by-category query touches
the same data on every call by design, so warm-up here exists purely
to absorb query-plan caching, not to spread load across the graph.
"""

from graphparity.adapters.protocol import GraphAdapter

from .common import Protocol, QueryTemplate, run_timed_workload

AGGREGATION_TEMPLATE = QueryTemplate(
    cypher=(
        "MATCH (n) RETURN n.category AS category, count(*) AS total ORDER BY total DESC"
    ),
    aql=(
        "FOR n IN nodes COLLECT category = n.category WITH COUNT INTO total "
        "SORT total DESC RETURN {category, total}"
    ),
)


async def run_aggregation(
    adapter: GraphAdapter,
    protocol: Protocol,
    warmup_iterations: int = 10,
    timed_iterations: int = 100,
) -> list[float]:
    """Run the count/group-by aggregation workload.

    Args:
        adapter: The connected GraphAdapter to run queries against.
        protocol: "bolt" for Cypher platforms, "http" for ArangoDB.
        warmup_iterations: Discarded iterations before timing starts.
        timed_iterations: Iterations whose latency is kept.

    Returns:
        One latency value (milliseconds) per timed iteration.
    """
    query = AGGREGATION_TEMPLATE.for_protocol(protocol)

    return await run_timed_workload(
        adapter=adapter,
        query=query,
        params_factory=dict,
        warmup_iterations=warmup_iterations,
        timed_iterations=timed_iterations,
    )
