# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""CLI entry point for genro-proxy (gproxy command).

Provides generic instance management commands that can be used by any
proxy built on genro-proxy. Specialized proxies extend this with their
own commands.

Commands:
    list: List all proxy instances with status
    stop: Stop running instances
    restart: Restart running instances
    version: Show version info
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

console = Console()

# Default instance directory (can be overridden by subclasses)
DEFAULT_INSTANCE_DIR = ".genro-proxy"


def get_instance_base_dir(proxy_name: str | None = None) -> Path:
    """Get the base directory for proxy instances.

    Args:
        proxy_name: Optional proxy-specific name (e.g., "mail-proxy").
                   If None, uses generic ".genro-proxy".

    Returns:
        Path to ~/.{proxy_name}/ or ~/.genro-proxy/
    """
    dir_name = f".{proxy_name}" if proxy_name else DEFAULT_INSTANCE_DIR
    return Path.home() / dir_name


def get_instance_dir(name: str, proxy_name: str | None = None) -> Path:
    """Get the instance directory path."""
    return get_instance_base_dir(proxy_name) / name


def get_pid_file(name: str, proxy_name: str | None = None) -> Path:
    """Get the PID file path for an instance."""
    return get_instance_dir(name, proxy_name) / "server.pid"


def is_instance_running(name: str, proxy_name: str | None = None) -> tuple[bool, int | None, int | None]:
    """Check if an instance is running.

    Returns:
        (is_running, pid, port) tuple
    """
    import os

    pid_file = get_pid_file(name, proxy_name)
    if not pid_file.exists():
        return False, None, None

    try:
        data = json.loads(pid_file.read_text())
        pid = data.get("pid")
        port = data.get("port")

        if pid is None:
            return False, None, port

        # Check if process is alive (signal 0 doesn't kill, just checks)
        os.kill(pid, 0)
        return True, pid, port
    except (json.JSONDecodeError, ProcessLookupError, PermissionError, OSError):
        return False, None, None


def remove_pid_file(name: str, proxy_name: str | None = None) -> None:
    """Remove PID file for an instance."""
    pid_file = get_pid_file(name, proxy_name)
    if pid_file.exists():
        pid_file.unlink()


def stop_instance(
    name: str,
    signal_type: int = 15,
    timeout: float = 5.0,
    fallback_kill: bool = True,
    proxy_name: str | None = None,
) -> bool:
    """Stop a running instance by sending a signal.

    Args:
        name: Instance name.
        signal_type: Signal to send (15=SIGTERM, 9=SIGKILL).
        timeout: Seconds to wait for process to terminate.
        fallback_kill: If True, send SIGKILL if SIGTERM doesn't work.
        proxy_name: Optional proxy-specific name for instance directory.

    Returns:
        True if successfully stopped, False otherwise.
    """
    import os
    import signal as sig
    import time

    is_running, pid, _ = is_instance_running(name, proxy_name)
    if not is_running or pid is None:
        return False

    try:
        os.kill(pid, signal_type)
        wait_iterations = int(timeout / 0.1)
        for _ in range(wait_iterations):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                remove_pid_file(name, proxy_name)
                return True

        if fallback_kill and signal_type != sig.SIGKILL:
            os.kill(pid, sig.SIGKILL)
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                remove_pid_file(name, proxy_name)
                return True

        return False
    except (ProcessLookupError, PermissionError, OSError):
        remove_pid_file(name, proxy_name)
        return False


def get_instance_config(name: str, proxy_name: str | None = None) -> dict[str, Any] | None:
    """Read instance configuration from config.ini."""
    import configparser

    instance_dir = get_instance_dir(name, proxy_name)
    config_file = instance_dir / "config.ini"
    if not config_file.exists():
        return None

    config = configparser.ConfigParser()
    config.read(config_file)

    return {
        "name": config.get("server", "name", fallback=name),
        "db_path": config.get("server", "db_path", fallback=str(instance_dir / "service.db")),
        "host": config.get("server", "host", fallback="0.0.0.0"),
        "port": config.getint("server", "port", fallback=8000),
        "config_file": str(config_file),
    }


