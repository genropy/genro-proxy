# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Instance configuration table manager (singleton pattern).

Stores instance-wide settings in a single row (id=1). Provides
typed access to common settings and flexible JSON storage.

Configuration access follows a dual pattern:
    - Typed columns: name, api_token, edition (direct column access)
    - JSON config: Additional key-value pairs in config column
"""

from __future__ import annotations

from typing import Any

from ...sql import Integer, String, Table, Timestamp


class InstanceTable(Table):
    """Singleton table for instance-level configuration.

    Schema: id (always 1), name, api_token, edition, config (JSON).
    """

    name = "instance"
    pkey = "id"

    def configure(self) -> None:
        """Define table columns."""
        c = self.columns
        c.column("id", Integer)
        c.column("name", String, default="proxy")
        c.column("api_token", String)
        c.column("edition", String, default="ce")
        c.column("config", String, json_encoded=True)
        c.column("created_at", Timestamp, default="CURRENT_TIMESTAMP")
        c.column("updated_at", Timestamp, default="CURRENT_TIMESTAMP")

    async def get_instance(self) -> dict[str, Any] | None:
        """Get the singleton instance configuration."""
        return await self.select_one(where={"id": 1})

    async def ensure_instance(self) -> dict[str, Any]:
        """Get or create the singleton instance configuration."""
        row = await self.get_instance()
        if row is None:
            await self.insert({"id": 1})
            row = await self.get_instance()
        return row  # type: ignore[return-value]

    async def update_instance(self, updates: dict[str, Any]) -> None:
        """Update the singleton instance configuration."""
        await self.ensure_instance()
        async with self.record(1) as rec:
            for key, value in updates.items():
                rec[key] = value

    async def get_name(self) -> str:
        """Get instance display name."""
        row = await self.ensure_instance()
        return row.get("name") or "proxy"

    async def set_name(self, name: str) -> None:
        """Set instance display name."""
        await self.update_instance({"name": name})

    async def get_api_token(self) -> str | None:
        """Get master API token."""
        row = await self.ensure_instance()
        return row.get("api_token")

    async def set_api_token(self, token: str) -> None:
        """Set master API token."""
        await self.update_instance({"api_token": token})

    async def get_edition(self) -> str:
        """Get current edition ("ce" or "ee")."""
        row = await self.ensure_instance()
        return row.get("edition") or "ce"

    async def is_enterprise(self) -> bool:
        """Check if running in Enterprise Edition mode."""
        return await self.get_edition() == "ee"

    async def set_edition(self, edition: str) -> None:
        """Set edition ("ce" or "ee")."""
        if edition not in ("ce", "ee"):
            raise ValueError(f"Invalid edition: {edition}. Must be 'ce' or 'ee'.")
        await self.update_instance({"edition": edition})

    # Typed column names for dual access pattern
    _TYPED_CONFIG_KEYS = {"name", "api_token", "edition"}

    async def get_config(self, key: str, default: str | None = None) -> str | None:
        """Get a configuration value by key (typed column or JSON config)."""
        row = await self.ensure_instance()
        if key in self._TYPED_CONFIG_KEYS:
            value = row.get(key)
        else:
            config = row.get("config") or {}
            value = config.get(key)
        return str(value) if value is not None else default

    async def set_config(self, key: str, value: str) -> None:
        """Set a configuration value (typed column or JSON config)."""
        if key in self._TYPED_CONFIG_KEYS:
            await self.update_instance({key: value})
        else:
            row = await self.ensure_instance()
            config = row.get("config") or {}
            config[key] = value
            await self.update_instance({"config": config})

    async def get_all_config(self) -> dict[str, Any]:
        """Get all configuration values merged (typed + JSON)."""
        row = await self.ensure_instance()
        result: dict[str, Any] = {}
        for key in self._TYPED_CONFIG_KEYS:
            if row.get(key) is not None:
                result[key] = row[key]
        config = row.get("config") or {}
        result.update(config)
        return result


__all__ = ["InstanceTable"]
