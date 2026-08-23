from authz.schema import Direct, Namespace, TupleToUserset, Union
from authz.tuples import RelationTuple


async def test_viewer_of_parent_folder_can_view_document(client):
    client.register_schema(
        Namespace("folder", {"viewer": Direct()}),
    )
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
    assert await client.check("user:alice", "viewer", "document:doc42") is True


async def test_non_viewer_of_parent_folder_cannot_view_document(client):
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
    assert await client.check("user:bob", "viewer", "document:doc42") is False


async def test_document_without_parent_tuple_has_no_inherited_viewer(client):
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
    assert await client.check("user:alice", "viewer", "document:doc42") is False
