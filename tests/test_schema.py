from authz.schema import (
    Direct,
    Exclusion,
    From,
    Intersection,
    Namespace,
    TupleToUserset,
    Union,
)


def test_direct_repr():
    assert repr(Direct()) == "Direct()"


def test_union_holds_children_in_order():
    d, f = Direct(), From("owner")
    u = Union(d, f)
    assert u.children == (d, f)


def test_intersection_holds_children_in_order():
    d, f = Direct(), From("compliance_cleared")
    i = Intersection(d, f)
    assert i.children == (d, f)


def test_exclusion_holds_base_and_subtract():
    base, subtract = Direct(), From("banned")
    e = Exclusion(base, subtract)
    assert e.base is base
    assert e.subtract is subtract


def test_from_holds_relation_name():
    assert From("owner").relation == "owner"


def test_tuple_to_userset_holds_relation_names():
    t2u = TupleToUserset("parent", "viewer")
    assert t2u.tupleset_relation == "parent"
    assert t2u.computed_relation == "viewer"


def test_namespace_holds_name_and_relations():
    relations = {
        "owner": Direct(),
        "editor": Union(Direct(), From("owner")),
    }
    ns = Namespace("document", relations)
    assert ns.name == "document"
    assert ns.relations is relations
