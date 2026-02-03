# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for TenantEndpoint - direct endpoint tests for coverage.

These tests directly exercise TenantEndpoint methods to cover edge cases
and error paths.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from proxy.entities.tenant.endpoint import TenantEndpoint


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
    """Create mock TenantsTable with new API methods."""
    table = MagicMock()
    # Mock record() context manager
    table.record_to_update = MagicMock(return_value=MockRecordContextManager())
    # Mock record
    table.record = AsyncMock(return_value={
        "id": "t1",
        "name": "Test Tenant",
        "active": 1,
        "client_base_url": "https://example.com",
    })
    # Mock select
    table.select = AsyncMock(return_value=[])
    # Mock delete
    table.delete = AsyncMock(return_value=1)
    # Mock _decode_active (helper method on table)
    table._decode_active = lambda t: {**t, "active": bool(t.get("active", 1))}
    return table


@pytest.fixture
def endpoint(mock_table):
    """Create TenantEndpoint with mock table."""
    return TenantEndpoint(mock_table)


class TestTenantEndpointAdd:
    """Tests for TenantEndpoint.add() method."""

    async def test_add_tenant_minimal(self, endpoint, mock_table):
        """add() creates tenant with minimal fields."""
        result = await endpoint.add(id="t1")
        mock_table.record_to_update.assert_called_once_with("t1", insert_missing=True)
        assert result["id"] == "t1"

    async def test_add_tenant_with_all_fields(self, endpoint, mock_table):
        """add() creates tenant with all fields."""
        result = await endpoint.add(
            id="t1",
            name="Test Tenant",
            client_auth={"method": "bearer", "token": "abc"},
            client_base_url="https://example.com",
            config={"custom": "value"},
            active=True,
        )
        mock_table.record_to_update.assert_called_once_with("t1", insert_missing=True)
        assert result["id"] == "t1"

    async def test_add_tenant_inactive(self, endpoint, mock_table):
        """add() creates inactive tenant."""
        await endpoint.add(id="t1", active=False)
        mock_table.record_to_update.assert_called_once()


class TestTenantEndpointGet:
    """Tests for TenantEndpoint.get() method."""

    async def test_get_existing(self, endpoint, mock_table):
        """get() returns tenant when found."""
        result = await endpoint.get("t1")
        mock_table.record.assert_called_once_with(pkey="t1")
        assert result["id"] == "t1"
        assert result["active"] is True  # _decode_active converts 1 to True

    async def test_get_not_found_raises(self, endpoint, mock_table):
        """get() raises ValueError when tenant not found."""
        from proxy.sql import RecordNotFoundError
        mock_table.record = AsyncMock(
            side_effect=RecordNotFoundError("tenants", pkey="nonexistent")
        )
        with pytest.raises(ValueError, match="Tenant 'nonexistent' not found"):
            await endpoint.get("nonexistent")


class TestTenantEndpointList:
    """Tests for TenantEndpoint.list() method."""

    async def test_list_empty(self, endpoint, mock_table):
        """list() returns empty list when no tenants."""
        result = await endpoint.list()
        assert result == []
        mock_table.select.assert_called_once_with(where=None, order_by="id")

    async def test_list_tenants(self, endpoint, mock_table):
        """list() returns all tenants."""
        mock_table.select = AsyncMock(return_value=[
            {"id": "t1", "name": "Tenant 1", "active": 1},
            {"id": "t2", "name": "Tenant 2", "active": 1},
        ])
        result = await endpoint.list()
        assert len(result) == 2
        mock_table.select.assert_called_once_with(where=None, order_by="id")

    async def test_list_active_only(self, endpoint, mock_table):
        """list(active_only=True) filters active tenants."""
        mock_table.select = AsyncMock(return_value=[
            {"id": "t1", "name": "Tenant 1", "active": 1},
        ])
        result = await endpoint.list(active_only=True)
        assert len(result) == 1
        mock_table.select.assert_called_once_with(where={"active": 1}, order_by="id")


class TestTenantEndpointDelete:
    """Tests for TenantEndpoint.delete() method."""

    async def test_delete_tenant(self, endpoint, mock_table):
        """delete() removes tenant."""
        result = await endpoint.delete("t1")
        mock_table.delete.assert_called_once_with(where={"id": "t1"})
        assert result == 1


class TestTenantEndpointUpdate:
    """Tests for TenantEndpoint.update() method."""

    async def test_update_name(self, endpoint, mock_table):
        """update() updates tenant name."""
        await endpoint.update("t1", name="New Name")
        mock_table.record_to_update.assert_called_once_with("t1")

    async def test_update_multiple_fields(self, endpoint, mock_table):
        """update() updates multiple fields."""
        await endpoint.update(
            "t1",
            name="New Name",
            client_base_url="https://new.example.com",
            config={"key": "value"},
        )
        mock_table.record_to_update.assert_called_once_with("t1")

    async def test_update_active_true(self, endpoint, mock_table):
        """update() converts active=True to 1."""
        await endpoint.update("t1", active=True)
        mock_table.record_to_update.assert_called_once()

    async def test_update_active_false(self, endpoint, mock_table):
        """update() converts active=False to 0."""
        await endpoint.update("t1", active=False)
        mock_table.record_to_update.assert_called_once()

    async def test_update_no_fields(self, endpoint, mock_table):
        """update() with no fields still calls record()."""
        await endpoint.update("t1")
        mock_table.record_to_update.assert_called_once_with("t1")
