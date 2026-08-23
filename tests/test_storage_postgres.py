import asyncio

import pytest
from testcontainers.community.postgres import PostgresContainer

from authz.storage.postgres import PostgresStorage
from tests.storage_conformance import *  # noqa: F401,F403


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16") as pg:
        yield pg


def _asyncpg_dsn(container: PostgresContainer) -> str:
    # testcontainers' get_connection_url() returns a SQLAlchemy-dialect URL
    # (postgresql+asyncpg://...); asyncpg's own DSN format has no "+driver"
    # suffix, so strip it.
    url = container.get_connection_url(driver="asyncpg")
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture
async def storage(postgres_container):
    async with PostgresStorage(_asyncpg_dsn(postgres_container)) as s:
        yield s
        async with s._pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE tuples RESTART IDENTITY")


async def test_context_manager_connects_and_closes(postgres_container):
    async with PostgresStorage(_asyncpg_dsn(postgres_container)) as s:
        rows = await s.read_tuples("document", object_id="doc42")
        assert rows == []


async def test_transaction_nested_calls_share_one_connection(storage):
    seen_connections = []

    async with storage.transaction():
        conn1, must_release1 = await storage._connection()
        conn2, must_release2 = await storage._connection()
        seen_connections.extend([conn1, conn2])
        assert must_release1 is False
        assert must_release2 is False

    assert seen_connections[0] is seen_connections[1]


async def test_connection_outside_transaction_must_be_released(storage):
    conn, must_release = await storage._connection()
    assert must_release is True
    await storage._pool.release(conn)


async def test_concurrent_transactions_do_not_share_connections(storage):
    results = {}

    async def run(name):
        async with storage.transaction():
            conn, _ = await storage._connection()
            await asyncio.sleep(0.05)  # widen the window for a real race
            results[name] = conn

    await asyncio.gather(run("a"), run("b"))
    assert results["a"] is not results["b"]
