import pytest

from authz.tuples import Condition, ObjectRef, RelationTuple, SubjectRef


def test_object_ref_parse_and_str():
    ref = ObjectRef.parse("document:doc42")
    assert ref == ObjectRef("document", "doc42")
    assert str(ref) == "document:doc42"


def test_object_ref_parse_rejects_missing_colon():
    with pytest.raises(ValueError):
        ObjectRef.parse("document")


def test_subject_ref_parse_plain_object():
    ref = SubjectRef.parse("user:alice")
    assert ref == SubjectRef("user", "alice", None)
    assert ref.is_userset is False
    assert str(ref) == "user:alice"


def test_subject_ref_parse_userset():
    ref = SubjectRef.parse("group:eng#member")
    assert ref == SubjectRef("group", "eng", "member")
    assert ref.is_userset is True
    assert str(ref) == "group:eng#member"


def test_subject_ref_parse_rejects_missing_colon():
    with pytest.raises(ValueError):
        SubjectRef.parse("alice")


def test_relation_tuple_object_and_subject_ref():
    t = RelationTuple("document", "doc42", "owner", "user:alice")
    assert t.object == ObjectRef("document", "doc42")
    assert t.subject_ref == SubjectRef("user", "alice", None)
    assert t.condition is None


def test_relation_tuple_with_condition():
    cond = Condition("business_hours", {"tz": "UTC"})
    t = RelationTuple("document", "doc42", "owner", "user:alice", condition=cond)
    assert t.condition.name == "business_hours"
    assert t.condition.context == {"tz": "UTC"}


def test_relation_tuple_str_is_readable():
    t = RelationTuple("document", "doc42", "owner", "user:alice")
    text = str(t)
    assert "document" in text and "doc42" in text and "owner" in text and "alice" in text
