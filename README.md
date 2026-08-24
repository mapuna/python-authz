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

Early release, version 0.5:

- the core engine, async SQLite and PostgreSQL storage backends, and the
  optional FastAPI `Depends()` integration (`authz.integrations.fastapi`,
  installed via `python-authz[fastapi]`)
- a reference sample app (`examples/sample_app/`) and OAuth2/JWT auth
  integration recipes (`examples/auth_integrations/`)

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
