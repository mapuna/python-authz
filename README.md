# authz

A framework-agnostic ReBAC/RBAC/ABAC authorization engine

## About

`authz` covers ReBAC, RBAC, and ABAC through one Zanzibar-style
relationship graph instead of three separate systems.

A role is a relation on an object. Group and folder hierarchies are native relationship traversal, and attribute-based rules attach as conditions on top of the same tuples resulting in code path for all three paradigms.

## Status

Early release:

- version 0.5
- the core engine, async SQLite and PostgreSQL storage backends, and the optional FastAPI `Depends()` integration
(`authz.integrations.fastapi`, installed via `python-authz[fastapi]`)
- a reference sample app (`examples/sample_app/`) and OAuth2/JWT auth integration recipes (`examples/auth_integrations/`)

## Roadmap

- DuckDB and MongoDB storage backends
- A standalone HTTP service mode beyond the sample app's admin routes
- SAML auth integration recipe (OAuth2 and JWT are already covered)
- JSON-Logic and CEL `ConditionEvaluator` implementations, alongside the
  existing Python-callable one
- Java, Kotlin, Rust, and C++ SDKs
- Making `asyncpg`/`duckdb` and `pyjwt`/`httpx2` genuinely optional too,
  the same principle applied to the rest of the dependency footprint

## Install

```bash
uv add python-authz
```

## Quickstart

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
[`examples/seed_data.py`](examples/seed_data.py) for a runnable version of it: `python -m examples.seed_data`.

Before designing your own schema, read [`docs/pitfalls.md`](docs/pitfalls.md). It covers schema vs. data cycles, which rewrite rule (`Union`, `Intersection`, `Exclusion`, `From`, `TupleToUserset`) fits which situation, and when depth-limit errors mean that your data is deep versus something bypassed the guards.

## FastAPI Integration Example

`authz.integrations.fastapi` is an optional adapter as a PoC: a Django, Flask, or plain-script consumer should call the same `Client` directly instead.

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

`requires()` gates a route on a `check()` call — denied requests never
reach the handler and get a 403 automatically. See
[`docs/fastapi_integration.md`](docs/fastapi_integration.md) for the full example, including how `get_client`/`get_subject` compose with your app's own database and auth setup.

## Development

```bash
uv sync --extra fastapi
uv run pytest
```
