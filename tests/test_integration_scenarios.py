from authz.schema import Direct, From, Namespace, TupleToUserset, Union
from authz.tuples import Condition, RelationTuple


async def test_folder_inheritance_nested_groups_and_conditional_grant(client):
    # RBAC: owner implies editor implies viewer.
    # ReBAC: viewer inherits from the parent folder.
    # ABAC: a conditional grant only counts when its condition holds.
    client.register_schema(
        Namespace(
            "group",
            {"member": Direct()},
        )
    )
    client.register_schema(
        Namespace(
            "folder",
            {
                "parent": Direct(),
                "owner": Direct(),
                "editor": Union(Direct(), From("owner")),
                "viewer": Union(
                    Direct(), From("editor"), TupleToUserset("parent", "viewer")
                ),
            },
        )
    )
    client.register_schema(
        Namespace(
            "document",
            {
                "parent": Direct(),
                "owner": Direct(),
                "editor": Union(Direct(), From("owner")),
                "viewer": Union(
                    Direct(), From("editor"), TupleToUserset("parent", "viewer")
                ),
            },
        )
    )

    def is_active_quarter(*, subject, resource, active):
        return active

    client.register_condition("is_active_quarter", is_active_quarter)

    await client.write(
        [
            # alice owns the top-level folder.
            RelationTuple("folder", "workspace", "owner", "user:alice"),
            # eng group nests the contractors group.
            RelationTuple("group", "contractors", "member", "user:dave"),
            RelationTuple("group", "eng", "member", "user:bob"),
            RelationTuple("group", "eng", "member", "group:contractors#member"),
            # eng group can view the workspace folder.
            RelationTuple("folder", "workspace", "viewer", "group:eng#member"),
            # the document lives inside the workspace folder.
            RelationTuple("document", "doc42", "parent", "folder:workspace"),
            # carol has a conditional editor grant, currently inactive.
            RelationTuple(
                "document",
                "doc42",
                "editor",
                "user:carol",
                condition=Condition("is_active_quarter", {"active": False}),
            ),
        ]
    )

    # alice: owner of the folder -> editor -> viewer -> inherited by the document.
    assert await client.check("user:alice", "viewer", "document:doc42") is True
    assert await client.check("user:alice", "editor", "document:doc42") is False

    # bob: direct eng member -> folder viewer -> inherited by the document.
    assert await client.check("user:bob", "viewer", "document:doc42") is True

    # dave: nested via contractors -> eng -> folder viewer -> inherited by the document.
    assert await client.check("user:dave", "viewer", "document:doc42") is True

    # carol: conditional editor grant is currently inactive -> denied.
    assert await client.check("user:carol", "editor", "document:doc42") is False

    # someone outside every group has no access at all.
    assert await client.check("user:eve", "viewer", "document:doc42") is False

    # expand() shows the inherited path from the parent folder.
    tree = await client.expand("viewer", "document:doc42")
    assert any(child.object.object_id == "workspace" for child in tree.children)


async def test_revoke_is_visible_immediately_via_consistency_token(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    t = RelationTuple("document", "doc42", "owner", "user:alice")
    await client.write([t])
    assert await client.check("user:alice", "owner", "document:doc42") is True

    revoke_token = await client.delete([t])
    result = await client.check(
        "user:alice", "owner", "document:doc42", at_least_as_fresh_as=revoke_token
    )
    assert result is False
