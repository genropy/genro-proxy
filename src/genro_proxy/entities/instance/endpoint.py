# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Instance REST API endpoint for service-level operations.

This module provides the InstanceEndpoint class exposing service-level
operations for any Genro proxy via REST API and CLI commands.

Operations include:
    Current instance (DB):
    - health: Container orchestration health check (unauthenticated)
    - status: Authenticated service status with active state
    - run_now: Trigger immediate processing cycle
    - suspend/activate: Control processing per tenant/batch
    - get/update: Instance configuration management
    - get_sync_status: Monitor tenant synchronization health
    - upgrade_to_ee: Transition from Community to Enterprise Edition

    All instances (filesystem proxy.base_dir):
    - list_all: List all configured instances with running status
    - stop: Stop running instance(s)
    - restart: Restart running instance(s)

Example:
    CLI commands auto-generated::

        gproxy instance health
        gproxy instance status
        gproxy instance list-all
        gproxy instance stop dev-instance
        gproxy instance restart dev-instance

Note:
    Enterprise Edition (EE) extends this with InstanceEndpoint_EE mixin
    adding additional configuration operations.
"""

from __future__ import annotations

import configparser
import json
import os
import secrets
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...interface.endpoint_base import POST, BaseEndpoint

if TYPE_CHECKING:
    from .table import InstanceTable


class InstanceEndpoint(BaseEndpoint):
    """REST API endpoint for instance-level operations.

    Provides service management operations including health checks,
    processing control, and configuration management.

    Attributes:
        name: Endpoint name used in URL paths ("instance").
        table: InstanceTable instance for configuration storage.
        proxy: Optional proxy instance for service operations.
    """

    name = "instance"

    def __init__(self, table: InstanceTable, proxy: object | None = None):
        """Initialize endpoint with table and optional proxy reference.

        Args:
            table: InstanceTable for configuration storage.
            proxy: Optional proxy instance for service operations.
                   When provided, enables run_now, suspend, activate,
                   and get_sync_status to interact with the running service.
        """
        super().__init__(table)
        self.proxy = proxy

    async def health(self) -> dict:
        """Health check for container orchestration.

        Lightweight endpoint for liveness/readiness probes. Does not
        require authentication. Returns immediately without database access.

        Returns:
            Dict with status "ok".
        """
        return {"status": "ok"}

    async def status(self) -> dict:
        """Authenticated service status.

        Returns the current active state of the proxy service.
        Requires authentication.

        Returns:
            Dict with ok=True and active boolean indicating if
            the processing loop is running.
        """
        active = True
        if self.proxy is not None:
            active = getattr(self.proxy, "_active", True)
        return {"ok": True, "active": active}

    @POST
    async def run_now(self, tenant_id: str | None = None) -> dict:
        """Trigger immediate processing cycle.

        Resets the tenant's sync timer, causing the next processing loop
        iteration to process items immediately.

        Args:
            tenant_id: If provided, only reset this tenant's sync timer.
                       If None, triggers processing for all tenants.

        Returns:
            Dict with ok=True.
        """
        if self.proxy is not None:
            result = await self.proxy.handle_command("run now", {"tenant_id": tenant_id})
            return result
        return {"ok": True}

    @POST
    async def suspend(
        self,
        tenant_id: str,
        batch_code: str | None = None,
    ) -> dict:
        """Suspend processing for a tenant.

        Prevents items from being processed for the specified tenant
        or batch. Items remain in queue and will be processed when activated.

        Args:
            tenant_id: Tenant to suspend.
            batch_code: Optional batch code. If None, suspends all batches.

        Returns:
            Dict with suspended batches list and pending item count.
        """
        if self.proxy is not None:
            result = await self.proxy.handle_command(
                "suspend",
                {
                    "tenant_id": tenant_id,
                    "batch_code": batch_code,
                },
            )
            return result
        return {"ok": True, "tenant_id": tenant_id, "batch_code": batch_code}

    @POST
    async def activate(
        self,
        tenant_id: str,
        batch_code: str | None = None,
    ) -> dict:
        """Resume processing for a tenant.

        Removes suspension for the specified tenant or batch, allowing
        queued items to be processed.

        Args:
            tenant_id: Tenant to activate.
            batch_code: Optional batch code. If None, clears all suspensions.

        Returns:
            Dict with remaining suspended batches list.
        """
        if self.proxy is not None:
            result = await self.proxy.handle_command(
                "activate",
                {
                    "tenant_id": tenant_id,
                    "batch_code": batch_code,
                },
            )
            return result
        return {"ok": True, "tenant_id": tenant_id, "batch_code": batch_code}

    async def get(self) -> dict:
        """Get instance configuration.

        Returns:
            Dict with ok=True and all instance configuration fields.
        """
        instance = await self.table.get_instance()
        if instance is None:
            return {"ok": True, "id": 1, "name": "proxy", "edition": "ce"}
        return {"ok": True, **instance}

    @POST
    async def update(
        self,
        name: str | None = None,
        api_token: str | None = None,
        edition: str | None = None,
    ) -> dict:
        """Update instance configuration.

        Args:
            name: New instance display name.
            api_token: New master API token.
            edition: New edition ("ce" or "ee").

        Returns:
            Dict with ok=True.
        """
        updates = {}
        if name is not None:
            updates["name"] = name
        if api_token is not None:
            updates["api_token"] = api_token
        if edition is not None:
            updates["edition"] = edition

        if updates:
            await self.table.update_instance(updates)
        return {"ok": True}

    async def get_sync_status(self) -> dict:
        """Get sync status for all tenants.

        Returns synchronization health information for each tenant,
        useful for monitoring and debugging processing issues.

        Returns:
            Dict with ok=True and tenants list. Each tenant contains:
                - id: Tenant identifier
                - last_sync_ts: Unix timestamp of last sync
                - next_sync_due: True if sync interval has expired
        """
        if self.proxy is not None:
            result = await self.proxy.handle_command("listTenantsSyncStatus", {})
            return result
        return {"ok": True, "tenants": []}

    @POST
    async def upgrade_to_ee(self) -> dict:
        """Upgrade from Community Edition to Enterprise Edition.

        Performs explicit upgrade from CE to EE mode:
            1. Verifies Enterprise modules are installed
            2. Sets edition="ee" in instance configuration
            3. Optionally generates API key for "default" tenant

        The upgrade is idempotent - calling when already EE is safe.

        Returns:
            Dict with ok=True, edition, optional default_tenant_token,
            and descriptive message.

        Raises:
            ValueError: If Enterprise modules are not installed.
        """
        # Check if already EE
        if await self.table.is_enterprise():
            return {"ok": True, "edition": "ee", "message": "Already in Enterprise Edition"}

        # Upgrade to EE
        await self.table.set_edition("ee")

        # If "default" tenant exists without token, generate one
        if self.proxy is not None:
            tenants_table = self.proxy.db.table("tenants")
            default_tenant = await tenants_table.get("default")
            if default_tenant and not default_tenant.get("api_key_hash"):
                token = await tenants_table.create_api_key("default")
                return {
                    "ok": True,
                    "edition": "ee",
                    "default_tenant_token": token,
                    "message": "Upgraded to Enterprise Edition. Save the default tenant token - it will not be shown again.",
                }

        return {"ok": True, "edition": "ee", "message": "Upgraded to Enterprise Edition"}

    # -------------------------------------------------------------------------
    # Filesystem instance management (proxy.base_dir)
    # -------------------------------------------------------------------------

    def _get_instance_dir(self, name: str) -> Path:
        """Get instance directory path."""
        return self.proxy.base_dir / name

    def _get_pid_file(self, name: str) -> Path:
        """Get PID file path for an instance."""
        return self._get_instance_dir(name) / "server.pid"

    def _get_config_file(self, name: str) -> Path:
        """Get config file path for an instance."""
        return self._get_instance_dir(name) / "config.ini"

    def _read_instance_config(self, name: str) -> dict[str, Any] | None:
        """Read instance configuration from config.ini."""
        config_file = self._get_config_file(name)
        if not config_file.exists():
            return None

        config = configparser.ConfigParser()
        config.read(config_file)

        return {
            "name": config.get("server", "name", fallback=name),
            "host": config.get("server", "host", fallback="0.0.0.0"),
            "port": config.getint("server", "port", fallback=8000),
            "db_path": config.get(
                "database",
                "path",
                fallback=str(self._get_instance_dir(name) / "data.db"),
            ),
            "config_file": str(config_file),
        }

    def _is_instance_running(self, name: str) -> tuple[bool, int | None, int | None]:
        """Check if instance is running. Returns (running, pid, port)."""
        pid_file = self._get_pid_file(name)
        if not pid_file.exists():
            return False, None, None

        try:
            data = json.loads(pid_file.read_text())
            pid = data.get("pid")
            port = data.get("port")

            if pid is None:
                return False, None, port

            # Check if process is alive
            os.kill(pid, 0)
            return True, pid, port
        except (json.JSONDecodeError, ProcessLookupError, PermissionError, OSError):
            return False, None, None

    def _stop_instance_process(
        self, name: str, force: bool = False, timeout: float = 5.0
    ) -> bool:
        """Stop instance process. Returns True if stopped."""
        is_running, pid, _ = self._is_instance_running(name)
        if not is_running or pid is None:
            return False

        sig = signal.SIGKILL if force else signal.SIGTERM

        try:
            os.kill(pid, sig)

            # Wait for process to terminate
            iterations = int(timeout / 0.1)
            for _ in range(iterations):
                time.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    self._remove_pid_file(name)
                    return True

            # Fallback to SIGKILL if SIGTERM didn't work
            if not force:
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    self._remove_pid_file(name)
                    return True

            return False
        except (ProcessLookupError, PermissionError, OSError):
            self._remove_pid_file(name)
            return False

    def _remove_pid_file(self, name: str) -> None:
        """Remove PID file for an instance."""
        pid_file = self._get_pid_file(name)
        if pid_file.exists():
            pid_file.unlink()

    def _write_pid_file(self, name: str, pid: int, port: int, host: str) -> None:
        """Write PID file for an instance."""
        pid_file = self._get_pid_file(name)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(json.dumps({
            "pid": pid,
            "port": port,
            "host": host,
            "started_at": datetime.now().isoformat(),
        }, indent=2))

    def _ensure_instance_config(
        self, name: str, port: int, host: str
    ) -> dict[str, Any]:
        """Ensure instance config exists, creating with defaults if needed."""
        config_dir = self._get_instance_dir(name)
        config_file = config_dir / "config.ini"
        db_path = str(config_dir / "data.db")

        if not config_file.exists():
            config_dir.mkdir(parents=True, exist_ok=True)

            api_token = secrets.token_urlsafe(32)
            config_content = f"""\
