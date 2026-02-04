# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for InstanceEndpoint - direct endpoint tests for coverage.

These tests directly exercise InstanceEndpoint methods to cover
edge cases and paths not reached by HTTP client tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from genro_proxy.entities.instance.endpoint import InstanceEndpoint


@pytest.fixture
def mock_table():
    """Create mock InstanceTable."""
    table = MagicMock()
    table.get_instance = AsyncMock(return_value={"id": 1, "name": "test-proxy", "edition": "ce"})
    table.update_instance = AsyncMock()
    table.is_enterprise = AsyncMock(return_value=False)
    table.set_edition = AsyncMock()
    return table


@pytest.fixture
def mock_proxy(tmp_path):
    """Create mock proxy."""
    proxy = MagicMock()
    proxy._active = True
    proxy.handle_command = AsyncMock(return_value={"ok": True})
    proxy.db = MagicMock()
    proxy.base_dir = tmp_path
    proxy.cli_command = "genro-proxy"
    return proxy


@pytest.fixture
def endpoint(mock_table):
    """Create InstanceEndpoint without proxy."""
    return InstanceEndpoint(mock_table)


@pytest.fixture
def endpoint_with_proxy(mock_table, mock_proxy):
    """Create InstanceEndpoint with proxy."""
    return InstanceEndpoint(mock_table, mock_proxy)


class TestInstanceEndpointHealth:
    """Tests for InstanceEndpoint.health() method."""

    async def test_health_returns_ok(self, endpoint):
        """health() returns status ok."""
        result = await endpoint.health()
        assert result == {"status": "ok"}


class TestInstanceEndpointStatus:
    """Tests for InstanceEndpoint.status() method."""

    async def test_status_without_proxy(self, endpoint):
        """status() returns active=True when no proxy."""
        result = await endpoint.status()
        assert result["ok"] is True
        assert result["active"] is True

    async def test_status_with_active_proxy(self, endpoint_with_proxy, mock_proxy):
        """status() returns proxy's active state."""
        mock_proxy._active = True
        result = await endpoint_with_proxy.status()
        assert result["active"] is True

    async def test_status_with_inactive_proxy(self, endpoint_with_proxy, mock_proxy):
        """status() returns false when proxy inactive."""
        mock_proxy._active = False
        result = await endpoint_with_proxy.status()
        assert result["active"] is False


class TestInstanceEndpointRunNow:
    """Tests for InstanceEndpoint.run_now() method."""

    async def test_run_now_without_proxy(self, endpoint):
        """run_now() returns ok when no proxy."""
        result = await endpoint.run_now()
        assert result == {"ok": True}

    async def test_run_now_with_proxy(self, endpoint_with_proxy, mock_proxy):
        """run_now() calls proxy handle_command."""
        mock_proxy.handle_command = AsyncMock(return_value={"ok": True, "triggered": True})
        result = await endpoint_with_proxy.run_now(tenant_id="t1")

        mock_proxy.handle_command.assert_called_once_with("run now", {"tenant_id": "t1"})
        assert result == {"ok": True, "triggered": True}


class TestInstanceEndpointSuspend:
    """Tests for InstanceEndpoint.suspend() method."""

    async def test_suspend_without_proxy(self, endpoint):
        """suspend() returns basic response when no proxy."""
        result = await endpoint.suspend("t1", "batch-001")
        assert result["ok"] is True
        assert result["tenant_id"] == "t1"
        assert result["batch_code"] == "batch-001"

    async def test_suspend_with_proxy(self, endpoint_with_proxy, mock_proxy):
        """suspend() calls proxy handle_command."""
        mock_proxy.handle_command = AsyncMock(return_value={"ok": True, "suspended": ["batch-001"]})
        result = await endpoint_with_proxy.suspend("t1", "batch-001")

        mock_proxy.handle_command.assert_called_once_with(
            "suspend",
            {"tenant_id": "t1", "batch_code": "batch-001"},
        )
        assert result["ok"] is True


class TestInstanceEndpointActivate:
    """Tests for InstanceEndpoint.activate() method."""

    async def test_activate_without_proxy(self, endpoint):
        """activate() returns basic response when no proxy."""
        result = await endpoint.activate("t1", "batch-001")
        assert result["ok"] is True
        assert result["tenant_id"] == "t1"

    async def test_activate_with_proxy(self, endpoint_with_proxy, mock_proxy):
        """activate() calls proxy handle_command."""
        mock_proxy.handle_command = AsyncMock(return_value={"ok": True, "activated": True})
        result = await endpoint_with_proxy.activate("t1")

        mock_proxy.handle_command.assert_called_once_with(
            "activate",
            {"tenant_id": "t1", "batch_code": None},
        )
        assert result["ok"] is True


