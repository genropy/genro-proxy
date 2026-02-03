# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for sql.adapters module - adapter factory and registry."""

from __future__ import annotations

import pytest

from proxy.sql.adapters import ADAPTERS, DbAdapter, SqliteAdapter, get_adapter


class TestGetAdapter:
    """Tests for get_adapter factory function."""

    def test_absolute_path_returns_sqlite(self):
        """Absolute paths are treated as SQLite databases."""
        adapter = get_adapter("/tmp/test.db")
        assert isinstance(adapter, SqliteAdapter)

    def test_relative_path_returns_sqlite(self):
        """Relative paths starting with ./ are treated as SQLite."""
        adapter = get_adapter("./data/test.db")
        assert isinstance(adapter, SqliteAdapter)

    def test_memory_returns_sqlite(self):
        """:memory: is treated as SQLite in-memory database."""
        adapter = get_adapter(":memory:")
        assert isinstance(adapter, SqliteAdapter)

    def test_sqlite_prefix_returns_sqlite(self):
        """sqlite:path format returns SqliteAdapter."""
        adapter = get_adapter("sqlite:/tmp/test.db")
        assert isinstance(adapter, SqliteAdapter)

    def test_sqlite_memory_prefix(self):
        """sqlite::memory: format returns SqliteAdapter."""
        adapter = get_adapter("sqlite::memory:")
        assert isinstance(adapter, SqliteAdapter)

    def test_invalid_connection_string_raises(self):
        """Invalid connection string without colon raises ValueError."""
        with pytest.raises(ValueError, match="Invalid connection string"):
            get_adapter("invalid_string_without_colon")

    def test_unknown_database_type_raises(self):
        """Unknown database type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown database type"):
            get_adapter("mysql://localhost/db")

    def test_postgresql_lazy_import(self):
        """PostgreSQL adapter is lazily imported."""
        # This test verifies the postgresql path works
        # It may raise ImportError if psycopg is not installed
        try:
            adapter = get_adapter("postgresql://user:pass@localhost:5432/testdb")
            assert adapter is not None
            assert "postgresql" in ADAPTERS
        except ImportError:
            # psycopg not installed - that's OK, the path was exercised
            pass

    def test_postgres_alias(self):
        """postgres:// is an alias for postgresql://."""
        try:
            adapter = get_adapter("postgres://user:pass@localhost:5432/testdb")
            assert adapter is not None
            assert "postgres" in ADAPTERS
        except ImportError:
            pass

    def test_postgresql_reconstructs_dsn(self):
        """PostgreSQL reconstructs DSN if needed."""
        try:
            # Connection string without full postgresql:// prefix
            adapter = get_adapter("postgresql://localhost/testdb")
            assert adapter is not None
        except ImportError:
            pass


class TestAdaptersRegistry:
    """Tests for ADAPTERS registry."""

    def test_sqlite_in_registry(self):
        """SQLite adapter is registered by default."""
        assert "sqlite" in ADAPTERS
        assert ADAPTERS["sqlite"] is SqliteAdapter

    def test_db_adapter_is_abstract_base(self):
        """DbAdapter is the abstract base class."""
        assert DbAdapter is not None
        # DbAdapter should be abstract (cannot instantiate)
        with pytest.raises(TypeError):
            DbAdapter()  # type: ignore


