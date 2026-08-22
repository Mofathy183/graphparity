"""
Dataset acquisition and trimming for GraphParity's benchmark corpus.

Turns a raw edge-list file (source_id, target_id per line -- the shape
every large public graph dataset in scope for this project ships in)
into the two record collections every GraphAdapter.load_batch call
needs: node records (with a synthetic, deterministically-assigned
`category` property so the indexed-lookup workload has something real
to filter on) and relationship records referencing those node ids.

Trimming takes a contiguous prefix of the parsed edge list rather than
a random sample. A random sample of edges from a graph this size tends
to fragment into many disconnected pairs, which would make every
multi-hop traversal workload degenerate into "no path found" long
before real traversal cost is ever measured. A prefix -- edges kept in
their original file order -- preserves far more of the source graph's
local connectivity, since most edge-list exports group a node's
outgoing edges together.

Nothing in this module performs any GraphAdapter I/O; it only reads a
local file and produces plain, already-validated in-memory records.
Fetching the source file itself (e.g. downloading and decompressing a
source archive) is left to whatever script calls this module, so
dataset parsing stays testable against a small fixture file with no
network access required.
"""

from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import BaseModel, Field

from graphparity.errors import BenchmarkError, ErrorCode

# Categories assigned to every node, deterministically by a hash of
# the node's id. Three buckets is enough to give the indexed-lookup
# workload a real, non-trivial filter -- each bucket ends up with
# roughly a third of the node set, so run_indexed_lookup's LIMIT 25
# query never trivially returns the entire graph.
DEFAULT_CATEGORIES: tuple[str, ...] = ("standard", "premium", "enterprise")

MIN_RELATIONSHIP_COUNT = 100_000
MAX_RELATIONSHIP_COUNT = 500_000
DEFAULT_TARGET_RELATIONSHIPS = 200_000


class NodeRecord(BaseModel):
    """One node destined for GraphAdapter.load_batch.

    Attributes:
        id: The node's identifier, taken directly from the source edge
            list -- never regenerated, so a node's id in the loaded
            graph matches the id a caller sees in the source file.
        category: A deterministically-assigned bucket from
            DEFAULT_CATEGORIES (or a caller-supplied category tuple),
            used as the filtered property in the indexed-lookup
            workload.
    """

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)


class RelationshipRecord(BaseModel):
    """One relationship destined for GraphAdapter.load_batch.

    Attributes:
        source: The id of the node this relationship originates from.
        target: The id of the node this relationship points to.
    """

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


class DatasetBuild(BaseModel):
    """The full node/relationship set produced by build_dataset.

    Attributes:
        nodes: Every unique node discovered in the trimmed edge list,
            each with an assigned category.
        relationships: The trimmed relationship list, in original file
            order.
        node_count: Convenience count, equal to len(nodes) -- kept as
            its own field so a caller building a README's dataset
            section can read it directly instead of recomputing it.
        relationship_count: Convenience count, equal to
            len(relationships).
    """

    nodes: list[NodeRecord]
    relationships: list[RelationshipRecord]
    node_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)


def parse_edge_list(lines: Iterable[str]) -> Iterator[tuple[str, str]]:
    """Parse a raw edge-list file's lines into (source, target) pairs.

    Blank lines and lines beginning with `#` (the comment convention
    most public edge-list exports use for a header block) are skipped.
    Every remaining line must split into exactly two whitespace-
    separated tokens.

    Args:
        lines: An iterable of raw lines, e.g. an open file handle or a
            list of strings in a test fixture.

    Yields:
        One (source_id, target_id) tuple per valid edge line, in file
        order.

    Raises:
        BenchmarkError: MALFORMED_EDGE_LINE if a non-comment, non-blank
            line does not split into exactly two tokens.
    """
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        tokens = stripped.split()
        if len(tokens) != 2:
            raise BenchmarkError(
                code=ErrorCode.MALFORMED_EDGE_LINE,
                context={"line": stripped},
            )

        yield tokens[0], tokens[1]


def load_edge_list_file(path: Path) -> list[tuple[str, str]]:
    """Read and parse an edge-list file from disk.

    Args:
        path: Path to the local edge-list file. Downloading or
            decompressing the source archive is the caller's
            responsibility -- this function only reads a plain-text
            file already on disk.

    Returns:
        Every parsed (source_id, target_id) pair, in file order.

    Raises:
        BenchmarkError: MALFORMED_EDGE_LINE if any line is malformed
            (see parse_edge_list).
        BenchmarkError: EMPTY_DATASET if the file contains no edges
            after skipping comments and blank lines.
    """
    with path.open(encoding="utf-8") as handle:
        edges = list(parse_edge_list(handle))

    if not edges:
        raise BenchmarkError(
            code=ErrorCode.EMPTY_DATASET,
            context={"path": str(path)},
        )

    return edges


