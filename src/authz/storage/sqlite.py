import json
from contextlib import asynccontextmanager
from typing import Sequence

import aiosqlite

from authz.storage.base import Token
from authz.tuples import Condition, RelationTuple

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tuples (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT NOT NULL,
    object_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    subject TEXT NOT NULL,
    condition_name TEXT,
    condition_context TEXT,
    UNIQUE(namespace, object_id, relation, subject)
);
CREATE INDEX IF NOT EXISTS idx_tuples_forward
    ON tuples(namespace, object_id, relation);
CREATE INDEX IF NOT EXISTS idx_tuples_reverse
    ON tuples(namespace, subject);
"""

_UPSERT_SQL = """
INSERT INTO tuples (namespace, object_id, relation, subject, condition_name, condition_context)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(namespace, object_id, relation, subject) DO UPDATE SET
    condition_name = excluded.condition_name,
    condition_context = excluded.condition_context
"""

_DELETE_SQL = """
DELETE FROM tuples WHERE namespace = ? AND object_id = ? AND relation = ? AND subject = ?
"""


def _row_to_tuple(row: tuple) -> RelationTuple:
    namespace, object_id, relation, subject, condition_name, condition_context = row
    condition = None
    if condition_name is not None:
        condition = Condition(condition_name, json.loads(condition_context or "{}"))
    return RelationTuple(namespace, object_id, relation, subject, condition=condition)


class SqliteStorage:
    def __init__(self, path: str):
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self._in_transaction = False

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.executescript(_SCHEMA_SQL)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "SqliteStorage":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    @asynccontextmanager
    async def transaction(self):
        if self._in_transaction:
            yield
            return
        self._in_transaction = True
        try:
            yield
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise
        finally:
            self._in_transaction = False

    async def write_tuples(self, tuples: Sequence[RelationTuple]) -> Token:
        async with self.transaction():
            for t in tuples:
                condition_name = t.condition.name if t.condition else None
                condition_context = (
                    json.dumps(dict(t.condition.context)) if t.condition else None
                )
                await self._conn.execute(
                    _UPSERT_SQL,
                    (
                        t.namespace,
                        t.object_id,
                        t.relation,
                        t.subject,
                        condition_name,
                        condition_context,
                    ),
                )
        return await self.current_token()

    async def delete_tuples(self, tuples: Sequence[RelationTuple]) -> Token:
        async with self.transaction():
            for t in tuples:
                await self._conn.execute(
                    _DELETE_SQL, (t.namespace, t.object_id, t.relation, t.subject)
                )
        return await self.current_token()

    async def read_tuples(
        self,
        namespace: str,
        object_id: str | None = None,
        relation: str | None = None,
        subject: str | None = None,
    ) -> list[RelationTuple]:
        query = (
            "SELECT namespace, object_id, relation, subject, condition_name, "
            "condition_context FROM tuples WHERE namespace = ?"
        )
        params: list[str] = [namespace]
        if object_id is not None:
            query += " AND object_id = ?"
            params.append(object_id)
        if relation is not None:
            query += " AND relation = ?"
            params.append(relation)
        if subject is not None:
            query += " AND subject = ?"
            params.append(subject)
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_tuple(row) for row in rows]

    async def current_token(self) -> Token:
        # MAX(change_id) over the live table would go backwards after a
        # delete empties it; sqlite_sequence tracks the AUTOINCREMENT
        # high-water mark, which only ever increases.
        async with self._conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'tuples'"
        ) as cursor:
            row = await cursor.fetchone()
        return str(row[0] if row else 0)

    async def wait_for_token(self, token: Token) -> None:
        current = await self.current_token()
        if int(current) < int(token):
            raise RuntimeError(
                f"storage is behind token {token!r} (current: {current!r})"
            )
