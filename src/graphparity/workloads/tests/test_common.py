import pytest

from graphparity.errors import BenchmarkError, ErrorCode
from graphparity.workloads.common import QueryTemplate, run_timed_workload
from tests.adapters import FakeGraphAdapter


@pytest.mark.unit
class TestQueryTemplate:
    def test_for_protocol_returns_cypher_for_bolt(self):
        template = QueryTemplate(cypher="MATCH ...", aql="FOR ...")

        assert template.for_protocol("bolt") == "MATCH ..."

    def test_for_protocol_returns_aql_for_http(self):
        template = QueryTemplate(cypher="MATCH ...", aql="FOR ...")

        assert template.for_protocol("http") == "FOR ..."


@pytest.mark.unit
class TestRunTimedWorkload:
    async def test_discards_warmup_latencies(self):
        adapter = FakeGraphAdapter()
        for _ in range(3):
            adapter.queue_query_result(latency_ms=999.0)  # warm-up, discarded
        for _ in range(2):
            adapter.queue_query_result(latency_ms=5.0)  # timed, kept

        result = await run_timed_workload(
            adapter,
            "MATCH (n) RETURN n",
            dict,
            warmup_iterations=3,
            timed_iterations=2,
        )

        assert result == [5.0, 5.0]

    async def test_exact_boundary_when_warmup_is_zero(self):
        adapter = FakeGraphAdapter()
        adapter.queue_query_result(latency_ms=1.0)
        adapter.queue_query_result(latency_ms=2.0)

        result = await run_timed_workload(
            adapter,
            "MATCH (n) RETURN n",
            dict,
            warmup_iterations=0,
            timed_iterations=2,
        )

        assert result == [1.0, 2.0]

    async def test_calls_adapter_once_per_warmup_plus_timed_iteration(self):
        adapter = FakeGraphAdapter()

        await run_timed_workload(
            adapter,
            "MATCH (n) RETURN n",
            dict,
            warmup_iterations=4,
            timed_iterations=6,
        )

        assert len(adapter.query_calls) == 10

    async def test_calls_params_factory_once_per_iteration_including_warmup(self):
        adapter = FakeGraphAdapter()
        calls: list[int] = []

        def params_factory():
            calls.append(1)
            return {"n": len(calls)}

        await run_timed_workload(
            adapter,
            "MATCH (n) RETURN n",
            params_factory,
            warmup_iterations=2,
            timed_iterations=3,
        )

        assert len(calls) == 5
        assert adapter.query_calls[-1][1] == {"n": 5}

    async def test_raises_value_error_for_negative_warmup(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_timed_workload(
                adapter,
                "MATCH (n) RETURN n",
                dict,
                warmup_iterations=-1,
                timed_iterations=1,
            )

    async def test_raises_value_error_for_zero_timed_iterations(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_timed_workload(
                adapter,
                "MATCH (n) RETURN n",
                dict,
                warmup_iterations=1,
                timed_iterations=0,
            )

    async def test_propagates_adapter_error(self):
        adapter = FakeGraphAdapter()
        adapter.queue_query_error(ErrorCode.QUERY_FAILED)

        with pytest.raises(BenchmarkError) as exc_info:
            await run_timed_workload(
                adapter,
                "MATCH (n) RETURN n",
                dict,
                warmup_iterations=0,
                timed_iterations=1,
            )

        assert exc_info.value.code == ErrorCode.QUERY_FAILED
