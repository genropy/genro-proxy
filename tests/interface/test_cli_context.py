# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for CLI context management."""

import os
from pathlib import Path

import pytest

from genro_proxy.interface.cli_context import CliContext


class TestCliContextParseContext:
    """Tests for parse_context method."""

    def test_instance_only(self):
        """Parse instance without tenant."""
        ctx = CliContext()
        assert ctx.parse_context("production") == ("production", None)

    def test_instance_and_tenant(self):
        """Parse instance/tenant format."""
        ctx = CliContext()
        assert ctx.parse_context("production/acme") == ("production", "acme")

    def test_tenant_only(self):
        """Parse /tenant format (keep current instance)."""
        ctx = CliContext()
        assert ctx.parse_context("/acme") == (None, "acme")

    def test_instance_explicit_no_tenant(self):
        """Parse instance/ format (explicit no tenant)."""
        ctx = CliContext()
        assert ctx.parse_context("production/") == ("production", None)


class TestCliContextResolveContext:
    """Tests for resolve_context method."""

    def test_explicit_overrides_all(self, tmp_path, monkeypatch):
        """Explicit arguments override env and file."""
        ctx = CliContext(base_dir=tmp_path)
        monkeypatch.setenv("GPROXY_INSTANCE", "env_instance")
        monkeypatch.setenv("GPROXY_TENANT", "env_tenant")

        instance, tenant = ctx.resolve_context(
            explicit_instance="explicit",
            explicit_tenant="explicit_tenant",
        )

        assert instance == "explicit"
        assert tenant == "explicit_tenant"

    def test_env_overrides_file(self, tmp_path, monkeypatch):
        """Env vars override .current file."""
        ctx = CliContext(base_dir=tmp_path)
        ctx.set_current_context("file_instance", "file_tenant")
        monkeypatch.setenv("GPROXY_INSTANCE", "env_instance")
        monkeypatch.setenv("GPROXY_TENANT", "env_tenant")

        instance, tenant = ctx.resolve_context()

        assert instance == "env_instance"
        assert tenant == "env_tenant"

    def test_file_fallback(self, tmp_path, monkeypatch):
        """Falls back to .current file when no env vars."""
        ctx = CliContext(base_dir=tmp_path)
        ctx.set_current_context("file_instance", "file_tenant")
        monkeypatch.delenv("GPROXY_INSTANCE", raising=False)
        monkeypatch.delenv("GPROXY_TENANT", raising=False)

        instance, tenant = ctx.resolve_context()

        assert instance == "file_instance"
        assert tenant == "file_tenant"

    def test_auto_select_single_instance(self, tmp_path, monkeypatch):
        """Auto-select when only one instance exists."""
        ctx = CliContext(base_dir=tmp_path, db_name="proxy.db")
        monkeypatch.delenv("GPROXY_INSTANCE", raising=False)
        monkeypatch.delenv("GPROXY_TENANT", raising=False)

        # Create single instance
        (tmp_path / "only_one").mkdir()
        (tmp_path / "only_one" / "proxy.db").touch()

        instance, tenant = ctx.resolve_context()

        assert instance == "only_one"
        assert tenant is None

    def test_no_auto_select_multiple_instances(self, tmp_path, monkeypatch):
        """No auto-select when multiple instances exist."""
        ctx = CliContext(base_dir=tmp_path, db_name="proxy.db")
        monkeypatch.delenv("GPROXY_INSTANCE", raising=False)
        monkeypatch.delenv("GPROXY_TENANT", raising=False)

        # Create multiple instances
        (tmp_path / "instance1").mkdir()
        (tmp_path / "instance1" / "proxy.db").touch()
        (tmp_path / "instance2").mkdir()
        (tmp_path / "instance2" / "proxy.db").touch()

        instance, tenant = ctx.resolve_context()

        assert instance is None
        assert tenant is None


class TestCliContextCurrentFile:
    """Tests for .current file operations."""

    def test_set_and_get_instance_only(self, tmp_path):
        """Set and get instance without tenant."""
        ctx = CliContext(base_dir=tmp_path)
        ctx.set_current_context("production", None)

        instance, tenant = ctx.get_current_context()

        assert instance == "production"
        assert tenant is None

    def test_set_and_get_instance_and_tenant(self, tmp_path):
        """Set and get instance with tenant."""
        ctx = CliContext(base_dir=tmp_path)
        ctx.set_current_context("production", "acme")

        instance, tenant = ctx.get_current_context()

        assert instance == "production"
        assert tenant == "acme"

    def test_get_nonexistent(self, tmp_path):
        """Get context when no .current file."""
        ctx = CliContext(base_dir=tmp_path)

        instance, tenant = ctx.get_current_context()

        assert instance is None
        assert tenant is None


