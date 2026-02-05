# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Storage endpoint: CRUD operations for tenant storage backends.

Designed for introspection by api_base/cli_base to auto-generate routes/commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...interface.endpoint_base import BaseEndpoint, endpoint

if TYPE_CHECKING:
    from .table import StoragesTable


class StorageEndpoint(BaseEndpoint):
    """Storage management endpoint. Methods are introspected for API/CLI generation."""

    name = "storages"

    def __init__(self, table: StoragesTable):
        super().__init__(table)

    @endpoint(post=True)
    async def add(
        self,
        tenant_id: str,
        name: str,
        protocol: str,
        config: dict[str, Any] | None = None,
    ) -> dict:
        """Add or update a storage backend for a tenant.

        Args:
            tenant_id: The tenant ID.
            name: Storage name (e.g., "HOME", "SALES").
            protocol: Storage protocol (local, s3, gcs, azure).
            config: Protocol-specific configuration.

        For local protocol:
            config: {"base_path": "/data/attachments"}

        For S3 protocol (EE only):
            config: {"bucket": "my-bucket", "prefix": "attachments/",
                    "aws_access_key_id": "...", "aws_secret_access_key": "..."}

        For GCS protocol (EE only):
            config: {"bucket": "my-bucket", "prefix": "attachments/",
                    "project": "...", "token": "..."}

        For Azure protocol (EE only):
            config: {"container": "my-container", "prefix": "attachments/",
                    "account_name": "...", "account_key": "..."}
        """
        async with self.table.record_to_update(
            {"tenant_id": tenant_id, "name": name},
            insert_missing=True,
        ) as rec:
            rec["protocol"] = protocol
            rec["config"] = config or {}

        return await self.get(tenant_id, name)

    async def get(self, tenant_id: str, name: str) -> dict:
        """Get a single storage configuration."""
        from genro_proxy.sql import RecordNotFoundError

        try:
            return await self.table.record(where={"tenant_id": tenant_id, "name": name})
        except RecordNotFoundError:
            raise ValueError(f"Storage '{name}' not found for tenant '{tenant_id}'")

    async def list(self, tenant_id: str) -> list[dict]:
        """List all storage backends for a tenant."""
        return await self.table.select(where={"tenant_id": tenant_id}, order_by="name")

    @endpoint(post=True)
    async def delete(self, tenant_id: str, name: str) -> dict:
        """Delete a storage backend."""
        deleted = await self.table.delete(where={"tenant_id": tenant_id, "name": name})
        return {"ok": deleted, "tenant_id": tenant_id, "name": name}

    async def list_files(
        self,
        tenant_id: str,
        storage_name: str,
        path: str = "/",
    ) -> list[dict]:
        """List files and directories in a storage path.

        Args:
            tenant_id: The tenant ID.
            storage_name: Name of the storage backend.
            path: Path within the storage (default: root).

        Returns:
            List of file/directory info dicts with keys:
                - name: File or directory name
                - path: Full path within storage
                - is_dir: True if directory
                - size: File size (0 for directories)
                - mtime: Last modification time (Unix timestamp)
        """
        manager = await self.table.get_storage_manager(tenant_id)

        if not manager.has_mount(storage_name):
            raise ValueError(f"Storage '{storage_name}' not found for tenant '{tenant_id}'")

        node = manager.node(storage_name, path.lstrip("/"))
        children = await node.children()

        result = []
        for child in children:
            is_dir = await child.is_dir()
            result.append({
                "name": child.basename,
                "path": child.path,
                "is_dir": is_dir,
                "size": 0 if is_dir else await child.size(),
                "mtime": await child.mtime() if await child.exists() else 0,
            })

        return result


__all__ = ["StorageEndpoint"]
