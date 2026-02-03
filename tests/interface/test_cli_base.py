# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for CLI command generation from endpoints."""

import asyncio
import inspect
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from genro_proxy.interface.cli_base import (
    CliManager,
    _annotation_to_click_type,
    _create_click_command,
    _print_result,
    register_endpoint,
)


class TestAnnotationToClickType:
    """Tests for _annotation_to_click_type function."""

    def test_empty_annotation_returns_str(self):
        """Empty annotation defaults to str."""
        result = _annotation_to_click_type(inspect.Parameter.empty)
        assert result is str

    def test_any_annotation_returns_str(self):
        """Any annotation defaults to str."""
        from typing import Any
        result = _annotation_to_click_type(Any)
        assert result is str

    def test_int_annotation(self):
        """int annotation returns int."""
        result = _annotation_to_click_type(int)
        assert result is int

    def test_bool_annotation(self):
        """bool annotation returns bool."""
        result = _annotation_to_click_type(bool)
        assert result is bool

    def test_float_annotation(self):
        """float annotation returns float."""
        result = _annotation_to_click_type(float)
        assert result is float

    def test_str_annotation(self):
        """str annotation returns str."""
        result = _annotation_to_click_type(str)
        assert result is str

    def test_optional_int_returns_int(self):
        """Optional[int] returns int."""
        result = _annotation_to_click_type(int | None)
        assert result is int

    def test_literal_returns_choice(self):
        """Literal returns click.Choice."""
        result = _annotation_to_click_type(Literal["a", "b", "c"])
        assert isinstance(result, click.Choice)
        assert list(result.choices) == ["a", "b", "c"]

    def test_none_type_returns_str(self):
        """None type returns str."""
        result = _annotation_to_click_type(type(None))
        assert result is str


class TestPrintResult:
    """Tests for _print_result function."""

    def test_print_dict(self, capsys):
        """Print dict as key-value pairs."""
        with patch("genro_proxy.interface.cli_base.console") as mock_console:
            _print_result({"key1": "value1", "key2": "value2"})
            assert mock_console.print.call_count == 2

    def test_print_list_of_dicts(self):
        """Print list of dicts as table."""
        with patch("genro_proxy.interface.cli_base.console") as mock_console:
            _print_result([{"id": "1", "name": "test"}])
            mock_console.print.assert_called_once()

    def test_print_simple_list(self):
        """Print simple list with bullets."""
        with patch("genro_proxy.interface.cli_base.console") as mock_console:
            _print_result(["item1", "item2"])
            assert mock_console.print.call_count == 2

    def test_print_string(self):
        """Print string directly."""
        with patch("genro_proxy.interface.cli_base.console") as mock_console:
            _print_result("hello")
            mock_console.print.assert_called_once_with("hello")

    def test_print_empty_list(self):
        """Print empty list."""
        with patch("genro_proxy.interface.cli_base.console") as mock_console:
            _print_result([])
            mock_console.print.assert_not_called()


class TestCreateClickCommand:
    """Tests for _create_click_command function."""

    def test_creates_command_for_simple_method(self):
        """Create command for method with no parameters."""
        class TestEndpoint:
            name = "test"

            async def simple(self):
                """Simple method."""
                return {"ok": True}

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        endpoint = TestEndpoint()
        cmd = _create_click_command(endpoint, "simple", asyncio.run)

        assert isinstance(cmd, click.Command)
        assert cmd.help == "Simple method."

    def test_creates_command_with_required_params(self):
        """Create command with required positional arguments."""
        class TestEndpoint:
            name = "test"

            async def with_args(self, id: str, name: str):
                """Method with args."""
                return {"id": id, "name": name}

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        endpoint = TestEndpoint()
        cmd = _create_click_command(endpoint, "with_args", asyncio.run)

        # Check that arguments were created
        assert len(cmd.params) == 2

    def test_creates_command_with_optional_params(self):
        """Create command with optional parameters as options."""
        class TestEndpoint:
            name = "test"

            async def with_options(self, name: str = "default"):
                """Method with options."""
                return {"name": name}

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        endpoint = TestEndpoint()
        cmd = _create_click_command(endpoint, "with_options", asyncio.run)

        # Check that option was created
        assert len(cmd.params) == 1
        assert cmd.params[0].default == "default"

    def test_creates_command_with_bool_flag(self):
        """Create command with boolean flag."""
        class TestEndpoint:
            name = "test"

            async def with_flag(self, enabled: bool = False):
                """Method with flag."""
                return {"enabled": enabled}

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        endpoint = TestEndpoint()
        cmd = _create_click_command(endpoint, "with_flag", asyncio.run)

        # Check that flag was created
        assert len(cmd.params) == 1

    def test_tenant_id_becomes_optional_positional(self):
        """tenant_id becomes optional positional with context fallback."""
        class TestEndpoint:
            name = "test"

            async def with_tenant(self, tenant_id: str):
                """Method requiring tenant."""
                return {"tenant_id": tenant_id}

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        endpoint = TestEndpoint()
        cmd = _create_click_command(endpoint, "with_tenant", asyncio.run)

        # Check that tenant_id is optional
        assert len(cmd.params) == 1
        assert cmd.params[0].required is False


