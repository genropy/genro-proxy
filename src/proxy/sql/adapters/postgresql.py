# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""PostgreSQL async adapter using psycopg3 with connection pooling.

Uses connection-per-request model: acquire() gets from pool,
release() returns to pool. Each request gets isolated transaction.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .base import DbAdapter

if TYPE_CHECKING:
    from collections.abc import Sequence


class PostgresAdapter(DbAdapter):
    """PostgreSQL async adapter with connection pooling.

    Uses :name placeholders converted to %(name)s. acquire() gets connection
    from pool, release() returns it. Each connection is isolated.

    Pool is initialized lazily on first acquire().
    """

    placeholder = "%(name)s"

    def pk_column(self, name: str) -> str:
        """Return SQL definition for autoincrement primary key column (PostgreSQL)."""
        return f'"{name}" SERIAL PRIMARY KEY'

    def __init__(self, dsn: str, pool_size: int = 10, connect_timeout: float = 10.0):
        self.dsn = dsn
        self.pool_size = pool_size
        self.connect_timeout = connect_timeout
        self._pool: Any = None

        # Verify psycopg is available at init time
        try:
            import psycopg  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "PostgreSQL support requires psycopg. "
                "Install with: pip install genro-proxy[postgresql]"
            ) from e

    def _convert_placeholders(self, query: str) -> str:
        """Convert :name placeholders to %(name)s for psycopg."""
        return re.sub(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)", r"%(\1)s", query)

    async def _ensure_pool(self) -> None:
        """Initialize connection pool if not already open."""
        if self._pool is not None:
            return

        import asyncio

        from psycopg_pool import AsyncConnectionPool

        async def configure(conn):
            await conn.execute("SET search_path TO public")
            await conn.commit()

        self._pool = AsyncConnectionPool(
            self.dsn,
            min_size=1,
            max_size=self.pool_size,
            open=False,
            configure=configure,
        )
        try:
            await asyncio.wait_for(
                self._pool.open(wait=True, timeout=self.connect_timeout),
                timeout=self.connect_timeout + 1,
            )
        except asyncio.TimeoutError:
            await self._pool.close()
            self._pool = None
            raise TimeoutError(
                f"PostgreSQL connection timed out after {self.connect_timeout}s. "
                "Check credentials and server availability."
            ) from None
        except Exception as e:
            await self._pool.close()
            self._pool = None
            raise ConnectionError(f"PostgreSQL connection failed: {e}") from e

    async def acquire(self) -> Any:
        """Acquire connection from pool."""
        await self._ensure_pool()
        return await self._pool.getconn()

    async def release(self, conn: Any) -> None:
        """Return connection to pool."""
        if self._pool:
            await self._pool.putconn(conn)

    async def shutdown(self) -> None:
        """Close connection pool (application shutdown)."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def commit(self, conn: Any) -> None:
        """Commit transaction on connection."""
        await conn.commit()

    async def rollback(self, conn: Any) -> None:
        """Rollback transaction on connection."""
        await conn.rollback()

    async def execute(self, conn: Any, query: str, params: dict[str, Any] | None = None) -> int:
        """Execute query, return affected row count."""
        query = self._convert_placeholders(query)
        async with conn.cursor() as cur:
            await cur.execute(query, params or {})
            return cur.rowcount

    async def execute_many(
        self, conn: Any, query: str, params_list: Sequence[dict[str, Any]]
    ) -> int:
        """Execute query multiple times with different params (batch insert)."""
        query = self._convert_placeholders(query)
        async with conn.cursor() as cur:
            await cur.executemany(query, params_list)
            return len(params_list)

    async def fetch_one(
        self, conn: Any, query: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Execute query, return single row as dict or None."""
        from psycopg.rows import dict_row

        query = self._convert_placeholders(query)
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params or {})
            return await cur.fetchone()

    async def fetch_all(
        self, conn: Any, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute query, return all rows as list of dicts."""
        from psycopg.rows import dict_row

        query = self._convert_placeholders(query)
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params or {})
            return await cur.fetchall()

    async def execute_script(self, conn: Any, script: str) -> None:
        """Execute multiple statements (for schema creation)."""
        async with conn.cursor() as cur:
            await cur.execute(script)

    async def insert_returning_id(
        self, conn: Any, table: str, values: dict[str, Any], pk_col: str = "id"
    ) -> Any:
        """Insert a row and return the generated primary key (RETURNING)."""
        from psycopg.rows import dict_row

        cols = list(values.keys())
        placeholders = ", ".join(self._placeholder(c) for c in cols)
        col_list = ", ".join(self._sql_name(c) for c in cols)
        query = f'INSERT INTO {table} ({col_list}) VALUES ({placeholders}) RETURNING "{pk_col}"'
        query = self._convert_placeholders(query)
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, values)
            row = await cur.fetchone()
            return row[pk_col] if row else None

    def for_update_clause(self) -> str:
        """Return FOR UPDATE clause for row locking."""
        return " FOR UPDATE"
