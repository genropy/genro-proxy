# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Storages table: per-tenant storage backend configurations."""

from __future__ import annotations

from ...sql import String, Table, Timestamp


class StoragesTable(Table):
    """Storages table: named storage backends per tenant.

    Each tenant can have multiple named storage backends (e.g., HOME, SALES, ARCHIVE).
    Supports local filesystem, S3, GCS, Azure via fsspec.

    Schema: pk (UUID), tenant_id, name (unique per tenant), protocol, config (JSON).
    """

    name = "storages"
    pkey = "pk"

    def create_table_sql(self) -> str:
        """Generate CREATE TABLE with UNIQUE (tenant_id, name)."""
        sql = super().create_table_sql()
        last_paren = sql.rfind(")")
        return sql[:last_paren] + ',\n    UNIQUE ("tenant_id", "name")\n)'

    def configure(self) -> None:
        """Define table columns."""
        c = self.columns
        c.column("pk", String)
        c.column("tenant_id", String, nullable=False).relation("tenants", sql=True)
        c.column("name", String, nullable=False)
        c.column("protocol", String, nullable=False)
        c.column("config", String, json_encoded=True, encrypted=True)
        c.column("created_at", Timestamp, default="CURRENT_TIMESTAMP")
        c.column("updated_at", Timestamp, default="CURRENT_TIMESTAMP")

    async def get_storage_manager(self, tenant_id: str):
        """Get a configured StorageManager for a tenant."""
        from ...storage import StorageManager

        storages = await self.select(where={"tenant_id": tenant_id})
        manager = StorageManager()

        for s in storages:
            config = s.get("config", {})
            config["protocol"] = s["protocol"]
            manager.register(s["name"], config)

        return manager


__all__ = ["StoragesTable"]
