import authz


def test_public_api_exports_expected_names():
    expected = {
        "Client",
        "Namespace",
        "Direct",
        "Union",
        "Intersection",
        "Exclusion",
        "From",
        "TupleToUserset",
        "Condition",
        "RelationTuple",
        "ObjectRef",
        "SubjectRef",
        "UsersetTree",
        "PythonCallableEvaluator",
        "SqliteStorage",
        "PostgresStorage",
        "AuthError",
        "NamespaceNotFound",
        "RelationNotFound",
        "ConditionNotFound",
        "SchemaCycleDetected",
        "WouldCreateCycle",
        "CycleDetected",
        "DepthLimitExceeded",
        "CheckItem",
        "EvaluationDecision",
        "builtin_conditions",
        "CardinalityViolationError",
        "build_role_hierarchy",
    }
    for name in expected:
        assert hasattr(authz, name), f"missing export: {name}"
