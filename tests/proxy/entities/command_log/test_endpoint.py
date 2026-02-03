# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for CommandLogEndpoint - direct endpoint tests for coverage."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from genro_proxy.entities.command_log.endpoint import CommandLogEndpoint


@pytest.fixture
def mock_table():
    """Create mock CommandLogTable."""
    table = MagicMock()
    table.list_commands = AsyncMock(return_value=[])
    table.get_command = AsyncMock(return_value=None)
    table.export_commands = AsyncMock(return_value=[])
    table.purge_before = AsyncMock(return_value=0)
    return table


@pytest.fixture
def endpoint(mock_table):
    """Create CommandLogEndpoint with mock table."""
    return CommandLogEndpoint(mock_table)


class TestCommandLogEndpointGet:
    """Tests for CommandLogEndpoint.get() method."""

    async def test_get_not_found_raises(self, endpoint, mock_table):
        """get() raises ValueError when command not found."""
        mock_table.get_command = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Command '999' not found"):
            await endpoint.get(999)

    async def test_get_success(self, endpoint, mock_table):
        """get() returns command when found."""
        mock_table.get_command = AsyncMock(return_value={
            "id": 123,
            "endpoint": "accounts/add",
            "tenant_id": "t1",
        })
        result = await endpoint.get(123)
        assert result["id"] == 123
        assert result["endpoint"] == "accounts/add"


class TestCommandLogEndpointList:
    """Tests for CommandLogEndpoint.list() method."""

    async def test_list_with_filters(self, endpoint, mock_table):
        """list() passes all filters to table."""
        await endpoint.list(
            tenant_id="t1",
            since_ts=1000,
            until_ts=2000,
            endpoint_filter="accounts",
            limit=50,
            offset=10,
        )
        mock_table.list_commands.assert_called_once_with(
            tenant_id="t1",
            since_ts=1000,
            until_ts=2000,
            endpoint_filter="accounts",
            limit=50,
            offset=10,
        )

    async def test_list_defaults(self, endpoint, mock_table):
        """list() uses default values."""
        await endpoint.list()
        mock_table.list_commands.assert_called_once_with(
            tenant_id=None,
            since_ts=None,
            until_ts=None,
            endpoint_filter=None,
            limit=100,
            offset=0,
        )

    async def test_list_returns_commands(self, endpoint, mock_table):
        """list() returns command list."""
        mock_table.list_commands = AsyncMock(return_value=[
            {"id": 1, "endpoint": "tenants/add"},
            {"id": 2, "endpoint": "accounts/add"},
        ])
        result = await endpoint.list()
        assert len(result) == 2


class TestCommandLogEndpointExport:
    """Tests for CommandLogEndpoint.export() method."""

    async def test_export_with_filters(self, endpoint, mock_table):
        """export() passes filters to table."""
        await endpoint.export(tenant_id="t1", since_ts=1000, until_ts=2000)
        mock_table.export_commands.assert_called_once_with(
            tenant_id="t1",
            since_ts=1000,
            until_ts=2000,
        )

    async def test_export_defaults(self, endpoint, mock_table):
        """export() uses default values."""
        await endpoint.export()
        mock_table.export_commands.assert_called_once_with(
            tenant_id=None,
            since_ts=None,
            until_ts=None,
        )

    async def test_export_returns_minimal_data(self, endpoint, mock_table):
        """export() returns minimal fields for replay."""
        mock_table.export_commands = AsyncMock(return_value=[
            {"endpoint": "tenants/add", "tenant_id": "t1", "payload": {}, "command_ts": 1000},
        ])
        result = await endpoint.export()
        assert len(result) == 1
        assert "endpoint" in result[0]


class TestCommandLogEndpointPurge:
    """Tests for CommandLogEndpoint.purge() method."""

    async def test_purge(self, endpoint, mock_table):
        """purge() deletes old commands and returns count."""
        mock_table.purge_before = AsyncMock(return_value=42)
        result = await endpoint.purge(threshold_ts=1700000000)
        mock_table.purge_before.assert_called_once_with(1700000000)
        assert result["ok"] is True
        assert result["deleted"] == 42

    async def test_purge_zero(self, endpoint, mock_table):
        """purge() returns zero when nothing to delete."""
        mock_table.purge_before = AsyncMock(return_value=0)
        result = await endpoint.purge(threshold_ts=1700000000)
        assert result["ok"] is True
        assert result["deleted"] == 0
