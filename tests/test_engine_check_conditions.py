from authz.schema import Direct, Namespace
from authz.tuples import Condition, RelationTuple


async def test_direct_grant_with_true_condition_is_allowed(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    client.register_condition("always_true", lambda **_: True)
    await client.write(
        [
            RelationTuple(
                "document", "doc42", "owner", "user:alice",
                condition=Condition("always_true"),
            )
        ]
    )
    assert await client.check("user:alice", "owner", "document:doc42") is True


async def test_direct_grant_with_false_condition_is_denied(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    client.register_condition("always_false", lambda **_: False)
    await client.write(
        [
            RelationTuple(
                "document", "doc42", "owner", "user:alice",
                condition=Condition("always_false"),
            )
        ]
    )
    assert await client.check("user:alice", "owner", "document:doc42") is False


async def test_condition_receives_subject_resource_and_context(client):
    seen = {}

    def is_owner(*, subject, resource, owner):
        seen["subject"] = subject
        seen["resource"] = resource
        return subject == owner

    client.register_schema(Namespace("document", {"owner": Direct()}))
    client.register_condition("is_owner", is_owner)
    await client.write(
        [
            RelationTuple(
                "document", "doc42", "owner", "user:alice",
                condition=Condition("is_owner", {"owner": "user:alice"}),
            )
        ]
    )
    assert await client.check("user:alice", "owner", "document:doc42") is True
    assert seen == {"subject": "user:alice", "resource": "document:doc42"}
