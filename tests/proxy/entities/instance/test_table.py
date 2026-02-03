# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for InstanceTable."""

import pytest
import pytest_asyncio

from genro_proxy.entities.instance.table import InstanceTable
from genro_proxy.sql import SqlDb


@pytest_asyncio.fixture
async def instance_table(sqlite_db: SqlDb) -> InstanceTable:
    """Create an InstanceTable with SQLite for testing."""
    table = InstanceTable(sqlite_db)
    await table.create_schema()
    return table


class TestGetInstance:
    """Tests for InstanceTable.get_instance() method."""

    async def test_get_instance_when_not_exists(self, instance_table: InstanceTable):
        """get_instance returns empty dict when no instance exists."""
        result = await instance_table.get_instance()
        assert result == {}

    async def test_get_instance_when_exists(self, instance_table: InstanceTable):
        """get_instance returns instance when exists."""
        await instance_table.insert({"id": 1, "name": "test"})

        result = await instance_table.get_instance()

        assert result is not None
        assert result["id"] == 1
        assert result["name"] == "test"


class TestEnsureInstance:
    """Tests for InstanceTable.ensure_instance() method."""

    async def test_creates_instance_if_not_exists(self, instance_table: InstanceTable):
        """ensure_instance creates instance if not exists."""
        result = await instance_table.ensure_instance()

        assert result is not None
        assert result["id"] == 1

    async def test_returns_existing_instance(self, instance_table: InstanceTable):
        """ensure_instance returns existing instance."""
        await instance_table.insert({"id": 1, "name": "existing"})

        result = await instance_table.ensure_instance()

        assert result["name"] == "existing"


class TestUpdateInstance:
    """Tests for InstanceTable.update_instance() method."""

    async def test_update_creates_if_not_exists(self, instance_table: InstanceTable):
        """update_instance creates instance if not exists."""
        await instance_table.update_instance({"name": "new name"})

        result = await instance_table.get_instance()
        assert result is not None
        assert result["name"] == "new name"

    async def test_update_multiple_fields(self, instance_table: InstanceTable):
        """update_instance updates multiple fields."""
        await instance_table.ensure_instance()
        await instance_table.update_instance({
            "name": "updated",
            "api_token": "token123",
        })

        result = await instance_table.get_instance()
        assert result["name"] == "updated"
        assert result["api_token"] == "token123"


class TestGetSetName:
    """Tests for InstanceTable name getter/setter."""

    async def test_get_name_default(self, instance_table: InstanceTable):
        """get_name returns 'proxy' as default."""
        name = await instance_table.get_name()
        assert name == "proxy"

    async def test_set_and_get_name(self, instance_table: InstanceTable):
        """set_name then get_name returns set value."""
        await instance_table.set_name("my-proxy")

        name = await instance_table.get_name()
        assert name == "my-proxy"


class TestGetSetApiToken:
    """Tests for InstanceTable api_token getter/setter."""

    async def test_get_api_token_default(self, instance_table: InstanceTable):
        """get_api_token returns None as default."""
        token = await instance_table.get_api_token()
        assert token is None

    async def test_set_and_get_api_token(self, instance_table: InstanceTable):
        """set_api_token then get_api_token returns set value."""
        await instance_table.set_api_token("secret-token-123")

        token = await instance_table.get_api_token()
        assert token == "secret-token-123"


class TestGetSetEdition:
    """Tests for InstanceTable edition getter/setter."""

    async def test_get_edition_default(self, instance_table: InstanceTable):
        """get_edition returns 'ce' as default."""
        edition = await instance_table.get_edition()
        assert edition == "ce"

    async def test_set_and_get_edition(self, instance_table: InstanceTable):
        """set_edition then get_edition returns set value."""
        await instance_table.set_edition("ee")

        edition = await instance_table.get_edition()
        assert edition == "ee"

    async def test_set_invalid_edition_raises(self, instance_table: InstanceTable):
        """set_edition with invalid value raises ValueError."""
        with pytest.raises(ValueError, match="Invalid edition"):
            await instance_table.set_edition("invalid")


class TestIsEnterprise:
    """Tests for InstanceTable.is_enterprise() method."""

    async def test_is_enterprise_default_false(self, instance_table: InstanceTable):
        """is_enterprise returns False by default."""
        result = await instance_table.is_enterprise()
        assert result is False

    async def test_is_enterprise_when_ee(self, instance_table: InstanceTable):
        """is_enterprise returns True when edition is 'ee'."""
        await instance_table.set_edition("ee")

        result = await instance_table.is_enterprise()
        assert result is True

    async def test_is_enterprise_when_ce(self, instance_table: InstanceTable):
        """is_enterprise returns False when edition is 'ce'."""
        await instance_table.set_edition("ce")

        result = await instance_table.is_enterprise()
        assert result is False


class TestGetSetConfig:
    """Tests for InstanceTable config getter/setter (dual access)."""

    async def test_get_config_typed_key(self, instance_table: InstanceTable):
        """get_config with typed key returns column value."""
        await instance_table.set_name("test-name")

        value = await instance_table.get_config("name")
        assert value == "test-name"

    async def test_get_config_json_key(self, instance_table: InstanceTable):
        """get_config with non-typed key returns JSON config value."""
        await instance_table.set_config("custom_key", "custom_value")

        value = await instance_table.get_config("custom_key")
        assert value == "custom_value"

    async def test_get_config_missing_returns_default(self, instance_table: InstanceTable):
        """get_config with missing key returns default."""
        value = await instance_table.get_config("missing", "default_val")
        assert value == "default_val"

    async def test_get_config_missing_returns_none(self, instance_table: InstanceTable):
        """get_config with missing key returns None if no default."""
        value = await instance_table.get_config("missing")
        assert value is None

    async def test_set_config_typed_key(self, instance_table: InstanceTable):
        """set_config with typed key updates column."""
        await instance_table.set_config("name", "new-name")

        row = await instance_table.get_instance()
        assert row["name"] == "new-name"

    async def test_set_config_json_key(self, instance_table: InstanceTable):
        """set_config with non-typed key updates JSON config."""
        await instance_table.set_config("my_setting", "my_value")

        row = await instance_table.get_instance()
        assert row["config"]["my_setting"] == "my_value"

    async def test_set_config_preserves_existing_json(self, instance_table: InstanceTable):
        """set_config preserves existing JSON config values."""
        await instance_table.set_config("key1", "value1")
        await instance_table.set_config("key2", "value2")

        row = await instance_table.get_instance()
        assert row["config"]["key1"] == "value1"
        assert row["config"]["key2"] == "value2"


class TestGetAllConfig:
    """Tests for InstanceTable.get_all_config() method."""

    async def test_get_all_config_empty(self, instance_table: InstanceTable):
        """get_all_config returns only set values."""
        result = await instance_table.get_all_config()

        # Default values should be present
        assert "name" in result or result == {}

    async def test_get_all_config_merges_typed_and_json(self, instance_table: InstanceTable):
        """get_all_config merges typed columns and JSON config."""
        await instance_table.set_name("test-instance")
        await instance_table.set_edition("ee")
        await instance_table.set_config("custom1", "value1")
        await instance_table.set_config("custom2", "value2")

        result = await instance_table.get_all_config()

        assert result["name"] == "test-instance"
        assert result["edition"] == "ee"
        assert result["custom1"] == "value1"
        assert result["custom2"] == "value2"
