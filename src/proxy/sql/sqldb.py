# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Async database manager with adapter pattern and table registration."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING, Any

from .adapters import DbAdapter, get_adapter

if TYPE_CHECKING:
    from .table import Table


class SqlDb:
    """Async database manager with adapter pattern.

    Supports multiple database types via adapters:
    - SQLite: "/path/to/db.sqlite" or "sqlite:/path/to/db"
    - PostgreSQL: "postgresql://user:pass@host/db"

    Features:
    - Table class registration via add_table() or discover()
    - Table access via table(name)
    - Schema creation and verification
    - CRUD operations via adapter
    - Encryption key access via parent.encryption_key

    Usage:
        db = SqlDb("/data/service.db", parent=proxy)
        await db.connect()

        db.discover("proxy.entities")
        await db.check_structure()

        tenant = await db.table('tenants').select_one(where={"id": "acme"})

        await db.close()
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

    # -------------------------------------------------------------------------
    # Connection management
    # -------------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to database."""
        await self.adapter.connect()

    async def close(self) -> None:
        """Close database connection."""
        await self.adapter.close()

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
        then registers any Table subclass found.

        Args:
            *packages: Package paths (e.g., "proxy.entities", "myproxy.entities")

        Returns:
            List of registered table instances.

        Example:
            db.discover("proxy.entities")
            # Registers: InstanceTable, TenantsTable, AccountsTable, etc.

            db.discover("proxy.entities", "myproxy.entities")
            # Registers tables from both packages
        """
        registered: list[Table] = []
        for package_path in packages:
            for table_class in self._find_table_classes(package_path):
                if table_class.name not in self.tables:
                    registered.append(self.add_table(table_class))
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
    # Direct adapter access
    # -------------------------------------------------------------------------

    async def execute(self, query: str, params: dict[str, Any] | None = None) -> int:
        """Execute raw query, return affected row count."""
        return await self.adapter.execute(query, params)

    async def fetch_one(
        self, query: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Execute raw query, return single row."""
        return await self.adapter.fetch_one(query, params)

    async def fetch_all(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute raw query, return all rows."""
        return await self.adapter.fetch_all(query, params)

    async def commit(self) -> None:
        """Commit transaction."""
        await self.adapter.commit()

    async def rollback(self) -> None:
        """Rollback transaction."""
        await self.adapter.rollback()

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
