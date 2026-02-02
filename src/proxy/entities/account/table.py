# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Account configuration table manager.

Manages generic account configurations in a multi-tenant environment.
Uses UUID primary key (pk) with unique constraint on (tenant_id, id).

The base table provides only generic fields. Domain-specific proxies
(mail, storage, API) extend this with their own fields via subclassing.
"""

from __future__ import annotations

from typing import Any

from genro_toolbox import get_uuid

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

    async def add(self, acc: dict[str, Any]) -> str:
        """Insert or update an account configuration.

        Args:
            acc: Account configuration dict with keys:
                - id (required): Client account identifier.
                - tenant_id (required): Owning tenant ID.
                - name: Display name.
                - config: JSON-serializable configuration dict.

        Returns:
            The account's internal UUID (pk).
        """
        tenant_id = acc["tenant_id"]
        account_id = acc["id"]

        async with self.record(
            {"tenant_id": tenant_id, "id": account_id},
            insert_missing=True,
        ) as rec:
            if "pk" not in rec:
                rec["pk"] = get_uuid()

            rec["name"] = acc.get("name") or account_id
            rec["config"] = acc.get("config")
            pk = rec["pk"]

        return pk

    async def get(self, tenant_id: str, account_id: str) -> dict[str, Any]:
        """Retrieve a single account by tenant and ID.

        Raises:
            ValueError: If account not found for this tenant.
        """
        account = await self.select_one(where={"tenant_id": tenant_id, "id": account_id})
        if not account:
            raise ValueError(f"Account '{account_id}' not found for tenant '{tenant_id}'")
        return account

    async def list_all(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """List accounts, optionally filtered by tenant."""
        if tenant_id:
            return await self.select(where={"tenant_id": tenant_id}, order_by="id")
        return await self.select(order_by="id")

    async def remove(self, tenant_id: str, account_id: str) -> None:
        """Delete an account."""
        await self.delete(where={"tenant_id": tenant_id, "id": account_id})

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