class TestInstanceEndpointGet:
    """Tests for InstanceEndpoint.get() method."""

    async def test_get_returns_instance(self, endpoint, mock_table):
        """get() returns instance configuration."""
        result = await endpoint.get()
        assert result["ok"] is True
        assert result["name"] == "test-proxy"

    async def test_get_returns_defaults_when_none(self, endpoint, mock_table):
        """get() returns defaults when no instance."""
        mock_table.get_instance = AsyncMock(return_value=None)
        result = await endpoint.get()
        assert result["ok"] is True
        assert result["id"] == 1
        assert result["name"] == "proxy"
        assert result["edition"] == "ce"


class TestInstanceEndpointUpdate:
    """Tests for InstanceEndpoint.update() method."""

    async def test_update_name(self, endpoint, mock_table):
        """update() updates name."""
        result = await endpoint.update(name="new-name")
        mock_table.update_instance.assert_called_once_with({"name": "new-name"})
        assert result["ok"] is True

    async def test_update_api_token(self, endpoint, mock_table):
        """update() updates api_token."""
        result = await endpoint.update(api_token="secret-token")
        mock_table.update_instance.assert_called_once_with({"api_token": "secret-token"})
        assert result["ok"] is True

    async def test_update_no_changes(self, endpoint, mock_table):
        """update() does nothing when no values provided."""
        result = await endpoint.update()
        mock_table.update_instance.assert_not_called()
        assert result["ok"] is True


class TestInstanceEndpointGetSyncStatus:
    """Tests for InstanceEndpoint.get_sync_status() method."""

    async def test_get_sync_status_without_proxy(self, endpoint):
        """get_sync_status() returns empty list when no proxy."""
        result = await endpoint.get_sync_status()
        assert result["ok"] is True
        assert result["tenants"] == []

    async def test_get_sync_status_with_proxy(self, endpoint_with_proxy, mock_proxy):
        """get_sync_status() calls proxy handle_command."""
        mock_proxy.handle_command = AsyncMock(return_value={
            "ok": True,
            "tenants": [{"id": "t1", "last_sync_ts": 12345}],
        })
        result = await endpoint_with_proxy.get_sync_status()

        mock_proxy.handle_command.assert_called_once_with("listTenantsSyncStatus", {})
        assert len(result["tenants"]) == 1


class TestInstanceEndpointUpgradeToEE:
    """Tests for InstanceEndpoint.upgrade_to_ee() method."""

    async def test_upgrade_already_ee(self, endpoint, mock_table):
        """upgrade_to_ee() returns message when already EE."""
        mock_table.is_enterprise = AsyncMock(return_value=True)
        result = await endpoint.upgrade_to_ee()
        assert result["edition"] == "ee"
        assert "Already" in result["message"]

    async def test_upgrade_to_ee_with_default_tenant(self, mock_table, mock_proxy):
        """upgrade_to_ee() generates token for default tenant."""
        mock_table.is_enterprise = AsyncMock(return_value=False)

        # Mock tenants table
        mock_tenants_table = MagicMock()
        mock_tenants_table.get = AsyncMock(return_value={"id": "default", "api_key_hash": None})
        mock_tenants_table.create_api_key = AsyncMock(return_value="new-token-123")
        mock_proxy.db.table = MagicMock(return_value=mock_tenants_table)

        endpoint = InstanceEndpoint(mock_table, mock_proxy)
        result = await endpoint.upgrade_to_ee()

        assert result["ok"] is True
        assert result["edition"] == "ee"
        assert result["default_tenant_token"] == "new-token-123"
        assert "Save the default tenant token" in result["message"]

    async def test_upgrade_to_ee_without_default_tenant(self, mock_table, mock_proxy):
        """upgrade_to_ee() works when no default tenant."""
        mock_table.is_enterprise = AsyncMock(return_value=False)

        # Mock tenants table without default tenant
        mock_tenants_table = MagicMock()
        mock_tenants_table.get = AsyncMock(return_value=None)
        mock_proxy.db.table = MagicMock(return_value=mock_tenants_table)

        endpoint = InstanceEndpoint(mock_table, mock_proxy)
        result = await endpoint.upgrade_to_ee()

        assert result["ok"] is True
        assert result["edition"] == "ee"
        assert "default_tenant_token" not in result
        assert "Upgraded to Enterprise Edition" in result["message"]

    async def test_upgrade_to_ee_without_proxy(self, endpoint, mock_table):
        """upgrade_to_ee() works without proxy."""
        mock_table.is_enterprise = AsyncMock(return_value=False)
        result = await endpoint.upgrade_to_ee()

        assert result["ok"] is True
        assert result["edition"] == "ee"
        mock_table.set_edition.assert_called_once_with("ee")


