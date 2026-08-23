import pytest

from authz.errors import SchemaCycleDetected
from authz.schema import (
    Direct,
    Exclusion,
    From,
    Intersection,
    Namespace,
    TupleToUserset,
    Union,
    check_schema_cycles,
    tupleset_relations,
)


def test_acyclic_schema_passes():
    ns = Namespace(
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
    check_schema_cycles(ns)  # must not raise


def test_direct_from_cycle_is_detected():
    ns = Namespace(
        "document",
        {"viewer": From("editor"), "editor": From("viewer")},
    )
    with pytest.raises(SchemaCycleDetected) as exc_info:
        check_schema_cycles(ns)
    assert exc_info.value.namespace == "document"


def test_self_referential_from_is_a_cycle():
    ns = Namespace("document", {"viewer": From("viewer")})
    with pytest.raises(SchemaCycleDetected):
        check_schema_cycles(ns)


def test_cycle_through_union_and_intersection_is_detected():
    ns = Namespace(
        "document",
        {
            "a": Union(Direct(), From("b")),
            "b": Intersection(Direct(), From("c")),
            "c": From("a"),
        },
    )
    with pytest.raises(SchemaCycleDetected):
        check_schema_cycles(ns)


def test_cycle_through_exclusion_is_detected():
    ns = Namespace(
        "document",
        {"a": Exclusion(Direct(), From("b")), "b": From("a")},
    )
    with pytest.raises(SchemaCycleDetected):
        check_schema_cycles(ns)


def test_tuple_to_userset_does_not_count_as_schema_cycle():
    # viewer -> TupleToUserset("parent", "viewer") references the SAME
    # relation name, but on a *different* object -- not a schema cycle.
    ns = Namespace(
        "folder",
        {"viewer": Union(Direct(), TupleToUserset("parent", "viewer"))},
    )
    check_schema_cycles(ns)  # must not raise


def test_tupleset_relations_collects_from_union_and_intersection():
    rule = Union(
        TupleToUserset("parent", "viewer"),
        Intersection(Direct(), TupleToUserset("workspace", "member")),
    )
    assert tupleset_relations(rule) == {"parent", "workspace"}


def test_tupleset_relations_collects_from_exclusion():
    rule = Exclusion(TupleToUserset("parent", "viewer"), Direct())
    assert tupleset_relations(rule) == {"parent"}


def test_tupleset_relations_empty_for_direct_and_from():
    assert tupleset_relations(Direct()) == set()
    assert tupleset_relations(From("owner")) == set()
