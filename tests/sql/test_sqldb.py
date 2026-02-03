# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for sql.sqldb module - SqlDb database manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from genro_proxy.sql import SqlDb
from genro_proxy.sql.table import Table


class DummyTable(Table):
    """Minimal table for testing."""

    name = "dummy"
    columns = []


class TableWithoutName(Table):
    """Table without name attribute for error testing."""

    columns = []


class TestSqlDbInit:
    """Tests for SqlDb initialization."""

    def test_init_creates_adapter(self):
        """SqlDb creates adapter from connection string."""
        db = SqlDb(":memory:")
        assert db.adapter is not None
        assert db.tables == {}

    def test_init_with_parent(self):
        """SqlDb stores parent reference."""
        parent = MagicMock()
        db = SqlDb(":memory:", parent=parent)
        assert db.parent is parent


class TestSqlDbEncryptionKey:
    """Tests for encryption_key property."""

    def test_encryption_key_none_without_parent(self):
        """encryption_key returns None when no parent."""
        db = SqlDb(":memory:")
        assert db.encryption_key is None

    def test_encryption_key_from_parent(self):
        """encryption_key is fetched from parent."""
        parent = MagicMock()
        parent.encryption_key = b"secret_key_32_bytes_long_12345"
        db = SqlDb(":memory:", parent=parent)
        assert db.encryption_key == b"secret_key_32_bytes_long_12345"

    def test_encryption_key_none_if_parent_has_no_attr(self):
        """encryption_key returns None if parent lacks attribute."""
        parent = object()  # No encryption_key attribute
        db = SqlDb(":memory:", parent=parent)
        assert db.encryption_key is None


class TestSqlDbTableManagement:
    """Tests for add_table and table methods."""

    def test_add_table_registers_table(self):
        """add_table registers and instantiates table."""
        db = SqlDb(":memory:")
        table = db.add_table(DummyTable)
        assert "dummy" in db.tables
        assert isinstance(table, DummyTable)

    def test_add_table_without_name_raises(self):
        """add_table raises if table has no name."""
        db = SqlDb(":memory:")
        # Remove name attribute for test
        TableWithoutName.name = ""
        with pytest.raises(ValueError, match="must define 'name'"):
            db.add_table(TableWithoutName)

    def test_table_returns_registered_table(self):
        """table() returns registered table instance."""
        db = SqlDb(":memory:")
        db.add_table(DummyTable)
        table = db.table("dummy")
        assert isinstance(table, DummyTable)

    def test_table_raises_for_unknown(self):
        """table() raises ValueError for unregistered table."""
        db = SqlDb(":memory:")
        with pytest.raises(ValueError, match="not registered"):
            db.table("nonexistent")


class TestSqlDbConnection:
    """Tests for connection context manager."""

    async def test_connection_provides_db(self):
        """connection() yields the SqlDb instance."""
        db = SqlDb(":memory:")
        async with db.connection() as yielded:
            assert yielded is db

    async def test_connection_enables_queries(self):
        """Inside connection(), queries can be executed."""
        db = SqlDb(":memory:")
        async with db.connection():
            await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            await db.execute("INSERT INTO test (id, name) VALUES (1, 'Test')")
            result = await db.fetch_one("SELECT * FROM test WHERE id = 1")
            assert result["name"] == "Test"

    async def test_connection_commits_on_success(self, tmp_path):
        """connection() commits on successful exit."""
        db_path = str(tmp_path / "test.db")
        db = SqlDb(db_path)
        async with db.connection():
            await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            await db.execute("INSERT INTO test (id, name) VALUES (1, 'Test')")

        # In new connection, data should be there
        async with db.connection():
            result = await db.fetch_one("SELECT * FROM test WHERE id = 1")
            assert result is not None
            assert result["name"] == "Test"

    async def test_connection_rollbacks_on_exception(self, tmp_path):
        """connection() rollbacks on exception."""
        db_path = str(tmp_path / "test.db")
        db = SqlDb(db_path)
        async with db.connection():
            await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")

        # Insert and raise - should rollback
        with pytest.raises(ValueError):
            async with db.connection():
                await db.execute("INSERT INTO test (id, name) VALUES (1, 'Test')")
                raise ValueError("Test error")

        # In new connection, data should NOT be there
        async with db.connection():
            result = await db.fetch_one("SELECT * FROM test WHERE id = 1")
            assert result is None

    async def test_conn_property_raises_outside_connection(self):
        """conn property raises RuntimeError outside connection context."""
        db = SqlDb(":memory:")
        with pytest.raises(RuntimeError, match="No active connection"):
            _ = db.conn

    async def test_conn_property_works_inside_connection(self):
        """conn property returns connection inside context."""
        db = SqlDb(":memory:")
        async with db.connection():
            assert db.conn is not None


