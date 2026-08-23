from authz.engine import UsersetTree
from authz.schema import Direct, Namespace, TupleToUserset, Union
from authz.tuples import ObjectRef, RelationTuple


async def test_expand_direct_only_relation(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    await client.write(
        [
            RelationTuple("document", "doc42", "owner", "user:alice"),
            RelationTuple("document", "doc42", "owner", "user:bob"),
        ]
    )
    tree = await client.expand("owner", "document:doc42")
    assert tree == UsersetTree(
        relation="owner",
        object=ObjectRef("document", "doc42"),
        direct_subjects=("user:alice", "user:bob"),
        children=(),
    )


async def test_expand_follows_tuple_to_userset(client):
    client.register_schema(Namespace("folder", {"viewer": Direct()}))
    client.register_schema(
        Namespace(
            "document",
            {
                "parent": Direct(),
                "viewer": Union(Direct(), TupleToUserset("parent", "viewer")),
            },
        )
    )
    await client.write(
        [
            RelationTuple("folder", "f1", "viewer", "user:alice"),
            RelationTuple("document", "doc42", "parent", "folder:f1"),
        ]
    )
    tree = await client.expand("viewer", "document:doc42")
    assert tree.direct_subjects == ()
    assert len(tree.children) == 1
    child = tree.children[0]
    assert child.relation == "viewer"
    assert child.object == ObjectRef("folder", "f1")
    assert child.direct_subjects == ("user:alice",)
