import pytest

from authz import (
    CardinalityViolationError,
    Client,
    Namespace,
    PythonCallableEvaluator,
    RelationTuple,
    SqliteStorage,
    build_role_hierarchy,
)


@pytest.fixture
async def client():
    storage = SqliteStorage(":memory:")
    await storage.connect()
    evaluator = PythonCallableEvaluator.with_builtins()
    c = Client(storage=storage, condition_evaluator=evaluator)
    yield c
    await storage.close()


# =============================================================================
# 1. Singleton & Cardinality Constraints
# =============================================================================


async def test_singleton_relations_enforcement(client):
    """Verify singleton_relations={"org_admin"} enforces at most 1 org_admin."""
    roles = build_role_hierarchy(["org_admin", "org_manager", "org_user"])
    ns = Namespace("org", roles, singleton_relations={"org_admin"})
    client.register_schema(ns)

    # 1. First org_admin write succeeds
    t_alice = RelationTuple("org", "acme", "org_admin", "user:alice")
    await client.write([t_alice])
    assert await client.check("user:alice", "org_admin", "org:acme") is True

    # 2. Idempotent re-write of same org_admin succeeds
    await client.write([t_alice])
    assert await client.check("user:alice", "org_admin", "org:acme") is True

    # 3. Second distinct org_admin raises CardinalityViolationError
    t_bob = RelationTuple("org", "acme", "org_admin", "user:bob")
    with pytest.raises(CardinalityViolationError) as exc_info:
        await client.write([t_bob])

    err = exc_info.value
    assert err.namespace == "org"
    assert err.object_id == "acme"
    assert err.relation == "org_admin"
    assert err.max_subjects == 1
    assert err.existing_subjects == ("user:alice",)
    assert err.attempted_subject == "user:bob"
    assert "Cardinality violation on org:acme#org_admin" in str(err)

    # bob was not written
    assert await client.check("user:bob", "org_admin", "org:acme") is False

    # 4. Deleting old org_admin then writing new org_admin succeeds
    await client.delete([t_alice])
    assert await client.check("user:alice", "org_admin", "org:acme") is False

    await client.write([t_bob])
    assert await client.check("user:bob", "org_admin", "org:acme") is True


async def test_max_subjects_dict_enforcement(client):
    """Verify max_subjects={"org_admin": 1} behaves identically to singleton_relations."""
    roles = build_role_hierarchy(["org_admin", "org_user"])
    ns = Namespace("org", roles, max_subjects={"org_admin": 1})
    client.register_schema(ns)

    t_alice = RelationTuple("org", "health_corp", "org_admin", "user:alice")
    await client.write([t_alice])
    assert await client.check("user:alice", "org_admin", "org:health_corp") is True

    # Idempotent re-write succeeds
    await client.write([t_alice])

    # Second subject fails
    t_bob = RelationTuple("org", "health_corp", "org_admin", "user:bob")
    with pytest.raises(CardinalityViolationError) as exc_info:
        await client.write([t_bob])
    assert exc_info.value.max_subjects == 1
    assert exc_info.value.existing_subjects == ("user:alice",)
    assert exc_info.value.attempted_subject == "user:bob"


async def test_max_subjects_greater_than_one(client):
    """Verify max_subjects allows multiple subjects up to the declared limit."""
    roles = build_role_hierarchy(["lead", "member"])
    ns = Namespace("team", roles, max_subjects={"lead": 2})
    client.register_schema(ns)

    t1 = RelationTuple("team", "platform", "lead", "user:alice")
    t2 = RelationTuple("team", "platform", "lead", "user:bob")
    t3 = RelationTuple("team", "platform", "lead", "user:charlie")

    # Write first 2 leads
    await client.write([t1, t2])
    assert await client.check("user:alice", "lead", "team:platform") is True
    assert await client.check("user:bob", "lead", "team:platform") is True

    # Idempotent rewrite of existing subjects
    await client.write([t1, t2])

    # 3rd lead exceeds limit of 2
    with pytest.raises(CardinalityViolationError) as exc_info:
        await client.write([t3])
    err = exc_info.value
    assert err.max_subjects == 2
    assert set(err.existing_subjects) == {"user:alice", "user:bob"}
    assert err.attempted_subject == "user:charlie"


