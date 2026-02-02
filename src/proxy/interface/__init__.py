# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Interface layer for proxy services.

This package provides base classes for building proxy service interfaces:

- endpoint_base: BaseEndpoint for entity operations with introspection
- api_base: FastAPI application factory
- cli_base: Click CLI command generation

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

from .cli_base import register_endpoint
from .endpoint_base import POST, BaseEndpoint

__all__ = ["BaseEndpoint", "POST", "register_endpoint"]
