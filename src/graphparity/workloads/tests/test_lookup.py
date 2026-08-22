import random

import pytest

from graphparity.workloads.lookup import run_indexed_lookup, run_point_lookup
from tests.adapters import FakeGraphAdapter


@pytest.mark.unit
class TestRunPointLookup:
    async def test_returns_one_latency_per_timed_iteration(self):
        adapter = FakeGraphAdapter()

        result = await run_point_lookup(
            adapter, "bolt", ["n1", "n2"], warmup_iterations=2, timed_iterations=4
        )

        assert len(result) == 4

    async def test_rejects_empty_node_ids(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_point_lookup(
                adapter, "bolt", [], warmup_iterations=0, timed_iterations=1
            )

    async def test_uses_document_lookup_for_http_protocol(self):
        adapter = FakeGraphAdapter()

        await run_point_lookup(
            adapter, "http", ["n1"], warmup_iterations=0, timed_iterations=1
        )

        assert "DOCUMENT" in adapter.query_calls[0][0]

    async def test_passes_selected_id_as_param(self):
        adapter = FakeGraphAdapter()
        rng = random.Random(0)

        await run_point_lookup(
            adapter,
            "bolt",
            ["only-node"],
            warmup_iterations=0,
            timed_iterations=1,
            rng=rng,
        )

        assert adapter.query_calls[0][1] == {"id": "only-node"}


@pytest.mark.unit
class TestRunIndexedLookup:
    async def test_returns_one_latency_per_timed_iteration(self):
        adapter = FakeGraphAdapter()

        result = await run_indexed_lookup(
            adapter,
            "bolt",
            ["premium", "standard"],
            warmup_iterations=1,
            timed_iterations=3,
        )

        assert len(result) == 3

    async def test_rejects_empty_categories(self):
        adapter = FakeGraphAdapter()

        with pytest.raises(ValueError):
            await run_indexed_lookup(
                adapter, "bolt", [], warmup_iterations=0, timed_iterations=1
            )

    async def test_uses_filter_clause_for_aql(self):
        adapter = FakeGraphAdapter()

        await run_indexed_lookup(
            adapter, "http", ["premium"], warmup_iterations=0, timed_iterations=1
        )

        assert "FILTER" in adapter.query_calls[0][0]

    async def test_passes_selected_category_as_param(self):
        adapter = FakeGraphAdapter()

        await run_indexed_lookup(
            adapter,
            "bolt",
            ["only-category"],
            warmup_iterations=0,
            timed_iterations=1,
        )

        assert adapter.query_calls[0][1] == {"category": "only-category"}
