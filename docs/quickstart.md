# Quickstart

This walkthrough uses plain `Client` calls throughout.

(See [`fastapi_integration.md`](fastapi_integration.md) for an optional FastAPI adapter.)

Instead of three separate systems, everything is expressed as a graph of
relationship tuples: `(namespace, object, relation, subject)`, with
roles and attribute conditions layered on top of that same graph. This
walkthrough builds the schema and data from [`examples/seed_data.py`](../examples/seed_data.py). You can run this example directly as well: `python -m examples.seed_data`.

## 1. Construct a `Client`

```python
from authz import Client, PythonCallableEvaluator, SqliteStorage


async with SqliteStorage(":memory:") as storage:
    client = Client(storage=storage, condition_evaluator=PythonCallableEvaluator())
    ...
```

`Client` is the single entry point: it validates against a registered
schema, persists tuples through the `storage` backend, and evaluates
`check()` calls. `SqliteStorage` is the Phase 1 backend — async, backed by `aiosqlite`. `PythonCallableEvaluator` resolves ABAC conditions as plain Python functions (see step 4).

## 2. Define the Schema

```python
from authz import Direct, From, Namespace, TupleToUserset, Union


group = Namespace("group", {"member": Direct()})

folder = Namespace("folder", {
    "owner":  Direct(),
    "editor": Union(Direct(), From("owner")),
    "viewer": Union(Direct(), From("editor")),
})

document = Namespace("document", {
    "parent": Direct(),
    "owner":  Direct(),
    "editor": Union(Direct(), From("owner")),
    "viewer": Union(Direct(), From("editor"), TupleToUserset("parent", "viewer")),
})

client.register_schema(group, folder, document)
```

Each relation is built from a small set of rewrite rules:

- **`Direct()`**: the relation holds if a matching tuple was written for it.
- **`Union(...)`**: RBAC-style role hierarchy: `editor` includes anyone who is directly an editor *or* who qualifies as `owner` (`From("owner")`).
- **`TupleToUserset(tupleset_relation, computed_relation)`**: ReBAC-style traversal: `document.viewer` also includes anyone who is a `viewer` of the document's `parent` folder.

`register_schema()` also runs a static cycle check over the rewrite rules before accepting them (see [pitfalls.md](pitfalls.md) for what that catches and what it doesn't).

## 3. Write Relationship Tuples

```python
from authz import RelationTuple


await client.write([
    RelationTuple("folder", "workspace", "owner", "user:alice"),
    RelationTuple("group", "eng", "member", "user:bob"),
    RelationTuple("folder", "workspace", "viewer", "group:eng#member"),
    RelationTuple("document", "roadmap", "parent", "folder:workspace"),
])
```

A subject is either a plain object (`"user:alice"`) or a **userset**
reference (`"group:eng#member"`: "members of group eng"), which is how
group membership composes with everything else without special-casing it.

`write()` returns a `Token`. Keep it if you need to guarantee a subsequent `check()` observes this exact write (see step 5).

## 4. Check Access

```python
await client.check("user:alice", "viewer", "document:roadmap")  # True: alice owns the folder
await client.check("user:bob", "viewer", "document:roadmap")    # True: bob is in eng, eng can view the folder
await client.check("user:mallory", "viewer", "document:roadmap")  # False
```

To add an ABAC condition, register a Python callable and attach it to a
tuple:

```python
from authz import Condition


def is_business_hours(*, subject, resource, timezone):
    ...  # your logic

client.register_condition("business_hours", is_business_hours)

await client.write([
    RelationTuple("document", "roadmap", "editor", "user:carol",
                  condition=Condition("business_hours", {"timezone": "UTC"})),
])
```

The condition is evaluated at check time, not write time, against the
current subject/resource/context, so its result can change between calls even though the tuple itself never does.

## 5. Consistency Tokens

```python
token = await client.write([...])
await client.check(subject, permission, resource, at_least_as_fresh_as=token)
```

Most checks don't need `at_least_as_fresh_as`. Rrdinary reads already see everything committed so far. It matters specifically right after a revoke, when you need a guarantee that the very next check can't miss it. See [pitfalls.md](pitfalls.md) for the full explanation.

## 6. Debugging with `expand()`

```python
tree = await client.expand("viewer", "document:roadmap")
```

Returns a `UsersetTree` showing every direct subject and every relation
`check()` would traverse into — useful for answering "who can access this, and through what path" without running a check per candidate subject.

## Next steps

Read [pitfalls.md](pitfalls.md) before designing your own schema. It
covers the failure modes that aren't obvious from the API surface: cycles, depth limits, and when each rewrite rule is the right tool.