async def test_batch_write_violating_cardinality_in_same_call(client):
    """Verify writing a batch of tuples where multiple distinct subjects exceed max_subjects."""
    roles = build_role_hierarchy(["org_admin"])
    ns = Namespace("org", roles, singleton_relations={"org_admin"})
    client.register_schema(ns)

    t_alice = RelationTuple("org", "acme", "org_admin", "user:alice")
    t_bob = RelationTuple("org", "acme", "org_admin", "user:bob")

    with pytest.raises(CardinalityViolationError) as exc_info:
        await client.write([t_alice, t_bob])

    assert exc_info.value.attempted_subject == "user:bob"
    # Neither should have been committed
    assert await client.check("user:alice", "org_admin", "org:acme") is False
    assert await client.check("user:bob", "org_admin", "org:acme") is False


# =============================================================================
# 2. 5-Tier Role Hierarchies with Downward Inheritance and Upward Override
# =============================================================================

FIVE_TIER_ROLES = [
    "org_admin",
    "org_manager",
    "tpa_coordinator",
    "org_user",
    "diagnostic_billing_staff",
]


async def test_5_tier_provider_hierarchy_transitive_inheritance(client):
    """Verify 5-tier Provider hierarchy gives org_admin all lower roles transitively."""
    rel_map = build_role_hierarchy(FIVE_TIER_ROLES)
    ns = Namespace("provider_org", rel_map, singleton_relations={"org_admin"})
    client.register_schema(ns)

    # Assign only org_admin to alice
    await client.write([RelationTuple("provider_org", "prov_1", "org_admin", "user:alice")])

    # org_admin satisfies ALL 5 tiers
    for role in FIVE_TIER_ROLES:
        assert (
            await client.check("user:alice", role, "provider_org:prov_1") is True
        ), f"org_admin should inherit role: {role}"

    # org_admin also satisfies all 5 override relations
    for role in FIVE_TIER_ROLES:
        override_rel = f"override_{role}"
        assert (
            await client.check("user:alice", override_rel, "provider_org:prov_1") is True
        ), f"org_admin should satisfy override relation: {override_rel}"


async def test_5_tier_payer_hierarchy_transitive_inheritance(client):
    """Verify 5-tier Payer hierarchy gives org_admin all lower roles transitively."""
    rel_map = build_role_hierarchy(FIVE_TIER_ROLES)
    ns = Namespace("payer_org", rel_map, singleton_relations={"org_admin"})
    client.register_schema(ns)

    # Assign only org_admin to payer_chief
    await client.write([RelationTuple("payer_org", "payer_1", "org_admin", "user:payer_chief")])

    for role in FIVE_TIER_ROLES:
        assert (
            await client.check("user:payer_chief", role, "payer_org:payer_1") is True
        ), f"payer org_admin should inherit role: {role}"

    for role in FIVE_TIER_ROLES:
        override_rel = f"override_{role}"
        assert (
            await client.check("user:payer_chief", override_rel, "payer_org:payer_1") is True
        ), f"payer org_admin should satisfy override relation: {override_rel}"