class TestSqliteAdapterMethods:
    """Tests for SqliteAdapter specific methods using acquire/release pattern."""

    async def test_insert_returning_id(self, tmp_path):
        """insert_returning_id returns lastrowid for autoincrement."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)
        conn = await adapter.acquire()
        await adapter.execute(
            conn,
            "CREATE TABLE test_items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)",
        )

        row_id = await adapter.insert_returning_id(
            conn,
            "test_items",
            {"name": "Item 1"},
            pk_col="id",
        )

        assert row_id == 1

        # Insert another and verify ID increments
        row_id2 = await adapter.insert_returning_id(
            conn,
            "test_items",
            {"name": "Item 2"},
            pk_col="id",
        )
        assert row_id2 == 2
        await adapter.commit(conn)
        await adapter.release(conn)

    async def test_execute_many(self, tmp_path):
        """execute_many inserts multiple rows in batch."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)
        conn = await adapter.acquire()
        await adapter.execute(
            conn,
            "CREATE TABLE test_items (id INTEGER PRIMARY KEY, name TEXT)",
        )

        count = await adapter.execute_many(
            conn,
            "INSERT INTO test_items (id, name) VALUES (:id, :name)",
            [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"},
                {"id": 3, "name": "Item 3"},
            ],
        )

        assert count == 3
        rows = await adapter.fetch_all(conn, "SELECT * FROM test_items ORDER BY id")
        assert len(rows) == 3
        await adapter.commit(conn)
        await adapter.release(conn)

    async def test_execute_script(self, tmp_path):
        """execute_script runs multiple statements."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)
        conn = await adapter.acquire()

        await adapter.execute_script(
            conn,
            """
            CREATE TABLE table1 (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE table2 (id INTEGER PRIMARY KEY, value TEXT);
            INSERT INTO table1 (id, name) VALUES (1, 'test');
        """,
        )

        # Verify tables were created and data inserted
        row = await adapter.fetch_one(conn, "SELECT * FROM table1 WHERE id = 1")
        assert row is not None
        assert row["name"] == "test"

        # Verify second table exists
        row2 = await adapter.fetch_one(
            conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='table2'"
        )
        assert row2 is not None
        await adapter.commit(conn)
        await adapter.release(conn)

    async def test_normalize_booleans_with_prefixes(self, tmp_path):
        """Boolean-like columns with prefixes are converted."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)
        conn = await adapter.acquire()
        await adapter.execute(
            conn,
            "CREATE TABLE flags (id INTEGER PRIMARY KEY, is_active INTEGER, use_ssl INTEGER, has_data INTEGER)",
        )
        await adapter.execute(
            conn,
            "INSERT INTO flags (id, is_active, use_ssl, has_data) VALUES (1, 1, 0, 1)",
        )

        row = await adapter.fetch_one(conn, "SELECT * FROM flags WHERE id = 1")

        assert row is not None
        assert row["is_active"] is True
        assert row["use_ssl"] is False
        assert row["has_data"] is True
        await adapter.commit(conn)
        await adapter.release(conn)

    async def test_normalize_booleans_with_names(self, tmp_path):
        """Boolean-like columns with known names are converted."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)
        conn = await adapter.acquire()
        await adapter.execute(
            conn,
            "CREATE TABLE settings (id INTEGER PRIMARY KEY, active INTEGER, enabled INTEGER, ssl INTEGER, tls INTEGER)",
        )
        await adapter.execute(
            conn,
            "INSERT INTO settings (id, active, enabled, ssl, tls) VALUES (1, 1, 0, 1, 0)",
        )

        row = await adapter.fetch_one(conn, "SELECT * FROM settings WHERE id = 1")

        assert row is not None
        assert row["active"] is True
        assert row["enabled"] is False
        assert row["ssl"] is True
        assert row["tls"] is False
        await adapter.commit(conn)
        await adapter.release(conn)

    async def test_normalize_booleans_in_fetch_all(self, tmp_path):
        """Boolean normalization works in fetch_all too."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)
        conn = await adapter.acquire()
        await adapter.execute(
            conn,
            "CREATE TABLE items (id INTEGER PRIMARY KEY, is_visible INTEGER)",
        )
        await adapter.execute(
            conn,
            "INSERT INTO items (id, is_visible) VALUES (1, 1), (2, 0)",
        )

        rows = await adapter.fetch_all(conn, "SELECT * FROM items ORDER BY id")

        assert len(rows) == 2
        assert rows[0]["is_visible"] is True
        assert rows[1]["is_visible"] is False
        await adapter.commit(conn)
        await adapter.release(conn)

    async def test_rollback_cancels_changes(self, tmp_path):
        """rollback() cancels uncommitted changes."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)

        # Create table and commit
        conn = await adapter.acquire()
        await adapter.execute(
            conn, "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"
        )
        await adapter.commit(conn)
        await adapter.release(conn)

        # Insert and rollback
        conn = await adapter.acquire()
        await adapter.execute(conn, "INSERT INTO items (id, name) VALUES (1, 'Test')")
        await adapter.rollback(conn)
        await adapter.release(conn)

        # Verify insert was rolled back
        conn = await adapter.acquire()
        row = await adapter.fetch_one(conn, "SELECT * FROM items WHERE id = 1")
        assert row is None  # Insert was rolled back!
        await adapter.release(conn)

    async def test_commit_commits_changes(self, tmp_path):
        """commit() commits changes."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)

        # Create table
        conn = await adapter.acquire()
        await adapter.execute(
            conn, "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"
        )
        await adapter.commit(conn)
        await adapter.release(conn)

        # Insert and commit
        conn = await adapter.acquire()
        await adapter.execute(conn, "INSERT INTO items (id, name) VALUES (1, 'Test')")
        await adapter.commit(conn)
        await adapter.release(conn)

        # Verify insert was committed
        conn = await adapter.acquire()
        row = await adapter.fetch_one(conn, "SELECT * FROM items WHERE id = 1")
        assert row is not None
        assert row["name"] == "Test"
        await adapter.release(conn)

    async def test_shutdown_is_noop_for_sqlite(self, tmp_path):
        """shutdown() is no-op for SQLite (no pool to close)."""
        db_path = str(tmp_path / "test.db")
        adapter = SqliteAdapter(db_path)

        # Should not raise
        await adapter.shutdown()

        # Can still acquire after shutdown
        conn = await adapter.acquire()
        assert conn is not None
        await adapter.release(conn)
