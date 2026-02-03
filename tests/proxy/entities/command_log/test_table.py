# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for CommandLogTable."""

import time

import pytest

from genro_proxy.entities.command_log.table import CommandLogTable


@pytest.mark.postgres
class TestCommandLogTable:
    """Tests for CommandLogTable with PostgreSQL."""

    @pytest.fixture
    async def table(self, pg_db):
        """Create CommandLogTable."""
        table = CommandLogTable(pg_db)
        await table.create_schema()
        return table

    async def test_log_command_minimal(self, table):
        """Log command with minimal fields."""
        cmd_id = await table.log_command(
            endpoint="POST /test",
            payload={"key": "value"},
        )
        assert cmd_id >= 0

    async def test_log_command_with_all_fields(self, table):
        """Log command with all fields."""
        ts = int(time.time())
        cmd_id = await table.log_command(
            endpoint="POST /api/accounts/add",
            payload={"id": "acc1", "name": "Test"},
            tenant_id="tenant1",
            response_status=200,
            response_body={"ok": True, "id": "acc1"},
            command_ts=ts,
        )
        assert cmd_id >= 0

    async def test_log_command_uses_current_time(self, table):
        """Log command uses current time if not provided."""
        before = int(time.time())
        cmd_id = await table.log_command(
            endpoint="GET /test",
            payload={},
        )
        after = int(time.time())

        # Retrieve and check timestamp
        commands = await table.list_commands(limit=1)
        assert len(commands) == 1
        assert before <= commands[0]["command_ts"] <= after

    async def test_list_commands_empty(self, table):
        """List returns empty when no commands."""
        result = await table.list_commands()
        assert result == []

    async def test_list_commands_returns_all(self, table):
        """List returns all logged commands."""
        await table.log_command("POST /a", {"a": 1})
        await table.log_command("POST /b", {"b": 2})
        await table.log_command("POST /c", {"c": 3})

        result = await table.list_commands()
        assert len(result) == 3

    async def test_list_commands_filter_by_tenant(self, table):
        """Filter commands by tenant_id."""
        await table.log_command("POST /a", {"a": 1}, tenant_id="t1")
        await table.log_command("POST /b", {"b": 2}, tenant_id="t2")
        await table.log_command("POST /c", {"c": 3}, tenant_id="t1")

        result = await table.list_commands(tenant_id="t1")
        assert len(result) == 2
        assert all(c["tenant_id"] == "t1" for c in result)

    async def test_list_commands_filter_by_since_ts(self, table):
        """Filter commands by since_ts."""
        ts = int(time.time())
        await table.log_command("POST /old", {}, command_ts=ts - 100)
        await table.log_command("POST /new", {}, command_ts=ts)

        result = await table.list_commands(since_ts=ts - 50)
        assert len(result) == 1
        assert result[0]["endpoint"] == "POST /new"

    async def test_list_commands_filter_by_until_ts(self, table):
        """Filter commands by until_ts."""
        ts = int(time.time())
        await table.log_command("POST /old", {}, command_ts=ts - 100)
        await table.log_command("POST /new", {}, command_ts=ts)

        result = await table.list_commands(until_ts=ts - 50)
        assert len(result) == 1
        assert result[0]["endpoint"] == "POST /old"

    async def test_list_commands_filter_by_endpoint(self, table):
        """Filter commands by endpoint pattern."""
        await table.log_command("POST /api/accounts/add", {})
        await table.log_command("POST /api/tenants/add", {})
        await table.log_command("GET /api/accounts/list", {})

        result = await table.list_commands(endpoint_filter="accounts")
        assert len(result) == 2

    async def test_list_commands_pagination(self, table):
        """Test pagination with limit and offset."""
        for i in range(5):
            await table.log_command(f"POST /cmd{i}", {"i": i})

        # First page
        page1 = await table.list_commands(limit=2, offset=0)
        assert len(page1) == 2

        # Second page
        page2 = await table.list_commands(limit=2, offset=2)
        assert len(page2) == 2

        # Third page (partial)
        page3 = await table.list_commands(limit=2, offset=4)
        assert len(page3) == 1

    async def test_list_commands_parses_json_payload(self, table):
        """List parses JSON payload field."""
        await table.log_command("POST /test", {"nested": {"key": "value"}})

        result = await table.list_commands()
        assert len(result) == 1
        assert result[0]["payload"] == {"nested": {"key": "value"}}

    async def test_list_commands_parses_json_response_body(self, table):
        """List parses JSON response_body field."""
        await table.log_command(
            "POST /test",
            {"a": 1},
            response_body={"result": "ok"},
        )

        result = await table.list_commands()
        assert len(result) == 1
        assert result[0]["response_body"] == {"result": "ok"}

    async def test_get_command_existing(self, table):
        """Get existing command by ID."""
        await table.log_command("POST /test", {"data": "value"}, tenant_id="t1")

        # Get first command
        commands = await table.list_commands()
        cmd_id = commands[0]["id"]

        result = await table.get_command(cmd_id)
        assert result is not None
        assert result["endpoint"] == "POST /test"
        assert result["payload"] == {"data": "value"}
        assert result["tenant_id"] == "t1"

    async def test_get_command_nonexistent(self, table):
        """Get nonexistent command returns None."""
        result = await table.get_command(99999)
        assert result is None

    async def test_export_commands(self, table):
        """Export commands in replay format."""
        ts = int(time.time())
        await table.log_command(
            "POST /api/accounts/add",
            {"id": "acc1"},
            tenant_id="t1",
            command_ts=ts,
        )

        result = await table.export_commands()
        assert len(result) == 1
        assert result[0]["endpoint"] == "POST /api/accounts/add"
        assert result[0]["tenant_id"] == "t1"
        assert result[0]["payload"] == {"id": "acc1"}
        assert result[0]["command_ts"] == ts

    async def test_export_commands_with_filters(self, table):
        """Export commands with tenant filter."""
        await table.log_command("POST /a", {}, tenant_id="t1")
        await table.log_command("POST /b", {}, tenant_id="t2")

        result = await table.export_commands(tenant_id="t1")
        assert len(result) == 1
        assert result[0]["tenant_id"] == "t1"

    async def test_purge_before(self, table):
        """Purge old commands."""
        ts = int(time.time())
        await table.log_command("POST /old", {}, command_ts=ts - 1000)
        await table.log_command("POST /new", {}, command_ts=ts)

        deleted = await table.purge_before(ts - 500)
        assert deleted == 1

        remaining = await table.list_commands()
        assert len(remaining) == 1
        assert remaining[0]["endpoint"] == "POST /new"

    async def test_purge_before_no_match(self, table):
        """Purge with no matching commands."""
        ts = int(time.time())
        await table.log_command("POST /new", {}, command_ts=ts)

        deleted = await table.purge_before(ts - 1000)
        assert deleted == 0

        remaining = await table.list_commands()
        assert len(remaining) == 1

    async def test_new_pkey_value_returns_none(self, table):
        """new_pkey_value returns None for autoincrement."""
        assert table.new_pkey_value() is None
