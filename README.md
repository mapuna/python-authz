# authz

A framework-agnostic ReBAC/RBAC/ABAC authorization engine.

## About

Most systems end up with three separate authorization mechanisms: roles
for admin/editor/viewer distinctions (RBAC), attribute rules for things
like "only during business hours" (ABAC), and some hand-rolled traversal
for hierarchies like folders or nested groups (ReBAC). `authz` implements
all three on one data structure instead: a graph of relationship facts,
each one a `(namespace, object, relation, subject)` tuple, in the style
of Google's Zanzibar paper.

A role is just a relation on an object, so "alice is an editor of
document:roadmap" is a tuple like any other. A folder hierarchy is a
traversal between tuples: "you can view a document if you can view its
parent folder" is one rule, applied uniformly no matter how deep the
folder tree goes. An attribute check is a condition attached to a
specific tuple, evaluated against the current subject and context at
check time. Because all three live in the same graph, a single `check()`
call can walk through a role, into a group, and across a parent/child
boundary in one pass, all using the same traversal logic, instead of
three separate mechanisms that would each need to be kept correct and
kept in agreement with each other.

## Status

Release, version 0.7.0:

- **Singleton & Cardinality Constraints**: Enforce subject limits on relations (e.g. at most 1 `org_admin`) via `singleton_relations` and `max_subjects` on `Namespace`, raising `CardinalityViolationError` on violations while maintaining idempotent rewrites.
- **Declarative Role Hierarchies & Strict Upward Overrides**: `build_role_hierarchy(roles_high_to_low, extra_relations=...)` creates multi-tier role hierarchies with transitive downward inheritance and strict upward override relations (`override_<role>`).
- **Unified ReBAC + RBAC + ABAC**: Zanzibar-style relationship graphs with dynamic runtime ABAC context.
- **Audit Trail & Policy Explanation**: `Client.explain()` returning `EvaluationDecision` with traversed paths, matched tuples, condition evaluations, and human-readable reasons.
- **Batch Evaluation & Caching**: `Client.check_batch()` evaluating sequences of `CheckItem`s with per-batch ephemeral read caching.
- **Introspection**: `Client.list_permissions()` and `Client.list_objects()` for resource and subject discovery.
- **Declarative Built-in ABAC Predicates**: `builtin_conditions()` and `PythonCallableEvaluator.with_builtins()` (`max_amount`, `min_amount`, `equals_attr`, `in_set`, `jurisdiction_match`, `not_same_subject`).
- **Enhanced FastAPI Integration**: `requires()` with `get_context`, path/query/header resource parameter resolution, and `explain_access()` storing decisions on `request.state.authz_decision`.
- Async SQLite and PostgreSQL storage backends.

## Roadmap

- DuckDB and MongoDB storage backends
- a standalone HTTP service mode beyond the sample app's admin routes
- a SAML auth integration recipe (OAuth2 and JWT are already covered)
- JSON-Logic and CEL `ConditionEvaluator` implementations, alongside the
  existing Python-callable one
- Java, Kotlin, Rust, and C++ SDKs
- making `asyncpg`/`duckdb` and `pyjwt`/`httpx2` optional too, the way
  `fastapi` already is

## Install

```bash
uv add python-authz
```

## Quickstart

A schema declares, per namespace, how each relation is computed: `Direct()`
means "true when a matching tuple exists," `Union` combines several rules
with OR, and `TupleToUserset` re-checks a relation on a related object (the
mechanism behind "viewer of the parent folder implies viewer of the
document"). Once the schema is registered, `write()` adds facts to the
graph and `check()` answers a yes/no access question against it:

```python
from authz import (
    Client, Direct, From, Namespace, PythonCallableEvaluator,
    RelationTuple, SqliteStorage, TupleToUserset, Union,
)

async with SqliteStorage(":memory:") as storage:
    client = Client(storage=storage, condition_evaluator=PythonCallableEvaluator())

    folder = Namespace("folder", {
        "owner": Direct(),
        "viewer": Union(Direct(), From("owner")),
    })
    document = Namespace("document", {
        "parent": Direct(),
        "viewer": Union(Direct(), TupleToUserset("parent", "viewer")),
    })

    client.register_schema(folder, document)

    await client.write([
        RelationTuple("folder", "workspace", "owner", "user:alice"),
        RelationTuple("document", "roadmap", "parent", "folder:workspace"),
    ])

    await client.check("user:alice", "viewer", "document:roadmap")  # True
```

See [`docs/quickstart.md`](docs/quickstart.md) for the full walkthrough
(groups, ABAC conditions, consistency tokens, `expand()`), and
[`examples/seed_data.py`](examples/seed_data.py) for a runnable version of
it: `python -m examples.seed_data`.

Before designing your own schema, read [`docs/pitfalls.md`](docs/pitfalls.md).
It covers schema vs. data cycles, which rewrite rule (`Union`,
`Intersection`, `Exclusion`, `From`, `TupleToUserset`) fits which
situation, and when a depth-limit error means your data is legitimately
deep versus something bypassed the guards.

## Role Hierarchies & Cardinality Constraints

v0.7.0 adds first-class support for ordered role tiers with upward override relations and singleton limits:

```python
from authz import Namespace, build_role_hierarchy, RelationTuple, CardinalityViolationError

# Build 5-tier role relations with downward inheritance and override_<role> relations
roles = build_role_hierarchy([
    "org_admin",
    "org_manager",
    "tpa_coordinator",
    "org_user",
    "diagnostic_billing_staff",
])

# Enforce singleton constraint: an organization can have at most ONE org_admin
org_ns = Namespace("org", roles, singleton_relations={"org_admin"})
client.register_schema(org_ns)

# Alice is assigned org_admin -> inherits org_manager, tpa_coordinator, etc.
await client.write([RelationTuple("org", "acme", "org_admin", "user:alice")])
assert await client.check("user:alice", "org_user", "org:acme") is True

# Bob cannot also be assigned org_admin on the same org
try:
    await client.write([RelationTuple("org", "acme", "org_admin", "user:bob")])
except CardinalityViolationError as e:
    print(f"Singleton violation: {e}")
```

## FastAPI Integration Example

A route needs one thing from an authorization library: block the request
before the handler runs if the caller lacks permission. `authz.integrations.fastapi`
does that as a single `Depends()`, so the check happens the same way
FastAPI already resolves any other dependency. It's an optional adapter
built as a proof of concept; a Django, Flask, or plain-script consumer
should call the same `Client` directly instead.

```python
from fastapi import Depends
from authz.integrations.fastapi import requires


@app.get("/documents/{document_id}")
async def read_document(
    document_id: str,
    _: None = Depends(requires(
        "viewer", "document:{document_id}",
        get_client=get_authz_client, get_subject=get_current_user,
    )),
):
    ...
```

`requires()` makes the route depend on a `check()` call: when that call
returns `False`, the request never reaches the handler body, and the
caller receives a 403 automatically. See
[`docs/fastapi_integration.md`](docs/fastapi_integration.md) for the full
example, including how `get_client`/`get_subject` compose with your app's
own database and auth setup.

## Development

```bash
uv sync --extra fastapi
uv run pytest
```
