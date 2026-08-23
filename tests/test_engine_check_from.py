from authz.schema import Direct, Exclusion, From, Namespace, Union
from authz.tuples import RelationTuple


async def test_owner_inherits_editor_via_from(client):
    client.register_schema(
        Namespace(
            "document",
            {"owner": Direct(), "editor": Union(Direct(), From("owner"))},
        )
    )
    await client.write([RelationTuple("document", "doc42", "owner", "user:alice")])
    assert await client.check("user:alice", "editor", "document:doc42") is True


async def test_non_owner_does_not_inherit_editor(client):
    client.register_schema(
        Namespace(
            "document",
            {"owner": Direct(), "editor": Union(Direct(), From("owner"))},
        )
    )
    await client.write([RelationTuple("document", "doc42", "owner", "user:alice")])
    assert await client.check("user:bob", "editor", "document:doc42") is False


async def test_direct_editor_grant_works_without_owner(client):
    client.register_schema(
        Namespace(
            "document",
            {"owner": Direct(), "editor": Union(Direct(), From("owner"))},
        )
    )
    await client.write([RelationTuple("document", "doc42", "editor", "user:bob")])
    assert await client.check("user:bob", "editor", "document:doc42") is True


async def test_exclusion_true_when_base_true_and_subtract_redirected_false(client):
    # The genuine Exclusion(base=True, subtract=False) case deferred from
    # Task 10: From lets subtract read a DIFFERENT relation than base, so
    # the two can disagree.
    client.register_schema(
        Namespace(
            "document",
            {
                "banned": Direct(),
                "viewer": Exclusion(Direct(), From("banned")),
            },
        )
    )
    await client.write([RelationTuple("document", "doc42", "viewer", "user:alice")])
    assert await client.check("user:alice", "viewer", "document:doc42") is True


async def test_exclusion_false_when_base_true_and_subtract_redirected_true(client):
    client.register_schema(
        Namespace(
            "document",
            {
                "banned": Direct(),
                "viewer": Exclusion(Direct(), From("banned")),
            },
        )
    )
    await client.write(
        [
            RelationTuple("document", "doc42", "viewer", "user:alice"),
            RelationTuple("document", "doc42", "banned", "user:alice"),
        ]
    )
    assert await client.check("user:alice", "viewer", "document:doc42") is False
