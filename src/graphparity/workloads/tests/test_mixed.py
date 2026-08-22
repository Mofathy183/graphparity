import random

import pytest

from graphparity.workloads.mixed import MixedWorkloadResult, run_mixed_workload
from tests.adapters import FakeGraphAdapter


@pytest.mark.unit
class TestRunMixedWorkload:
    async def test_returns_mixed_workload_result(self):
        adapter = FakeGraphAdapter()

        result = await run_mixed_workload(
            adapter, "bolt", ["n1"], concurrency=2, duration_seconds=0.05
        )

        assert isinstance(result, MixedWorkloadResult)

    async def test_completes_at_least_one_query_per_worker(self):
        adapter = FakeGraphAdapter()

        result = await run_mixed_workload(
            adapter, "bolt", ["n1"], concurrency=3, duration_seconds=0.05
        )

        assert result.queries_completed >= 3

    async def test_never_exceeds_requested_concurrency(self):
        adapter = FakeGraphAdapter()

        await run_mixed_workload(
            adapter, "bolt", ["n1"], concurrency=4, duration_seconds=0.05
        )

        assert adapter.max_observed_concurrency <= 4

    async def test_all_reads_when_ratio_is_one(self):
        adapter = FakeGraphAdapter()
        rng = random.Random(0)

        result = await run_mixed_workload(
            adapter,
            "bolt",
            ["n1"],
            concurrency=1,
            duration_seconds=0.02,
            read_write_ratio=1.0,
            rng=rng,
        )

        assert result.queries_completed == len(result.read_latencies_ms)
        assert result.write_latencies_ms == []

    async def test_all_writes_when_ratio_is_zero(self):
        adapter = FakeGraphAdapter()
        rng = random.Random(0)

        result = await run_mixed_workload(
            adapter,
            "bolt",
            ["n1"],
            concurrency=1,
            duration_seconds=0.02,
            read_write_ratio=0.0,
            rng=rng,
        )

        assert result.queries_completed == len(result.write_latencies_ms)
        assert result.read_latencies_ms == []

    async def test_throughput_is_completed_over_elapsed(self):
        adapter = FakeGraphAdapter()

        result = await run_mixed_workload(
            adapter, "bolt", ["n1"], concurrency=1, duration_seconds=0.02
        )

        assert result.throughput_qps == pytest.approx(
            result.queries_completed / result.elapsed_seconds, rel=1e-6
        )

    async def test_rejects_empty_node_ids(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_mixed_workload(
                adapter, "bolt", [], concurrency=1, duration_seconds=0.01
            )

    async def test_rejects_zero_concurrency(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_mixed_workload(
                adapter, "bolt", ["n1"], concurrency=0, duration_seconds=0.01
            )

    async def test_rejects_non_positive_duration(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_mixed_workload(
                adapter, "bolt", ["n1"], concurrency=1, duration_seconds=0
            )

    @pytest.mark.parametrize("bad_ratio", [-0.1, 1.1])
    async def test_rejects_ratio_out_of_range(self, bad_ratio):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_mixed_workload(
                adapter,
                "bolt",
                ["n1"],
                concurrency=1,
                duration_seconds=0.01,
                read_write_ratio=bad_ratio,
            )
