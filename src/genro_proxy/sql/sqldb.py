# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Async database manager with adapter pattern, contextvars for connection isolation."""

from __future__ import annotations

import importlib
import pkgutil
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from .adapters import DbAdapter, get_adapter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from .table import Table

# Connection context variable - each async task gets its own connection
_current_conn: ContextVar[Any] = ContextVar("db_conn", default=None)


class SqlDb:
    """Async database manager with per-request connection isolation.

    Uses contextvars to provide each request/task with its own database connection,
    ensuring proper transaction isolation in concurrent environments.

    Supports multiple database types via adapters:
    - SQLite: "/path/to/db.sqlite" or "sqlite:/path/to/db"
    - PostgreSQL: "postgresql://user:pass@host/db"

    Features:
    - Per-request connection via contextvars (no shared state)
    - Table class registration via add_table() or discover()
    - Table access via table(name)
    - Schema creation and verification
    - Encryption key access via parent.encryption_key

    Connection model:
    - connection(): Context manager that acquires connection, commits/rollbacks, releases
    - conn property: Returns current context's connection (raises if none active)
    - shutdown(): Closes pool (application shutdown only)

    Usage:
        db = SqlDb("/data/service.db", parent=proxy)

        # For schema setup
        async with db.connection():
            db.discover("genro_proxy.entities")
            await db.check_structure()

        # For transactions (automatic commit/rollback)
        async with db.connection():
            tenant = await db.table('tenants').record(where={"id": "acme"})
            await db.table('tenants').update({"active": False}, where={"id": "acme"})
        # COMMIT on success, ROLLBACK on exception

        # Application shutdown
        await db.shutdown()
    """

    def __init__(self, connection_string: str, parent: Any = None):
        """Initialize database manager.

        Args:
            connection_string: Database connection string.
            parent: Parent object (e.g., proxy) that provides encryption_key.
        """
        self.connection_string = connection_string
        self.parent = parent
        self.adapter: DbAdapter = get_adapter(connection_string)
        self.tables: dict[str, Table] = {}

    @property
    def encryption_key(self) -> bytes | None:
        """Get encryption key from parent. Returns None if not configured."""
        if self.parent is None:
            return None
        return getattr(self.parent, "encryption_key", None)

    @property
    def conn(self) -> Any:
        """Get current connection from context.

        Returns:
            Active database connection for this context.

        Raises:
            RuntimeError: If no connection is active (not inside connection() context).
        """
        c = _current_conn.get()
        if c is None:
            raise RuntimeError("No active connection. Use 'async with db.connection():'")
        return c

    # -------------------------------------------------------------------------
    # Connection management
    # -------------------------------------------------------------------------

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[SqlDb]:
        """Context manager for per-request connection with transaction.

        Acquires a connection from the adapter, sets it in contextvars,
        and handles commit/rollback on exit.

        Usage:
            async with db.connection():
                await db.table('items').insert({"id": "1", "name": "Test"})
                await db.table('items').update({"name": "Updated"}, where={"id": "1"})
            # COMMIT automatic

            async with db.connection():
                await db.table('items').insert({"id": "2", "name": "Test"})
                raise ValueError("Ops")  # ROLLBACK automatic
        """
        conn = await self.adapter.acquire()
        token = _current_conn.set(conn)
        try:
            yield self
            await self.adapter.commit(conn)
        except Exception:
            await self.adapter.rollback(conn)
            raise
        finally:
            _current_conn.reset(token)
            await self.adapter.release(conn)

    async def shutdown(self) -> None:
        """Close connection pool (application shutdown)."""
        await self.adapter.shutdown()

    # -------------------------------------------------------------------------
    # Table management
    # -------------------------------------------------------------------------

    def add_table(self, table_class: type[Table]) -> Table:
        """Register and instantiate a table class.

        Args:
            table_class: Table manager class (must have name attribute).

        Returns:
            The instantiated table.
        """
        if not hasattr(table_class, "name") or not table_class.name:
            raise ValueError(f"Table class {table_class.__name__} must define 'name'")

        instance = table_class(self)
        self.tables[instance.name] = instance
        return instance

    def discover(self, *packages: str) -> list[Table]:
        """Auto-discover and register Table classes from entity packages.

        Scans each package for sub-packages containing table.py modules,
        then registers any Table subclass found. When multiple classes have
        the same table name, the most derived class (per MRO) is used.

        Args:
            *packages: Package paths (e.g., "genro_proxy.entities", "myproxy.entities")

        Returns:
            List of registered table instances.

        Example:
            db.discover("genro_proxy.entities")
            # Registers: InstanceTable, TenantsTable, AccountsTable, etc.

            db.discover("genro_proxy.entities", "myproxy.entities")
            # Registers tables from both packages
            # If myproxy extends TenantsTable, the derived version is used
        """
        # Phase 1: Collect all table classes from all packages
        all_classes: list[type[Table]] = []
        for package_path in packages:
            all_classes.extend(self._find_table_classes(package_path))

        # Phase 2: For each table name, keep only the most derived class
        by_name: dict[str, type[Table]] = {}
        for table_class in all_classes:
            name = table_class.name
            existing = by_name.get(name)
            if existing is None:
                by_name[name] = table_class
            elif issubclass(table_class, existing):
                # New class is more derived, replace
                by_name[name] = table_class
            # else: existing is same or more derived, keep it

        # Phase 3: Register or replace with more derived classes
        registered: list[Table] = []
        for table_class in by_name.values():
            name = table_class.name
            existing = self.tables.get(name)
            if existing is None:
                # New table
                registered.append(self.add_table(table_class))
            elif table_class is not type(existing) and issubclass(table_class, type(existing)):
                # New class is strictly more derived, replace existing
                self.tables[name] = table_class(self)
                registered.append(self.tables[name])
            # else: existing is same or more derived, keep it
        return registered

    def table(self, name: str) -> Table:
        """Get table instance by name.

        Args:
            name: Table name.

        Returns:
            Table instance.

        Raises:
            ValueError: If table not registered.
        """
        if name not in self.tables:
            raise ValueError(f"Table '{name}' not registered. Use add_table() first.")
        return self.tables[name]

    async def check_structure(self) -> None:
        """Create all registered tables if they don't exist."""
        for table in self.tables.values():
            await table.create_schema()

    # -------------------------------------------------------------------------
    # Direct query access (uses current connection from context)
    # -------------------------------------------------------------------------

    async def execute(self, query: str, params: dict[str, Any] | None = None) -> int:
        """Execute raw query, return affected row count."""
        return await self.adapter.execute(self.conn, query, params)

    async def execute_many(self, query: str, params_list: Sequence[dict[str, Any]]) -> int:
        """Execute query multiple times with different params (batch insert)."""
        return await self.adapter.execute_many(self.conn, query, params_list)

    async def fetch_one(
        self, query: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Execute raw query, return single row."""
        return await self.adapter.fetch_one(self.conn, query, params)

    async def fetch_all(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute raw query, return all rows."""
        return await self.adapter.fetch_all(self.conn, query, params)

    async def execute_script(self, script: str) -> None:
        """Execute multiple statements (for schema creation)."""
        await self.adapter.execute_script(self.conn, script)

    async def commit(self) -> None:
        """Commit current transaction."""
        await self.adapter.commit(self.conn)

    async def rollback(self) -> None:
        """Rollback current transaction."""
        await self.adapter.rollback(self.conn)

    # -------------------------------------------------------------------------
    # CRUD helpers (use current connection from context)
    # -------------------------------------------------------------------------

    def _sql_name(self, name: str) -> str:
        """Return quoted SQL identifier."""
        return self.adapter._sql_name(name)

    def _placeholder(self, name: str) -> str:
        """Return placeholder for named parameter."""
        return self.adapter._placeholder(name)

    async def insert(self, table: str, values: dict[str, Any]) -> int:
        """Insert a row, return rowcount."""
        cols = list(values.keys())
        placeholders = ", ".join(self._placeholder(c) for c in cols)
        col_list = ", ".join(self._sql_name(c) for c in cols)
        query = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        return await self.execute(query, values)

    async def insert_returning_id(
        self, table: str, values: dict[str, Any], pk_col: str = "id"
    ) -> Any:
        """Insert a row and return the generated primary key."""
        return await self.adapter.insert_returning_id(self.conn, table, values, pk_col)

    async def select(
        self,
        table: str,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows, return list of dicts."""
        cols_sql = ", ".join(self._sql_name(c) for c in columns) if columns else "*"
        query = f"SELECT {cols_sql} FROM {table}"

        params: dict[str, Any] = {}
        if where:
            conditions = [f"{self._sql_name(k)} = {self._placeholder(k)}" for k in where]
            query += " WHERE " + " AND ".join(conditions)
            params.update(where)

        if order_by:
            query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {limit}"

        return await self.fetch_all(query, params)

    async def select_one(
        self,
        table: str,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Select single row, return dict or None."""
        results = await self.select(table, columns, where, limit=1)
        return results[0] if results else None

    async def update(self, table: str, values: dict[str, Any], where: dict[str, Any]) -> int:
        """Update rows, return rowcount."""
        set_parts = [f"{self._sql_name(k)} = {self._placeholder('val_' + k)}" for k in values]
        where_parts = [f"{self._sql_name(k)} = {self._placeholder('whr_' + k)}" for k in where]

        query = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"

        params = {f"val_{k}": v for k, v in values.items()}
        params.update({f"whr_{k}": v for k, v in where.items()})

        return await self.execute(query, params)

    async def delete(self, table: str, where: dict[str, Any]) -> int:
        """Delete rows, return rowcount."""
        where_parts = [f"{self._sql_name(k)} = {self._placeholder(k)}" for k in where]
        query = f"DELETE FROM {table} WHERE {' AND '.join(where_parts)}"
        return await self.execute(query, where)

    async def exists(self, table: str, where: dict[str, Any]) -> bool:
        """Check if row exists."""
        conditions = [f"{self._sql_name(k)} = {self._placeholder(k)}" for k in where]
        query = f"SELECT 1 FROM {table} WHERE {' AND '.join(conditions)} LIMIT 1"
        result = await self.fetch_one(query, where)
        return result is not None

    async def count(self, table: str, where: dict[str, Any] | None = None) -> int:
        """Count rows in table."""
        query = f"SELECT COUNT(*) as cnt FROM {table}"
        params: dict[str, Any] = {}

        if where:
            conditions = [f"{self._sql_name(k)} = {self._placeholder(k)}" for k in where]
            query += " WHERE " + " AND ".join(conditions)
            params.update(where)

        result = await self.fetch_one(query, params)
        return result["cnt"] if result else 0

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _find_table_classes(self, package_path: str) -> list[type[Table]]:
        """Find all Table classes in a package's entity sub-packages."""
        from .table import Table

        result: list[type[Table]] = []
        try:
            package = importlib.import_module(package_path)
        except ImportError:
            return result

        package_dir = getattr(package, "__path__", None)
        if not package_dir:
            return result

        for _, name, is_pkg in pkgutil.iter_modules(package_dir):
            if not is_pkg:
                continue
            module_path = f"{package_path}.{name}.table"
            try:
                module = importlib.import_module(module_path)
            except ImportError:
                continue

            for attr_name in dir(module):
                if attr_name.startswith("_"):
                    continue
                obj = getattr(module, attr_name)
                if not isinstance(obj, type):
                    continue
                if not issubclass(obj, Table):
                    continue
                if obj is Table:
                    continue
                if not hasattr(obj, "name") or not obj.name:
                    continue
                result.append(obj)

        return result


__all__ = ["SqlDb"]
