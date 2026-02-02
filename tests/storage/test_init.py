# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for storage module initialization."""

from __future__ import annotations


class TestStorageModuleImport:
    """Tests for storage module import behavior."""

    def test_storage_manager_exported(self):
        """StorageManager is exported from storage module."""
        from proxy.storage import StorageManager

        assert StorageManager is not None

    def test_storage_node_exported(self):
        """StorageNode is exported from storage module."""
        from proxy.storage import StorageNode

        assert StorageNode is not None

    def test_storage_node_has_cloud_methods(self):
        """StorageNode includes cloud methods (Apache 2.0)."""
        from proxy.storage import StorageNode

        # Cloud methods should be available
        assert hasattr(StorageNode, "_get_fs")
        assert hasattr(StorageNode, "_cloud_read_bytes")
        assert hasattr(StorageNode, "_cloud_write_bytes")
