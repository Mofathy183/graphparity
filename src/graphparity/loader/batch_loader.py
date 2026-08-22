"""
Idempotent batch loading of a DatasetBuild into a connected
GraphAdapter.

Nodes and relationships are loaded in separate batch passes -- every
node batch first, then every relationship batch -- rather than
interleaved, because a relationship's endpoints must already exist
(with their assigned category) before that relationship is merged in;
loading nodes first removes any ordering dependency between individual
relationship batches and the node batches that established their
endpoints.

Every GraphAdapter.load_batch call is expected to MERGE rather than
CREATE (see GraphAdapter's own contract in adapters/protocol.py), so
re-running this loader after a partial failure is safe: already-loaded
nodes and relationships are matched and left unchanged, not duplicated.
"""

import time
from dataclasses import dataclass

from graphparity.adapters.protocol import GraphAdapter
from graphparity.errors import BenchmarkError

from .dataset import DatasetBuild


@dataclass
class BatchLoadSummary:
    """Aggregated outcome of loading one DatasetBuild into one platform.

    Attributes:
        platform: The GraphAdapter.name this dataset was loaded into.
        nodes_loaded: Total nodes reported across every node batch.
        relationships_loaded: Total relationships reported across every
            relationship batch.
        elapsed_seconds: Wall-clock time for the entire load (node
            batches plus relationship batches), measured here rather
            than summed from each batch's own reported
            wall_clock_seconds -- this is the number ingest-throughput
            reporting should use, since it reflects the actual time a
            caller waited, including any inter-batch overhead a
            per-call timing wouldn't capture.
        node_batches: Number of load_batch calls used to load nodes.
        relationship_batches: Number of load_batch calls used to load
            relationships.
    """

    platform: str
    nodes_loaded: int = 0
    relationships_loaded: int = 0
    elapsed_seconds: float = 0.0
    node_batches: int = 0
    relationship_batches: int = 0

    @property
    def nodes_per_second(self) -> float:
        """Ingest throughput for nodes, or 0.0 if elapsed_seconds is 0."""
        return self.nodes_loaded / self.elapsed_seconds if self.elapsed_seconds else 0.0

    @property
    def relationships_per_second(self) -> float:
        """Ingest throughput for relationships, or 0.0 if elapsed_seconds is 0."""
        return (
            self.relationships_loaded / self.elapsed_seconds
            if self.elapsed_seconds
            else 0.0
        )


def _chunk(items: list, size: int) -> list[list]:
    """Split a list into consecutive chunks of at most `size` items."""
    return [items[i : i + size] for i in range(0, len(items), size)]


async def load_dataset(
    adapter: GraphAdapter,
    dataset: DatasetBuild,
    batch_size: int = 2000,
) -> BatchLoadSummary:
    """Load a full DatasetBuild into a connected adapter, batch by batch.

    Assumes `adapter` is already connected -- connection lifecycle is
    the caller's responsibility, the same precondition the workload
    runner places on an adapter it's given.

    Args:
        adapter: The already-connected GraphAdapter to load into.
        dataset: The node/relationship records to load, e.g. the output
            of dataset.build_dataset.
        batch_size: Maximum number of records per load_batch call. Node
            batches and relationship batches are chunked
            independently, each up to this size. Must be >= 1.

    Returns:
        The aggregated load outcome across every batch.

    Raises:
        ValueError: If `batch_size` is less than 1.
        BenchmarkError: LOAD_FAILED if any batch fails -- this function
            does not retry or continue past a failed batch, since a
            partial load left in an unknown state should not be
            silently reported as if every batch had succeeded.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")

    summary = BatchLoadSummary(platform=adapter.name)

    node_dicts = [node.model_dump() for node in dataset.nodes]
    relationship_dicts = [rel.model_dump() for rel in dataset.relationships]

    node_batches = _chunk(node_dicts, batch_size)
    relationship_batches = _chunk(relationship_dicts, batch_size)

    start = time.monotonic()
    try:
        for batch in node_batches:
            result = await adapter.load_batch(batch, [])
            summary.nodes_loaded += result.nodes_loaded
            summary.node_batches += 1

        for batch in relationship_batches:
            result = await adapter.load_batch([], batch)
            summary.relationships_loaded += result.relationships_loaded
            summary.relationship_batches += 1
    except BenchmarkError:
        raise
    finally:
        summary.elapsed_seconds = time.monotonic() - start

    return summary
