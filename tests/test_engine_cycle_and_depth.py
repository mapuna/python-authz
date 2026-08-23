import pytest

from authz.engine import Client
from authz.errors import CycleDetected, DepthLimitExceeded
from authz.schema import Direct, Namespace, TupleToUserset, Union
from authz.tuples import RelationTuple


@pytest.fixture
def folder_namespace():
    return Namespace(
        "folder",
        {
            "parent": Direct(),
            "viewer": Union(Direct(), TupleToUserset("parent", "viewer")),
        },
    )


async def test_data_cycle_raises_cycle_detected(storage, condition_evaluator, folder_namespace):
    client = Client(storage=storage, condition_evaluator=condition_evaluator)
    client.register_schema(folder_namespace)
    # Bypass client.write()'s guard (Task 17) by writing directly through storage.
    await storage.write_tuples(
        [
            RelationTuple("folder", "A", "parent", "folder:B"),
            RelationTuple("folder", "B", "parent", "folder:A"),
        ]
    )
    with pytest.raises(CycleDetected):
        await client.check("user:alice", "viewer", "folder:A")


async def test_deep_acyclic_chain_raises_depth_limit_exceeded(
    storage, condition_evaluator, folder_namespace
):
    client = Client(storage=storage, condition_evaluator=condition_evaluator, max_depth=3)
    client.register_schema(folder_namespace)
    # folder-0 -> folder-1 -> folder-2 -> ... -> folder-5 (acyclic, deeper than max_depth=3)
    tuples = [
        RelationTuple("folder", f"folder-{i}", "parent", f"folder:folder-{i + 1}")
        for i in range(5)
    ]
    await storage.write_tuples(tuples)
    with pytest.raises(DepthLimitExceeded):
        await client.check("user:alice", "viewer", "folder:folder-0")


async def test_shallow_chain_within_depth_limit_succeeds(
    storage, condition_evaluator, folder_namespace
):
    client = Client(storage=storage, condition_evaluator=condition_evaluator, max_depth=3)
    client.register_schema(folder_namespace)
    await storage.write_tuples(
        [
            RelationTuple("folder", "top", "viewer", "user:alice"),
            RelationTuple("folder", "mid", "parent", "folder:top"),
        ]
    )
    assert await client.check("user:alice", "viewer", "folder:mid") is True
