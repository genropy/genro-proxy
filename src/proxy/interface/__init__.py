# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Interface layer for proxy services.

This package provides base classes for building proxy service interfaces:

- endpoint_base: BaseEndpoint for entity operations with introspection
- api_base: FastAPI application factory
- cli_base: Click CLI command generation
- cli_context: CLI context management for instance/tenant resolution

Example:
    ::

        from proxy.interface import BaseEndpoint, POST, register_endpoint

        class ItemEndpoint(BaseEndpoint):
            name = "items"

            async def list(self) -> list[dict]:
                return await self.table.list_all()

            @POST
            async def add(self, id: str, name: str) -> dict:
                return await self.table.add({"id": id, "name": name})
"""

from .api_base import ApiManager
from .cli_base import CliManager, console, register_endpoint
from .cli_context import CliContext, require_context, resolve_context
from .endpoint_base import POST, BaseEndpoint, EndpointManager
from .repl import REPLWrapper, repl_wrap, reserved

__all__ = [
    "ApiManager",
    "BaseEndpoint",
    "CliContext",
    "CliManager",
    "EndpointManager",
    "POST",
    "REPLWrapper",
    "console",
    "register_endpoint",
    "repl_wrap",
    "require_context",
    "reserved",
    "resolve_context",
]
