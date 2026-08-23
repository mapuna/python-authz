from authz.schema import Direct, Namespace
from authz.tuples import RelationTuple


async def test_group_member_has_access_via_group_tuple(client):
    client.register_schema(Namespace("group", {"member": Direct()}))
    client.register_schema(Namespace("document", {"viewer": Direct()}))
    await client.write(
        [
            RelationTuple("group", "eng", "member", "user:alice"),
            RelationTuple("document", "doc42", "viewer", "group:eng#member"),
        ]
    )
    assert await client.check("user:alice", "viewer", "document:doc42") is True


async def test_non_member_has_no_access_via_group_tuple(client):
    client.register_schema(Namespace("group", {"member": Direct()}))
    client.register_schema(Namespace("document", {"viewer": Direct()}))
    await client.write(
        [
            RelationTuple("group", "eng", "member", "user:alice"),
            RelationTuple("document", "doc42", "viewer", "group:eng#member"),
        ]
    )
    assert await client.check("user:bob", "viewer", "document:doc42") is False


async def test_nested_group_membership_resolves_transitively(client):
    client.register_schema(Namespace("group", {"member": Direct()}))
    client.register_schema(Namespace("document", {"viewer": Direct()}))
    await client.write(
        [
            RelationTuple("group", "leads", "member", "user:alice"),
            RelationTuple("group", "eng", "member", "group:leads#member"),
            RelationTuple("document", "doc42", "viewer", "group:eng#member"),
        ]
    )
    assert await client.check("user:alice", "viewer", "document:doc42") is True
