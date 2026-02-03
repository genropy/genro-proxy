# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Database adapters for SQLite and PostgreSQL with per-request connections.

This package provides async database adapters with a unified interface
for executing queries and transaction management. Each request gets
its own isolated connection via contextvars in SqlDb.

Components:
    DbAdapter: Abstract base class defining the adapter interface.
    SqliteAdapter: SQLite adapter using aiosqlite with per-request connections.
    PostgresAdapter: PostgreSQL adapter using psycopg3 with connection pooling.
    get_adapter: Factory function to create adapters from connection strings.

Connection Model:
    Adapters provide connection management, SqlDb uses contextvars for isolation:

    - acquire(): Returns a new connection (from pool or new file handle)
    - release(conn): Returns connection to pool or closes it
    - commit(conn): COMMIT transaction on connection
    - rollback(conn): ROLLBACK transaction on connection
    - shutdown(): Closes pool (PostgreSQL) or no-op (SQLite)

    This model ensures:
    - Each async task gets its own connection via contextvars
    - No shared state between concurrent requests
    - Proper transaction isolation

Example:
    Usage via SqlDb (recommended)::

        from genro_proxy.sql import SqlDb

        db = SqlDb("/data/app.db")  # or "postgresql://..."
        async with db.connection():
            await db.execute("INSERT INTO users (id) VALUES (:id)", {"id": "u1"})
            await db.execute("UPDATE users SET active = 1 WHERE id = :id", {"id": "u1"})
        # COMMIT on success, ROLLBACK on exception

    Application shutdown::

        await db.shutdown()  # Close the pool (PostgreSQL)

Note:
    PostgreSQL requires psycopg: `pip install genro-proxy[postgresql]`.
"""

from .base import DbAdapter
from .sqlite import SqliteAdapter

__all__ = ["DbAdapter", "SqliteAdapter", "ADAPTERS", "get_adapter"]

# Adapter registry
ADAPTERS: dict[str, type[DbAdapter]] = {
    "sqlite": SqliteAdapter,
}


def get_adapter(connection_string: str) -> DbAdapter:
    """Create database adapter from connection string.

    Connection string formats:
        - "/path/to/db.sqlite" → SQLite (absolute path)
        - "./path/to/db.sqlite" → SQLite (relative path)
        - "sqlite:/path/to/db.sqlite" → SQLite
        - "sqlite::memory:" → SQLite in-memory
        - "postgresql://user:pass@host:port/dbname" → PostgreSQL

    Args:
        connection_string: Database connection string.

    Returns:
        Configured DbAdapter instance.

    Raises:
        ValueError: If connection string format is invalid.
        ImportError: If postgresql requested but psycopg not installed.
    """
    # Handle bare paths as SQLite (backward compatibility)
    # Accept absolute paths (/path), relative paths (./path), and :memory:
    if (
        connection_string.startswith("/")
        or connection_string.startswith("./")
        or connection_string == ":memory:"
    ):
        return SqliteAdapter(connection_string)

    # Parse "type:connection_info" format
    if ":" not in connection_string:
        raise ValueError(
            f"Invalid connection string: '{connection_string}'. "
            "Expected 'type:connection_info' or path (absolute or relative)."
        )

    db_type, connection_info = connection_string.split(":", 1)
    db_type = db_type.lower()

    if db_type == "sqlite":
        return SqliteAdapter(connection_info)

    if db_type in ("postgresql", "postgres"):
        # Lazy import to avoid ImportError when psycopg not installed
        from .postgresql import PostgresAdapter

        # Register if not already
        if "postgresql" not in ADAPTERS:
            ADAPTERS["postgresql"] = PostgresAdapter
            ADAPTERS["postgres"] = PostgresAdapter

        # Reconstruct full DSN if needed
        if not connection_info.startswith("postgresql://"):
            dsn = f"postgresql:{connection_info}"
        else:
            dsn = connection_info
        return PostgresAdapter(dsn)

    raise ValueError(f"Unknown database type: '{db_type}'. Supported: sqlite, postgresql")