async def test_5_tier_upward_override_semantics(client):
    """Verify strict upward override:

    - org_manager satisfies override_tpa_coordinator, override_org_user,
      override_diagnostic_billing_staff
    - org_manager DOES NOT satisfy override_org_manager or override_org_admin.
    - tpa_coordinator satisfies override_org_user, override_diagnostic_billing_staff,
      but NOT override_tpa_coordinator, override_org_manager, or override_org_admin.
    - diagnostic_billing_staff satisfies NONE of the overrides.
    """
    rel_map = build_role_hierarchy(FIVE_TIER_ROLES)
    ns = Namespace("provider_org", rel_map, singleton_relations={"org_admin"})
    client.register_schema(ns)

    # Assign manager directly
    await client.write([RelationTuple("provider_org", "prov_1", "org_manager", "user:mgr")])

    # Manager does NOT have org_admin
    assert await client.check("user:mgr", "org_admin", "provider_org:prov_1") is False

    # Manager has own role and all roles below it
    assert await client.check("user:mgr", "org_manager", "provider_org:prov_1") is True
    assert await client.check("user:mgr", "tpa_coordinator", "provider_org:prov_1") is True
    assert await client.check("user:mgr", "org_user", "provider_org:prov_1") is True
    assert await client.check("user:mgr", "diagnostic_billing_staff", "provider_org:prov_1") is True

    # Manager satisfies overrides for STRICTLY LOWER tiers:
    assert await client.check("user:mgr", "override_tpa_coordinator", "provider_org:prov_1") is True
    assert await client.check("user:mgr", "override_org_user", "provider_org:prov_1") is True
    assert await client.check("user:mgr", "override_diagnostic_billing_staff", "provider_org:prov_1") is True

    # Manager DOES NOT satisfy override for own role or higher:
    assert await client.check("user:mgr", "override_org_manager", "provider_org:prov_1") is False
    assert await client.check("user:mgr", "override_org_admin", "provider_org:prov_1") is False

    # Now test tpa_coordinator
    await client.write([RelationTuple("provider_org", "prov_1", "tpa_coordinator", "user:tpa")])
    assert await client.check("user:tpa", "override_org_user", "provider_org:prov_1") is True
    assert await client.check("user:tpa", "override_diagnostic_billing_staff", "provider_org:prov_1") is True
    assert await client.check("user:tpa", "override_tpa_coordinator", "provider_org:prov_1") is False
    assert await client.check("user:tpa", "override_org_manager", "provider_org:prov_1") is False
    assert await client.check("user:tpa", "override_org_admin", "provider_org:prov_1") is False

    # Lowest tier: diagnostic_billing_staff
    await client.write([RelationTuple("provider_org", "prov_1", "diagnostic_billing_staff", "user:billing")])
    assert await client.check("user:billing", "diagnostic_billing_staff", "provider_org:prov_1") is True
    assert await client.check("user:billing", "org_user", "provider_org:prov_1") is False
    for role in FIVE_TIER_ROLES:
        assert await client.check("user:billing", f"override_{role}", "provider_org:prov_1") is False


async def test_role_hierarchy_with_audit_explain(client):
    """Verify explain traces hierarchical role checks properly."""
    rel_map = build_role_hierarchy(FIVE_TIER_ROLES)
    ns = Namespace("provider_org", rel_map, singleton_relations={"org_admin"})
    client.register_schema(ns)

    await client.write([RelationTuple("provider_org", "prov_1", "org_admin", "user:alice")])

    decision = await client.explain("user:alice", "diagnostic_billing_staff", "provider_org:prov_1")
    assert decision.allowed is True
    assert "user:alice" in decision.reason
    assert "provider_org:prov_1#diagnostic_billing_staff" in decision.reason


async def test_list_permissions_with_hierarchy(client):
    """Verify list_permissions returns all transitive roles for an org_admin."""
    rel_map = build_role_hierarchy(FIVE_TIER_ROLES)
    ns = Namespace("provider_org", rel_map, singleton_relations={"org_admin"})
    client.register_schema(ns)

    await client.write([RelationTuple("provider_org", "prov_1", "org_admin", "user:alice")])

    perms = await client.list_permissions("user:alice", "provider_org:prov_1")
    # Should include all 5 roles and all 5 overrides
    for role in FIVE_TIER_ROLES:
        assert role in perms
        assert f"override_{role}" in perms
