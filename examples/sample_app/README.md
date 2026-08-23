# Sample App: Task Tracker

A small task-tracker API demonstrating `authz` in a real application.

This example tries to achieve two things at once:

1. A **reference app**: `/projects/*` and `/tasks/*` are ordinary domain
routes, protected via `requires()` exactly the way any app integrating
this library would protect its own routes.
2. A **standalone authorization service**: `/authz/check`, `/authz/write`,
and `/authz/expand` expose the underlying `Client` directly over HTTP, so
external tools can query or manage the authorization graph without going
through Python at all.

## Run

```bash
uv run uvicorn examples.sample_app.main:app --reload
```

The API is then available at `http://localhost:8000`. It seeds itself with
sample data on startup (an in-memory SQLite store, reset every restart):
no database setup, or external services, or login flow configuration.

## Facets

**Domain routes** (`/projects/*`, `/tasks/*`) are what a real task-tracker
app may have regardless of this library, viz, creating tasks, viewing
projects. Each one is behind permissions via `Depends(requires(...))`,
matching [`docs/fastapi_integration.md`](../../docs/fastapi_integration.md).

**Admin authz routes** (`/authz/*`) are thin, direct passthrough to
`Client.check`/`write`/`expand`. They're restricted to `ADMIN_USERS` (just
`alice` in this sample). Anyone else gets a 403, and an unauthenticated
request gets a 401.

## Try it: Deny, Grant, Retry

This walks through the exact scenario `test_deny_then_admin_grants_then_retry_succeeds`
exercises. `bob` is assigned a task, but has no permission on its parent
project, so he can't create new tasks there yet.

```bash
# bob is denied -- he has no editor grant on the project
curl -X POST localhost:8000/projects/p1/tasks \
  -H "X-User-Id: bob" -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
# 403 Forbidden

# alice (admin) grants bob editor access via the raw authz API
curl -X POST localhost:8000/authz/write \
  -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"tuples": [{"namespace": "project", "object_id": "p1", "relation": "editor", "subject": "user:bob"}]}'
# 200, returns a consistency token

# bob retries the exact same request -- now succeeds
curl -X POST localhost:8000/projects/p1/tasks \
  -H "X-User-Id: bob" -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
# 201 Created
```

Note that nothing about the domain routes changed between the first and
third request. Only the underlying relationship graph changed, via the
admin API. That's the point: both facets talk to the same `Client`.

## `require_admin` Doesn't Use `requires()`

The admin routes are deliberately *not* gated through the authorization
engine itself. Something has to be allowed to write the very first tuple
and that can't be a permission granted *by* the tuple-based system, since
there'd be nothing yet to grant it. `require_admin` in `auth.py` checks a
hardcoded `ADMIN_USERS` set directly, sidestepping that bootstrapping
problem entirely. It's the one access-control boundary in this sample that
intentionally sits outside the library.

Following are deliberately fake:

- **Login**: `get_current_user` reads an `X-User-Id` header directly: no
passwords, or tokens, or sessions. This library stays out of authentication
entirely (see `docs/fastapi_integration.md`), and a real auth mechanism
(OAuth2, JWT, sessions) would teach a second, unrelated lesson instead
of the one this sample is actually about. Swap `get_current_user` for your
app's real auth dependency; nothing else changes.
- **Domain data**: project and task content (`domain.py`) lives in plain
in-memory dicts, reset on every restart. Only the authorization graph
(who can do what) goes through a real `Client`/`SqliteStorage`.
