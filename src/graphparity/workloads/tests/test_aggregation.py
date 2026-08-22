import pytest

from graphparity.workloads.aggregation import run_aggregation
from tests.adapters import FakeGraphAdapter


@pytest.mark.unit
class TestRunAggregation:
    async def test_returns_one_latency_per_timed_iteration(self):
        adapter = FakeGraphAdapter()

        result = await run_aggregation(
            adapter, "bolt", warmup_iterations=2, timed_iterations=5
        )

        assert len(result) == 5

    async def test_uses_cypher_for_bolt_protocol(self):
        adapter = FakeGraphAdapter()

        await run_aggregation(adapter, "bolt", warmup_iterations=0, timed_iterations=1)

        assert "MATCH" in adapter.query_calls[0][0]

    async def test_uses_aql_for_http_protocol(self):
        adapter = FakeGraphAdapter()

        await run_aggregation(adapter, "http", warmup_iterations=0, timed_iterations=1)

        assert "COLLECT" in adapter.query_calls[0][0]

    async def test_passes_no_params(self):
        adapter = FakeGraphAdapter()

        await run_aggregation(adapter, "bolt", warmup_iterations=0, timed_iterations=1)

        assert adapter.query_calls[0][1] == {}
