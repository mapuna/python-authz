"""Backend-agnostic behavioral contract for the Storage protocol.

Each backend's test file imports this module with `import *` and supplies
its own `storage` fixture. No fixtures are defined here.
"""
import pytest

from authz.tuples import Condition, RelationTuple


async def test_write_then_read_round_trips(storage):
    await storage.write_tuples(
        [RelationTuple("document", "doc42", "owner", "user:alice")]
    )
    rows = await storage.read_tuples("document", object_id="doc42", relation="owner")
    assert rows == [RelationTuple("document", "doc42", "owner", "user:alice")]


async def test_read_filters_by_namespace_object_relation_subject(storage):
    await storage.write_tuples(
        [
            RelationTuple("document", "doc42", "owner", "user:alice"),
            RelationTuple("document", "doc42", "editor", "user:bob"),
            RelationTuple("document", "doc7", "owner", "user:carol"),
        ]
    )
    rows = await storage.read_tuples("document", object_id="doc42")
    assert {r.relation for r in rows} == {"owner", "editor"}

    rows = await storage.read_tuples("document", subject="user:bob")
    assert len(rows) == 1
    assert rows[0].object_id == "doc42"


async def test_write_preserves_condition(storage):
    cond = Condition("business_hours", {"tz": "UTC"})
    await storage.write_tuples(
        [RelationTuple("document", "doc42", "owner", "user:alice", condition=cond)]
    )
    rows = await storage.read_tuples("document", object_id="doc42", relation="owner")
    assert rows[0].condition == cond


async def test_delete_removes_tuple(storage):
    t = RelationTuple("document", "doc42", "owner", "user:alice")
    await storage.write_tuples([t])
    await storage.delete_tuples([t])
    rows = await storage.read_tuples("document", object_id="doc42", relation="owner")
    assert rows == []


async def test_current_token_increases_after_write(storage):
    before = await storage.current_token()
    await storage.write_tuples(
        [RelationTuple("document", "doc42", "owner", "user:alice")]
    )
    after = await storage.current_token()
    assert int(after) > int(before)


async def test_current_token_survives_delete_emptying_the_table(storage):
    t = RelationTuple("document", "doc42", "owner", "user:alice")
    write_token = await storage.write_tuples([t])
    await storage.delete_tuples([t])
    token_after_delete = await storage.current_token()
    assert int(token_after_delete) >= int(write_token)


async def test_write_tuples_returns_token(storage):
    token = await storage.write_tuples(
        [RelationTuple("document", "doc42", "owner", "user:alice")]
    )
    current = await storage.current_token()
    assert token == current


async def test_wait_for_token_returns_for_current_or_past_token(storage):
    token = await storage.write_tuples(
        [RelationTuple("document", "doc42", "owner", "user:alice")]
    )
    await storage.wait_for_token(token)  # must not raise


async def test_transaction_commits_on_success(storage):
    async with storage.transaction():
        await storage.write_tuples(
            [RelationTuple("document", "doc42", "owner", "user:alice")]
        )
    rows = await storage.read_tuples("document", object_id="doc42", relation="owner")
    assert len(rows) == 1


async def test_transaction_rolls_back_on_error(storage):
    with pytest.raises(RuntimeError):
        async with storage.transaction():
            await storage.write_tuples(
                [RelationTuple("document", "doc42", "owner", "user:alice")]
            )
            raise RuntimeError("boom")
    rows = await storage.read_tuples("document", object_id="doc42", relation="owner")
    assert rows == []