def list_instances(proxy_name: str | None = None) -> list[dict[str, Any]]:
    """List all configured instances.

    Args:
        proxy_name: Optional proxy-specific name for instance directory.

    Returns:
        List of instance info dicts.
    """
    import configparser

    base_dir = get_instance_base_dir(proxy_name)
    if not base_dir.exists():
        return []

    instances = []
    for item in base_dir.iterdir():
        if item.is_dir():
            config_file = item / "config.ini"
            db_file = item / "service.db"
            instance_name = item.name

            # Check for config.ini (new format) or service.db (legacy)
            if config_file.exists():
                config = configparser.ConfigParser()
                config.read(config_file)
                port = config.getint("server", "port", fallback=8000)
                host = config.get("server", "host", fallback="0.0.0.0")
                is_legacy = False
            elif db_file.exists():
                port = 8000
                host = "0.0.0.0"
                is_legacy = True
            else:
                continue

            is_running, pid, running_port = is_instance_running(instance_name, proxy_name)

            instances.append({
                "name": instance_name,
                "port": running_port or port,
                "host": host,
                "running": is_running,
                "pid": pid,
                "legacy": is_legacy,
            })

    return instances


# ============================================================================
# CLI Commands
# ============================================================================


@click.group()
@click.version_option(package_name="genro-proxy")
def main() -> None:
    """Genro Proxy - Base infrastructure for Genro microservices."""
    pass


@main.command("list")
@click.option("--proxy", "-p", default=None, help="Proxy type (e.g., 'mail-proxy'). Default: generic.")
def list_cmd(proxy: str | None) -> None:
    """List proxy instances with their status."""
    instances = list_instances(proxy)

    if not instances:
        dir_name = f".{proxy}" if proxy else DEFAULT_INSTANCE_DIR
        console.print(f"[dim]No instances found in ~/{dir_name}/[/dim]")
        return

    table = Table(title="Proxy Instances")
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Port", justify="right")
    table.add_column("PID", justify="right")
    table.add_column("URL")
    table.add_column("Note")

    for inst in sorted(instances, key=lambda x: x["name"]):
        if inst["running"]:
            status = "[green]running[/green]"
            pid_str = str(inst["pid"])
            url = f"http://localhost:{inst['port']}"
        else:
            status = "[dim]stopped[/dim]"
            pid_str = "[dim]-[/dim]"
            url = "[dim]-[/dim]"

        note = "[yellow]legacy[/yellow]" if inst.get("legacy") else ""

        table.add_row(
            inst["name"],
            status,
            str(inst["port"]),
            pid_str,
            url,
            note,
        )

    console.print(table)


@main.command("stop")
@click.argument("name", default="*")
@click.option("--proxy", "-p", default=None, help="Proxy type (e.g., 'mail-proxy'). Default: generic.")
@click.option("--force", "-f", is_flag=True, help="Force kill (SIGKILL) instead of graceful shutdown.")
def stop_cmd(name: str, proxy: str | None, force: bool) -> None:
    """Stop running proxy instance(s).

    NAME can be an instance name or '*' to stop all.
    """
    import signal as sig

    signal_type = sig.SIGKILL if force else sig.SIGTERM
    signal_name = "SIGKILL" if force else "SIGTERM"

    if name == "*":
        instances = list_instances(proxy)
        if not instances:
            console.print("[dim]No instances configured.[/dim]")
            return

        stopped = []
        for inst in instances:
            if inst["running"]:
                instance_name = inst["name"]
                console.print(f"Stopping {instance_name} (PID {inst['pid']})... ", end="")
                if stop_instance(instance_name, signal_type, proxy_name=proxy):
                    console.print("[green]stopped[/green]")
                    stopped.append(instance_name)
                else:
                    console.print(f"[yellow]sent {signal_name}[/yellow]")

        if not stopped:
            console.print("[dim]No running instances found.[/dim]")
        else:
            console.print(f"\n[green]Stopped {len(stopped)} instance(s)[/green]")
    else:
        is_running, pid, _ = is_instance_running(name, proxy)
        if not is_running:
            console.print(f"[dim]Instance '{name}' is not running.[/dim]")
            return

        console.print(f"Stopping {name} (PID {pid})... ", end="")
        if stop_instance(name, signal_type, proxy_name=proxy):
            console.print("[green]stopped[/green]")
        else:
            console.print(f"[yellow]sent {signal_name}, may still be shutting down[/yellow]")


