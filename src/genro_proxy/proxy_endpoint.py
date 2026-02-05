# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Proxy-level endpoint for server and instance management.

This module provides the ProxyEndpoint class for managing proxy server
instances at the process/configuration level (as opposed to InstanceEndpoint
which manages the current running instance state via database).

Operations include:
    - serve: Start a proxy server instance (process management)
    - stop: Stop running instance(s) (process management)
    - restart: Restart running instance(s) (process management)
    - list_instances: List all configured instances with running status

The ProxyEndpoint is designed to be subclassed by proxy implementations
that need to expose additional proxy-level commands. For example::

    class MyProxyEndpoint(ProxyEndpoint):
        name = "myproxy"  # or keep "proxy"

        async def custom_command(self) -> dict:
            '''Custom proxy-level command.'''
            return {"ok": True}

Example:
    CLI commands auto-generated::

        gproxy proxy serve default --port 8000
        gproxy proxy list-instances
        gproxy proxy stop dev-instance
        gproxy proxy restart "*"
"""

from __future__ import annotations

import configparser
import json
import os
import secrets
import signal
import subprocess
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .interface.endpoint_base import BaseEndpoint, endpoint

if TYPE_CHECKING:
    from .proxy_base import ProxyBase


class ProxyEndpoint(BaseEndpoint):
    """Endpoint for proxy server and instance management.

    Provides process and configuration operations for managing proxy instances:
    starting, stopping, restarting server processes, and listing instances.

    This class can be subclassed by proxy implementations to add custom
    proxy-level commands that are not related to specific entities.

    Attributes:
        name: Endpoint name used in URL paths ("proxy").
        proxy: ProxyBase instance for accessing configuration.
    """

    name = "proxy"

    def __init__(self, proxy: ProxyBase):
        """Initialize endpoint with proxy reference.

        Args:
            proxy: ProxyBase instance for accessing base_dir, cli_command, etc.
        """
        # ProxyEndpoint doesn't use a table, pass None
        super().__init__(table=None)
        self.proxy = proxy

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[None]:
        """No-op connection context for ProxyEndpoint (no database)."""
        yield

    # -------------------------------------------------------------------------
    # Private helpers for instance/process management
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

    # -------------------------------------------------------------------------
    # Public async methods (API/CLI)
    # -------------------------------------------------------------------------

    @endpoint(post=True, api=False)
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

    async def list_instances(self) -> dict:
        """List all configured instances with running status.

        Scans the proxy base_dir for instance directories and returns
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

    @endpoint(post=True)
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
            result = await self.list_instances()
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

    @endpoint(post=True)
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


__all__ = ["ProxyEndpoint"]
