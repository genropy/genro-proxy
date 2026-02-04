# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""SQLite async adapter using aiosqlite with per-request connections."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import aiosqlite

from .base import DbAdapter

if TYPE_CHECKING:
    from collections.abc import Sequence


class SqliteAdapter(DbAdapter):
    """SQLite async adapter with per-request connections.

    Uses :name placeholders natively. Each acquire() opens a new connection,
    release() closes it. This ensures request isolation.

    Type normalization ensures consistent behavior with PostgreSQL:
    - ISO datetime strings → datetime objects
    - 0/1 for boolean columns → False/True
    """

    placeholder = ":name"

    # Column name patterns that should be converted from 0/1 to False/True
    _BOOL_PREFIXES = ("is_", "use_", "has_")
    _BOOL_NAMES = frozenset({"active", "enabled", "ssl", "tls"})

    # Column name patterns for timestamp columns
    _TIMESTAMP_SUFFIXES = ("_at", "_date", "_time")
    _TIMESTAMP_NAMES = frozenset({"created", "updated", "timestamp", "expires"})

    def __init__(self, db_path: str):
        self.db_path = db_path or ":memory:"

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Normalize SQLite values to match PostgreSQL behavior.

        Converts:
        - ISO datetime strings to datetime objects (for timestamp columns)
        - 0/1 to False/True (for boolean columns)
        """
        for key, value in row.items():
            if value is None:
                continue

            # Convert ISO strings to datetime for timestamp columns
            if isinstance(value, str) and (
                key.endswith(self._TIMESTAMP_SUFFIXES) or key in self._TIMESTAMP_NAMES
            ):
                row[key] = self._parse_datetime(value)

            # Convert 0/1 to bool for boolean columns
            elif value in (0, 1):
                if key.startswith(self._BOOL_PREFIXES) or key in self._BOOL_NAMES:
                    row[key] = bool(value)

        return row

    def _parse_datetime(self, value: str) -> datetime | str:
        """Parse ISO datetime string to datetime object."""
        try:
            # Handle various ISO formats
            if "T" in value:
                # ISO format with T separator
                clean = value.replace("Z", "+00:00")
                if "+" in clean or clean.count("-") > 2:
                    # Has timezone info, strip it for naive datetime
                    clean = clean.split("+")[0].split("-")[0] if "+" in clean else clean
                    if clean.count("-") > 2:
                        clean = "-".join(clean.split("-")[:3])
                return datetime.fromisoformat(value.replace("Z", ""))
            elif " " in value:
                # SQLite default format: "YYYY-MM-DD HH:MM:SS"
                return datetime.fromisoformat(value)
            else:
                # Just a date, return as-is
                return value
        except (ValueError, TypeError):
            return value

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
            return self._normalize_row(dict(zip(cols, row, strict=True)))

    async def fetch_all(
        self, conn: aiosqlite.Connection, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute query, return all rows as list of dicts."""
        async with conn.execute(query, params or {}) as cursor:
            rows = await cursor.fetchall()
            cols = [c[0] for c in cursor.description]
            return [self._normalize_row(dict(zip(cols, row, strict=True))) for row in rows]

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
