# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""CLI context management for instance/tenant resolution.

Provides configurable context resolution for multi-instance proxy deployments.
Each proxy can override the default settings (env vars, base directory, db name).

Default configuration:
    - Base directory: ~/.gproxy/
    - Env vars: GPROXY_INSTANCE, GPROXY_TENANT
    - DB name: proxy.db

Resolution order for instance:
    1. Explicit argument
    2. Environment variable (GPROXY_INSTANCE)
    3. ~/.gproxy/.current file
    4. Auto-select if only one instance exists

Resolution order for tenant:
    1. Explicit argument
    2. Environment variable (GPROXY_TENANT)
    3. ~/.gproxy/.current file (tenant part)

Example:
    Basic usage::

        from proxy.interface.cli_context import resolve_context, require_context

        instance, tenant = resolve_context()
        instance, tenant = require_context(require_tenant=True)

    Custom configuration for mail-proxy::

        from proxy.interface.cli_context import CliContext

        ctx = CliContext(
            base_dir=Path.home() / ".mail-proxy",
            env_instance="GMP_INSTANCE",
            env_tenant="GMP_TENANT",
            db_name="mail_service.db",
            cli_name="mail-proxy",
        )
        instance, tenant = ctx.resolve_context()
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable


# Default configuration
_DEFAULT_BASE_DIR = Path.home() / ".gproxy"
_DEFAULT_ENV_INSTANCE = "GPROXY_INSTANCE"
_DEFAULT_ENV_TENANT = "GPROXY_TENANT"
_DEFAULT_DB_NAME = "proxy.db"
_DEFAULT_CLI_NAME = "gproxy"


