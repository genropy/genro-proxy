# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tenant REST API endpoint.

This module provides the TenantEndpoint class exposing CRUD operations
for tenant configurations via REST API and CLI commands.

The endpoint is designed for automatic introspection by api_base and
cli_base modules, which generate FastAPI routes and Typer commands
from method signatures.

Example:
    CLI commands auto-generated::

        gproxy tenants add --id acme --name "Acme Corp"
        gproxy tenants list
        gproxy tenants get --tenant-id acme
        gproxy tenants delete --tenant-id acme
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...interface.endpoint_base import POST, BaseEndpoint

if TYPE_CHECKING:
    from .table import TenantsTable


class TenantEndpoint(BaseEndpoint):
    """REST API endpoint for tenant management.

    Provides CRUD operations for tenant configurations.

    Attributes:
        name: Endpoint name used in URL paths ("tenants").
        table: TenantsTable instance for database operations.
    """

    name = "tenants"

    def __init__(self, table: TenantsTable):
        """Initialize endpoint with table reference.

        Args:
            table: TenantsTable instance for database operations.
        """
        super().__init__(table)

    @POST
    async def add(
        self,
        id: str,
        name: str | None = None,
        client_auth: dict[str, Any] | None = None,
        client_base_url: str | None = None,
        config: dict[str, Any] | None = None,
        active: bool = True,
    ) -> dict:
        """Add or update a tenant configuration.

        Args:
            id: Tenant identifier (unique).
            name: Human-readable tenant name.
            client_auth: HTTP auth config for callbacks (method, credentials).
            client_base_url: Base URL for client HTTP callbacks.
            config: Additional tenant-specific configuration.
            active: Whether tenant is active.

        Returns:
            Tenant dict.
        """
        async with self.table.record_to_update(id, insert_missing=True) as rec:
            if name is not None:
                rec["name"] = name
            if client_auth is not None:
                rec["client_auth"] = client_auth
            if client_base_url is not None:
                rec["client_base_url"] = client_base_url
            if config is not None:
                rec["config"] = config
            rec["active"] = 1 if active else 0

        return await self.get(id)

    async def get(self, tenant_id: str) -> dict:
        """Retrieve a single tenant configuration.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Tenant configuration dict.

        Raises:
            ValueError: If tenant not found.
        """
        from genro_proxy.sql import RecordNotFoundError

        try:
            tenant = await self.table.record(pkey=tenant_id)
        except RecordNotFoundError:
            raise ValueError(f"Tenant '{tenant_id}' not found")
        return self.table._decode_active(tenant)

    async def list(self, active_only: bool = False) -> list[dict]:
        """List all tenants.

        Args:
            active_only: If True, only return active tenants.

        Returns:
            List of tenant configuration dicts.
        """
        where = {"active": 1} if active_only else None
        tenants = await self.table.select(where=where, order_by="id")
        return [self.table._decode_active(t) for t in tenants]

    @POST
    async def delete(self, tenant_id: str) -> int:
        """Delete a tenant and all associated data.

        Args:
            tenant_id: Tenant identifier to delete.

        Returns:
            Number of deleted rows (0 or 1).
        """
        return await self.table.delete(where={"id": tenant_id})

    @POST
    async def update(
        self,
        tenant_id: str,
        name: str | None = None,
        client_auth: dict[str, Any] | None = None,
        client_base_url: str | None = None,
        config: dict[str, Any] | None = None,
        active: bool | None = None,
    ) -> dict:
        """Update tenant configuration fields.

        Only provided fields are updated; None values are ignored.

        Args:
            tenant_id: Tenant identifier.
            name: New tenant name.
            client_auth: New auth config.
            client_base_url: New base URL.
            config: New config dict.
            active: New active status.

        Returns:
            Updated tenant configuration dict.
        """
        async with self.table.record_to_update(tenant_id) as rec:
            if name is not None:
                rec["name"] = name
            if client_auth is not None:
                rec["client_auth"] = client_auth
            if client_base_url is not None:
                rec["client_base_url"] = client_base_url
            if config is not None:
                rec["config"] = config
            if active is not None:
                rec["active"] = 1 if active else 0

        return await self.get(tenant_id)


__all__ = ["TenantEndpoint"]
