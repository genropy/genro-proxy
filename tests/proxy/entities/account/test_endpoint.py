# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for AccountEndpoint - direct endpoint tests for coverage."""

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
        "host": "server.example.com",
        "port": 587,
        "user": "testuser",
        "use_tls": True,
        "ttl": 300,
        "limit_behavior": "defer",
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
            host="server.example.com",
            port=587,
        )
        mock_table.add.assert_called_once()
        assert result["id"] == "acc1"
        assert result["tenant_id"] == "t1"

    async def test_add_with_credentials(self, endpoint, mock_table):
        """Add account with user/password."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            host="server.example.com",
            port=587,
            user="myuser",
            password="mypass",
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["user"] == "myuser"
        assert call_args["password"] == "mypass"

    async def test_add_with_tls(self, endpoint, mock_table):
        """Add account with use_tls setting."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            host="server.example.com",
            port=465,
            use_tls=True,
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["use_tls"] is True

    async def test_add_with_rate_limits(self, endpoint, mock_table):
        """Add account with rate limits."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            host="server.example.com",
            port=587,
            limit_per_minute=10,
            limit_per_hour=100,
            limit_per_day=1000,
            limit_behavior="reject",
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["limit_per_minute"] == 10
        assert call_args["limit_per_hour"] == 100
        assert call_args["limit_per_day"] == 1000
        assert call_args["limit_behavior"] == "reject"

    async def test_add_with_ttl_and_batch(self, endpoint, mock_table):
        """Add account with ttl and batch_size."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            host="server.example.com",
            port=587,
            ttl=600,
            batch_size=50,
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["ttl"] == 600
        assert call_args["batch_size"] == 50


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
            {"id": "a1", "tenant_id": "t1"},
            {"id": "a2", "tenant_id": "t1"},
            {"id": "a3", "tenant_id": "t1"},
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


class TestAccountEndpointDefaults:
    """Tests for default values in AccountEndpoint.add()."""

    async def test_default_use_tls(self, endpoint, mock_table):
        """Default use_tls is True."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            host="server.example.com",
            port=587,
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["use_tls"] is True

    async def test_default_ttl(self, endpoint, mock_table):
        """Default ttl is 300."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            host="server.example.com",
            port=587,
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["ttl"] == 300

    async def test_default_limit_behavior(self, endpoint, mock_table):
        """Default limit_behavior is 'defer'."""
        await endpoint.add(
            id="acc1",
            tenant_id="t1",
            host="server.example.com",
            port=587,
        )
        call_args = mock_table.add.call_args[0][0]
        assert call_args["limit_behavior"] == "defer"