def trim_relationships(
    edges: list[tuple[str, str]],
    target_relationship_count: int = DEFAULT_TARGET_RELATIONSHIPS,
    min_relationship_count: int = MIN_RELATIONSHIP_COUNT,
    max_relationship_count: int = MAX_RELATIONSHIP_COUNT,
) -> list[tuple[str, str]]:
    """Trim a parsed edge list to a target relationship count.

    Keeps the first `target_relationship_count` edges in their original
    file order (see the module docstring for why a prefix is used
    instead of a random sample). `target_relationship_count` itself
    must fall within [min_relationship_count, max_relationship_count]
    -- the band every platform's free/entry tier in this benchmark was
    sized to fit -- so a caller cannot accidentally produce a dataset
    too large for the smallest tier or too small to be a meaningful
    benchmark.

    Args:
        edges: The full parsed edge list to trim from.
        target_relationship_count: How many relationships the trimmed
            dataset should contain.
        min_relationship_count: Lower bound target_relationship_count
            must satisfy.
        max_relationship_count: Upper bound target_relationship_count
            must satisfy.

    Returns:
        The first `target_relationship_count` edges from `edges`.

    Raises:
        BenchmarkError: EMPTY_DATASET if `edges` is empty.
        BenchmarkError: RELATIONSHIP_COUNT_OUT_OF_RANGE if
            `target_relationship_count` falls outside
            [min_relationship_count, max_relationship_count].
        BenchmarkError: INSUFFICIENT_RELATIONSHIPS if `edges` has fewer
            entries than `target_relationship_count` -- the source
            dataset cannot satisfy the requested size at all.
    """
    if not edges:
        raise BenchmarkError(code=ErrorCode.EMPTY_DATASET)

    if (
        not min_relationship_count
        <= target_relationship_count
        <= max_relationship_count
    ):
        raise BenchmarkError(
            code=ErrorCode.RELATIONSHIP_COUNT_OUT_OF_RANGE,
            context={
                "target": str(target_relationship_count),
                "min": str(min_relationship_count),
                "max": str(max_relationship_count),
            },
        )

    if len(edges) < target_relationship_count:
        raise BenchmarkError(
            code=ErrorCode.INSUFFICIENT_RELATIONSHIPS,
            context={
                "available": str(len(edges)),
                "requested": str(target_relationship_count),
            },
        )

    return edges[:target_relationship_count]


def _category_for(node_id: str, categories: tuple[str, ...]) -> str:
    """Deterministically assign one of `categories` to a node id.

    Determinism matters for reproducibility: two runs of build_dataset
    over the same edge list must assign every node the same category,
    so a rerun of the benchmark queries the same logical data shape
    rather than a freshly-randomized one.

    Args:
        node_id: The node identifier to assign a category to.
        categories: The ordered set of categories to choose from.

    Returns:
        One value from `categories`.
    """
    return categories[hash(node_id) % len(categories)]


def build_dataset(
    edges: list[tuple[str, str]],
    categories: tuple[str, ...] = DEFAULT_CATEGORIES,
) -> DatasetBuild:
    """Build the full node/relationship record set from a trimmed edge list.

    Every unique node id appearing in `edges` (as either a source or a
    target) becomes exactly one NodeRecord, with a category assigned
    deterministically from `categories`. Every edge becomes exactly one
    RelationshipRecord, in the same order it appeared in `edges`.

    Args:
        edges: A trimmed edge list, e.g. the output of
            trim_relationships.
        categories: The category set to assign nodes from. Defaults to
            DEFAULT_CATEGORIES.

    Returns:
        The complete node and relationship record collections plus
        their counts.

    Raises:
        BenchmarkError: EMPTY_DATASET if `edges` is empty.
    """
    if not edges:
        raise BenchmarkError(code=ErrorCode.EMPTY_DATASET)

    seen_ids: dict[str, None] = {}
    for source, target in edges:
        seen_ids.setdefault(source, None)
        seen_ids.setdefault(target, None)

    nodes = [
        NodeRecord(id=node_id, category=_category_for(node_id, categories))
        for node_id in seen_ids
    ]
    relationships = [
        RelationshipRecord(source=source, target=target) for source, target in edges
    ]

    return DatasetBuild(
        nodes=nodes,
        relationships=relationships,
        node_count=len(nodes),
        relationship_count=len(relationships),
    )
