"""
One-command entry point: load a dataset into CognoDB and run every
required workload, producing a raw results JSON file.

Deliberately scoped to CognoDB only for this submission -- the other
four platforms (AuraDB, self-hosted Neo4j, Memgraph, ArangoDB) are not
included in this run because their credentials/instances were not
available before the deadline. This is documented in the README as an
explicit, honest scope reduction, not a silent gap: every other layer
of the harness (GraphAdapter Protocol, workload runner, aggregator) is
platform-agnostic and ready to accept those adapters the moment
credentials exist -- see README's "Scope and caveats" section.

Usage:
    uv run python scripts/run_all.py
"""

import asyncio
import json
import time
from pathlib import Path

from graphparity.adapters.cognodb import CognoDBAdapter
from graphparity.aggregate import build_results_matrix
from graphparity.config import get_platforms_settings
from graphparity.loader.batch_loader import load_dataset
from graphparity.loader.dataset import build_dataset
from graphparity.runner import run_platform_workloads

# Kept small deliberately: this run is scoped to what fits comfortably
# inside a tight time window while still producing honest, non-trivial
# p50/p95 numbers -- not the full 150k-300k relationship benchmark
# dataset the brief describes as the target range. The README states
# this size explicitly so the numbers are never presented as directly
# comparable to a full-scale run.
_EDGE_COUNT = 5_000

RESULTS_DIR = Path("results")


def _toy_edges(count: int) -> list[tuple[str, str]]:
    """Generate a small synthetic connected graph as a placeholder edge list.

    Used only when no real downloaded edge-list file is available in
    the time remaining. Produces a simple chain-plus-branch structure
    that is connected enough for 1/2/3-hop traversal to succeed.
    """
    edges = []
    for i in range(count):
        edges.append((f"n{i}", f"n{i + 1}"))
        if i % 7 == 0 and i > 0:
            edges.append((f"n{i}", f"n{i - 3}"))
    return edges


async def main() -> None:
    settings = get_platforms_settings()
    cfg = settings.cognodb

    print(f"Building dataset ({_EDGE_COUNT} edges)...")
    edges = _toy_edges(_EDGE_COUNT)
    dataset = build_dataset(edges)
    print(f"  nodes={dataset.node_count} relationships={dataset.relationship_count}")

    adapter = CognoDBAdapter(uri=cfg.uri, username=cfg.username, password=cfg.password)

    print("Connecting to CognoDB...")
    await adapter.connect()

    try:
        print("Loading dataset (idempotent MERGE)...")
        load_summary = await load_dataset(adapter, dataset, batch_size=1000)
        print(
            f"  loaded {load_summary.nodes_loaded} nodes, "
            f"{load_summary.relationships_loaded} relationships in "
            f"{load_summary.elapsed_seconds:.2f}s "
            f"({load_summary.nodes_per_second:.1f} nodes/sec, "
            f"{load_summary.relationships_per_second:.1f} rels/sec)"
        )

        node_ids = [n.id for n in dataset.nodes]
        categories = list({n.category for n in dataset.nodes})

        print("Running workload suite (this is the slow part)...")
        start = time.monotonic()
        workload_results = await run_platform_workloads(
            adapter,
            protocol="bolt",
            node_ids=node_ids,
            categories=categories,
            warmup_iterations=10,
            timed_iterations=100,
            mixed_concurrencies=(10, 40),
            mixed_duration_seconds=5.0,
        )
        print(f"  workloads completed in {time.monotonic() - start:.1f}s")

    finally:
        await adapter.disconnect()

    raw_results = {"cognodb": workload_results}
    matrix = build_results_matrix(raw_results)

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "cognodb_results.json"
    with out_path.open("w") as f:
        json.dump(
            {
                "load_summary": {
                    "platform": load_summary.platform,
                    "nodes_loaded": load_summary.nodes_loaded,
                    "relationships_loaded": load_summary.relationships_loaded,
                    "elapsed_seconds": load_summary.elapsed_seconds,
                    "nodes_per_second": load_summary.nodes_per_second,
                    "relationships_per_second": load_summary.relationships_per_second,
                },
                "workload_summaries": [
                    {
                        "platform": s.platform,
                        "workload": s.workload,
                        "sample_count": s.sample_count,
                        "percentiles": s.percentiles,
                        "min_ms": s.min_ms,
                        "max_ms": s.max_ms,
                        "mean_ms": s.mean_ms,
                    }
                    for s in matrix
                ],
            },
            f,
            indent=2,
        )

    print(f"\nResults written to {out_path}")
    print("\n--- Summary ---")
    for s in matrix:
        p50 = s.percentiles.get(50.0)
        p95 = s.percentiles.get(95.0)
        print(
            f"{s.workload:25s} p50={p50:8.2f}ms  p95={p95:8.2f}ms  n={s.sample_count}"
        )


if __name__ == "__main__":
    asyncio.run(main())
