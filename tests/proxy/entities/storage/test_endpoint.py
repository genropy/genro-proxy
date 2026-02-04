# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for StorageEndpoint - direct endpoint tests for coverage."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from genro_proxy.entities.storage.endpoint import StorageEndpoint


class MockRecordContextManager:
    """Mock for table.record_to_update() context manager."""

    def __init__(self, initial_data=None):
        self.data = initial_data or {}

    async def __aenter__(self):
        return self.data

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def mock_table():
    """Create mock StoragesTable with new API methods."""
    table = MagicMock()
    # Mock record() context manager
    table.record_to_update = MagicMock(return_value=MockRecordContextManager())
    # Mock record
    table.record = AsyncMock(return_value={
        "pk": "uuid-1",
        "tenant_id": "t1",
        "name": "HOME",
        "protocol": "local",
        "config": {"base_path": "/data"},
    })
    # Mock select
    table.select = AsyncMock(return_value=[])
    # Mock delete
    table.delete = AsyncMock(return_value=1)
    return table


@pytest.fixture
def endpoint(mock_table):
    """Create StorageEndpoint with mock table."""
    return StorageEndpoint(mock_table)


class TestStorageEndpointAdd:
    """Tests for StorageEndpoint.add() method."""

    async def test_add_storage(self, endpoint, mock_table):
        """add() creates storage and returns it."""
        result = await endpoint.add(
            tenant_id="t1",
            name="HOME",
            protocol="local",
            config={"base_path": "/data"},
        )
        mock_table.record_to_update.assert_called_once_with(
            {"tenant_id": "t1", "name": "HOME"},
            insert_missing=True,
        )
        assert result["tenant_id"] == "t1"
        assert result["name"] == "HOME"

    async def test_add_storage_without_config(self, endpoint, mock_table):
        """add() uses empty config when not provided."""
        await endpoint.add(tenant_id="t1", name="SALES", protocol="s3")
        mock_table.record_to_update.assert_called_once()

    async def test_add_storage_with_s3_config(self, endpoint, mock_table):
        """add() passes S3 config correctly."""
        s3_config = {
            "bucket": "my-bucket",
            "prefix": "attachments/",
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret123",
        }
        await endpoint.add(
            tenant_id="t1",
            name="CLOUD",
            protocol="s3",
            config=s3_config,
        )
        mock_table.record_to_update.assert_called_once()


class TestStorageEndpointGet:
    """Tests for StorageEndpoint.get() method."""

    async def test_get_storage(self, endpoint, mock_table):
        """get() returns storage configuration."""
        result = await endpoint.get("t1", "HOME")
        mock_table.record.assert_called_once_with(
            where={"tenant_id": "t1", "name": "HOME"}
        )
        assert result["name"] == "HOME"


class TestStorageEndpointList:
    """Tests for StorageEndpoint.list() method."""

    async def test_list_storages(self, endpoint, mock_table):
        """list() returns all storages for tenant."""
        mock_table.select = AsyncMock(return_value=[
            {"name": "HOME", "protocol": "local"},
            {"name": "SALES", "protocol": "s3"},
        ])
        result = await endpoint.list("t1")
        mock_table.select.assert_called_once_with(
            where={"tenant_id": "t1"}, order_by="name"
        )
        assert len(result) == 2

    async def test_list_empty(self, endpoint, mock_table):
        """list() returns empty list when no storages."""
        result = await endpoint.list("t1")
        assert result == []


class TestStorageEndpointDelete:
    """Tests for StorageEndpoint.delete() method."""

    async def test_delete_storage(self, endpoint, mock_table):
        """delete() removes storage and returns status."""
        result = await endpoint.delete("t1", "HOME")
        mock_table.delete.assert_called_once_with(
            where={"tenant_id": "t1", "name": "HOME"}
        )
        assert result["ok"] == 1
        assert result["tenant_id"] == "t1"
        assert result["name"] == "HOME"

    async def test_delete_not_found(self, endpoint, mock_table):
        """delete() returns ok=0 when not found."""
        mock_table.delete = AsyncMock(return_value=0)
        result = await endpoint.delete("t1", "NONEXISTENT")
        assert result["ok"] == 0


class TestStorageEndpointListFiles:
    """Tests for StorageEndpoint.list_files() method."""

    async def test_list_files_root(self, endpoint, mock_table):
        """list_files() returns files in root directory."""
        mock_manager = MagicMock()
        mock_manager.has_mount.return_value = True

        mock_child1 = MagicMock()
        mock_child1.basename = "file1.txt"
        mock_child1.path = "file1.txt"
        mock_child1.is_dir = AsyncMock(return_value=False)
        mock_child1.size = AsyncMock(return_value=1024)
        mock_child1.mtime = AsyncMock(return_value=1700000000.0)
        mock_child1.exists = AsyncMock(return_value=True)

        mock_child2 = MagicMock()
        mock_child2.basename = "subdir"
        mock_child2.path = "subdir"
        mock_child2.is_dir = AsyncMock(return_value=True)
        mock_child2.size = AsyncMock(return_value=0)
        mock_child2.mtime = AsyncMock(return_value=1700000000.0)
        mock_child2.exists = AsyncMock(return_value=True)

        mock_node = MagicMock()
        mock_node.children = AsyncMock(return_value=[mock_child1, mock_child2])
        mock_manager.node.return_value = mock_node

        mock_table.get_storage_manager = AsyncMock(return_value=mock_manager)

        result = await endpoint.list_files("t1", "HOME", "/")

        mock_table.get_storage_manager.assert_called_once_with("t1")
        mock_manager.has_mount.assert_called_once_with("HOME")
        mock_manager.node.assert_called_once_with("HOME", "")

        assert len(result) == 2
        assert result[0]["name"] == "file1.txt"
        assert result[0]["is_dir"] is False
        assert result[0]["size"] == 1024
        assert result[1]["name"] == "subdir"
        assert result[1]["is_dir"] is True
        assert result[1]["size"] == 0

    async def test_list_files_subdir(self, endpoint, mock_table):
        """list_files() with path navigates to subdirectory."""
        mock_manager = MagicMock()
        mock_manager.has_mount.return_value = True

        mock_node = MagicMock()
        mock_node.children = AsyncMock(return_value=[])
        mock_manager.node.return_value = mock_node

        mock_table.get_storage_manager = AsyncMock(return_value=mock_manager)

        await endpoint.list_files("t1", "HOME", "/subdir/nested")

        mock_manager.node.assert_called_once_with("HOME", "subdir/nested")

    async def test_list_files_storage_not_found(self, endpoint, mock_table):
        """list_files() raises ValueError for unknown storage."""
        mock_manager = MagicMock()
        mock_manager.has_mount.return_value = False

        mock_table.get_storage_manager = AsyncMock(return_value=mock_manager)

        with pytest.raises(ValueError, match="Storage 'UNKNOWN' not found"):
            await endpoint.list_files("t1", "UNKNOWN", "/")