# genro-proxy configuration
# Generated automatically - edit as needed

[server]
name = {name}
host = {host}
port = {port}

[database]
path = {db_path}

[auth]
api_token = {api_token}
"""
            config_file.write_text(config_content)

        return self._read_instance_config(name) or {
            "name": name,
            "db_path": db_path,
            "host": host,
            "port": port,
            "config_file": str(config_file),
        }

    @POST
    async def serve(
        self,
        name: str = "default",
        host: str | None = None,
        port: int | None = None,
        background: bool = False,
    ) -> dict:
        """Start a proxy server instance.

        If the instance doesn't exist, creates it with default config.
        If already running, returns status and exits.

        Args:
            name: Instance name (default: "default").
            host: Host to bind to (default: from config or "0.0.0.0").
            port: Port to listen on (default: from config or 8000).
            background: If True, start in background and return immediately.

        Returns:
            Dict with ok=True and instance information.
        """
        # Check if already running
        is_running, pid, running_port = self._is_instance_running(name)
        if is_running:
            return {
                "ok": True,
                "already_running": True,
                "name": name,
                "pid": pid,
                "port": running_port,
                "url": f"http://localhost:{running_port}",
            }

        # Get or create instance config
        instance_config = self._read_instance_config(name)

        if instance_config is None:
            # New instance - use provided values or defaults
            effective_host = host or "0.0.0.0"
            effective_port = port or 8000
            instance_config = self._ensure_instance_config(
                name, effective_port, effective_host
            )
        else:
            # Existing instance - use config values, allow override
            effective_host = host or instance_config.get("host", "0.0.0.0")
            effective_port = port or instance_config.get("port", 8000)

        db_path = instance_config.get("db_path", str(self._get_instance_dir(name) / "data.db"))
        config_file = instance_config.get("config_file", str(self._get_config_file(name)))

        if background:
            # Start in background via subprocess
            cmd = [
                self.proxy.cli_command, "serve", name,
                "--host", effective_host,
                "--port", str(effective_port),
            ]
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            # Wait briefly for startup
            for _ in range(20):  # Max 2 seconds
                time.sleep(0.1)
                is_running, pid, _ = self._is_instance_running(name)
                if is_running:
                    break

            return {
                "ok": True,
                "background": True,
                "name": name,
                "pid": pid if is_running else None,
                "port": effective_port,
                "host": effective_host,
                "url": f"http://localhost:{effective_port}",
                "started": is_running,
            }

        # Return config for foreground start (actual uvicorn start done by CLI)
        return {
            "ok": True,
            "name": name,
            "host": effective_host,
            "port": effective_port,
            "db_path": db_path,
            "config_file": config_file,
            "env": {
                "GENRO_PROXY_DB": db_path,
                "GENRO_PROXY_CONFIG": config_file,
                "GENRO_PROXY_INSTANCE": name,
                "GENRO_PROXY_HOST": effective_host,
                "GENRO_PROXY_PORT": str(effective_port),
            },
        }

    async def list_all(self) -> dict:
        """List all configured instances with running status.

        Scans ~/.gproxy/ for instance directories and returns
        their configuration and running status.

        Returns:
            Dict with ok=True and instances list. Each instance contains:
                - name: Instance identifier
                - port: Configured port
                - host: Configured host
                - running: True if process is running
                - pid: Process ID if running
                - url: URL if running
        """
        base_dir = self.proxy.base_dir

        if not base_dir.exists():
            return {"ok": True, "instances": []}

        instances = []
        for item in base_dir.iterdir():
            if not item.is_dir():
                continue

            config_file = item / "config.ini"
            db_file = item / "data.db"

            # Skip directories without config or database
            if not config_file.exists() and not db_file.exists():
                continue

            instance_name = item.name
            config = self._read_instance_config(instance_name)

            if config is None:
                # Legacy instance with database but no config
                config = {
                    "name": instance_name,
                    "host": "0.0.0.0",
                    "port": 8000,
                }

            is_running, pid, running_port = self._is_instance_running(instance_name)

            instance_info: dict[str, Any] = {
                "name": instance_name,
                "port": running_port or config.get("port", 8000),
                "host": config.get("host", "0.0.0.0"),
                "running": is_running,
            }

            if is_running:
                instance_info["pid"] = pid
                instance_info["url"] = f"http://localhost:{instance_info['port']}"

            instances.append(instance_info)

        # Sort by name
        instances.sort(key=lambda x: x["name"])

        return {"ok": True, "instances": instances}

    @POST
    async def stop(self, name: str = "*", force: bool = False) -> dict:
        """Stop running instance(s).

        Args:
            name: Instance name or "*" to stop all running instances.
            force: If True, use SIGKILL instead of SIGTERM.

        Returns:
            Dict with ok=True and stopped instances list.
        """
        stopped = []

        if name == "*":
            # Stop all running instances
            result = await self.list_all()
            for inst in result.get("instances", []):
                if inst.get("running"):
                    if self._stop_instance_process(inst["name"], force=force):
                        stopped.append(inst["name"])
        else:
            # Stop specific instance
            is_running, _, _ = self._is_instance_running(name)
            if is_running:
                if self._stop_instance_process(name, force=force):
                    stopped.append(name)
            else:
                return {"ok": False, "error": f"Instance '{name}' is not running"}

        return {"ok": True, "stopped": stopped, "count": len(stopped)}

    @POST
    async def restart(self, name: str = "*", force: bool = False) -> dict:
        """Restart running instance(s).

        Stops the instance(s) and returns instructions to start them.
        Actual start must be done via CLI since it requires spawning a process.

        Args:
            name: Instance name or "*" to restart all running instances.
            force: If True, use SIGKILL for stopping.

        Returns:
            Dict with ok=True, stopped instances, and start instructions.
        """
        # First stop
        stop_result = await self.stop(name=name, force=force)

        if not stop_result.get("ok"):
            return stop_result

        stopped = stop_result.get("stopped", [])

        # Return instructions for starting
        start_commands = [f"{self.proxy.cli_command} serve {inst}" for inst in stopped]

        return {
            "ok": True,
            "stopped": stopped,
            "message": "Instances stopped. Start them with the commands below.",
            "start_commands": start_commands,
        }


__all__ = ["InstanceEndpoint"]
