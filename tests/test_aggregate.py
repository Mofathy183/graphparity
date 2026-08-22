import pytest

from graphparity.aggregate import (
    REPORTED_PERCENTILES,
    MetricSummary,
    build_results_matrix,
    compute_percentile,
    summarize,
)
from graphparity.errors import BenchmarkError, ErrorCode


@pytest.mark.unit
class TestComputePercentile:
    def test_returns_exact_value_for_single_sample(self):
        result = compute_percentile([42.0], 50.0)

        assert result == 42.0

    def test_returns_same_value_for_any_percentile_with_single_sample(self):
        assert compute_percentile([42.0], 0.0) == 42.0
        assert compute_percentile([42.0], 95.0) == 42.0
        assert compute_percentile([42.0], 100.0) == 42.0

    def test_computes_p50_for_odd_sample_count(self):
        # sorted: [10, 20, 30, 40, 50] -- rank = 0.5*4 = 2 -> exact index
        result = compute_percentile([50.0, 10.0, 30.0, 20.0, 40.0], 50.0)

        assert result == 30.0

    def test_computes_p50_for_even_sample_count(self):
        # sorted: [10, 20, 30, 40] -- rank = 0.5*3 = 1.5 -> interpolated
        result = compute_percentile([10.0, 20.0, 30.0, 40.0], 50.0)

        assert result == 25.0

    def test_computes_p95_with_interpolation(self):
        # sorted: [10, 20, 30, 40, 50] -- rank = 0.95*4 = 3.8
        # lower=index 3 (40), upper=index 4 (50), weight=0.8 -> 48.0
        result = compute_percentile([10.0, 20.0, 30.0, 40.0, 50.0], 95.0)

        assert result == pytest.approx(48.0)

    def test_p0_returns_minimum(self):
        result = compute_percentile([30.0, 10.0, 20.0], 0.0)

        assert result == 10.0

    def test_p100_returns_maximum(self):
        result = compute_percentile([30.0, 10.0, 20.0], 100.0)

        assert result == 30.0

    def test_does_not_mutate_input_order(self):
        samples = [30.0, 10.0, 20.0]

        compute_percentile(samples, 50.0)

        assert samples == [30.0, 10.0, 20.0]

    def test_raises_empty_sample_set_code_on_empty_samples(self):
        with pytest.raises(BenchmarkError) as exc_info:
            compute_percentile([], 50.0)

        assert exc_info.value.code == ErrorCode.EMPTY_SAMPLE_SET

    @pytest.mark.parametrize("bad_percentile", [-1.0, 100.1, 200.0])
    def test_raises_value_error_for_percentile_out_of_range(self, bad_percentile):
        with pytest.raises(ValueError):
            compute_percentile([1.0, 2.0, 3.0], bad_percentile)


@pytest.mark.unit
class TestSummarize:
    def test_returns_metric_summary_instance(self):
        result = summarize("cognodb", "1_hop_traversal", [10.0, 20.0, 30.0])

        assert isinstance(result, MetricSummary)

    def test_maps_platform_and_workload(self):
        result = summarize("aura", "point_lookup", [5.0])

        assert result.platform == "aura"
        assert result.workload == "point_lookup"

    def test_sample_count_matches_input_length(self):
        result = summarize("cognodb", "aggregation", [1.0, 2.0, 3.0, 4.0])

        assert result.sample_count == 4

    def test_computes_min_max_mean(self):
        result = summarize("cognodb", "aggregation", [10.0, 20.0, 30.0])

        assert result.min_ms == 10.0
        assert result.max_ms == 30.0
        assert result.mean_ms == pytest.approx(20.0)

    def test_reports_default_percentiles(self):
        result = summarize("cognodb", "aggregation", [10.0, 20.0, 30.0])

        assert set(result.percentiles.keys()) == set(REPORTED_PERCENTILES)

    def test_accepts_custom_percentiles(self):
        result = summarize(
            "cognodb", "aggregation", [10.0, 20.0, 30.0], percentiles=(99.0,)
        )

        assert set(result.percentiles.keys()) == {99.0}

    def test_raises_empty_sample_set_code_on_empty_samples(self):
        with pytest.raises(BenchmarkError) as exc_info:
            summarize("cognodb", "aggregation", [])

        assert exc_info.value.code == ErrorCode.EMPTY_SAMPLE_SET

    def test_empty_sample_error_context_names_platform_and_workload(self):
        with pytest.raises(BenchmarkError) as exc_info:
            summarize("cognodb", "aggregation", [])

        assert exc_info.value.context["platform"] == "cognodb"
        assert exc_info.value.context["workload"] == "aggregation"


@pytest.mark.unit
class TestBuildResultsMatrix:
    def test_returns_one_summary_per_platform_workload_pair(self):
        raw = {
            "cognodb": {
                "1_hop_traversal": [10.0, 20.0],
                "point_lookup": [5.0, 6.0],
            },
            "aura": {
                "1_hop_traversal": [15.0, 25.0],
            },
        }

        result = build_results_matrix(raw)

        assert len(result) == 3

    def test_preserves_platform_and_workload_order(self):
        raw = {
            "cognodb": {"1_hop_traversal": [10.0], "point_lookup": [5.0]},
            "aura": {"1_hop_traversal": [15.0]},
        }

        result = build_results_matrix(raw)

        pairs = [(s.platform, s.workload) for s in result]
        assert pairs == [
            ("cognodb", "1_hop_traversal"),
            ("cognodb", "point_lookup"),
            ("aura", "1_hop_traversal"),
        ]

    def test_returns_empty_list_for_empty_input(self):
        result = build_results_matrix({})

        assert result == []

    def test_raises_empty_sample_set_when_any_workload_has_no_samples(self):
        raw = {
            "cognodb": {
                "1_hop_traversal": [10.0, 20.0],
                "point_lookup": [],
            }
        }

        with pytest.raises(BenchmarkError) as exc_info:
            build_results_matrix(raw)

        assert exc_info.value.code == ErrorCode.EMPTY_SAMPLE_SET

    def test_every_summary_is_metric_summary_instance(self):
        raw = {"cognodb": {"1_hop_traversal": [10.0, 20.0]}}

        result = build_results_matrix(raw)

        assert all(isinstance(s, MetricSummary) for s in result)
