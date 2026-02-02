# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Account configuration table manager.

Manages account configurations in a multi-tenant environment.
Uses UUID primary key (pk) with unique constraint on (tenant_id, id).
"""

from __future__ import annotations

from typing import Any

from genro_toolbox import get_uuid

from ...sql import Integer, String, Table, Timestamp


class AccountsTable(Table):
    """Account configurations for multi-tenant resources.

    Schema: pk (UUID), id, tenant_id (FK), host, port, user, password, etc.
    UNIQUE constraint on (tenant_id, id).
    """

    name = "accounts"
    pkey = "pk"

    def create_table_sql(self) -> str:
        """Generate CREATE TABLE with UNIQUE (tenant_id, id)."""
        sql = super().create_table_sql()
        last_paren = sql.rfind(")")
        return sql[:last_paren] + ',\n    UNIQUE ("tenant_id", "id")\n)'

    def configure(self) -> None:
        """Define table columns."""
        c = self.columns
        c.column("pk", String)
        c.column("id", String, nullable=False)
        c.column("tenant_id", String, nullable=False).relation("tenants", sql=True)
        c.column("host", String, nullable=False)
        c.column("port", Integer, nullable=False)
        c.column("user", String)
        c.column("password", String, encrypted=True)
        c.column("ttl", Integer, default=300)
        c.column("limit_per_minute", Integer)
        c.column("limit_per_hour", Integer)
        c.column("limit_per_day", Integer)
        c.column("limit_behavior", String)
        c.column("use_tls", Integer)
        c.column("batch_size", Integer)
        c.column("created_at", Timestamp, default="CURRENT_TIMESTAMP")
        c.column("updated_at", Timestamp, default="CURRENT_TIMESTAMP")

    async def add(self, acc: dict[str, Any]) -> str:
        """Insert or update an account configuration.

        Args:
            acc: Account configuration dict with keys:
                - id (required): Client account identifier.
                - tenant_id (required): Owning tenant ID.
                - host (required): Server hostname.
                - port (required): Server port.
                - user: Username.
                - password: Password (will be encrypted).
                - ttl: Connection cache TTL (default: 300).
                - limit_per_minute/hour/day: Rate limits.
                - limit_behavior: "defer" or "reject".
                - use_tls: True/False/None for TLS mode.
                - batch_size: Messages per connection.

        Returns:
            The account's internal UUID (pk).
        """
        tenant_id = acc["tenant_id"]
        account_id = acc["id"]

        use_tls = acc.get("use_tls")
        use_tls_val = None if use_tls is None else (1 if use_tls else 0)

        async with self.record(
            {"tenant_id": tenant_id, "id": account_id},
            insert_missing=True,
        ) as rec:
            if "pk" not in rec:
                rec["pk"] = get_uuid()

            rec["host"] = acc["host"]
            rec["port"] = int(acc["port"])
            rec["user"] = acc.get("user")
            rec["password"] = acc.get("password")
            rec["ttl"] = int(acc.get("ttl", 300))
            rec["limit_per_minute"] = acc.get("limit_per_minute")
            rec["limit_per_hour"] = acc.get("limit_per_hour")
            rec["limit_per_day"] = acc.get("limit_per_day")
            rec["limit_behavior"] = acc.get("limit_behavior", "defer")
            rec["use_tls"] = use_tls_val
            rec["batch_size"] = acc.get("batch_size")
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
        return self._decode_use_tls(account)

    async def list_all(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """List accounts, optionally filtered by tenant."""
        columns = [
            "pk", "id", "tenant_id", "host", "port", "user", "ttl",
            "limit_per_minute", "limit_per_hour", "limit_per_day",
            "limit_behavior", "use_tls", "batch_size",
            "created_at", "updated_at",
        ]

        if tenant_id:
            rows = await self.select(columns=columns, where={"tenant_id": tenant_id}, order_by="id")
        else:
            rows = await self.select(columns=columns, order_by="id")

        return [self._decode_use_tls(acc) for acc in rows]

    async def remove(self, tenant_id: str, account_id: str) -> None:
        """Delete an account."""
        await self.delete(where={"tenant_id": tenant_id, "id": account_id})

    def _decode_use_tls(self, account: dict[str, Any]) -> dict[str, Any]:
        """Convert use_tls from INTEGER to bool/None."""
        if "use_tls" in account:
            val = account["use_tls"]
            account["use_tls"] = bool(val) if val is not None else None
        return account

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