@main.command("restart")
@click.argument("name", default="*")
@click.option("--proxy", "-p", default=None, help="Proxy type (e.g., 'mail-proxy'). Default: generic.")
@click.option("--force", "-f", is_flag=True, help="Force kill before restart.")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development.")
def restart_cmd(name: str, proxy: str | None, force: bool, reload: bool) -> None:
    """Restart proxy instance(s).

    NAME can be an instance name or '*' to restart all.

    Note: This command requires the specific proxy CLI to be installed
    (e.g., mail-proxy for mail instances).
    """
    import signal as sig
    import subprocess
    import time

    signal_type = sig.SIGKILL if force else sig.SIGTERM

    instances_to_restart: list[tuple[str, dict[str, Any]]] = []

    if name == "*":
        instances = list_instances(proxy)
        if not instances:
            console.print("[dim]No instances configured.[/dim]")
            return

        for inst in instances:
            if inst["running"]:
                config = get_instance_config(inst["name"], proxy)
                if config:
                    instances_to_restart.append((inst["name"], config))

        if not instances_to_restart:
            console.print("[dim]No running instances found.[/dim]")
            return
    else:
        is_running, _, _ = is_instance_running(name, proxy)
        if not is_running:
            console.print(f"[dim]Instance '{name}' is not running.[/dim]")
            return
        config = get_instance_config(name, proxy)
        if config:
            instances_to_restart.append((name, config))

    # Determine CLI command based on proxy type
    cli_cmd = proxy if proxy else "gproxy"

    # Stop all instances first
    for instance_name, _ in instances_to_restart:
        is_running, pid, _ = is_instance_running(instance_name, proxy)
        if is_running:
            console.print(f"Stopping {instance_name} (PID {pid})... ", end="")
            if stop_instance(instance_name, signal_type, timeout=3.0, proxy_name=proxy):
                console.print("[green]stopped[/green]")
            else:
                if not force:
                    console.print("[yellow]forcing...[/yellow] ", end="")
                    stop_instance(instance_name, sig.SIGKILL, timeout=1.0, proxy_name=proxy)
                console.print("[green]stopped[/green]")

    # Brief pause to ensure ports are released
    time.sleep(0.5)

    # Restart instances in background
    for instance_name, _config in instances_to_restart:
        console.print(f"Starting {instance_name}... ", end="")
        cmd = [cli_cmd, "serve", instance_name]
        if reload:
            cmd.append("--reload")

        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(1.0)
            is_running, pid, port = is_instance_running(instance_name, proxy)
            if is_running:
                console.print(f"[green]started[/green] (PID {pid}, port {port})")
            else:
                console.print("[yellow]starting in background...[/yellow]")
        except FileNotFoundError:
            console.print(f"[red]error: '{cli_cmd}' command not found[/red]")
            sys.exit(1)

    console.print(f"\n[green]Restarted {len(instances_to_restart)} instance(s)[/green]")


@main.command("version")
def version_cmd() -> None:
    """Show version information."""
    from proxy import __version__

    console.print(f"genro-proxy {__version__}")


if __name__ == "__main__":
    main()
