import pytest

from authz.storage.sqlite import SqliteStorage
from tests.storage_conformance import *  # noqa: F401,F403


@pytest.fixture
async def storage():
    s = SqliteStorage(":memory:")
    await s.connect()
    yield s
    await s.close()


async def test_context_manager_connects_and_closes():
    async with SqliteStorage(":memory:") as s:
        rows = await s.read_tuples("document", object_id="doc42")
        assert rows == []