class TestInstanceEndpointListAll:
    """Tests for InstanceEndpoint.list_all() method."""

    async def test_list_all_empty_dir(self, endpoint_with_proxy):
        """list_all() returns empty list when no instances."""
        result = await endpoint_with_proxy.list_all()
        assert result["ok"] is True
        assert result["instances"] == []

    async def test_list_all_nonexistent_dir(self, endpoint_with_proxy, mock_proxy, tmp_path):
        """list_all() returns empty when base dir doesn't exist."""
        mock_proxy.base_dir = tmp_path / "nonexistent"
        result = await endpoint_with_proxy.list_all()
        assert result["ok"] is True
        assert result["instances"] == []

    async def test_list_all_with_config(self, endpoint_with_proxy, mock_proxy):
        """list_all() finds instance with config.ini."""
        # Create instance directory with config
        inst_dir = mock_proxy.base_dir / "test-instance"
        inst_dir.mkdir()
        config_file = inst_dir / "config.ini"
        config_file.write_text("""
[server]
name = test-instance
host = 127.0.0.1
port = 8001

[database]
path = /tmp/test.db
""")

        result = await endpoint_with_proxy.list_all()
        assert result["ok"] is True
        assert len(result["instances"]) == 1
        assert result["instances"][0]["name"] == "test-instance"
        assert result["instances"][0]["port"] == 8001
        assert result["instances"][0]["host"] == "127.0.0.1"
        assert result["instances"][0]["running"] is False

    async def test_list_all_with_db_only(self, endpoint_with_proxy, mock_proxy):
        """list_all() finds legacy instance with only database."""
        # Create instance directory with only database
        inst_dir = mock_proxy.base_dir / "legacy-instance"
        inst_dir.mkdir()
        (inst_dir / "data.db").touch()

        result = await endpoint_with_proxy.list_all()
        assert result["ok"] is True
        assert len(result["instances"]) == 1
        assert result["instances"][0]["name"] == "legacy-instance"
        assert result["instances"][0]["port"] == 8000  # default

    async def test_list_all_skips_empty_dirs(self, endpoint_with_proxy, mock_proxy):
        """list_all() skips directories without config or database."""
        # Create empty directory
        (mock_proxy.base_dir / "empty-dir").mkdir()
        # Create directory with random file
        random_dir = mock_proxy.base_dir / "random-dir"
        random_dir.mkdir()
        (random_dir / "random.txt").touch()

        result = await endpoint_with_proxy.list_all()
        assert result["ok"] is True
        assert result["instances"] == []


class TestInstanceEndpointStop:
    """Tests for InstanceEndpoint.stop() method."""

    async def test_stop_not_running(self, endpoint_with_proxy, monkeypatch):
        """stop() returns error when instance not running."""
        monkeypatch.setattr(endpoint_with_proxy, "_is_instance_running", lambda name: (False, None, None))

        result = await endpoint_with_proxy.stop(name="test-instance")
        assert result["ok"] is False
        assert "not running" in result["error"]

    async def test_stop_all_none_running(self, endpoint_with_proxy):
        """stop('*') returns empty list when none running."""
        result = await endpoint_with_proxy.stop(name="*")
        assert result["ok"] is True
        assert result["stopped"] == []
        assert result["count"] == 0


class TestInstanceEndpointRestart:
    """Tests for InstanceEndpoint.restart() method."""

    async def test_restart_not_running(self, endpoint_with_proxy, monkeypatch):
        """restart() returns error when instance not running."""
        monkeypatch.setattr(endpoint_with_proxy, "_is_instance_running", lambda name: (False, None, None))

        result = await endpoint_with_proxy.restart(name="test-instance")
        assert result["ok"] is False

    async def test_restart_all_none_running(self, endpoint_with_proxy):
        """restart('*') returns empty when none running."""
        result = await endpoint_with_proxy.restart(name="*")
        assert result["ok"] is True
        assert result["stopped"] == []


