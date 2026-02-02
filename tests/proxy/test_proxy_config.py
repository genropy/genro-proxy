# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for proxy_config module."""

import pytest

from proxy.proxy_base import ProxyConfigBase, config_from_env


class TestProxyConfigBase:
    """Tests for ProxyConfigBase dataclass."""

    def test_default_values(self):
        """Default values should be set correctly."""
        config = ProxyConfigBase()
        assert config.db_path == "/data/service.db"
        assert config.instance_name == "proxy"
        assert config.port == 8000
        assert config.api_token is None
        assert config.test_mode is False
        assert config.start_active is False

    def test_custom_values(self):
        """Custom values should override defaults."""
        config = ProxyConfigBase(
            db_path="/custom/path.db",
            instance_name="my-proxy",
            port=9000,
            api_token="secret-token",
            test_mode=True,
            start_active=True,
        )
        assert config.db_path == "/custom/path.db"
        assert config.instance_name == "my-proxy"
        assert config.port == 9000
        assert config.api_token == "secret-token"
        assert config.test_mode is True
        assert config.start_active is True


class TestConfigFromEnv:
    """Tests for config_from_env() function."""

    def test_default_values_when_no_env(self, monkeypatch):
        """Should use defaults when no env vars set."""
        # Clear all GENRO_PROXY_* env vars
        monkeypatch.delenv("GENRO_PROXY_DB", raising=False)
        monkeypatch.delenv("GENRO_PROXY_API_TOKEN", raising=False)
        monkeypatch.delenv("GENRO_PROXY_INSTANCE", raising=False)
        monkeypatch.delenv("GENRO_PROXY_PORT", raising=False)
        monkeypatch.delenv("GENRO_PROXY_TEST_MODE", raising=False)
        monkeypatch.delenv("GENRO_PROXY_START_ACTIVE", raising=False)

        config = config_from_env()

        assert config.db_path == "/data/service.db"
        assert config.instance_name == "proxy"
        assert config.port == 8000
        assert config.api_token is None
        assert config.test_mode is False
        assert config.start_active is False

    def test_reads_db_path_from_env(self, monkeypatch):
        """Should read GENRO_PROXY_DB from environment."""
        monkeypatch.setenv("GENRO_PROXY_DB", "/custom/database.db")

        config = config_from_env()

        assert config.db_path == "/custom/database.db"

    def test_reads_api_token_from_env(self, monkeypatch):
        """Should read GENRO_PROXY_API_TOKEN from environment."""
        monkeypatch.setenv("GENRO_PROXY_API_TOKEN", "my-secret-token")

        config = config_from_env()

        assert config.api_token == "my-secret-token"

    def test_reads_instance_name_from_env(self, monkeypatch):
        """Should read GENRO_PROXY_INSTANCE from environment."""
        monkeypatch.setenv("GENRO_PROXY_INSTANCE", "production-proxy")

        config = config_from_env()

        assert config.instance_name == "production-proxy"

    def test_reads_port_from_env(self, monkeypatch):
        """Should read GENRO_PROXY_PORT from environment."""
        monkeypatch.setenv("GENRO_PROXY_PORT", "9000")

        config = config_from_env()

        assert config.port == 9000

    def test_reads_test_mode_true_from_env(self, monkeypatch):
        """Should read GENRO_PROXY_TEST_MODE=true from environment."""
        monkeypatch.setenv("GENRO_PROXY_TEST_MODE", "true")

        config = config_from_env()

        assert config.test_mode is True

    def test_reads_test_mode_1_from_env(self, monkeypatch):
        """Should read GENRO_PROXY_TEST_MODE=1 from environment."""
        monkeypatch.setenv("GENRO_PROXY_TEST_MODE", "1")

        config = config_from_env()

        assert config.test_mode is True

    def test_reads_test_mode_yes_from_env(self, monkeypatch):
        """Should read GENRO_PROXY_TEST_MODE=yes from environment."""
        monkeypatch.setenv("GENRO_PROXY_TEST_MODE", "yes")

        config = config_from_env()

        assert config.test_mode is True

    def test_test_mode_false_for_other_values(self, monkeypatch):
        """Should be False for non-truthy values."""
        monkeypatch.setenv("GENRO_PROXY_TEST_MODE", "false")

        config = config_from_env()

        assert config.test_mode is False

    def test_reads_start_active_from_env(self, monkeypatch):
        """Should read GENRO_PROXY_START_ACTIVE from environment."""
        monkeypatch.setenv("GENRO_PROXY_START_ACTIVE", "true")

        config = config_from_env()

        assert config.start_active is True

    def test_all_env_vars_together(self, monkeypatch):
        """Should read all env vars correctly together."""
        monkeypatch.setenv("GENRO_PROXY_DB", "postgresql://localhost/proxy")
        monkeypatch.setenv("GENRO_PROXY_API_TOKEN", "prod-token")
        monkeypatch.setenv("GENRO_PROXY_INSTANCE", "prod-01")
        monkeypatch.setenv("GENRO_PROXY_PORT", "8080")
        monkeypatch.setenv("GENRO_PROXY_TEST_MODE", "false")
        monkeypatch.setenv("GENRO_PROXY_START_ACTIVE", "1")

        config = config_from_env()

        assert config.db_path == "postgresql://localhost/proxy"
        assert config.api_token == "prod-token"
        assert config.instance_name == "prod-01"
        assert config.port == 8080
        assert config.test_mode is False
        assert config.start_active is True
