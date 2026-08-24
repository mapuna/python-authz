# Using authz with FastAPI (Optional)

`authz`'s core (`Client`, the schema DSL, storage backends) has no
dependency on FastAPI or any other web framework.
`authz.integrations.fastapi` is a thin adapter on top of it, installed via
`pip install python-authz[fastapi]`. A Django, Flask, or plain-script
consumer should call `Client.check()`/`write()`/`expand()` directly
instead.

The adapter's job is to turn a permission check into a FastAPI
dependency, so that a route can depend on it exactly the way it depends
on anything else, a database connection, an authenticated user, and so
on. Put `requires()` in a route's dependency list, and if the check
fails, the route's own body never runs at all: the caller receives a 403
automatically, before any handler code executes.

## Example

```python
from fastapi import Depends, FastAPI, Request
from authz import Client, Direct, Namespace, PythonCallableEvaluator, SqliteStorage
from authz.integrations.fastapi import requires

app = FastAPI()


@app.on_event("startup")
async def setup_authz():
    storage = SqliteStorage("auth.db")
    await storage.connect()
    client = Client(storage=storage, condition_evaluator=PythonCallableEvaluator())
    client.register_schema(Namespace("document", {"owner": Direct(), "viewer": Direct()}))
    app.state.authz_client = client


async def get_authz_client(request: Request) -> Client:
    return request.app.state.authz_client


async def get_current_user() -> str:
    # Stand-in for real authentication (OAuth2, session cookie, JWT, ...).
    # Whatever it is, it just needs to return a subject string like this.
    return "user:alice"


@app.get("/documents/{document_id}")
async def read_document(
    document_id: str,
    _: None = Depends(requires(
        "viewer", "document:{document_id}",
        get_client=get_authz_client, get_subject=get_current_user,
    )),
):
    return {"document_id": document_id}
```

The resource string `"document:{document_id}"` is filled in from the
route's own path parameter automatically: `document_id` here matches the
`{document_id}` in the route path, and `requires()` fills the placeholder
from FastAPI's already-parsed path parameters. If a route's resource
can't be expressed as a path parameter, because it comes from a header,
or needs a lookup, pass a function instead:

```python
def resource_from_header(request):
    return f"document:{request.headers['X-Document-Id']}"

# or, if it needs to await something:
async def resource_from_lookup(request):
    doc = await look_up_document(request.path_params["slug"])
    return f"document:{doc.id}"

Depends(requires("viewer", resource_from_header, get_client=..., get_subject=...))
```

`requires()` doesn't own the `Client` or the user lookup. Every real app
already has its own way of storing a database connection and its own way
of identifying the current user; those choices are none of this
library's business. So `requires()` takes `get_client` and `get_subject`
as plain functions you supply, rather than deciding for you how a
`Client` gets constructed or how a request gets mapped to a user.

Both are ordinary FastAPI dependencies under the hood: `requires()` wraps
them with `Depends(...)` internally when it builds its own inner
dependency function, so FastAPI resolves their dependency chains exactly
as it would for any other route. If `get_current_user` itself depends on
an OAuth2 bearer-token parser, that keeps working unchanged; `requires()`
never even needs to know such a dependency exists.

## The 403 vs. 500

A denied check and a broken check are not the same thing, and
`requires()` treats them differently on purpose:

- `client.check(...)` returning `False` means `requires()` raises
  `HTTPException(403)`. This is the only way it produces a 403.
- `client.check(...)` raising `CycleDetected`, `WouldCreateCycle`,
  `DepthLimitExceeded`, or any other `AuthError` propagates completely
  unhandled, all the way to FastAPI's default 500 handling (or your app's
  own exception handlers, if you have them).

The distinction matters because those errors mean your schema or your
data has a real bug in it (see [`pitfalls.md`](pitfalls.md) for what each
one means and why): a 403 tells a caller "you don't have access," a 500
here means something is actually broken and needs fixing. Collapsing the
two into the same response would hide that difference from whoever needs
to see it, so `requires()` never catches `AuthError` anywhere in its
implementation.

## Testing with `requires()`

Override `get_client` and `get_subject` independently via
`app.dependency_overrides`, keyed by the exact function object you passed
into `requires()`:

```python
from fastapi.testclient import TestClient


client = TestClient(app)

async def fake_subject():
    return "user:mallory"

app.dependency_overrides[get_current_user] = fake_subject
response = client.get("/documents/doc42")
assert response.status_code == 403

del app.dependency_overrides[get_current_user]
```

This is the same pattern FastAPI's own docs recommend for overriding any
dependency in tests. `requires()` doesn't need anything special here,
since `get_client`/`get_subject` are just regular dependencies from
FastAPI's point of view.
