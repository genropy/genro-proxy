# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for AccountEndpoint - generic account CRUD operations."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from proxy.entities.account.endpoint import AccountEndpoint


@pytest.fixture
def mock_table():
    """Create mock AccountsTable."""
    table = MagicMock()
    table.add = AsyncMock()
    table.get = AsyncMock(return_value={
        "pk": "uuid-1",
        "id": "acc1",
        "tenant_id": "t1",
        "name": "Account One",
        "config": {"key": "value"},
    })
    table.list_all = AsyncMock(return_value=[])
    table.remove = AsyncMock()
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
        mock_table.add.assert_called_once()
        assert result["id"] == "acc1"
        assert result["tenant_id"] == "t1"

    async def test_add_with_name(self, endpoint, mock_table):
        """Add account with display name."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            name="My Account",
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["name"] == "My Account"

    async def test_add_with_config(self, endpoint, mock_table):
        """Add account with config dict."""
        config = {"host": "example.com", "port": 8080}
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            config=config,
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["config"] == config

    async def test_add_with_all_fields(self, endpoint, mock_table):
        """Add account with all fields."""
        config = {"setting": "value"}
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            name="Full Account",
            config=config,
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["id"] == "acc1"
        assert call_args["tenant_id"] == "t1"
        assert call_args["name"] == "Full Account"
        assert call_args["config"] == config


class TestAccountEndpointGet:
    """Tests for AccountEndpoint.get() method."""

    async def test_get_existing(self, endpoint, mock_table):
        """Get an existing account."""
        result = await endpoint.get(tenant_id="t1", account_id="acc1")
        mock_table.get.assert_called_once_with("t1", "acc1")
        assert result["id"] == "acc1"

    async def test_get_nonexistent_raises(self, endpoint, mock_table):
        """Get non-existent account raises ValueError."""
        mock_table.get = AsyncMock(side_effect=ValueError("Account not found"))
        with pytest.raises(ValueError):
            await endpoint.get(tenant_id="t1", account_id="nonexistent")


class TestAccountEndpointList:
    """Tests for AccountEndpoint.list() method."""

    async def test_list_empty(self, endpoint, mock_table):
        """List returns empty when no accounts."""
        result = await endpoint.list(tenant_id="t1")
        assert result == []

    async def test_list_multiple(self, endpoint, mock_table):
        """List returns all accounts for tenant."""
        mock_table.list_all = AsyncMock(return_value=[
            {"id": "a1", "tenant_id": "t1", "name": "Account 1"},
            {"id": "a2", "tenant_id": "t1", "name": "Account 2"},
            {"id": "a3", "tenant_id": "t1", "name": "Account 3"},
        ])
        result = await endpoint.list(tenant_id="t1")
        assert len(result) == 3
        mock_table.list_all.assert_called_once_with(tenant_id="t1")


class TestAccountEndpointDelete:
    """Tests for AccountEndpoint.delete() method."""

    async def test_delete_existing(self, endpoint, mock_table):
        """Delete an existing account."""
        await endpoint.delete(tenant_id="t1", account_id="acc1")
        mock_table.remove.assert_called_once_with("t1", "acc1")
