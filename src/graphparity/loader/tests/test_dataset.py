import pytest

from graphparity.errors import BenchmarkError, ErrorCode
from graphparity.loader.dataset import (
    DEFAULT_CATEGORIES,
    build_dataset,
    parse_edge_list,
    trim_relationships,
)


@pytest.mark.unit
class TestParseEdgeList:
    def test_parses_simple_edges(self):
        result = list(parse_edge_list(["a\tb", "b\tc"]))

        assert result == [("a", "b"), ("b", "c")]

    def test_skips_comment_lines(self):
        result = list(parse_edge_list(["# header", "a\tb"]))

        assert result == [("a", "b")]

    def test_skips_blank_lines(self):
        result = list(parse_edge_list(["a\tb", "", "   ", "c\td"]))

        assert result == [("a", "b"), ("c", "d")]

    def test_raises_on_malformed_line(self):
        with pytest.raises(BenchmarkError) as exc_info:
            list(parse_edge_list(["a b c"]))

        assert exc_info.value.code == ErrorCode.MALFORMED_EDGE_LINE

    def test_malformed_error_context_includes_line(self):
        with pytest.raises(BenchmarkError) as exc_info:
            list(parse_edge_list(["only-one-token"]))

        assert exc_info.value.context["line"] == "only-one-token"


@pytest.mark.unit
class TestTrimRelationships:
    def test_keeps_first_n_edges_in_order(self):
        edges = [(str(i), str(i + 1)) for i in range(150_000)]

        result = trim_relationships(edges, target_relationship_count=100_000)

        assert len(result) == 100_000
        assert result[0] == ("0", "1")
        assert result[-1] == ("99999", "100000")

    def test_raises_empty_dataset_for_empty_edges(self):
        with pytest.raises(BenchmarkError) as exc_info:
            trim_relationships([], target_relationship_count=100_000)

        assert exc_info.value.code == ErrorCode.EMPTY_DATASET

    def test_raises_out_of_range_when_target_below_minimum(self):
        edges = [(str(i), str(i + 1)) for i in range(200_000)]

        with pytest.raises(BenchmarkError) as exc_info:
            trim_relationships(edges, target_relationship_count=1_000)

        assert exc_info.value.code == ErrorCode.RELATIONSHIP_COUNT_OUT_OF_RANGE

    def test_raises_out_of_range_when_target_above_maximum(self):
        edges = [(str(i), str(i + 1)) for i in range(600_000)]

        with pytest.raises(BenchmarkError) as exc_info:
            trim_relationships(edges, target_relationship_count=600_000)

        assert exc_info.value.code == ErrorCode.RELATIONSHIP_COUNT_OUT_OF_RANGE

    def test_raises_insufficient_when_source_too_small(self):
        edges = [(str(i), str(i + 1)) for i in range(1_000)]

        with pytest.raises(BenchmarkError) as exc_info:
            trim_relationships(edges, target_relationship_count=100_000)

        assert exc_info.value.code == ErrorCode.INSUFFICIENT_RELATIONSHIPS


@pytest.mark.unit
class TestBuildDataset:
    def test_returns_unique_nodes(self):
        edges = [("a", "b"), ("b", "c"), ("a", "c")]

        result = build_dataset(edges)

        assert result.node_count == 3
        assert {n.id for n in result.nodes} == {"a", "b", "c"}

    def test_returns_one_relationship_per_edge(self):
        edges = [("a", "b"), ("b", "c")]

        result = build_dataset(edges)

        assert result.relationship_count == 2

    def test_assigns_category_from_given_set(self):
        edges = [("a", "b")]

        result = build_dataset(edges, categories=("only",))

        assert all(n.category == "only" for n in result.nodes)

    def test_default_categories_are_used_when_unspecified(self):
        edges = [("a", "b")]

        result = build_dataset(edges)

        assert all(n.category in DEFAULT_CATEGORIES for n in result.nodes)

    def test_same_node_id_gets_same_category_across_runs(self):
        edges = [("a", "b")]

        first = build_dataset(edges)
        second = build_dataset(edges)

        first_by_id = {n.id: n.category for n in first.nodes}
        second_by_id = {n.id: n.category for n in second.nodes}
        assert first_by_id == second_by_id

    def test_raises_empty_dataset_for_empty_edges(self):
        with pytest.raises(BenchmarkError) as exc_info:
            build_dataset([])

        assert exc_info.value.code == ErrorCode.EMPTY_DATASET
