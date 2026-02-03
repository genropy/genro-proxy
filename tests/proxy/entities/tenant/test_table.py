# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for TenantsTable."""

import pytest_asyncio

from proxy.entities.tenant.table import TenantsTable
from proxy.sql import SqlDb


@pytest_asyncio.fixture
async def tenant_table(sqlite_db: SqlDb) -> TenantsTable:
    """Create a TenantsTable with SQLite for testing."""
    table = TenantsTable(sqlite_db)
    await table.create_schema()
    return table


class TestDecodeActive:
    """Tests for TenantsTable._decode_active() method."""

    async def test_decode_active_true(self, tenant_table: TenantsTable):
        """Active=1 becomes True."""
        tenant = {"id": "t1", "active": 1}
        result = tenant_table._decode_active(tenant)
        assert result["active"] is True

    async def test_decode_active_false(self, tenant_table: TenantsTable):
        """Active=0 becomes False."""
        tenant = {"id": "t1", "active": 0}
        result = tenant_table._decode_active(tenant)
        assert result["active"] is False

    async def test_decode_active_missing(self, tenant_table: TenantsTable):
        """Missing active defaults to True."""
        tenant = {"id": "t1"}
        result = tenant_table._decode_active(tenant)
        assert result["active"] is True


class TestEnsureDefault:
    """Tests for TenantsTable.ensure_default() method."""

    async def test_creates_default_tenant(self, tenant_table: TenantsTable):
        """Creates default tenant if not exists."""
        await tenant_table.ensure_default()

        tenant = await tenant_table.record(where={"id": "default"})
        assert tenant is not None
        assert tenant["id"] == "default"
        assert tenant["name"] == "Default Tenant"
        assert tenant["active"] == 1

    async def test_does_not_overwrite_existing(self, tenant_table: TenantsTable):
        """Does not overwrite existing default tenant with custom name."""
        await tenant_table.insert({
            "id": "default",
            "name": "Custom Default",
            "active": 1,
        })

        await tenant_table.ensure_default()

        tenant = await tenant_table.record(where={"id": "default"})
        assert tenant is not None
        assert tenant["name"] == "Custom Default"

    async def test_sets_name_if_missing(self, tenant_table: TenantsTable):
        """Sets name if default exists but name is empty."""
        await tenant_table.insert({"id": "default", "name": "", "active": 0})

        await tenant_table.ensure_default()

        tenant = await tenant_table.record(where={"id": "default"})
        assert tenant is not None
        assert tenant["name"] == "Default Tenant"
        assert tenant["active"] == 1


class TestTenantsTableWithConfig:
    """Tests for TenantsTable with config field."""

    async def test_insert_with_config(self, tenant_table: TenantsTable):
        """Insert tenant with JSON config."""
        config = {"setting1": "value1", "nested": {"key": "value"}}
        await tenant_table.insert({
            "id": "t1",
            "name": "Test",
            "config": config,
            "active": 1,
        })

        tenant = await tenant_table.record(where={"id": "t1"})
        assert tenant is not None
        assert tenant["config"] == config

    async def test_insert_with_client_auth(self, tenant_table: TenantsTable):
        """Insert tenant with client_auth JSON."""
        auth = {"method": "bearer", "token": "secret123"}
        await tenant_table.insert({
            "id": "t1",
            "name": "Test",
            "client_auth": auth,
            "active": 1,
        })

        tenant = await tenant_table.record(where={"id": "t1"})
        assert tenant is not None
        assert tenant["client_auth"] == auth

    async def test_insert_with_client_base_url(self, tenant_table: TenantsTable):
        """Insert tenant with client_base_url field."""
        await tenant_table.insert({
            "id": "t1",
            "name": "Test",
            "client_base_url": "https://example.com",
            "active": 1,
        })

        tenant = await tenant_table.record(where={"id": "t1"})
        assert tenant is not None
        assert tenant["client_base_url"] == "https://example.com"


class TestTenantsTableApiKey:
    """Tests for TenantsTable API key methods."""

    async def test_create_api_key(self, tenant_table: TenantsTable):
        """create_api_key() generates and stores API key."""
        await tenant_table.insert({"id": "t1", "name": "Test", "active": 1})

        api_key = await tenant_table.create_api_key("t1")

        assert api_key is not None
        assert len(api_key) > 20  # URL-safe base64 is ~43 chars for 32 bytes

        tenant = await tenant_table.record(where={"id": "t1"})
        assert tenant is not None
        assert tenant["api_key_hash"] is not None

    async def test_create_api_key_with_expiration(self, tenant_table: TenantsTable):
        """create_api_key() stores expiration timestamp."""
        await tenant_table.insert({"id": "t1", "name": "Test", "active": 1})

        expires_at = 1700000000
        await tenant_table.create_api_key("t1", expires_at=expires_at)

        tenant = await tenant_table.record(where={"id": "t1"})
        assert tenant is not None
        assert tenant["api_key_expires_at"] == expires_at

    async def test_get_tenant_by_token(self, tenant_table: TenantsTable):
        """get_tenant_by_token() finds tenant by API key."""
        await tenant_table.insert({"id": "t1", "name": "Test", "active": 1})
        api_key = await tenant_table.create_api_key("t1")

        tenant = await tenant_table.get_tenant_by_token(api_key)

        assert tenant is not None
        assert tenant["id"] == "t1"

    async def test_get_tenant_by_token_not_found(self, tenant_table: TenantsTable):
        """get_tenant_by_token() returns None for invalid key."""
        tenant = await tenant_table.get_tenant_by_token("invalid-key")
        assert tenant is None

    async def test_get_tenant_by_token_expired(self, tenant_table: TenantsTable):
        """get_tenant_by_token() returns None for expired key."""
        await tenant_table.insert({"id": "t1", "name": "Test", "active": 1})
        # Set expiration to past
        api_key = await tenant_table.create_api_key("t1", expires_at=1)

        tenant = await tenant_table.get_tenant_by_token(api_key)

        assert tenant is None
