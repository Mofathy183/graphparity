import random

import pytest

from graphparity.workloads.traversal import run_traversal
from tests.adapters import FakeGraphAdapter


@pytest.mark.unit
class TestRunTraversal:
    async def test_returns_one_latency_per_timed_iteration(self):
        adapter = FakeGraphAdapter()

        result = await run_traversal(
            adapter,
            "bolt",
            ["n1", "n2"],
            hops=1,
            warmup_iterations=2,
            timed_iterations=5,
        )

        assert len(result) == 5

    @pytest.mark.parametrize("hops", [1, 2, 3])
    async def test_accepts_every_valid_hop_depth(self, hops):
        adapter = FakeGraphAdapter()

        result = await run_traversal(
            adapter, "bolt", ["n1"], hops=hops, warmup_iterations=0, timed_iterations=1
        )

        assert len(result) == 1

    async def test_rejects_invalid_hop_depth(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_traversal(
                adapter, "bolt", ["n1"], hops=4, warmup_iterations=0, timed_iterations=1
            )

    async def test_rejects_empty_node_ids(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_traversal(
                adapter, "bolt", [], hops=1, warmup_iterations=0, timed_iterations=1
            )

    async def test_uses_cypher_query_for_bolt_protocol(self):
        adapter = FakeGraphAdapter()

        await run_traversal(
            adapter, "bolt", ["n1"], hops=1, warmup_iterations=0, timed_iterations=1
        )

        assert "MATCH" in adapter.query_calls[0][0]

    async def test_uses_aql_query_for_http_protocol(self):
        adapter = FakeGraphAdapter()

        await run_traversal(
            adapter, "http", ["n1"], hops=1, warmup_iterations=0, timed_iterations=1
        )

        assert "FOR v IN" in adapter.query_calls[0][0]

    async def test_selects_start_node_from_given_ids(self):
        adapter = FakeGraphAdapter()
        rng = random.Random(0)

        await run_traversal(
            adapter,
            "bolt",
            ["only-node"],
            hops=1,
            warmup_iterations=0,
            timed_iterations=3,
            rng=rng,
        )

        assert all(
            params["start_id"] == "only-node" for _, params in adapter.query_calls
        )

    async def test_deeper_hops_use_longer_query_pattern(self):
        one_hop_adapter = FakeGraphAdapter()
        await run_traversal(
            one_hop_adapter,
            "bolt",
            ["n1"],
            hops=1,
            warmup_iterations=0,
            timed_iterations=1,
        )

        three_hop_adapter = FakeGraphAdapter()
        await run_traversal(
            three_hop_adapter,
            "bolt",
            ["n1"],
            hops=3,
            warmup_iterations=0,
            timed_iterations=1,
        )

        one_hop_query = one_hop_adapter.query_calls[0][0]
        three_hop_query = three_hop_adapter.query_calls[0][0]
        assert one_hop_query.count("-->") < three_hop_query.count("-->")
