# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Account REST API endpoint.

This module provides the AccountEndpoint class exposing CRUD operations
for generic account configurations via REST API and CLI commands.

The base endpoint provides only generic fields (id, name, config).
Domain-specific proxies should subclass and add their own parameters.

Example:
    Register endpoint with the API router::

        from proxy.entities.account import AccountEndpoint

        endpoint = AccountEndpoint(proxy.db.table("accounts"))
        # Routes auto-generated: POST /accounts, GET /accounts/{id}, etc.

    CLI commands auto-generated::

        gproxy accounts add --tenant-id acme --id main --name "Main Account"
        gproxy accounts list --tenant-id acme
        gproxy accounts get --tenant-id acme --account-id main
        gproxy accounts delete --tenant-id acme --account-id main
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...interface.endpoint_base import POST, BaseEndpoint

if TYPE_CHECKING:
    from .table import AccountsTable


class AccountEndpoint(BaseEndpoint):
    """REST API endpoint for generic account management.

    Provides CRUD operations for accounts. Each method is
    introspected to auto-generate API routes and CLI commands.

    Domain-specific proxies should subclass and override add()
    to accept their specific parameters.

    Attributes:
        name: Endpoint name used in URL paths ("accounts").
        table: AccountsTable instance for database operations.
    """

    name = "accounts"

    def __init__(self, table: AccountsTable):
        """Initialize endpoint with table reference.

        Args:
            table: AccountsTable instance for database operations.
        """
        super().__init__(table)

    @POST
    async def add(
        self,
        id: str,
        tenant_id: str,
        name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict:
        """Add or update an account configuration.

        Performs upsert: creates new account or updates existing one
        based on (tenant_id, id) composite key.

        Args:
            id: Account identifier (unique within tenant).
            tenant_id: Owning tenant ID.
            name: Display name (defaults to id).
            config: JSON configuration dict (domain-specific).

        Returns:
            Complete account record after insert/update.
        """
        async with self.table.record_to_update(
            {"tenant_id": tenant_id, "id": id},
            insert_missing=True,
        ) as rec:
            rec["name"] = name or id
            rec["config"] = config

        return await self.get(tenant_id, id)

    async def get(self, tenant_id: str, account_id: str) -> dict:
        """Retrieve a single account by tenant and ID.

        Args:
            tenant_id: Tenant that owns the account.
            account_id: Account identifier.

        Returns:
            Account configuration dict.

        Raises:
            ValueError: If account not found.
        """
        from proxy.sql import RecordNotFoundError

        try:
            return await self.table.record(where={"tenant_id": tenant_id, "id": account_id})
        except RecordNotFoundError:
            raise ValueError(f"Account '{account_id}' not found for tenant '{tenant_id}'")

    async def list(self, tenant_id: str) -> list[dict]:
        """List all accounts for a tenant.

        Args:
            tenant_id: Tenant to list accounts for.

        Returns:
            List of account dicts ordered by ID.
        """
        return await self.table.select(where={"tenant_id": tenant_id}, order_by="id")

    @POST
    async def delete(self, tenant_id: str, account_id: str) -> int:
        """Delete an account.

        Args:
            tenant_id: Tenant that owns the account.
            account_id: Account identifier to delete.

        Returns:
            Number of deleted rows (0 or 1).
        """
        return await self.table.delete(where={"tenant_id": tenant_id, "id": account_id})


__all__ = ["AccountEndpoint"]
