import pytest

from graphparity.adapters.protocol import LoadResult
from graphparity.errors import ErrorCode
from graphparity.loader.batch_loader import load_dataset
from graphparity.loader.dataset import build_dataset
from tests.adapters import FakeGraphAdapter


def _dataset(edge_count: int = 5):
    edges = [(f"n{i}", f"n{i + 1}") for i in range(edge_count)]
    return build_dataset(edges)


@pytest.mark.unit
class TestLoadDataset:
    async def test_loads_all_nodes_and_relationships(self):
        adapter = FakeGraphAdapter(name="fake")
        dataset = _dataset(edge_count=5)
        adapter.queue_load_result(
            LoadResult(
                nodes_loaded=dataset.node_count,
                relationships_loaded=0,
                wall_clock_seconds=0.0,
            )
        )
        adapter.queue_load_result(
            LoadResult(
                nodes_loaded=0,
                relationships_loaded=dataset.relationship_count,
                wall_clock_seconds=0.0,
            )
        )

        summary = await load_dataset(adapter, dataset, batch_size=1000)

        assert summary.nodes_loaded == dataset.node_count
        assert summary.relationships_loaded == dataset.relationship_count

    async def test_chunks_into_multiple_batches(self):
        adapter = FakeGraphAdapter(name="fake")
        dataset = _dataset(edge_count=10)

        await load_dataset(adapter, dataset, batch_size=3)

        node_calls = [call for call in adapter.load_calls if call[0]]
        rel_calls = [call for call in adapter.load_calls if call[1]]
        assert len(node_calls) >= 2
        assert len(rel_calls) >= 2

    async def test_loads_nodes_before_relationships(self):
        adapter = FakeGraphAdapter(name="fake")
        dataset = _dataset(edge_count=5)

        await load_dataset(adapter, dataset, batch_size=1000)

        node_call_indices = [i for i, call in enumerate(adapter.load_calls) if call[0]]
        rel_call_indices = [i for i, call in enumerate(adapter.load_calls) if call[1]]
        assert max(node_call_indices) < min(rel_call_indices)

    async def test_reports_platform_name(self):
        adapter = FakeGraphAdapter(name="cognodb")
        dataset = _dataset(edge_count=3)

        summary = await load_dataset(adapter, dataset, batch_size=1000)

        assert summary.platform == "cognodb"

    async def test_rejects_batch_size_below_one(self):
        adapter = FakeGraphAdapter(name="fake")
        dataset = _dataset(edge_count=3)

        with pytest.raises(ValueError):
            await load_dataset(adapter, dataset, batch_size=0)

    async def test_propagates_load_failed_error(self):
        adapter = FakeGraphAdapter(name="fake")
        adapter.queue_load_error(ErrorCode.LOAD_FAILED)
        dataset = _dataset(edge_count=3)

        with pytest.raises(Exception) as exc_info:  # noqa: B017 -- BenchmarkError
            await load_dataset(adapter, dataset, batch_size=1000)

        assert exc_info.value.code == ErrorCode.LOAD_FAILED  # ty: ignore[unresolved-attribute]
