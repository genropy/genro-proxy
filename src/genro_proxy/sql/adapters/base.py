# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Base adapter class for async database backends with CRUD helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


class DbAdapter(ABC):
    """Abstract base class for async database adapters with CRUD helpers.

    Provides a unified interface for SQLite and PostgreSQL with:
    - Connection management (acquire, release, shutdown)
    - Transaction control (commit, rollback on connection)
    - Raw query execution (execute, fetch_one, fetch_all)
    - CRUD helpers (insert, select, update, delete)

    Connection model:
    - acquire(): Returns a new connection (from pool or new file handle)
    - release(conn): Returns connection to pool or closes it
    - shutdown(): Closes connection pool (application shutdown only)

    Connections support commit/rollback for transaction control.
    SqlDb manages connection lifecycle via contextvars for per-request isolation.

    Subclasses must implement the abstract methods and set the placeholder
    attribute for parameter binding (`:name` for SQLite, `%(name)s` for PostgreSQL).
    """

    placeholder: str = ":name"  # Override in subclass

    def pk_column(self, name: str) -> str:
        """Return SQL definition for autoincrement primary key column."""
        return f'"{name}" INTEGER PRIMARY KEY'

    def for_update_clause(self) -> str:
        """Return FOR UPDATE clause if supported, empty string otherwise."""
        return ""

    @abstractmethod
    async def acquire(self) -> Any:
        """Acquire a new connection.

        For pooled adapters: gets connection from pool.
        For file-based adapters: opens new connection.

        Returns:
            Database connection object.
        """
        ...

    @abstractmethod
    async def release(self, conn: Any) -> None:
        """Release a connection.

        For pooled adapters: returns connection to pool.
        For file-based adapters: closes connection.
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Close connection pool (application shutdown).

        Called once at application shutdown to release all resources.
        For pooled adapters: closes the pool.
        For file-based adapters: no-op (connections are per-request).
        """
        ...

    # -------------------------------------------------------------------------
    # Connection-bound operations (require active connection from context)
    # -------------------------------------------------------------------------

    @abstractmethod
    async def execute(
        self, conn: Any, query: str, params: dict[str, Any] | None = None
    ) -> int:
        """Execute query on connection, return affected row count."""
        ...

    @abstractmethod
    async def execute_many(
        self, conn: Any, query: str, params_list: Sequence[dict[str, Any]]
    ) -> int:
        """Execute query multiple times with different params (batch insert)."""
        ...

    @abstractmethod
    async def fetch_one(
        self, conn: Any, query: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Execute query on connection, return single row as dict or None."""
        ...

    @abstractmethod
    async def fetch_all(
        self, conn: Any, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute query on connection, return all rows as list of dicts."""
        ...

    @abstractmethod
    async def execute_script(self, conn: Any, script: str) -> None:
        """Execute multiple statements on connection (for schema creation)."""
        ...

    @abstractmethod
    async def commit(self, conn: Any) -> None:
        """Commit transaction on connection."""
        ...

    @abstractmethod
    async def rollback(self, conn: Any) -> None:
        """Rollback transaction on connection."""
        ...

    @abstractmethod
    async def insert_returning_id(
        self, conn: Any, table: str, values: dict[str, Any], pk_col: str = "id"
    ) -> Any:
        """Insert a row and return the generated primary key."""
        ...

    # -------------------------------------------------------------------------
    # SQL Helpers
    # -------------------------------------------------------------------------

    def _sql_name(self, name: str) -> str:
        """Return quoted SQL identifier for column/table name."""
        return f'"{name}"'

    def _placeholder(self, name: str) -> str:
        """Return placeholder for named parameter."""
        return self.placeholder.replace("name", name)