class TestCliContextListInstances:
    """Tests for list_instances method."""

    def test_empty_dir(self, tmp_path):
        """Empty base dir returns empty list."""
        ctx = CliContext(base_dir=tmp_path)
        assert ctx.list_instances() == []

    def test_nonexistent_dir(self, tmp_path):
        """Nonexistent base dir returns empty list."""
        ctx = CliContext(base_dir=tmp_path / "nonexistent")
        assert ctx.list_instances() == []

    def test_finds_instances_by_db(self, tmp_path):
        """Finds instances by database file."""
        ctx = CliContext(base_dir=tmp_path, db_name="proxy.db")

        (tmp_path / "instance1").mkdir()
        (tmp_path / "instance1" / "proxy.db").touch()
        (tmp_path / "instance2").mkdir()
        (tmp_path / "instance2" / "proxy.db").touch()
        (tmp_path / "not_an_instance").mkdir()  # No db file

        instances = ctx.list_instances()

        assert sorted(instances) == ["instance1", "instance2"]

    def test_finds_instances_by_config(self, tmp_path):
        """Finds instances by config.ini file."""
        ctx = CliContext(base_dir=tmp_path, db_name="proxy.db")

        (tmp_path / "instance1").mkdir()
        (tmp_path / "instance1" / "config.ini").touch()

        instances = ctx.list_instances()

        assert instances == ["instance1"]


class TestCliContextRequireContext:
    """Tests for require_context method."""

    def test_require_context_returns_resolved(self, tmp_path, monkeypatch):
        """require_context returns resolved instance and tenant."""
        ctx = CliContext(base_dir=tmp_path, db_name="proxy.db")
        monkeypatch.setenv("GPROXY_INSTANCE", "my_instance")
        monkeypatch.setenv("GPROXY_TENANT", "my_tenant")

        instance, tenant = ctx.require_context()

        assert instance == "my_instance"
        assert tenant == "my_tenant"

    def test_require_context_exits_no_instances(self, tmp_path, monkeypatch):
        """require_context exits with error if no instances configured."""
        messages = []
        ctx = CliContext(base_dir=tmp_path, db_name="proxy.db", print_func=messages.append)
        monkeypatch.delenv("GPROXY_INSTANCE", raising=False)
        monkeypatch.delenv("GPROXY_TENANT", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            ctx.require_context()

        assert exc_info.value.code == 1
        assert any("No instances configured" in msg for msg in messages)

    def test_require_context_exits_multiple_instances(self, tmp_path, monkeypatch):
        """require_context exits with error if multiple instances and none selected."""
        messages = []
        ctx = CliContext(base_dir=tmp_path, db_name="proxy.db", print_func=messages.append)
        monkeypatch.delenv("GPROXY_INSTANCE", raising=False)
        monkeypatch.delenv("GPROXY_TENANT", raising=False)

        # Create multiple instances
        (tmp_path / "instance1").mkdir()
        (tmp_path / "instance1" / "proxy.db").touch()
        (tmp_path / "instance2").mkdir()
        (tmp_path / "instance2" / "proxy.db").touch()

        with pytest.raises(SystemExit) as exc_info:
            ctx.require_context()

        assert exc_info.value.code == 1
        assert any("Multiple instances found" in msg for msg in messages)

    def test_require_context_exits_tenant_required(self, tmp_path, monkeypatch):
        """require_context exits with error if tenant required but missing."""
        messages = []
        ctx = CliContext(base_dir=tmp_path, db_name="proxy.db", print_func=messages.append)
        monkeypatch.setenv("GPROXY_INSTANCE", "my_instance")
        monkeypatch.delenv("GPROXY_TENANT", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            ctx.require_context(require_tenant=True)

        assert exc_info.value.code == 1
        assert any("Tenant required" in msg for msg in messages)

    def test_require_context_with_explicit_values(self, tmp_path, monkeypatch):
        """require_context uses explicit values over env vars."""
        ctx = CliContext(base_dir=tmp_path)
        monkeypatch.setenv("GPROXY_INSTANCE", "env_instance")
        monkeypatch.setenv("GPROXY_TENANT", "env_tenant")

        instance, tenant = ctx.require_context(
            explicit_instance="explicit_inst",
            explicit_tenant="explicit_ten",
        )

        assert instance == "explicit_inst"
        assert tenant == "explicit_ten"


class TestCliContextCustomConfiguration:
    """Tests for custom CliContext configuration."""

    def test_custom_env_vars(self, tmp_path, monkeypatch):
        """Custom env var names work correctly."""
        ctx = CliContext(
            base_dir=tmp_path,
            env_instance="CUSTOM_INSTANCE",
            env_tenant="CUSTOM_TENANT",
        )
        monkeypatch.setenv("CUSTOM_INSTANCE", "my_instance")
        monkeypatch.setenv("CUSTOM_TENANT", "my_tenant")

        instance, tenant = ctx.resolve_context()

        assert instance == "my_instance"
        assert tenant == "my_tenant"

    def test_custom_db_name(self, tmp_path, monkeypatch):
        """Custom db name for instance detection."""
        ctx = CliContext(base_dir=tmp_path, db_name="mail_service.db")
        monkeypatch.delenv("GPROXY_INSTANCE", raising=False)

        (tmp_path / "mail_instance").mkdir()
        (tmp_path / "mail_instance" / "mail_service.db").touch()

        instances = ctx.list_instances()

        assert instances == ["mail_instance"]
