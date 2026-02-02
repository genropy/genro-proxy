# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tenant configuration table manager.

Manages tenant configurations in a multi-tenant environment.
In CE, a single "default" tenant is used implicitly.
EE extends with full multi-tenant management via mixin.
"""

from __future__ import annotations

from typing import Any

from ...sql import Integer, String, Table, Timestamp


class TenantsTable(Table):
    """Tenant configuration storage table.

    Schema: id (PK), name, client_auth (JSON), client_base_url, active, etc.
    """

    name = "tenants"
    pkey = "id"

    def configure(self) -> None:
        """Define table columns."""
        c = self.columns
        c.column("id", String)
        c.column("name", String)
        c.column("client_auth", String, json_encoded=True)
        c.column("client_base_url", String)
        c.column("client_sync_path", String)
        c.column("client_attachment_path", String)
        c.column("rate_limits", String, json_encoded=True)
        c.column("large_file_config", String, json_encoded=True)
        c.column("active", Integer, default=1)
        c.column("suspended_batches", String)
        c.column("api_key_hash", String)
        c.column("api_key_expires_at", Timestamp)
        c.column("created_at", Timestamp, default="CURRENT_TIMESTAMP")
        c.column("updated_at", Timestamp, default="CURRENT_TIMESTAMP")

    async def get(self, tenant_id: str) -> dict[str, Any] | None:
        """Fetch a tenant configuration by ID."""
        tenant = await self.select_one(where={"id": tenant_id})
        if not tenant:
            return None
        return self._decode_active(tenant)

    def _decode_active(self, tenant: dict[str, Any]) -> dict[str, Any]:
        """Convert active INTEGER to bool."""
        tenant["active"] = bool(tenant.get("active", 1))
        return tenant

    def is_batch_suspended(self, suspended_batches: str | None, batch_code: str | None) -> bool:
        """Check if a batch is suspended.

        - "*" suspends all messages regardless of batch_code
        - Messages without batch_code are only suspended by "*"
        - Specific batch codes must match exactly
        """
        if not suspended_batches:
            return False
        if suspended_batches == "*":
            return True
        if batch_code is None:
            return False
        suspended_set = set(suspended_batches.split(","))
        return batch_code in suspended_set

    async def ensure_default(self) -> None:
        """Ensure the 'default' tenant exists for CE single-tenant mode."""
        async with self.record("default", insert_missing=True) as rec:
            if not rec.get("name"):
                rec["name"] = "Default Tenant"
                rec["active"] = 1

    async def suspend_batch(self, tenant_id: str, batch_code: str | None = None) -> bool:
        """Suspend sending for a tenant.

        Args:
            tenant_id: Tenant identifier.
            batch_code: Batch to suspend. If None, suspends all ("*").

        Returns:
            True if tenant found and updated, False if not found.
        """
        async with self.record(tenant_id) as rec:
            if not rec:
                return False

            if batch_code is None:
                rec["suspended_batches"] = "*"
            else:
                current = rec.get("suspended_batches") or ""
                if current == "*":
                    return True
                batches = set(current.split(",")) if current else set()
                batches.discard("")
                batches.add(batch_code)
                rec["suspended_batches"] = ",".join(sorted(batches))

        return True

    async def activate_batch(self, tenant_id: str, batch_code: str | None = None) -> bool:
        """Resume sending for a tenant.

        Args:
            tenant_id: Tenant identifier.
            batch_code: Batch to activate. If None, clears all suspensions.

        Returns:
            True if updated successfully, False if not found or cannot remove.
        """
        async with self.record(tenant_id) as rec:
            if not rec:
                return False

            if batch_code is None:
                rec["suspended_batches"] = None
            else:
                current = rec.get("suspended_batches") or ""
                if current == "*":
                    return False
                batches = set(current.split(",")) if current else set()
                batches.discard("")
                batches.discard(batch_code)
                rec["suspended_batches"] = ",".join(sorted(batches)) if batches else None

        return True

    async def get_suspended_batches(self, tenant_id: str) -> set[str]:
        """Get suspended batch codes for a tenant."""
        tenant = await self.get(tenant_id)
        if not tenant:
            return set()

        suspended = tenant.get("suspended_batches") or ""
        if not suspended:
            return set()
        if suspended == "*":
            return {"*"}
        batches = set(suspended.split(","))
        batches.discard("")
        return batches


__all__ = ["TenantsTable"]
