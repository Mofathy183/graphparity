"""
1-hop, 2-hop, and 3-hop traversal workloads.

Each hop depth is expressed as one QueryTemplate (Cypher + AQL), and
every timed iteration starts from a different randomly chosen node --
the brief requires random start nodes specifically so results reflect
typical traversal cost rather than one cached hot path.
"""

import random

from graphparity.adapters.protocol import GraphAdapter

from .common import Protocol, QueryTemplate, run_timed_workload

_TRAVERSAL_TEMPLATES: dict[int, QueryTemplate] = {
    1: QueryTemplate(
        cypher=("MATCH (start {id: $start_id})-->(neighbor) RETURN neighbor LIMIT 1"),
        aql=(
            "FOR v IN 1..1 OUTBOUND CONCAT('nodes/', @start_id) edges LIMIT 1 RETURN v"
        ),
    ),
    2: QueryTemplate(
        cypher=(
            "MATCH (start {id: $start_id})-->()-->(neighbor) RETURN neighbor LIMIT 1"
        ),
        aql=(
            "FOR v IN 2..2 OUTBOUND CONCAT('nodes/', @start_id) edges LIMIT 1 RETURN v"
        ),
    ),
    3: QueryTemplate(
        cypher=(
            "MATCH (start {id: $start_id})-->()-->()-->(neighbor) "
            "RETURN neighbor LIMIT 1"
        ),
        aql=(
            "FOR v IN 3..3 OUTBOUND CONCAT('nodes/', @start_id) edges LIMIT 1 RETURN v"
        ),
    ),
}


async def run_traversal(
    adapter: GraphAdapter,
    protocol: Protocol,
    node_ids: list[str],
    hops: int,
    warmup_iterations: int = 10,
    timed_iterations: int = 100,
    rng: random.Random | None = None,
) -> list[float]:
    """Run a fixed-depth traversal workload with random start nodes.

    Args:
        adapter: The connected GraphAdapter to run queries against.
        protocol: Which query language to use -- "bolt" for Cypher
            platforms, "http" for ArangoDB.
        node_ids: Candidate start-node identifiers. Must be non-empty;
            one is chosen at random (with replacement) per iteration.
        hops: Traversal depth. Must be 1, 2, or 3 -- the three depths
            the brief requires.
        warmup_iterations: Discarded iterations before timing starts.
        timed_iterations: Iterations whose latency is kept.
        rng: Optional Random instance for deterministic start-node
            selection in tests. Defaults to the module-level random
            functions when omitted.

    Returns:
        One latency value (milliseconds) per timed iteration.

    Raises:
        ValueError: If `hops` is not 1, 2, or 3, or if `node_ids` is
            empty.
    """
    if hops not in _TRAVERSAL_TEMPLATES:
        raise ValueError(f"hops must be 1, 2, or 3, got {hops}")
    if not node_ids:
        raise ValueError("node_ids must be non-empty")

    chooser = rng.choice if rng is not None else random.choice
    query = _TRAVERSAL_TEMPLATES[hops].for_protocol(protocol)

    return await run_timed_workload(
        adapter=adapter,
        query=query,
        params_factory=lambda: {"start_id": chooser(node_ids)},
        warmup_iterations=warmup_iterations,
        timed_iterations=timed_iterations,
    )
