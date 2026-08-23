from authz.schema import Direct, Exclusion, Intersection, Namespace, Union
from authz.tuples import RelationTuple


async def test_union_true_if_either_branch_true(client):
    client.register_schema(
        Namespace(
            "document",
            {"owner": Direct(), "banned": Direct(), "editor": Union(Direct(), Direct())},
        )
    )
    # both branches are Direct() on "editor" itself here; write directly to it.
    await client.write([RelationTuple("document", "doc42", "editor", "user:alice")])
    assert await client.check("user:alice", "editor", "document:doc42") is True


async def test_intersection_requires_all_children_true(client):
    client.register_schema(
        Namespace(
            "document",
            {
                "editor": Direct(),
                "compliance_cleared": Direct(),
                "can_delete": Intersection(Direct(), Direct()),
            },
        )
    )
    # can_delete's two Direct() branches both read the "can_delete" relation directly;
    # exercise real cross-relation composition via Exclusion/From in later tasks --
    # here we only need to prove Intersection short-circuits correctly.
    await client.write([RelationTuple("document", "doc42", "can_delete", "user:bob")])
    assert await client.check("user:bob", "can_delete", "document:doc42") is True


async def test_intersection_false_if_no_tuple_for_relation(client):
    client.register_schema(
        Namespace("document", {"can_delete": Intersection(Direct(), Direct())})
    )
    assert await client.check("user:bob", "can_delete", "document:doc42") is False


async def test_exclusion_false_when_no_tuple_at_all(client):
    # Exclusion(Direct(), Direct()) on the SAME relation is a degenerate case:
    # base and subtract always agree, so the result is always False. The
    # genuine base=True/subtract=False case needs From to redirect subtract
    # to a *different* relation -- covered in test_engine_check_from.py once
    # From exists (Task 11).
    client.register_schema(
        Namespace("folder", {"viewer": Exclusion(Direct(), Direct())})
    )
    assert await client.check("user:alice", "viewer", "folder:f1") is False


async def test_exclusion_false_when_subtract_true(client):
    client.register_schema(
        Namespace("group", {"blocked": Direct(), "viewer": Exclusion(Direct(), Direct())})
    )
    # Exclusion(Direct(), Direct()) both read the SAME relation ("viewer") here,
    # so writing a "viewer" tuple makes both base and subtract true -> excluded.
    await client.write([RelationTuple("group", "g1", "viewer", "user:alice")])
    assert await client.check("user:alice", "viewer", "group:g1") is False
