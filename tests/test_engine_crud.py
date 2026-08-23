import pytest

from authz.errors import ConditionNotFound, NamespaceNotFound, RelationNotFound
from authz.schema import Direct, Namespace
from authz.tuples import Condition, RelationTuple


@pytest.fixture
async def registered_client(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    return client


async def test_write_persists_tuple(registered_client):
    await registered_client.write(
        [RelationTuple("document", "doc42", "owner", "user:alice")]
    )
    rows = await registered_client.read("document", object_id="doc42", relation="owner")
    assert rows == [RelationTuple("document", "doc42", "owner", "user:alice")]


async def test_write_rejects_unknown_namespace(registered_client):
    with pytest.raises(NamespaceNotFound):
        await registered_client.write(
            [RelationTuple("folder", "f1", "owner", "user:alice")]
        )


async def test_write_rejects_unknown_relation(registered_client):
    with pytest.raises(RelationNotFound):
        await registered_client.write(
            [RelationTuple("document", "doc42", "editor", "user:alice")]
        )


async def test_write_rejects_unregistered_condition(registered_client):
    with pytest.raises(ConditionNotFound):
        await registered_client.write(
            [
                RelationTuple(
                    "document",
                    "doc42",
                    "owner",
                    "user:alice",
                    condition=Condition("business_hours"),
                )
            ]
        )


async def test_write_accepts_registered_condition(registered_client):
    registered_client.register_condition("business_hours", lambda **_: True)
    await registered_client.write(
        [
            RelationTuple(
                "document",
                "doc42",
                "owner",
                "user:alice",
                condition=Condition("business_hours"),
            )
        ]
    )
    rows = await registered_client.read("document", object_id="doc42", relation="owner")
    assert rows[0].condition.name == "business_hours"


async def test_delete_removes_tuple(registered_client):
    t = RelationTuple("document", "doc42", "owner", "user:alice")
    await registered_client.write([t])
    await registered_client.delete([t])
    rows = await registered_client.read("document", object_id="doc42", relation="owner")
    assert rows == []


async def test_read_rejects_unknown_namespace(registered_client):
    with pytest.raises(NamespaceNotFound):
        await registered_client.read("folder")


async def test_read_rejects_unknown_relation(registered_client):
    with pytest.raises(RelationNotFound):
        await registered_client.read("document", relation="editor")
