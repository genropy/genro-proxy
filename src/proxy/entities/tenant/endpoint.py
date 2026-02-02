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
        gproxy tenants suspend-batch --tenant-id acme --batch-code newsletter
        gproxy tenants activate-batch --tenant-id acme

Note:
    Enterprise Edition (EE) extends this with TenantEndpoint_EE mixin
    adding API key management (create_api_key, revoke_api_key).
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from ...interface.endpoint_base import POST, BaseEndpoint

if TYPE_CHECKING:
    from .table import TenantsTable


class AuthMethod(str, Enum):
    """Authentication methods for HTTP client callbacks.

    Attributes:
        NONE: No authentication required.
        BEARER: Bearer token authentication.
        BASIC: HTTP Basic authentication.
    """

    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"


class LargeFileAction(str, Enum):
    """Action when file exceeds size threshold.

    Attributes:
        WARN: Log warning but proceed.
        REJECT: Reject the request entirely.
        REWRITE: Store file externally and rewrite URL.
    """

    WARN = "warn"
    REJECT = "reject"
    REWRITE = "rewrite"


DEFAULT_SYNC_PATH = "/proxy/sync"
DEFAULT_ATTACHMENT_PATH = "/proxy/attachments"


def get_tenant_sync_url(tenant: dict[str, Any]) -> str | None:
    """Build full sync callback URL from tenant config.

    Args:
        tenant: Tenant configuration dict.

    Returns:
        Full URL (base_url + sync_path) or None if no base_url.
    """
    base_url = tenant.get("client_base_url")
    if not base_url:
        return None
    sync_path = tenant.get("client_sync_path") or DEFAULT_SYNC_PATH
    return f"{base_url.rstrip('/')}{sync_path}"


def get_tenant_attachment_url(tenant: dict[str, Any]) -> str | None:
    """Build full attachment fetch URL from tenant config.

    Args:
        tenant: Tenant configuration dict.

    Returns:
        Full URL (base_url + attachment_path) or None if no base_url.
    """
    base_url = tenant.get("client_base_url")
    if not base_url:
        return None
    attachment_path = tenant.get("client_attachment_path") or DEFAULT_ATTACHMENT_PATH
    return f"{base_url.rstrip('/')}{attachment_path}"


class TenantEndpoint(BaseEndpoint):
    """REST API endpoint for tenant management.

    Provides CRUD operations for tenant configurations including
    batch suspension for campaign control.

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
        client_sync_path: str | None = None,
        client_attachment_path: str | None = None,
        rate_limits: dict[str, Any] | None = None,
        large_file_config: dict[str, Any] | None = None,
        active: bool = True,
    ) -> dict:
        """Add or update a tenant configuration.

        Args:
            id: Tenant identifier (unique).
            name: Human-readable tenant name.
            client_auth: HTTP auth config for callbacks (method, credentials).
            client_base_url: Base URL for client HTTP callbacks.
            client_sync_path: Path for sync endpoint (default: /proxy/sync).
            client_attachment_path: Path for attachments (default: /proxy/attachments).
            rate_limits: Rate limit config (per_minute, per_hour, per_day).
            large_file_config: Large file handling (threshold, action).
            active: Whether tenant is active.

        Returns:
            Tenant dict, including api_key for new tenants (EE only).
        """
        data = {k: v for k, v in locals().items() if k != "self"}
        api_key = await self.table.add(data)
        tenant = await self.table.get(id)
        if api_key:
            tenant["api_key"] = api_key
        return tenant

    async def get(self, tenant_id: str) -> dict:
        """Retrieve a single tenant configuration.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Tenant configuration dict.

        Raises:
            ValueError: If tenant not found.
        """
        tenant = await self.table.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found")
        return tenant

    async def list(self, active_only: bool = False) -> list[dict]:
        """List all tenants.

        Args:
            active_only: If True, only return active tenants.

        Returns:
            List of tenant configuration dicts.
        """
        where = {"active": 1} if active_only else None
        return await self.table.select(where=where)

    @POST
    async def delete(self, tenant_id: str) -> bool:
        """Delete a tenant and all associated data.

        Args:
            tenant_id: Tenant identifier to delete.

        Returns:
            True if deleted.
        """
        return await self.table.remove(tenant_id)

    @POST
    async def update(
        self,
        tenant_id: str,
        name: str | None = None,
        client_auth: dict[str, Any] | None = None,
        client_base_url: str | None = None,
        client_sync_path: str | None = None,
        client_attachment_path: str | None = None,
        rate_limits: dict[str, Any] | None = None,
        large_file_config: dict[str, Any] | None = None,
        active: bool | None = None,
    ) -> dict:
        """Update tenant configuration fields.

        Only provided fields are updated; None values are ignored.

        Args:
            tenant_id: Tenant identifier.
            name: New tenant name.
            client_auth: New auth config.
            client_base_url: New base URL.
            client_sync_path: New sync path.
            client_attachment_path: New attachment path.
            rate_limits: New rate limits.
            large_file_config: New large file config.
            active: New active status.

        Returns:
            Updated tenant configuration dict.
        """
        fields = {
            k: v for k, v in locals().items() if k not in ("self", "tenant_id") and v is not None
        }
        await self.table.update_fields(tenant_id, fields)
        return await self.table.get(tenant_id)

    @POST
    async def suspend_batch(
        self,
        tenant_id: str,
        batch_code: str | None = None,
    ) -> dict:
        """Suspend processing for a tenant.

        Suspended batches are skipped by the processor.

        Args:
            tenant_id: Tenant identifier.
            batch_code: Batch to suspend. If None, suspends all processing.

        Returns:
            Dict with ok=True and suspended_batches list.

        Raises:
            ValueError: If tenant not found.
        """
        success = await self.table.suspend_batch(tenant_id, batch_code)
        if not success:
            raise ValueError(f"Tenant '{tenant_id}' not found")
        suspended = await self.table.get_suspended_batches(tenant_id)
        return {"ok": True, "tenant_id": tenant_id, "suspended_batches": list(suspended)}

    @POST
    async def activate_batch(
        self,
        tenant_id: str,
        batch_code: str | None = None,
    ) -> dict:
        """Resume processing for a tenant.

        Removes batch from suspension list.

        Args:
            tenant_id: Tenant identifier.
            batch_code: Batch to activate. If None, clears all suspensions.

        Returns:
            Dict with ok=True and remaining suspended_batches.

        Raises:
            ValueError: If tenant not found or cannot remove single batch from "*".
        """
        success = await self.table.activate_batch(tenant_id, batch_code)
        if not success:
            tenant = await self.table.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant '{tenant_id}' not found")
            raise ValueError(
                "Cannot remove single batch when all suspended. Use activate_batch(None) first."
            )
        suspended = await self.table.get_suspended_batches(tenant_id)
        return {"ok": True, "tenant_id": tenant_id, "suspended_batches": list(suspended)}

    async def get_suspended_batches(self, tenant_id: str) -> dict:
        """Get suspended batches for a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Dict with ok=True and suspended_batches list.

        Raises:
            ValueError: If tenant not found.
        """
        tenant = await self.table.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found")
        suspended = await self.table.get_suspended_batches(tenant_id)
        return {"ok": True, "tenant_id": tenant_id, "suspended_batches": list(suspended)}


__all__ = [
    "AuthMethod",
    "DEFAULT_ATTACHMENT_PATH",
    "DEFAULT_SYNC_PATH",
    "LargeFileAction",
    "TenantEndpoint",
    "get_tenant_attachment_url",
    "get_tenant_sync_url",
]
