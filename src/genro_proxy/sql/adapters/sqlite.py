# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""SQLite async adapter using aiosqlite with per-request connections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aiosqlite

from .base import DbAdapter

if TYPE_CHECKING:
    from collections.abc import Sequence


class SqliteAdapter(DbAdapter):
    """SQLite async adapter with per-request connections.

    Uses :name placeholders natively. Each acquire() opens a new connection,
    release() closes it. This ensures request isolation.
    """

    placeholder = ":name"

    # Column name patterns that should be converted from 0/1 to False/True
    _BOOL_PREFIXES = ("is_", "use_", "has_")
    _BOOL_NAMES = frozenset({"active", "enabled", "ssl", "tls"})

    def __init__(self, db_path: str):
        self.db_path = db_path or ":memory:"

    def _normalize_booleans(self, row: dict[str, Any]) -> dict[str, Any]:
        """Convert SQLite 0/1 to Python False/True for boolean-like columns."""
        for key, value in row.items():
            if value in (0, 1):
                if key.startswith(self._BOOL_PREFIXES) or key in self._BOOL_NAMES:
                    row[key] = bool(value)
        return row

    async def acquire(self) -> aiosqlite.Connection:
        """Open new connection for request."""
        return await aiosqlite.connect(self.db_path)

    async def release(self, conn: aiosqlite.Connection) -> None:
        """Close connection."""
        await conn.close()

    async def shutdown(self) -> None:
        """No-op for SQLite (no pool to close)."""
        pass

    async def commit(self, conn: aiosqlite.Connection) -> None:
        """Commit transaction on connection."""
        await conn.commit()

    async def rollback(self, conn: aiosqlite.Connection) -> None:
        """Rollback transaction on connection."""
        await conn.rollback()

    async def execute(
        self, conn: aiosqlite.Connection, query: str, params: dict[str, Any] | None = None
    ) -> int:
        """Execute query, return affected row count."""
        cursor = await conn.execute(query, params or {})
        return cursor.rowcount

    async def execute_many(
        self, conn: aiosqlite.Connection, query: str, params_list: Sequence[dict[str, Any]]
    ) -> int:
        """Execute query multiple times with different params (batch insert)."""
        await conn.executemany(query, params_list)
        return len(params_list)

    async def fetch_one(
        self, conn: aiosqlite.Connection, query: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Execute query, return single row as dict or None."""
        async with conn.execute(query, params or {}) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            cols = [c[0] for c in cursor.description]
            return self._normalize_booleans(dict(zip(cols, row, strict=True)))

    async def fetch_all(
        self, conn: aiosqlite.Connection, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute query, return all rows as list of dicts."""
        async with conn.execute(query, params or {}) as cursor:
            rows = await cursor.fetchall()
            cols = [c[0] for c in cursor.description]
            return [self._normalize_booleans(dict(zip(cols, row, strict=True))) for row in rows]

    async def execute_script(self, conn: aiosqlite.Connection, script: str) -> None:
        """Execute multiple statements (for schema creation)."""
        await conn.executescript(script)

    async def insert_returning_id(
        self, conn: aiosqlite.Connection, table: str, values: dict[str, Any], pk_col: str = "id"
    ) -> Any:
        """Insert a row and return the generated primary key (lastrowid)."""
        cols = list(values.keys())
        placeholders = ", ".join(self._placeholder(c) for c in cols)
        col_list = ", ".join(self._sql_name(c) for c in cols)
        query = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        cursor = await conn.execute(query, values)
        return cursor.lastrowid