class TestRegisterEndpoint:
    """Tests for register_endpoint function."""

    def test_registers_endpoint_as_group(self):
        """Register endpoint creates a subgroup."""
        class TestEndpoint:
            name = "myendpoint"

            async def list(self):
                """List items."""
                return []

        @click.group()
        def cli():
            pass

        endpoint = TestEndpoint()
        register_endpoint(cli, endpoint)

        # Check that subgroup was created
        assert "myendpoint" in cli.commands

    def test_registers_all_async_methods(self):
        """Register all async methods as commands."""
        class TestEndpoint:
            name = "items"

            async def list(self):
                """List items."""
                return []

            async def get(self, id: str):
                """Get item."""
                return {}

            async def add(self, name: str):
                """Add item."""
                return {}

            def sync_method(self):
                """Sync method should be ignored."""
                pass

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        @click.group()
        def cli():
            pass

        endpoint = TestEndpoint()
        register_endpoint(cli, endpoint)

        group = cli.commands["items"]
        # Should have list, get, add, invoke - but not sync_method
        assert "list" in group.commands
        assert "get" in group.commands
        assert "add" in group.commands
        assert "sync-method" not in group.commands

    def test_uses_class_name_if_no_name_attr(self):
        """Use class name lowercased if no name attribute."""
        class MyCustomEndpoint:
            async def test(self):
                return {}

        @click.group()
        def cli():
            pass

        endpoint = MyCustomEndpoint()
        register_endpoint(cli, endpoint)

        assert "mycustomendpoint" in cli.commands

    def test_replaces_underscores_with_dashes(self):
        """Method names with underscores become dashed commands."""
        class TestEndpoint:
            name = "test"

            async def get_all_items(self):
                """Get all items."""
                return []

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        @click.group()
        def cli():
            pass

        endpoint = TestEndpoint()
        register_endpoint(cli, endpoint)

        group = cli.commands["test"]
        assert "get-all-items" in group.commands


class TestCliManager:
    """Tests for CliManager class."""

    def test_init_stores_proxy(self):
        """CliManager stores proxy reference."""
        proxy = MagicMock()
        manager = CliManager(proxy)
        assert manager.proxy is proxy
        assert manager._cli is None

    def test_cli_property_creates_lazily(self):
        """cli property creates CLI lazily."""
        proxy = MagicMock()
        proxy.endpoints = {}
        proxy.config.port = 8000

        manager = CliManager(proxy)
        assert manager._cli is None

        cli = manager.cli
        assert cli is not None
        assert manager._cli is cli

    def test_cli_property_returns_same_instance(self):
        """cli property returns same instance on multiple calls."""
        proxy = MagicMock()
        proxy.endpoints = {}
        proxy.config.port = 8000

        manager = CliManager(proxy)

        cli1 = manager.cli
        cli2 = manager.cli
        assert cli1 is cli2

    def test_cli_has_serve_command(self):
        """CLI has serve command."""
        proxy = MagicMock()
        proxy.endpoints = {}
        proxy.config.port = 8000

        manager = CliManager(proxy)
        cli = manager.cli

        assert "serve" in cli.commands

    def test_get_server_module_returns_default(self):
        """_get_server_module returns default path."""
        proxy = MagicMock()
        manager = CliManager(proxy)
        assert manager._get_server_module() == "genro_proxy.server:app"


class TestCliIntegration:
    """Integration tests using CliRunner."""

    def test_command_execution(self):
        """Test actual command execution with CliRunner."""
        class TestEndpoint:
            name = "test"

            async def hello(self, name: str = "World"):
                """Say hello."""
                return {"message": f"Hello, {name}!"}

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        @click.group()
        def cli():
            pass

        endpoint = TestEndpoint()
        register_endpoint(cli, endpoint)

        runner = CliRunner()
        result = runner.invoke(cli, ["test", "hello", "--name", "Test"])

        assert result.exit_code == 0
        assert "Hello" in result.output

    def test_command_with_positional_args(self):
        """Test command with positional arguments."""
        class TestEndpoint:
            name = "items"

            async def get(self, id: str):
                """Get item by ID."""
                return {"id": id}

            async def invoke(self, method_name, params):
                return await getattr(self, method_name)(**params)

        @click.group()
        def cli():
            pass

        endpoint = TestEndpoint()
        register_endpoint(cli, endpoint)

        runner = CliRunner()
        result = runner.invoke(cli, ["items", "get", "item-123"])

        assert result.exit_code == 0
        assert "item-123" in result.output
