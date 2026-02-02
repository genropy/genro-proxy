# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Command log table for API audit trail.

Implements an audit log for API commands, recording every
state-modifying operation with its full payload. Enables:
- Debugging: Trace what happened and when
- Migration: Replay commands to reconstruct state
- Recovery: Restore from command history after failures
- Compliance: Audit trail for regulatory requirements
"""

from __future__ import annotations

import json
import time
from typing import Any

from ...sql import Integer, String, Table


class CommandLogTable(Table):
    """Audit log table for API command tracking.

    Records every state-modifying API command with timestamp, endpoint,
    tenant context, request payload, and response status.

    Schema: id (auto-increment), command_ts, endpoint, tenant_id, payload, etc.
    """

    name = "command_log"
    pkey = "id"

    def new_pkey_value(self) -> None:
        """Return None for INTEGER PRIMARY KEY autoincrement."""
        return None

    def configure(self) -> None:
        """Define table columns."""
        c = self.columns
        c.column("id", Integer)
        c.column("command_ts", Integer, nullable=False)
        c.column("endpoint", String, nullable=False)
        c.column("tenant_id", String)
        c.column("payload", String, nullable=False)
        c.column("response_status", Integer)
        c.column("response_body", String)

    async def log_command(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        tenant_id: str | None = None,
        response_status: int | None = None,
        response_body: dict[str, Any] | None = None,
        command_ts: int | None = None,
    ) -> int:
        """Record an API command in the audit log.

        Args:
            endpoint: HTTP method + path (e.g., "POST /commands/add-messages").
            payload: Request body as dict (will be JSON-serialized).
            tenant_id: Tenant context for multi-tenant commands.
            response_status: HTTP response status code.
            response_body: Response body as dict (will be JSON-serialized).
            command_ts: Unix timestamp. Defaults to current time.

        Returns:
            Auto-generated command log ID.
        """
        ts = command_ts if command_ts is not None else int(time.time())

        record: dict[str, Any] = {
            "command_ts": ts,
            "endpoint": endpoint,
            "tenant_id": tenant_id,
            "payload": json.dumps(payload),
            "response_status": response_status,
            "response_body": json.dumps(response_body) if response_body else None,
        }

        await self.insert(record)
        return int(record.get("id", 0))

    async def list_commands(
        self,
        *,
        tenant_id: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
        endpoint_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List logged commands with optional filters.

        Args:
            tenant_id: Filter by tenant.
            since_ts: Include commands with command_ts >= since_ts.
            until_ts: Include commands with command_ts <= until_ts.
            endpoint_filter: Filter by endpoint (SQL LIKE partial match).
            limit: Maximum number of results to return.
            offset: Skip first N results for pagination.

        Returns:
            List of command records with parsed JSON fields.
        """
        conditions = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if tenant_id:
            conditions.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if since_ts:
            conditions.append("command_ts >= :since_ts")
            params["since_ts"] = since_ts
        if until_ts:
            conditions.append("command_ts <= :until_ts")
            params["until_ts"] = until_ts
        if endpoint_filter:
            conditions.append("endpoint LIKE :endpoint_filter")
            params["endpoint_filter"] = f"%{endpoint_filter}%"

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        rows = await self.db.adapter.fetch_all(
            f"""
            SELECT id, command_ts, endpoint, tenant_id, payload, response_status, response_body
            FROM command_log
            WHERE {where_clause}
            ORDER BY command_ts ASC, id ASC
            LIMIT :limit OFFSET :offset
            """,
            params,
        )

        result = []
        for row in rows:
            record = dict(row)
            if record.get("payload"):
                try:
                    record["payload"] = json.loads(record["payload"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if record.get("response_body"):
                try:
                    record["response_body"] = json.loads(record["response_body"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(record)
        return result

    async def get_command(self, command_id: int) -> dict[str, Any] | None:
        """Retrieve a single command log entry by ID."""
        row = await self.db.adapter.fetch_one(
            """
            SELECT id, command_ts, endpoint, tenant_id, payload, response_status, response_body
            FROM command_log
            WHERE id = :id
            """,
            {"id": command_id},
        )
        if not row:
            return None

        record = dict(row)
        if record.get("payload"):
            try:
                record["payload"] = json.loads(record["payload"])
            except (json.JSONDecodeError, TypeError):
                pass
        if record.get("response_body"):
            try:
                record["response_body"] = json.loads(record["response_body"])
            except (json.JSONDecodeError, TypeError):
                pass
        return record

    async def export_commands(
        self,
        *,
        tenant_id: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        """Export commands in replay-friendly format.

        Returns minimal fields needed for replay: endpoint, tenant_id,
        payload, and command_ts (for ordering).
        """
        commands = await self.list_commands(
            tenant_id=tenant_id,
            since_ts=since_ts,
            until_ts=until_ts,
            limit=100000,
        )

        return [
            {
                "endpoint": cmd["endpoint"],
                "tenant_id": cmd["tenant_id"],
                "payload": cmd["payload"],
                "command_ts": cmd["command_ts"],
            }
            for cmd in commands
        ]

    async def purge_before(self, threshold_ts: int) -> int:
        """Delete command logs older than threshold.

        Args:
            threshold_ts: Delete commands with command_ts < threshold_ts.

        Returns:
            Number of deleted records.
        """
        row = await self.db.adapter.fetch_one(
            "SELECT COUNT(*) as cnt FROM command_log WHERE command_ts < :threshold_ts",
            {"threshold_ts": threshold_ts},
        )
        count = int(row["cnt"]) if row else 0

        if count > 0:
            await self.execute(
                "DELETE FROM command_log WHERE command_ts < :threshold_ts",
                {"threshold_ts": threshold_ts},
            )
        return count


__all__ = ["CommandLogTable"]