class TestSqlDbAsyncMethods:
    """Tests for async database methods within connection context."""

    async def test_execute_works_in_connection(self):
        """execute() works within connection context."""
        db = SqlDb(":memory:")
        async with db.connection():
            await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val INTEGER)")
            result = await db.execute("INSERT INTO test (id, val) VALUES (1, 42)")
            assert result == 1  # rowcount

    async def test_fetch_one_works_in_connection(self):
        """fetch_one() works within connection context."""
        db = SqlDb(":memory:")
        async with db.connection():
            await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val INTEGER)")
            await db.execute("INSERT INTO test (id, val) VALUES (1, 42)")
            result = await db.fetch_one("SELECT * FROM test WHERE id = :id", {"id": 1})
            assert result == {"id": 1, "val": 42}

    async def test_fetch_all_works_in_connection(self):
        """fetch_all() works within connection context."""
        db = SqlDb(":memory:")
        async with db.connection():
            await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val INTEGER)")
            await db.execute("INSERT INTO test (id, val) VALUES (1, 10)")
            await db.execute("INSERT INTO test (id, val) VALUES (2, 20)")
            results = await db.fetch_all("SELECT * FROM test ORDER BY id")
            assert len(results) == 2
            assert results[0]["val"] == 10
            assert results[1]["val"] == 20


class TestSqlDbCheckStructure:
    """Tests for check_structure method."""

    async def test_check_structure_creates_all_tables(self):
        """check_structure() calls create_schema on all tables."""
        db = SqlDb(":memory:")
        db.add_table(DummyTable)

        # Mock the table's create_schema
        db.tables["dummy"].create_schema = AsyncMock()

        async with db.connection():
            await db.check_structure()

        db.tables["dummy"].create_schema.assert_called_once()


class TestSqlDbDiscover:
    """Tests for discover method."""

    def test_discover_finds_entity_tables(self):
        """discover() finds and registers Table classes from entity packages."""
        db = SqlDb(":memory:")
        tables = db.discover("genro_proxy.entities")

        # Should find all 5 base entities
        assert len(tables) >= 5
        assert "instance" in db.tables
        assert "tenants" in db.tables
        assert "accounts" in db.tables
        assert "storages" in db.tables
        assert "command_log" in db.tables

    def test_discover_returns_registered_tables(self):
        """discover() returns list of registered table instances."""
        db = SqlDb(":memory:")
        tables = db.discover("genro_proxy.entities")

        for table in tables:
            assert isinstance(table, Table)
            assert table.name in db.tables

    def test_discover_skips_already_registered(self):
        """discover() skips tables already registered."""
        db = SqlDb(":memory:")

        # First discover
        tables1 = db.discover("genro_proxy.entities")
        count1 = len(tables1)

        # Second discover should return empty (all already registered)
        tables2 = db.discover("genro_proxy.entities")
        assert len(tables2) == 0

        # Total tables unchanged
        assert len(db.tables) == count1

    def test_discover_multiple_packages(self):
        """discover() can scan multiple packages."""
        db = SqlDb(":memory:")
        tables = db.discover("genro_proxy.entities")

        # All tables registered from genro_proxy.entities
        assert "instance" in db.tables
        assert "tenants" in db.tables

    def test_discover_invalid_package_ignored(self):
        """discover() ignores non-existent packages."""
        db = SqlDb(":memory:")
        tables = db.discover("nonexistent.package")
        assert tables == []

    def test_discover_empty_package(self):
        """discover() handles packages with no table modules."""
        db = SqlDb(":memory:")
        # proxy.sql has no entity sub-packages with table.py
        tables = db.discover("genro_proxy.sql")
        assert tables == []
