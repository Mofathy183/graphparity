"""
Point lookup and indexed/filtered lookup workloads.

Point lookup resolves a single node by its primary identifier -- the
cheapest possible read, and the baseline every other workload's
latency should be compared against. Indexed lookup filters by a
secondary, indexed property, which exercises the platform's index
rather than a direct key lookup.
"""

import random

from graphparity.adapters.protocol import GraphAdapter

from .common import Protocol, QueryTemplate, run_timed_workload

POINT_LOOKUP_TEMPLATE = QueryTemplate(
    cypher="MATCH (n {id: $id}) RETURN n LIMIT 1",
    aql="RETURN DOCUMENT(CONCAT('nodes/', @id))",
)

INDEXED_LOOKUP_TEMPLATE = QueryTemplate(
    cypher="MATCH (n {category: $category}) RETURN n LIMIT 25",
    aql="FOR n IN nodes FILTER n.category == @category LIMIT 25 RETURN n",
)


async def run_point_lookup(
    adapter: GraphAdapter,
    protocol: Protocol,
    node_ids: list[str],
    warmup_iterations: int = 10,
    timed_iterations: int = 100,
    rng: random.Random | None = None,
) -> list[float]:
    """Run the point-lookup workload with a random node id per iteration.

    Args:
        adapter: The connected GraphAdapter to run queries against.
        protocol: "bolt" for Cypher platforms, "http" for ArangoDB.
        node_ids: Candidate node identifiers. Must be non-empty.
        warmup_iterations: Discarded iterations before timing starts.
        timed_iterations: Iterations whose latency is kept.
        rng: Optional Random instance for deterministic selection in
            tests.

    Returns:
        One latency value (milliseconds) per timed iteration.

    Raises:
        ValueError: If `node_ids` is empty.
    """
    if not node_ids:
        raise ValueError("node_ids must be non-empty")

    chooser = rng.choice if rng is not None else random.choice
    query = POINT_LOOKUP_TEMPLATE.for_protocol(protocol)

    return await run_timed_workload(
        adapter=adapter,
        query=query,
        params_factory=lambda: {"id": chooser(node_ids)},
        warmup_iterations=warmup_iterations,
        timed_iterations=timed_iterations,
    )


async def run_indexed_lookup(
    adapter: GraphAdapter,
    protocol: Protocol,
    categories: list[str],
    warmup_iterations: int = 10,
    timed_iterations: int = 100,
    rng: random.Random | None = None,
) -> list[float]:
    """Run the indexed/filtered lookup workload with a random category.

    Args:
        adapter: The connected GraphAdapter to run queries against.
        protocol: "bolt" for Cypher platforms, "http" for ArangoDB.
        categories: Candidate values for the indexed property being
            filtered on. Must be non-empty.
        warmup_iterations: Discarded iterations before timing starts.
        timed_iterations: Iterations whose latency is kept.
        rng: Optional Random instance for deterministic selection in
            tests.

    Returns:
        One latency value (milliseconds) per timed iteration.

    Raises:
        ValueError: If `categories` is empty.
    """
    if not categories:
        raise ValueError("categories must be non-empty")

    chooser = rng.choice if rng is not None else random.choice
    query = INDEXED_LOOKUP_TEMPLATE.for_protocol(protocol)

    return await run_timed_workload(
        adapter=adapter,
        query=query,
        params_factory=lambda: {"category": chooser(categories)},
        warmup_iterations=warmup_iterations,
        timed_iterations=timed_iterations,
    )
