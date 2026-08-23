import pytest

from authz.errors import RelationNotFound
from authz.schema import Direct, Namespace
from authz.tuples import RelationTuple


@pytest.fixture
async def registered_client(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    return client


async def test_check_true_for_matching_direct_tuple(registered_client):
    await registered_client.write(
        [RelationTuple("document", "doc42", "owner", "user:alice")]
    )
    assert await registered_client.check("user:alice", "owner", "document:doc42") is True


async def test_check_false_when_no_tuple_exists(registered_client):
    assert await registered_client.check("user:alice", "owner", "document:doc42") is False


async def test_check_false_for_different_subject(registered_client):
    await registered_client.write(
        [RelationTuple("document", "doc42", "owner", "user:alice")]
    )
    assert await registered_client.check("user:bob", "owner", "document:doc42") is False


async def test_check_raises_for_unknown_relation(registered_client):
    with pytest.raises(RelationNotFound):
        await registered_client.check("user:alice", "editor", "document:doc42")
