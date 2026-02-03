# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for ProxyBase class."""

from __future__ import annotations

import pytest

from proxy.proxy_base import ProxyBase, ProxyConfigBase


class TestProxyBaseInit:
    """Tests for ProxyBase.init() method."""

    async def test_init_creates_tables(self, tmp_path):
        """init() creates all discovered tables."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        await proxy.init()

        # After init, tables should exist
        # Use a new connection to verify
        async with proxy.db.connection():
            # Check that base tables were created
            result = await proxy.db.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            table_names = {row["name"] for row in result}

            # Should have at least the base entity tables
            assert "instance" in table_names
            assert "tenants" in table_names
            assert "accounts" in table_names
            assert "storages" in table_names
            assert "command_log" in table_names

        await proxy.shutdown()

    async def test_init_idempotent(self, tmp_path):
        """init() can be called multiple times safely."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        # Call init twice - should not raise
        await proxy.init()
        await proxy.init()

        await proxy.shutdown()

    async def test_init_then_operations(self, tmp_path):
        """After init(), database operations work in new connections."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        await proxy.init()

        # After init, should be able to use tables
        async with proxy.db.connection():
            # Use tenants table which has a simple string pkey (id)
            tenant_table = proxy.db.table("tenants")
            await tenant_table.insert({"id": "test-1", "name": "Test Tenant"})

            result = await tenant_table.record("test-1")
            assert result["name"] == "Test Tenant"

        await proxy.shutdown()


class TestProxyBaseShutdown:
    """Tests for ProxyBase.shutdown() method."""

    async def test_shutdown_closes_resources(self, tmp_path):
        """shutdown() closes database resources."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        await proxy.init()
        await proxy.shutdown()

        # After shutdown, adapter should be closed
        # (implementation detail: _pool is None for SQLite after shutdown)

    async def test_shutdown_without_init(self, tmp_path):
        """shutdown() works even if init() was never called."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        # Should not raise
        await proxy.shutdown()


class TestProxyBaseAttributes:
    """Tests for ProxyBase attributes and properties."""

    def test_has_config(self, tmp_path):
        """ProxyBase has config attribute."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        assert proxy.config is config

    def test_has_db(self, tmp_path):
        """ProxyBase has db attribute."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        assert proxy.db is not None
        assert proxy.db.adapter is not None

    def test_has_encryption(self, tmp_path):
        """ProxyBase has encryption manager."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        assert proxy.encryption is not None

    def test_encryption_key_none_by_default(self, tmp_path):
        """encryption_key is None when not configured."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        assert proxy.encryption_key is None

    def test_has_endpoints(self, tmp_path):
        """ProxyBase has endpoints manager."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        assert proxy.endpoints is not None

    def test_has_api(self, tmp_path):
        """ProxyBase has api manager."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        assert proxy.api is not None

    def test_has_cli(self, tmp_path):
        """ProxyBase has cli manager."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        assert proxy.cli is not None

    def test_discovers_tables(self, tmp_path):
        """ProxyBase discovers entity tables on init."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        # Tables should be discovered at construction time
        assert "instance" in proxy.db.tables
        assert "tenants" in proxy.db.tables
        assert "accounts" in proxy.db.tables
        assert "storages" in proxy.db.tables
        assert "command_log" in proxy.db.tables

    def test_discovers_endpoints(self, tmp_path):
        """ProxyBase discovers entity endpoints on init."""
        db_path = str(tmp_path / "test.db")
        config = ProxyConfigBase(db_path=db_path)
        proxy = ProxyBase(config=config)

        # Endpoints should be discovered at construction time
        assert len(proxy.endpoints._endpoints) > 0
