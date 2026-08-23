import pytest

from authz.errors import NamespaceNotFound, RelationNotFound, SchemaCycleDetected
from authz.schema import Direct, From, Namespace, Union


def test_register_schema_accepts_valid_namespaces(client):
    document = Namespace(
        "document", {"owner": Direct(), "editor": Union(Direct(), From("owner"))}
    )
    client.register_schema(document)  # must not raise


def test_register_schema_rejects_cyclic_namespace(client):
    bad = Namespace("document", {"viewer": From("editor"), "editor": From("viewer")})
    with pytest.raises(SchemaCycleDetected):
        client.register_schema(bad)


def test_get_relation_raises_for_unknown_namespace(client):
    with pytest.raises(NamespaceNotFound):
        client._get_relation("document", "owner")


def test_get_relation_raises_for_unknown_relation(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    with pytest.raises(RelationNotFound):
        client._get_relation("document", "editor")


def test_get_relation_returns_registered_rule(client):
    rule = Direct()
    client.register_schema(Namespace("document", {"owner": rule}))
    assert client._get_relation("document", "owner") is rule


def test_register_condition_makes_it_available(client, condition_evaluator):
    client.register_condition("always_true", lambda **_: True)
    assert condition_evaluator.is_registered("always_true") is True
