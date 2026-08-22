import pytest

from graphparity.errors import BenchmarkError, ErrorCode
from graphparity.runner import run_all_platforms, run_platform_workloads
from tests.adapters import FakeGraphAdapter


@pytest.mark.unit
class TestRunPlatformWorkloads:
    async def test_returns_one_entry_per_required_workload(self):
        adapter = FakeGraphAdapter(name="fake")

        result = await run_platform_workloads(
            adapter,
            "bolt",
            node_ids=["n1", "n2"],
            categories=["premium"],
            warmup_iterations=1,
            timed_iterations=2,
            mixed_concurrencies=(1, 2),
            mixed_duration_seconds=0.02,
        )

        expected_keys = {
            "1_hop_traversal",
            "2_hop_traversal",
            "3_hop_traversal",
            "point_lookup",
            "indexed_lookup",
            "aggregation",
            "mixed_1_concurrency",
            "mixed_2_concurrency",
        }
        assert set(result.keys()) == expected_keys

    async def test_traversal_results_have_timed_iteration_count(self):
        adapter = FakeGraphAdapter(name="fake")

        result = await run_platform_workloads(
            adapter,
            "bolt",
            node_ids=["n1"],
            categories=["premium"],
            warmup_iterations=1,
            timed_iterations=4,
            mixed_concurrencies=(1,),
            mixed_duration_seconds=0.01,
        )

        assert len(result["1_hop_traversal"]) == 4

    async def test_mixed_workload_combines_read_and_write_latencies(self):
        adapter = FakeGraphAdapter(name="fake")

        result = await run_platform_workloads(
            adapter,
            "bolt",
            node_ids=["n1"],
            categories=["premium"],
            warmup_iterations=0,
            timed_iterations=1,
            mixed_concurrencies=(2,),
            mixed_duration_seconds=0.02,
        )

        assert len(result["mixed_2_concurrency"]) >= 2

    async def test_propagates_benchmark_error_from_a_workload(self):
        adapter = FakeGraphAdapter(name="fake")
        adapter.queue_query_error(ErrorCode.QUERY_FAILED)

        with pytest.raises(BenchmarkError) as exc_info:
            await run_platform_workloads(
                adapter,
                "bolt",
                node_ids=["n1"],
                categories=["premium"],
                warmup_iterations=0,
                timed_iterations=1,
                mixed_concurrencies=(1,),
                mixed_duration_seconds=0.01,
            )

        assert exc_info.value.code == ErrorCode.QUERY_FAILED


@pytest.mark.unit
class TestRunAllPlatforms:
    async def test_connects_and_disconnects_every_adapter(self):
        adapter_a = FakeGraphAdapter(name="a")
        adapter_b = FakeGraphAdapter(name="b")

        await run_all_platforms(
            [adapter_a, adapter_b],
            protocols={"a": "bolt", "b": "bolt"},
            node_ids=["n1"],
            categories=["premium"],
            warmup_iterations=0,
            timed_iterations=1,
            mixed_concurrencies=(1,),
            mixed_duration_seconds=0.01,
        )

        assert adapter_a.connect_calls == 1
        assert adapter_a.disconnect_calls == 1
        assert adapter_b.connect_calls == 1
        assert adapter_b.disconnect_calls == 1

    async def test_returns_results_keyed_by_platform_name(self):
        adapter = FakeGraphAdapter(name="cognodb")

        result = await run_all_platforms(
            [adapter],
            protocols={"cognodb": "bolt"},
            node_ids=["n1"],
            categories=["premium"],
            warmup_iterations=0,
            timed_iterations=1,
            mixed_concurrencies=(1,),
            mixed_duration_seconds=0.01,
        )

        assert "cognodb" in result
        assert "point_lookup" in result["cognodb"]

    async def test_skips_platform_that_fails_but_continues_to_next(self):
        failing = FakeGraphAdapter(name="failing")
        failing.queue_query_error(ErrorCode.CONNECTION_FAILED)
        healthy = FakeGraphAdapter(name="healthy")

        result = await run_all_platforms(
            [failing, healthy],
            protocols={"failing": "bolt", "healthy": "bolt"},
            node_ids=["n1"],
            categories=["premium"],
            warmup_iterations=0,
            timed_iterations=1,
            mixed_concurrencies=(1,),
            mixed_duration_seconds=0.01,
        )

        assert "failing" not in result
        assert "healthy" in result

    async def test_disconnects_failing_platform_even_though_it_failed(self):
        failing = FakeGraphAdapter(name="failing")
        failing.queue_query_error(ErrorCode.QUERY_FAILED)

        await run_all_platforms(
            [failing],
            protocols={"failing": "bolt"},
            node_ids=["n1"],
            categories=["premium"],
            warmup_iterations=0,
            timed_iterations=1,
            mixed_concurrencies=(1,),
            mixed_duration_seconds=0.01,
        )

        assert failing.disconnect_calls == 1
