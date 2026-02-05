# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Interface layer for proxy services.

This package provides base classes for building proxy service interfaces:

- endpoint_base: BaseEndpoint for entity operations with introspection
- api_base: FastAPI application factory
- cli_base: Click CLI command generation
- cli_context: CLI context management for instance/tenant resolution

Example:
    ::

        from genro_proxy.interface import BaseEndpoint, endpoint, register_endpoint

        class ItemEndpoint(BaseEndpoint):
            name = "items"

            async def list(self) -> list[dict]:
                return await self.table.list_all()

            @endpoint(post=True)
            async def add(self, id: str, name: str) -> dict:
                return await self.table.add({"id": id, "name": name})

            @endpoint(api=False)
            async def serve(self, host: str = "0.0.0.0") -> None:
                \"\"\"CLI/REPL only - start the server.\"\"\"
                ...
"""

from .api_base import (
    API_TOKEN_HEADER,
    ApiManager,
    admin_dependency,
    auth_dependency,
    register_api_endpoint,
    require_admin_token,
    require_token,
)
from .cli_base import CliManager, console, register_endpoint
from .cli_context import CliContext
from .endpoint_base import BaseEndpoint, EndpointManager, endpoint
from .repl import REPLWrapper, repl_wrap, reserved

__all__ = [
    # API
    "API_TOKEN_HEADER",
    "ApiManager",
    "admin_dependency",
    "auth_dependency",
    "register_api_endpoint",
    "require_admin_token",
    "require_token",
    # CLI
    "CliContext",
    "CliManager",
    "console",
    "register_endpoint",
    # Endpoints
    "BaseEndpoint",
    "EndpointManager",
    "endpoint",
    # REPL
    "REPLWrapper",
    "repl_wrap",
    "reserved",
]
