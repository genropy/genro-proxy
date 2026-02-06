# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tenant configuration table manager.

Manages tenant configurations in a multi-tenant environment.
In CE, a single "default" tenant is used implicitly.
EE extends with full multi-tenant management via mixin.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from ...sql import Integer, String, Table, Timestamp


class TenantsTable(Table):
    """Tenant configuration storage table.

    Schema: id (PK), name, client_auth, client_base_url, config (JSON),
    active, api_key_hash, api_key_expires_at, timestamps.
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
        c.column("config", String, json_encoded=True)
        c.column("active", Integer, default=1)
        c.column("api_key_hash", String)
        c.column("api_key_expires_at", Timestamp)
        c.column("created_at", Timestamp, default="CURRENT_TIMESTAMP")
        c.column("updated_at", Timestamp, default="CURRENT_TIMESTAMP")

    def _decode_active(self, tenant: dict[str, Any]) -> dict[str, Any]:
        """Convert active INTEGER to bool."""
        tenant["active"] = bool(tenant.get("active", 1))
        return tenant

    def on_inserting(self, record: dict[str, Any]) -> None:
        """Generate API key on tenant creation."""
        api_key = secrets.token_urlsafe(32)
        record["api_key_hash"] = hashlib.sha256(api_key.encode()).hexdigest()
        record["_api_key"] = api_key  # Transient field, returned once

    async def create_api_key(
        self, tenant_id: str, expires_at: int | None = None
    ) -> str:
        """Generate and store a new API key for a tenant.

        Args:
            tenant_id: Tenant identifier.
            expires_at: Unix timestamp for key expiration (None = never expires).

        Returns:
            The generated API key (only returned once, store securely).

        Raises:
            ValueError: If tenant does not exist.
        """
        # Verify tenant exists (raises ValueError if not found)
        await self.record(pkey=tenant_id)

        api_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        async with self.record_to_update(tenant_id) as rec:
            rec["api_key_hash"] = key_hash
            rec["api_key_expires_at"] = expires_at

        return api_key

    async def get_tenant_by_token(self, api_key: str) -> dict[str, Any] | None:
        """Find tenant by API key.

        Args:
            api_key: The API key to look up.

        Returns:
            Tenant dict if found and key is valid/not expired, None otherwise.
        """
        import time

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        tenant = await self.record(where={"api_key_hash": key_hash}, ignore_missing=True)

        if not tenant:
            return None

        expires_at = tenant.get("api_key_expires_at")
        if expires_at and expires_at < int(time.time()):
            return None

        return self._decode_active(tenant)


__all__ = ["TenantsTable"]
