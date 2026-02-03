# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Async SQL layer with adapter pattern and transaction support.

This package provides a lightweight ORM-like interface for SQLite and
PostgreSQL with table class registration, async operations, and proper
transaction management.

Components:
    SqlDb: Database manager with table registry, schema management, and
           transaction context manager.
    Table: Base class for table definitions with Columns schema.
    DbAdapter: Abstract base for SQLite/PostgreSQL adapters.
    Column, Columns: Schema definition with types and constraints.

Transaction Model:
    The SQL layer uses a connection-per-transaction model:

    - connect(): Acquires connection and begins transaction (implicit BEGIN)
    - close(): COMMIT and releases connection
    - rollback(): ROLLBACK and releases connection
    - shutdown(): Closes pool/file (application shutdown only)
    - connection(): Context manager for automatic commit/rollback

    This ensures atomicity: multiple operations within a transaction either
    all succeed (COMMIT) or all fail (ROLLBACK).

Example:
    Using SqlDb with transaction context manager (recommended)::

        from proxy.sql import SqlDb, Table, String, Integer

        class UsersTable(Table):
            name = "users"
            def configure(self):
                self.columns.column("id", String, unique=True)
                self.columns.column("name", String)
                self.columns.column("active", Integer, default=1)

        db = SqlDb("/data/app.db")

        # Schema setup (single transaction)
        await db.connect()
        db.add_table(UsersTable)
        await db.check_structure()
        await db.close()  # COMMIT schema

        # Data operations with automatic commit/rollback
        async with db.connection():
            user = await db.table("users").select_one(where={"id": "u1"})
            await db.table("users").update({"active": 0}, where={"id": "u1"})
        # COMMIT on success, ROLLBACK on exception

        # Application shutdown
        await db.shutdown()

    Using adapter directly::

        adapter = get_adapter("postgresql://user:pass@host/db")
        await adapter.connect()
        try:
            await adapter.execute("INSERT INTO users (id) VALUES (:id)", {"id": "u1"})
            await adapter.execute("UPDATE users SET active = 1 WHERE id = :id", {"id": "u1"})
            await adapter.close()  # COMMIT
        except Exception:
            await adapter.rollback()  # ROLLBACK
            raise

Note:
    Connection strings: "/path/to/db.sqlite" (SQLite), "sqlite::memory:"
    (in-memory), "postgresql://user:pass@host:port/dbname" (PostgreSQL).
"""

from .adapters import DbAdapter, get_adapter
from .column import Boolean, Column, Columns, Integer, String, Timestamp
from .query import Query, WhereBuilder
from .sqldb import SqlDb
from .table import RecordDuplicateError, RecordNotFoundError, Table

__all__ = [
    # Main classes
    "SqlDb",
    "Table",
    "Query",
    "WhereBuilder",
    # Exceptions
    "RecordNotFoundError",
    "RecordDuplicateError",
    # Column definitions
    "Column",
    "Columns",
    "Integer",
    "String",
    "Boolean",
    "Timestamp",
    # Adapters
    "DbAdapter",
    "get_adapter",
    # Backward compatibility
    "create_adapter",
]

# Backward compatibility alias
create_adapter = get_adapter