class TestInstanceEndpointHelpers:
    """Tests for private helper methods."""

    def test_get_instance_dir(self, endpoint_with_proxy, mock_proxy):
        """_get_instance_dir() returns correct path."""
        path = endpoint_with_proxy._get_instance_dir("myinstance")
        assert path.name == "myinstance"
        assert path.parent == mock_proxy.base_dir

    def test_get_pid_file(self, endpoint_with_proxy):
        """_get_pid_file() returns correct path."""
        path = endpoint_with_proxy._get_pid_file("myinstance")
        assert path.name == "server.pid"

    def test_get_config_file(self, endpoint_with_proxy):
        """_get_config_file() returns correct path."""
        path = endpoint_with_proxy._get_config_file("myinstance")
        assert path.name == "config.ini"

    def test_read_instance_config_missing(self, endpoint_with_proxy):
        """_read_instance_config() returns None for missing config."""
        result = endpoint_with_proxy._read_instance_config("nonexistent")
        assert result is None

    def test_is_instance_running_no_pid_file(self, endpoint_with_proxy):
        """_is_instance_running() returns False when no PID file."""
        running, pid, port = endpoint_with_proxy._is_instance_running("test")
        assert running is False
        assert pid is None
        assert port is None

    def test_write_pid_file(self, endpoint_with_proxy, mock_proxy):
        """_write_pid_file() creates PID file with correct content."""
        endpoint_with_proxy._write_pid_file("test-instance", 12345, 8000, "127.0.0.1")

        pid_file = mock_proxy.base_dir / "test-instance" / "server.pid"
        assert pid_file.exists()

        import json
        data = json.loads(pid_file.read_text())
        assert data["pid"] == 12345
        assert data["port"] == 8000
        assert data["host"] == "127.0.0.1"
        assert "started_at" in data

    def test_ensure_instance_config_creates_new(self, endpoint_with_proxy, mock_proxy):
        """_ensure_instance_config() creates config for new instance."""
        config = endpoint_with_proxy._ensure_instance_config("new-instance", 8080, "0.0.0.0")

        assert config["name"] == "new-instance"
        assert config["port"] == 8080
        assert config["host"] == "0.0.0.0"

        config_file = mock_proxy.base_dir / "new-instance" / "config.ini"
        assert config_file.exists()

    def test_ensure_instance_config_preserves_existing(self, endpoint_with_proxy, mock_proxy):
        """_ensure_instance_config() doesn't overwrite existing config."""
        # Create existing config
        inst_dir = mock_proxy.base_dir / "existing-instance"
        inst_dir.mkdir()
        config_file = inst_dir / "config.ini"
        config_file.write_text("""
[server]
name = existing-instance
host = 192.168.1.1
port = 9000

[database]
path = /custom/path/data.db
""")

        config = endpoint_with_proxy._ensure_instance_config("existing-instance", 8080, "0.0.0.0")

        # Should return existing config, not override with new values
        assert config["name"] == "existing-instance"
        assert config["port"] == 9000
        assert config["host"] == "192.168.1.1"


class TestInstanceEndpointServe:
    """Tests for InstanceEndpoint.serve() method."""

    async def test_serve_already_running(self, endpoint_with_proxy, monkeypatch):
        """serve() returns info when instance already running."""
        monkeypatch.setattr(
            endpoint_with_proxy, "_is_instance_running",
            lambda name: (True, 12345, 8000)
        )

        result = await endpoint_with_proxy.serve(name="test-instance")
        assert result["ok"] is True
        assert result["already_running"] is True
        assert result["pid"] == 12345
        assert result["port"] == 8000

    async def test_serve_new_instance(self, endpoint_with_proxy, monkeypatch):
        """serve() creates new instance config."""
        monkeypatch.setattr(
            endpoint_with_proxy, "_is_instance_running",
            lambda name: (False, None, None)
        )

        result = await endpoint_with_proxy.serve(name="new-instance", port=8080, host="127.0.0.1")
        assert result["ok"] is True
        assert result["name"] == "new-instance"
        assert result["port"] == 8080
        assert result["host"] == "127.0.0.1"
        assert "env" in result
        assert result["env"]["GENRO_PROXY_PORT"] == "8080"

    async def test_serve_existing_instance(self, endpoint_with_proxy, mock_proxy, monkeypatch):
        """serve() uses existing instance config."""
        monkeypatch.setattr(
            endpoint_with_proxy, "_is_instance_running",
            lambda name: (False, None, None)
        )

        # Create existing config
        inst_dir = mock_proxy.base_dir / "existing"
        inst_dir.mkdir()
        config_file = inst_dir / "config.ini"
        config_file.write_text("""
[server]
name = existing
host = 192.168.1.1
port = 9000

[database]
path = /custom/path/data.db
""")

        result = await endpoint_with_proxy.serve(name="existing")
        assert result["ok"] is True
        assert result["port"] == 9000
        assert result["host"] == "192.168.1.1"

    async def test_serve_override_existing_config(self, endpoint_with_proxy, mock_proxy, monkeypatch):
        """serve() allows overriding existing config values."""
        monkeypatch.setattr(
            endpoint_with_proxy, "_is_instance_running",
            lambda name: (False, None, None)
        )

        # Create existing config
        inst_dir = mock_proxy.base_dir / "override-test"
        inst_dir.mkdir()
        config_file = inst_dir / "config.ini"
        config_file.write_text("""
[server]
name = override-test
host = 192.168.1.1
port = 9000

[database]
path = /custom/path/data.db
""")

        # Override port and host
        result = await endpoint_with_proxy.serve(name="override-test", port=7000, host="0.0.0.0")
        assert result["ok"] is True
        assert result["port"] == 7000
        assert result["host"] == "0.0.0.0"
