# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for AccountEndpoint - generic account CRUD operations."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from genro_proxy.entities.account.endpoint import AccountEndpoint


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
    """Create mock AccountsTable with new API methods."""
    table = MagicMock()
    # Mock record_to_update() context manager
    table.record_to_update = MagicMock(return_value=MockRecordContextManager())
    # Mock record
    table.record = AsyncMock(return_value={
        "pk": "uuid-1",
        "id": "acc1",
        "tenant_id": "t1",
        "name": "Account One",
        "config": {"key": "value"},
    })
    # Mock select
    table.select = AsyncMock(return_value=[])
    # Mock delete
    table.delete = AsyncMock(return_value=1)
    return table


@pytest.fixture
def endpoint(mock_table):
    """Create AccountEndpoint with mock table."""
    return AccountEndpoint(mock_table)


class TestAccountEndpointAdd:
    """Tests for AccountEndpoint.add() method."""

    async def test_add_minimal(self, endpoint, mock_table):
        """Add account with minimal required fields."""
        result = await endpoint.add(
            id="acc1",
            tenant_id="t1",
        )
        mock_table.record_to_update.assert_called_once_with(
            {"tenant_id": "t1", "id": "acc1"},
            insert_missing=True,
        )
        assert result["id"] == "acc1"
        assert result["tenant_id"] == "t1"

    async def test_add_with_name(self, endpoint, mock_table):
        """Add account with display name."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            name="My Account",
        )
        mock_table.record_to_update.assert_called_once()

    async def test_add_with_config(self, endpoint, mock_table):
        """Add account with config dict."""
        config = {"host": "example.com", "port": 8080}
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            config=config,
        )
        mock_table.record_to_update.assert_called_once()

    async def test_add_with_all_fields(self, endpoint, mock_table):
        """Add account with all fields."""
        config = {"setting": "value"}
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            name="Full Account",
            config=config,
        )
        mock_table.record_to_update.assert_called_once_with(
            {"tenant_id": "t1", "id": "acc1"},
            insert_missing=True,
        )


class TestAccountEndpointGet:
    """Tests for AccountEndpoint.get() method."""

    async def test_get_existing(self, endpoint, mock_table):
        """Get an existing account."""
        result = await endpoint.get(tenant_id="t1", account_id="acc1")
        mock_table.record.assert_called_once_with(
            where={"tenant_id": "t1", "id": "acc1"}
        )
        assert result["id"] == "acc1"

    async def test_get_nonexistent_raises(self, endpoint, mock_table):
        """Get non-existent account raises ValueError."""
        from genro_proxy.sql import RecordNotFoundError
        mock_table.record = AsyncMock(
            side_effect=RecordNotFoundError("accounts", where={"tenant_id": "t1", "id": "nonexistent"})
        )
        with pytest.raises(ValueError, match="Account 'nonexistent' not found"):
            await endpoint.get(tenant_id="t1", account_id="nonexistent")


class TestAccountEndpointList:
    """Tests for AccountEndpoint.list() method."""

    async def test_list_empty(self, endpoint, mock_table):
        """List returns empty when no accounts."""
        result = await endpoint.list(tenant_id="t1")
        assert result == []
        mock_table.select.assert_called_once_with(
            where={"tenant_id": "t1"}, order_by="id"
        )

    async def test_list_multiple(self, endpoint, mock_table):
        """List returns all accounts for tenant."""
        mock_table.select = AsyncMock(return_value=[
            {"id": "a1", "tenant_id": "t1", "name": "Account 1"},
            {"id": "a2", "tenant_id": "t1", "name": "Account 2"},
            {"id": "a3", "tenant_id": "t1", "name": "Account 3"},
        ])
        result = await endpoint.list(tenant_id="t1")
        assert len(result) == 3
        mock_table.select.assert_called_once_with(
            where={"tenant_id": "t1"}, order_by="id"
        )


class TestAccountEndpointDelete:
    """Tests for AccountEndpoint.delete() method."""

    async def test_delete_existing(self, endpoint, mock_table):
        """Delete an existing account."""
        result = await endpoint.delete(tenant_id="t1", account_id="acc1")
        mock_table.delete.assert_called_once_with(
            where={"tenant_id": "t1", "id": "acc1"}
        )
        assert result == 1
