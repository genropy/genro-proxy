# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for StoragesTable schema and base operations."""

import pytest_asyncio

from proxy.entities.storage.table import StoragesTable
from proxy.sql import SqlDb


@pytest_asyncio.fixture
async def storage_table(sqlite_db: SqlDb) -> StoragesTable:
    """Create a StoragesTable with SQLite for testing."""
    table = StoragesTable(sqlite_db)
    await table.create_schema()
    return table


class TestCreateTableSql:
    """Tests for StoragesTable.create_table_sql() method."""

    async def test_includes_unique_constraint(self, storage_table: StoragesTable):
        """create_table_sql includes UNIQUE constraint on (tenant_id, name)."""
        sql = storage_table.create_table_sql()
        assert 'UNIQUE ("tenant_id", "name")' in sql


class TestSchema:
    """Tests for StoragesTable schema."""

    async def test_insert_generates_pk(self, storage_table: StoragesTable):
        """insert() generates pk via new_pkey_value()."""
        await storage_table.insert({
            "tenant_id": "t1",
            "name": "HOME",
            "protocol": "local",
        })

        storage = await storage_table.record(where={"tenant_id": "t1", "name": "HOME"})
        assert storage is not None
        assert storage["pk"] is not None
        assert len(storage["pk"]) > 10  # UUID format

    async def test_insert_with_config(self, storage_table: StoragesTable):
        """insert() stores JSON config (encrypted)."""
        config = {"base_path": "/data", "nested": {"a": 1}}
        await storage_table.insert({
            "tenant_id": "t1",
            "name": "HOME",
            "protocol": "local",
            "config": config,
        })

        storage = await storage_table.record(where={"tenant_id": "t1", "name": "HOME"})
        assert storage is not None
        assert storage["config"] == config


class TestGetStorageManager:
    """Tests for StoragesTable.get_storage_manager() method."""

    async def test_get_storage_manager_empty(self, storage_table: StoragesTable):
        """get_storage_manager returns manager with no storages."""
        manager = await storage_table.get_storage_manager("t1")

        assert manager is not None
        assert manager._mounts == {}

    async def test_get_storage_manager_with_storages(self, storage_table: StoragesTable):
        """get_storage_manager registers all tenant storages."""
        await storage_table.insert({
            "tenant_id": "t1",
            "name": "HOME",
            "protocol": "local",
            "config": {"base_path": "/home"},
        })
        await storage_table.insert({
            "tenant_id": "t1",
            "name": "ARCHIVE",
            "protocol": "local",
            "config": {"base_path": "/archive"},
        })

        manager = await storage_table.get_storage_manager("t1")

        assert "HOME" in manager._mounts
        assert "ARCHIVE" in manager._mounts
        assert manager._mounts["HOME"]["protocol"] == "local"
