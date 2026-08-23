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
    }
    for name in expected:
        assert hasattr(authz, name), f"missing export: {name}"
