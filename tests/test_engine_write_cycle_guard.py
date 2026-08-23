import pytest

from authz.errors import WouldCreateCycle
from authz.schema import Direct, Namespace, TupleToUserset, Union
from authz.tuples import RelationTuple


@pytest.fixture
async def folder_client(client):
    client.register_schema(
        Namespace(
            "folder",
            {
                "parent": Direct(),
                "viewer": Union(Direct(), TupleToUserset("parent", "viewer")),
            },
        )
    )
    return client


async def test_write_rejects_traversal_edge_cycle(folder_client):
    await folder_client.write(
        [RelationTuple("folder", "A", "parent", "folder:B")]
    )
    with pytest.raises(WouldCreateCycle):
        await folder_client.write(
            [RelationTuple("folder", "B", "parent", "folder:A")]
        )


async def test_write_rejects_self_referential_traversal_edge(folder_client):
    with pytest.raises(WouldCreateCycle):
        await folder_client.write(
            [RelationTuple("folder", "A", "parent", "folder:A")]
        )


async def test_write_allows_non_cyclic_traversal_chain(folder_client):
    await folder_client.write(
        [
            RelationTuple("folder", "A", "parent", "folder:B"),
            RelationTuple("folder", "B", "parent", "folder:C"),
        ]
    )
    rows = await folder_client.read("folder", object_id="A", relation="parent")
    assert rows[0].subject == "folder:B"


async def test_write_rejects_membership_edge_cycle(client):
    client.register_schema(Namespace("group", {"member": Direct()}))
    await client.write(
        [RelationTuple("group", "A", "member", "group:B#member")]
    )
    with pytest.raises(WouldCreateCycle):
        await client.write(
            [RelationTuple("group", "B", "member", "group:A#member")]
        )


async def test_write_allows_non_cyclic_nested_membership(client):
    client.register_schema(Namespace("group", {"member": Direct()}))
    await client.write(
        [
            RelationTuple("group", "leads", "member", "user:alice"),
            RelationTuple("group", "eng", "member", "group:leads#member"),
        ]
    )
    rows = await client.read("group", object_id="eng", relation="member")
    assert rows[0].subject == "group:leads#member"


async def test_failed_write_does_not_partially_persist_batch(folder_client):
    await folder_client.write([RelationTuple("folder", "A", "parent", "folder:B")])
    with pytest.raises(WouldCreateCycle):
        await folder_client.write(
            [
                RelationTuple("folder", "C", "parent", "folder:D"),
                RelationTuple("folder", "B", "parent", "folder:A"),  # closes the cycle
            ]
        )
    # "C" -> "D" must not have been persisted either, since it shared the transaction.
    rows = await folder_client.read("folder", object_id="C", relation="parent")
    assert rows == []


async def test_two_new_tuples_in_one_batch_forming_a_cycle_together_are_rejected(
    folder_client,
):
    # Neither tuple closes a cycle on its own against *existing* data -- only
    # together, within this single write() call, do they form one. The guard
    # must catch this by persisting/guarding one tuple at a time, not by
    # checking the whole batch against storage before writing any of it.
    with pytest.raises(WouldCreateCycle):
        await folder_client.write(
            [
                RelationTuple("folder", "X", "parent", "folder:Y"),
                RelationTuple("folder", "Y", "parent", "folder:X"),
            ]
        )
    rows = await folder_client.read("folder", object_id="X", relation="parent")
    assert rows == []
