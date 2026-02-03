# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Account configuration table manager.

Manages generic account configurations in a multi-tenant environment.
Uses UUID primary key (pk) with unique constraint on (tenant_id, id).

The base table provides only generic fields. Domain-specific proxies
(mail, storage, API) extend this with their own fields via subclassing.
"""

from __future__ import annotations

from ...sql import String, Table, Timestamp


class AccountsTable(Table):
    """Generic account configurations for multi-tenant resources.

    Schema: pk (UUID), id, tenant_id (FK), name, config (JSON).
    UNIQUE constraint on (tenant_id, id).

    Domain-specific proxies should subclass and add their own columns.
    """

    name = "accounts"
    pkey = "pk"

    def create_table_sql(self) -> str:
        """Generate CREATE TABLE with UNIQUE (tenant_id, id)."""
        sql = super().create_table_sql()
        last_paren = sql.rfind(")")
        return sql[:last_paren] + ',\n    UNIQUE ("tenant_id", "id")\n)'

    def configure(self) -> None:
        """Define table columns. Override in subclass to add domain-specific fields."""
        c = self.columns
        c.column("pk", String)
        c.column("id", String, nullable=False)
        c.column("tenant_id", String, nullable=False).relation("tenants", sql=True)
        c.column("name", String)
        c.column("config", String, json_encoded=True, encrypted=True)
        c.column("created_at", Timestamp, default="CURRENT_TIMESTAMP")
        c.column("updated_at", Timestamp, default="CURRENT_TIMESTAMP")

    async def sync_schema(self) -> None:
        """Sync schema and ensure UNIQUE index."""
        await super().sync_schema()
        try:
            await self.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_tenant_id "
                'ON accounts ("tenant_id", "id")'
            )
        except Exception:
            pass


__all__ = ["AccountsTable"]