class CliContext:
    """Configurable CLI context manager for instance/tenant resolution.

    Attributes:
        base_dir: Base directory for all instances (~/.gproxy/).
        env_instance: Environment variable for instance (GPROXY_INSTANCE).
        env_tenant: Environment variable for tenant (GPROXY_TENANT).
        db_name: Database filename to detect instances (proxy.db).
        cli_name: CLI command name for error messages (gproxy).
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        env_instance: str | None = None,
        env_tenant: str | None = None,
        db_name: str | None = None,
        cli_name: str | None = None,
        print_func: Callable[[str], None] | None = None,
    ):
        """Initialize CLI context with custom configuration.

        Args:
            base_dir: Base directory for instances. Default: ~/.gproxy/
            env_instance: Env var name for instance. Default: GPROXY_INSTANCE
            env_tenant: Env var name for tenant. Default: GPROXY_TENANT
            db_name: Database filename. Default: proxy.db
            cli_name: CLI name for messages. Default: gproxy
            print_func: Custom print function for messages. Default: print
        """
        self.base_dir = base_dir or _DEFAULT_BASE_DIR
        self.env_instance = env_instance or _DEFAULT_ENV_INSTANCE
        self.env_tenant = env_tenant or _DEFAULT_ENV_TENANT
        self.db_name = db_name or _DEFAULT_DB_NAME
        self.cli_name = cli_name or _DEFAULT_CLI_NAME
        self._print = print_func or print

    @property
    def current_file(self) -> Path:
        """Path to .current file storing active context."""
        return self.base_dir / ".current"

    def get_instance_dir(self, name: str) -> Path:
        """Get the instance directory path."""
        return self.base_dir / name

    def list_instances(self) -> list[str]:
        """List all configured instance names."""
        if not self.base_dir.exists():
            return []
        return [
            item.name
            for item in self.base_dir.iterdir()
            if item.is_dir()
            and ((item / "config.ini").exists() or (item / self.db_name).exists())
        ]

    def parse_context(self, value: str) -> tuple[str | None, str | None]:
        """Parse instance/tenant context string.

        Formats:
            "instance" -> (instance, None)
            "instance/tenant" -> (instance, tenant)
            "/tenant" -> (None, tenant)
            "instance/" -> (instance, None)

        Returns:
            (instance, tenant) tuple. None means "keep current".
        """
        if "/" in value:
            parts = value.split("/", 1)
            instance = parts[0] or None
            tenant = parts[1] or None
            return instance, tenant
        return value, None

    def get_current_context(self) -> tuple[str | None, str | None]:
        """Get current instance and tenant from .current file."""
        if not self.current_file.exists():
            return None, None
        content = self.current_file.read_text().strip()
        if not content:
            return None, None
        return self.parse_context(content)

    def set_current_context(self, instance: str | None, tenant: str | None) -> None:
        """Set current instance and tenant in .current file."""
        if not instance:
            return
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if tenant:
            self.current_file.write_text(f"{instance}/{tenant}")
        else:
            self.current_file.write_text(instance)

    def resolve_context(
        self,
        explicit_instance: str | None = None,
        explicit_tenant: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Resolve active instance and tenant using priority chain.

        Resolution order for instance:
            1. Explicit argument
            2. Environment variable
            3. .current file
            4. Auto-select if only one instance

        Resolution order for tenant:
            1. Explicit argument
            2. Environment variable
            3. .current file

        Returns:
            (instance, tenant) tuple. Either can be None.
        """
        # Resolve instance
        instance: str | None = None

        if explicit_instance:
            instance = explicit_instance
        else:
            env_instance = os.environ.get(self.env_instance)
            if env_instance:
                instance = env_instance
            else:
                current_instance, _ = self.get_current_context()
                if current_instance:
                    instance = current_instance
                else:
                    instances = self.list_instances()
                    if len(instances) == 1:
                        instance = instances[0]

        # Resolve tenant
        tenant: str | None = None

        if explicit_tenant:
            tenant = explicit_tenant
        else:
            env_tenant = os.environ.get(self.env_tenant)
            if env_tenant:
                tenant = env_tenant
            else:
                _, current_tenant = self.get_current_context()
                if current_tenant:
                    tenant = current_tenant

        return instance, tenant

    def require_context(
        self,
        explicit_instance: str | None = None,
        explicit_tenant: str | None = None,
        require_tenant: bool = False,
    ) -> tuple[str, str | None]:
        """Resolve context or exit with error if ambiguous.

        Args:
            explicit_instance: Explicitly specified instance name.
            explicit_tenant: Explicitly specified tenant name.
            require_tenant: If True, tenant must be resolved.

        Returns:
            (instance, tenant) tuple.

        Raises:
            SystemExit: If required context cannot be resolved.
        """
        instance, tenant = self.resolve_context(explicit_instance, explicit_tenant)

        if not instance:
            instances = self.list_instances()
            if not instances:
                self._print(f"Error: No instances configured.")
                self._print(f"Use '{self.cli_name} serve <name>' to create one.")
                sys.exit(1)

            self._print("Error: Multiple instances found. Specify which one:")
            self._print("")
            for name in sorted(instances):
                self._print(f"  - {name}")
            self._print("")
            self._print("Options:")
            self._print(f"  - Use '{self.cli_name} use <instance>' to set default")
            self._print(f"  - Set {self.env_instance} environment variable")
            sys.exit(1)

        if require_tenant and not tenant:
            self._print("Error: Tenant required for this command.")
            self._print("")
            self._print("Options:")
            self._print(f"  - Use '{self.cli_name} use {instance}/<tenant>'")
            self._print(f"  - Set {self.env_tenant} environment variable")
            sys.exit(1)

        return instance, tenant


# Default instance for simple usage
_default_context = CliContext()


def resolve_context(
    explicit_instance: str | None = None,
    explicit_tenant: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve active instance and tenant using default configuration."""
    return _default_context.resolve_context(explicit_instance, explicit_tenant)


def require_context(
    explicit_instance: str | None = None,
    explicit_tenant: str | None = None,
    require_tenant: bool = False,
) -> tuple[str, str | None]:
    """Resolve context or exit with error using default configuration."""
    return _default_context.require_context(
        explicit_instance, explicit_tenant, require_tenant
    )


def get_default_context() -> CliContext:
    """Get the default CliContext instance."""
    return _default_context


def set_default_context(ctx: CliContext) -> None:
    """Set the default CliContext instance."""
    global _default_context
    _default_context = ctx


__all__ = [
    "CliContext",
    "resolve_context",
    "require_context",
    "get_default_context",
    "set_default_context",
]
