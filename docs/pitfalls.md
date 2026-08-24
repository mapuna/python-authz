# Pitfalls Guide

This guide is for anyone designing their own schema on top of `authz`.
Each section starts with something you'll actually see, an error message,
a surprising `False`, a slow request, then explains the mechanism behind
it. You don't need to think in terms of relationship graphs to follow
along.

## 1. Schema Cycles vs. Data Cycles

A relation can be defined in terms of other relations (`editor` includes
`owner`, `viewer` includes `editor`), and a tuple's subject can point at
another object instead of a plain user (a folder's parent, a nested
group). Both are ways of building a loop that would make `check()` recurse
forever, and they're different kinds of mistakes: one is in the shape of
your schema, the other is in the data written against a schema that was
fine. `authz` catches each with a separate guard, at a different point in
the code:

- **`SchemaCycleDetected`** fires at `register_schema()`, before any data
  exists, because it needs none: it's a bug in the *shape* of the schema
  itself, like accidentally writing `"viewer": From("editor")` and
  `"editor": From("viewer")` on the same namespace. The engine walks the
  `From`/`Union`/`Intersection`/`Exclusion` references between relations
  and rejects a cyclic graph before anything else runs. Catching this at
  registration, rather than the first time it happens to matter at
  runtime, is the whole point: a schema bug should become visible
  immediately, not on whichever `check()` call happens to hit it first.

- **`WouldCreateCycle`** fires at `write()`, and is about the data, not
  the schema. Two things create a graph edge between objects: relations
  used as `TupleToUserset`'s first argument (like `"parent"` in a folder
  hierarchy), and any tuple whose subject is a userset reference
  (`"group:B#member"`, used for nested group membership). Before
  persisting one, `write()` checks whether the new edge's target can
  already reach back to its source. If `folder:A`'s parent is `folder:B`,
  writing `folder:B`'s parent as `folder:A` is rejected outright, and the
  error names the exact tuple that would have closed the loop.

- **`CycleDetected`** is the last resort, raised mid-`check()`. It only
  fires for cyclic data that reached storage some other way than
  `client.write()`, e.g. a bulk import, a migration, a direct database
  edit. Everything written through the normal API is protected by the two
  guards above; this one exists because those guards can't see data they
  never validated.

Never catch these and treat them as `False`. If your application code
wraps a `check()` call in a broad `except Exception: return False`, a real
bug in your schema or data will produce a result that looks exactly like
a correctly denied request: `check()` itself never raises to mean "access
denied," that's always a plain `False`. Nobody notices the difference,
because nothing looks broken. `CycleDetected`, `WouldCreateCycle`,
`SchemaCycleDetected`, and `DepthLimitExceeded` are all subclasses of
`AuthError` and sit outside `check()`'s boolean return contract on
purpose. Let them propagate, or catch them specifically and alert on
them, instead of folding them into a denial.

## 2. The Correct Rewrite Rule

Three different problems all look like "I need to combine two
conditions," and each needs a different rewrite rule.

- **"This role should include everyone who has that other role"**: use
  `Union` and `From`. `Union(Direct(), From("owner"))` on an `editor`
  relation means someone is an editor if there's a direct `editor` tuple
  for them, or if they qualify as `owner`. Writing only an `owner` tuple
  is enough to pass an `editor` check; see
  `tests/test_engine_check_from.py::test_owner_inherits_editor_via_from`.

- **"This needs two independent things to both be true"**: use
  `Intersection`. `Intersection(From("editor"), From("compliance_cleared"))`
  requires both relations to hold; being an editor alone isn't enough.
  See `tests/test_engine_check_boolean_ops.py::test_intersection_requires_all_children_true`.

- **"Grant broadly, then carve out an exception"**: use `Exclusion`.
  `Exclusion(Direct(), From("banned"))` on a `viewer` relation means
  viewer access holds if directly granted, unless a `banned` tuple also
  exists for that same object. `Exclusion`'s two branches need to read
  *different* relations, or they can never disagree. See
  `tests/test_engine_check_from.py::test_exclusion_true_when_base_true_and_subtract_redirected_false`
  for a working example, and its neighboring `_redirected_true` test for
  the case where the exclusion actually fires.

- **"Access should follow a parent/child relationship between different
  objects"**: use `TupleToUserset`, the only one of these rules that
  crosses from one object to another.
  `TupleToUserset("parent", "viewer")` looks up the `parent` tuple on the
  current object, then re-checks `viewer` on that other object. This is
  what makes "you can view a document if you can view its folder" work
  without writing a `viewer` tuple on every document.

## 3. Consistency Tokens

A plain `check()` call already sees every write that completed before it,
so most code never needs to think about tokens at all. The case where a
token matters is small but important: you just revoked someone's access,
and the very next thing you do is check whether they still have it, often
to decide whether to show a "revoked" confirmation, or because a test is
asserting the revoke worked. Skip the token in that situation and you'll
see a revoke that appears not to have taken effect: a caller that ran
`check()` immediately after `delete()` gets a stale-looking `True`.

Pass the token that `delete()` returned as `at_least_as_fresh_as`, and
`check()` will wait until storage has caught up to at least that point
before evaluating. See
`tests/test_integration_scenarios.py::test_revoke_is_visible_immediately_via_consistency_token`
for the shape of this. Outside that narrow window, omit the token: it has
a real cost, and ordinary reads don't need it.

## 4. Depth-limit tuning

`DepthLimitExceeded` can fire on a `check()` call against data that has no
cycle in it anywhere: every object in the chain is distinct, nothing
repeats, and the check still fails. That happens for two different
reasons, and each needs the opposite response.

- **Your hierarchy is legitimately deep.** A folder tree nested 30 levels,
  or an org chart with many layers of nested groups, can need more than
  the default `max_depth=25` hops to resolve. If you hit this
  on real, correct data, raise `max_depth` when constructing the `Client`
  (`Client(storage=..., condition_evaluator=..., max_depth=50)`), or
  consider flattening the hierarchy by writing a direct tuple instead of
  relying on deep traversal for every check.

- **Someone, or something, built an unreasonably long chain on purpose.**
  `CycleDetected` only catches *repeated* nodes, so a long-but-acyclic
  chain of `parent` tuples crafted specifically to make one `check()`
  call expensive slips past it entirely: nothing repeats, so there's no
  cycle to detect. `DepthLimitExceeded` bounds the cost here. Don't raise
  `max_depth` reflexively without checking whether the data that
  triggered it is expected.

`tests/test_engine_cycle_and_depth.py::test_deep_acyclic_chain_raises_depth_limit_exceeded`
shows the mechanics: a five-hop acyclic `parent` chain against a
`max_depth=3` client raises `DepthLimitExceeded` even though every folder
in the chain is a distinct object.
