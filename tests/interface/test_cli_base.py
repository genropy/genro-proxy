# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for CLI command generation from endpoints.

Note: CLI functionality is tested through the exposed surface (CliRunner)
in integration tests. This module tests utility functions and CliManager.
"""

import inspect
from typing import Literal
from unittest.mock import MagicMock, patch

import click
import pytest

from genro_proxy.interface.cli_base import (
    CliManager,
    _annotation_to_click_type,
    _print_result,
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

    def test_print_dict(self):
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
