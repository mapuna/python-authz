# Pitfalls Guide

This guide is for anyone designing their own schema on top of `authz`. Each section starts with an error message, a surprising `False`, a slow request, before explaining the mechanism behind it, You don't need to think in terms of relationship graphs to follow along.

## 1. Schema Cycles vs. Data Cycles

**What you'll see:** one of three different errors

- `SchemaCycleDetected` is caught the moment you call `register_schema()`;
- `WouldCreateCycle` is caught the moment you call `write()`, or
- `CycleDetected` is caught much later, during an unrelated `check()` call that happens to touch the broken part of the graph.

These map to three separate guards, each catching a different kind of
mistake:

- **`SchemaCycleDetected`** fires at `register_schema()` and needs no data at all, meaning that it's a bug in the *shape* of your schema, like accidentally writing `"viewer": From("editor")` and `"editor": From("viewer")` on the same namespace. The engine walks the `From`/`Union`/`Intersection`/`Exclusion` references between relations and rejects a cyclic graph (even before anything else runs). The intention is to have the library user be known of her mistakes early!

- **`WouldCreateCycle`** fires at `write()` and is about the *data*, not the schema. Relations used as `TupleToUserset`'s first argument (like `"parent"` in a folder hierarchy) and any tuple whose subject is a userset reference (`"group:B#member"`, used for nested group membership) are graph edges. Before persisting one, `write()` checks whether the new edge's target can already reach back to its source e.g., if `folder:A`'s parent is `folder:B`, writing `folder:B`'s parent as `folder:A` is rejected outright, naming the exact tuple that would have closed the loop.

- **`CycleDetected`** is the last resort, raised mid-`check()`. It only fires for cyclic data that reached storage some other way than `client.write()`, e.g., a bulk import, a migration, a direct database edit, etc. Everything written through the normal API is protected by the two guards above; this one exists because those guards can't see data they never validated.

**NOTE**: *Never catch these and treat them as `False`*

**What if you get this wrong?** Permission check that should
have failed loudly with a clear error instead just quietly returns "no
access", resulting in a real bug in your schema or data looks identical to a correctly-denied request. Nobody notices, because it doesn't look broken; it will look like the system is working exactly as intended.

Technically: `CycleDetected`, `WouldCreateCycle`, `SchemaCycleDetected`,
and `DepthLimitExceeded` are all subclasses of `AuthError`. They are not part of `check()`'s boolean return contract. `check()` itself never raises to mean "access denied" (that's always a plain `False`). If your application code wraps a `check()` call in a broad `except Exception: return False`, it will silently swallow these and mask the underlying problem. Let them propagate (or catch them specifically and alert on them) instead.

## 2. The Correct Rewrite Rule

**What you'll see:** three different problems that all look like "I need
to combine two conditions", but need three different tools.

- **"This role should include everyone who has that other role"**: use `Union` and `From`. `Union(Direct(), From("owner"))` on an `editor` relation means: someone is an editor if there's a direct `editor` tuple for them, *or* if they qualify as `owner`. This is confirmed in `tests/test_engine_check_from.py::test_owner_inherits_editor_via_from`, i.e., writing only an `owner` tuple is enough to pass an `editor` check.

- **"This needs two independent things to both be true"**: use `Intersection`. `Intersection(From("editor"), From("compliance_cleared"))` requires both relations to hold; being an editor alone isn't enough. See `tests/test_engine_check_boolean_ops.py::test_intersection_requires_all_children_true`.

- **"Grant broadly, then carve out an exception"**: use `Exclusion`. `Exclusion(Direct(), From("banned"))` on a `viewer` relation means viewer access holds if directly granted, *unless* a `banned` tuple also exists for that same object. Note that `Exclusion`'s two branches need to read *different* relations to ever disagree. See `tests/test_engine_check_from.py::test_exclusion_true_when_base_true_and_subtract_redirected_false` for a working example, and its neighboring `_redirected_true` test for the case where the exclusion actually happens.

- **"Access should follow a parent/child relationship between different objects"**: use `TupleToUserset`. This is the one genuinely ReBAC rule: `TupleToUserset("parent", "viewer")` looks up the `parent` tuple on the current object, then re-checks `viewer` *on that other object*. This is what makes "you can view a document if you can view its folder" work without writing a `viewer` tuple on every single document.

## 3. Consistency Tokens

When `at_least_as_fresh_as` actually matters!

**What you'll see if you skip it:** nothing, almost all of the time: a
plain `check()` call already sees every write that completed before it, so most code never needs to think about tokens at all.

**What you'll see if you need it and don't have it:** a revoke that appears not to have taken effect, in a caller that ran a `check()` immediately after a `delete()` and got a stale-looking `True`.

The case where a token matters is small but important: you just revoked
someone's access, and the *very next* thing you do is check whether they
still have it (often to decide whether to show a "revoked" confirmation,
or because a test is asserting the revoke worked). Pass the token that
`delete()` returned as `at_least_as_fresh_as`, and `check()` will wait
until storage has caught up to at least that point before evaluating.
See `tests/test_integration_scenarios.py::test_revoke_is_visible_immediately_via_consistency_token` for the shape of this. Outside of this small window, omit the token, because it's not free (has a real cost), and ordinary reads don't need it.

## 4. Depth-limit tuning

**What you'll see:** `DepthLimitExceeded`, on a `check()` call against data that has no cycle in it anywhere, i.e., every object in the chain is distinct, nothing repeats, and yet the check still fails.

This happens for two different reasons, and need two opposite
responses:

- **Your hierarchy is legitimately deep.** A folder tree nested 30 levels, or an org chart with many layers of nested groups, can genuinely need more than the default `max_depth=25` hops to resolve. If you hit this on real, correct data, raise `max_depth` when constructing the `Client` (`Client(storage=..., condition_evaluator=..., max_depth=50)`), or consider flattening the hierarchy by writing a direct tuple instead of relying on deep traversal for every check.
- **Someone (or something) built an unreasonably long chain on purpose.** Because `CycleDetected` only catches *repeated* nodes, a long-but-acyclic chain of `parent` tuples specifically crafted to make one `check()` call expensive slips past it entirely, because nothing repeats, so there's no cycle to detect. `DepthLimitExceeded`  bounds the cost here; don't raise `max_depth` reflexively without checking whether the data that triggered it is expected.

`tests/test_engine_cycle_and_depth.py::test_deep_acyclic_chain_raises_depth_limit_exceeded` shows the mechanics: a five-hop acyclic `parent` chain against a `max_depth=3` client raises `DepthLimitExceeded` even though every folder in the chain is a distinct object.
