# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Click command generation from endpoint classes via introspection.

This module generates CLI commands automatically from endpoint classes
by introspecting method signatures and creating Click commands.

Components:
    register_endpoint: Register endpoint methods as Click commands.

Example:
    Register endpoint commands::

        import click
        from proxy.interface import register_endpoint
        from myservice.entities.account import AccountEndpoint

        @click.group()
        def cli():
            pass

        endpoint = AccountEndpoint(table)
        register_endpoint(cli, endpoint)
        # Creates: cli accounts add, cli accounts get, cli accounts list

    Generated commands::

        myservice accounts list                    # uses context tenant
        myservice accounts list acme               # explicit tenant
        myservice accounts add main --host smtp.example.com
        myservice tenants list

Note:
    - tenant_id is special: optional positional with context fallback
    - Other required params become positional arguments
    - Optional params become --options
    - Boolean params become --flag/--no-flag toggles
    - Method underscores become dashes (add_batch → add-batch)
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Literal, get_args, get_origin

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _print_result(result: Any) -> None:
    """Print command result with rich formatting."""
    if isinstance(result, list) and result and isinstance(result[0], dict):
        # List of dicts → table
        table = Table(show_header=True, header_style="bold cyan")
        keys = list(result[0].keys())
        for key in keys:
            table.add_column(key)
        for row in result:
            table.add_row(*[str(row.get(k, "")) for k in keys])
        console.print(table)
    elif isinstance(result, dict):
        # Single dict → key: value pairs
        for key, value in result.items():
            console.print(f"[bold]{key}:[/bold] {value}")
    elif isinstance(result, list):
        # Simple list
        for item in result:
            console.print(f"  • {item}")
    else:
        console.print(result)


def _annotation_to_click_type(annotation: Any) -> type | click.Choice:
    """Convert Python type annotation to Click type.

    Args:
        annotation: Python type annotation.

    Returns:
        Click-compatible type (int, str, bool, float, or click.Choice).
    """
    if annotation is inspect.Parameter.empty or annotation is Any:
        return str

    origin = get_origin(annotation)
    if origin is type(None):
        return str

    args = get_args(annotation)
    if origin is type(int | str):  # UnionType
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            annotation = non_none[0]

    if get_origin(annotation) is Literal:
        choices = get_args(annotation)
        return click.Choice(choices)

    if annotation is int:
        return int
    if annotation is bool:
        return bool
    if annotation is float:
        return float

    return str


def _create_click_command(
    endpoint: Any, method_name: str, run_async: Callable
) -> click.Command:
    """Create a Click command from an endpoint method.

    Args:
        endpoint: Endpoint instance with the method.
        method_name: Name of the method to wrap.
        run_async: Function to run async code (e.g., asyncio.run).

    Returns:
        Click command ready to be added to a group.

    Note:
        Uses endpoint.call() for unified Pydantic validation.
        tenant_id is treated specially: optional positional with context fallback.
    """
    from .cli_context import require_context

    method = getattr(endpoint, method_name)
    sig = inspect.signature(method)
    doc = method.__doc__ or f"{method_name} operation"

    options = []
    arguments = []
    has_tenant_id = False

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        click_type = _annotation_to_click_type(param.annotation)
        has_default = param.default is not inspect.Parameter.empty
        is_bool = param.annotation is bool

        cli_name = param_name.replace("_", "-")

        # Special case: required tenant_id becomes optional positional with context fallback
        if param_name == "tenant_id" and not has_default:
            has_tenant_id = True
            arguments.append(
                click.argument("tenant_id", type=click_type, required=False, default=None)
            )
        elif is_bool:
            options.append(
                click.option(
                    f"--{cli_name}/--no-{cli_name}",
                    default=param.default if has_default else False,
                    help=f"Enable/disable {param_name}",
                )
            )
        elif has_default:
            options.append(
                click.option(
                    f"--{cli_name}",
                    type=click_type,
                    default=param.default,
                    show_default=True,
                    help=f"{param_name} parameter",
                )
            )
        else:
            arguments.append(click.argument(param_name, type=click_type))

    def cmd_func(**kwargs: Any) -> None:
        py_kwargs = {k.replace("-", "_"): v for k, v in kwargs.items()}

        # Resolve tenant_id from context if not provided
        if has_tenant_id and not py_kwargs.get("tenant_id"):
            _, tenant = require_context(require_tenant=True)
            py_kwargs["tenant_id"] = tenant

        # Use endpoint.invoke() for unified Pydantic validation
        result = run_async(endpoint.invoke(method_name, py_kwargs))
        if result is not None:
            _print_result(result)

    cmd: click.Command = click.command(help=doc)(cmd_func)
    for opt in reversed(options):
        cmd = opt(cmd)
    for arg in reversed(arguments):
        cmd = arg(cmd)

    return cmd


def register_endpoint(
    group: click.Group, endpoint: Any, run_async: Callable | None = None
) -> click.Group:
    """Register all methods of an endpoint as Click commands.

    Creates a subgroup named after the endpoint and adds commands
    for each public async method.

    Args:
        group: Click group to add commands to.
        endpoint: Endpoint instance with async methods.
        run_async: Function to run async code. Defaults to asyncio.run.

    Returns:
        The created Click subgroup with all endpoint commands.

    Example:
        ::

            @click.group()
            def cli():
                pass

            endpoint = AccountEndpoint(db.table("accounts"))
            register_endpoint(cli, endpoint)

            # Now available:
            # cli accounts list
            # cli accounts add <id> --host <host> --port <port>
            # cli accounts delete <id>
    """
    if run_async is None:
        run_async = asyncio.run

    name = getattr(endpoint, "name", endpoint.__class__.__name__.lower())

    @group.group(name=name)
    def endpoint_group() -> None:
        """Endpoint commands."""
        pass

    endpoint_group.__doc__ = f"Manage {name}."

    for method_name in dir(endpoint):
        if method_name.startswith("_"):
            continue

        method = getattr(endpoint, method_name)
        if not callable(method) or not inspect.iscoroutinefunction(method):
            continue

        cmd = _create_click_command(endpoint, method_name, run_async)
        cmd.name = method_name.replace("_", "-")
        endpoint_group.add_command(cmd)

    return endpoint_group


class CliManager:
    """Manager for Click CLI application. Creates CLI lazily on first access."""

    def __init__(self, parent: Any):
        self.proxy = parent
        self._cli: click.Group | None = None

    @property
    def cli(self) -> click.Group:
        """Lazy-create Click CLI group."""
        if self._cli is None:
            self._cli = self._create_cli()
        return self._cli

    def _create_cli(self) -> click.Group:
        """Build Click CLI: endpoint commands + service commands."""

        @click.group()
        @click.version_option()
        def cli() -> None:
            """Genro Proxy service."""
            pass

        # Register endpoint-based commands
        for endpoint in self.proxy.endpoints.values():
            register_endpoint(cli, endpoint)

        # Add serve command
        @cli.command("serve")
        @click.option("--host", default="0.0.0.0", help="Bind host")
        @click.option("--port", "-p", default=self.proxy.config.port, help="Bind port")
        @click.option("--reload", is_flag=True, help="Enable auto-reload")
        def serve_cmd(host: str, port: int, reload: bool) -> None:
            """Start the API server."""
            import uvicorn

            uvicorn.run(
                self._get_server_module(),
                host=host,
                port=port,
                reload=reload,
            )

        return cli

    def _get_server_module(self) -> str:
        """Get the server module path for uvicorn. Override in subclass."""
        return "proxy.server:app"


__all__ = ["CliManager", "console", "register_endpoint"]
