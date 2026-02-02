# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Base class for Genro Proxy services: database, tables, endpoints, and interface factories.

ProxyBase is the foundation layer of genro-proxy, providing:

1. Configuration: ProxyConfigBase instance at self.config
2. Database: SqlDb at self.db with autodiscovered Table classes
3. Endpoints: Registry at self.endpoints with autodiscovered Endpoint classes
4. Interfaces: Lazy `api` (FastAPI) and `cli` (Click) properties

Class Hierarchy:
    ProxyBase (this class)
        └── MailProxy (genro-mail-proxy): adds SMTP sender, background loops
        └── WopiProxy (genro-wopi): adds WOPI protocol handlers

Discovery Mechanism:
    Tables are discovered from entity packages specified in `entity_packages`.
    Optional EE mixins are composed with CE classes automatically.

Usage:
    class MyProxy(ProxyBase):
        entity_packages = ["myproxy.entities"]

    proxy = MyProxy(config=ProxyConfigBase(db_path=":memory:"))
    await proxy.init()
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING, Any

from .proxy_config import ProxyConfigBase
from .sql import SqlDb

if TYPE_CHECKING:
    import click
    from fastapi import FastAPI

    from .interface.endpoint_base import BaseEndpoint

logger = logging.getLogger(__name__)


class ProxyBase:
    """Foundation layer: config, database, tables, endpoints, interface factories.

    Attributes:
        config: ProxyConfigBase instance with all configuration
        db: SqlDb with autodiscovered Table classes
        endpoints: Dict of Endpoint instances keyed by name

    Properties:
        api: FastAPI app (lazy, created on first access)
        cli: Click CLI group (lazy, created on first access)

    Class Attributes (override in subclass):
        entity_packages: List of package names to scan for entities
        ee_entity_packages: List of EE package names for mixin composition
        encryption_key_env: Environment variable name for encryption key
    """

    # Override in subclass to specify entity discovery packages
    entity_packages: list[str] = ["proxy.entities"]
    ee_entity_packages: list[str] = []
    encryption_key_env: str = "PROXY_ENCRYPTION_KEY"

    def __init__(self, config: ProxyConfigBase | None = None):
        """Initialize base proxy with config and database.

        Args:
            config: ProxyConfigBase instance. If None, creates default.
        """
        self.config = config or ProxyConfigBase()

        self._encryption_key: bytes | None = None
        self._load_encryption_key()

        self.db = SqlDb(self.config.db_path or ":memory:", parent=self)
        self._discover_tables()

        self.endpoints: dict[str, BaseEndpoint] = {}
        self._discover_endpoints()

        self._api: FastAPI | None = None
        self._cli: click.Group | None = None

    def _load_encryption_key(self) -> None:
        """Load encryption key from environment or secrets file.

        Sources (in priority order):
        1. Environment variable (base64-encoded 32 bytes)
        2. /run/secrets/encryption_key file (Docker/K8s secrets)

        If no key is configured, encryption is disabled.
        """
        import base64
        import os
        from pathlib import Path

        # 1. Environment variable
        key_b64 = os.environ.get(self.encryption_key_env)
        if key_b64:
            try:
                key = base64.b64decode(key_b64)
                if len(key) == 32:
                    self._encryption_key = key
                    return
            except Exception:
                pass

        # 2. Secrets file
        secrets_path = Path("/run/secrets/encryption_key")
        if secrets_path.exists():
            try:
                key = secrets_path.read_bytes().strip()
                if len(key) == 32:
                    self._encryption_key = key
                    return
            except Exception:
                pass

    @property
    def encryption_key(self) -> bytes | None:
        """Encryption key for database field encryption. None if not configured."""
        return self._encryption_key

    def set_encryption_key(self, key: bytes) -> None:
        """Set encryption key programmatically (for testing)."""
        if len(key) != 32:
            raise ValueError("Encryption key must be 32 bytes")
        self._encryption_key = key

    def _discover_tables(self) -> None:
        """Autodiscover Table classes from entity packages and compose with EE mixins."""
        # Collect CE modules from all entity packages
        ce_modules: dict[str, Any] = {}
        for package in self.entity_packages:
            ce_modules.update(self._find_entity_modules(package, "table"))

        # Collect EE modules if packages specified
        ee_modules: dict[str, Any] = {}
        for package in self.ee_entity_packages:
            ee_modules.update(self._find_entity_modules(package, "table_ee"))

        for entity_name, ce_module in ce_modules.items():
            ce_class = self._get_class_from_module(ce_module, "Table")
            if not ce_class:
                continue

            ee_module = ee_modules.get(entity_name)
            if ee_module:
                ee_mixin = self._get_ee_mixin_from_module(ee_module, "_EE")
                if ee_mixin:
                    composed_class = type(
                        ce_class.__name__, (ee_mixin, ce_class), {"__module__": ce_class.__module__}
                    )
                    self.db.add_table(composed_class)
                    continue

            self.db.add_table(ce_class)

    def _discover_endpoints(self) -> None:
        """Autodiscover Endpoint classes and instantiate them."""
        from .interface.endpoint_base import BaseEndpoint

        for endpoint_class in BaseEndpoint.discover():
            table = self.db.table(endpoint_class.name)
            # InstanceEndpoint needs proxy reference, others just need table
            if endpoint_class.name == "instance":
                self.endpoints[endpoint_class.name] = endpoint_class(table, proxy=self)
            else:
                self.endpoints[endpoint_class.name] = endpoint_class(table)

    def endpoint(self, name: str) -> "BaseEndpoint":
        """Get endpoint by name."""
        if name not in self.endpoints:
            raise ValueError(f"Endpoint '{name}' not found")
        return self.endpoints[name]

    async def init(self) -> None:
        """Initialize database: connect and create tables.

        Override in subclass to add domain-specific initialization.
        """
        await self.db.connect()
        await self.db.check_structure()

        # Sync schema for base tables
        for table_name in self.db.tables:
            table = self.db.table(table_name)
            if hasattr(table, "sync_schema"):
                await table.sync_schema()

        # Initialize edition
        await self._init_edition()

    async def _init_edition(self) -> None:
        """Detect CE/EE mode based on installed modules and existing data.

        Override in subclass for domain-specific edition detection.
        """
        # Default implementation: check if tenants table exists and has data
        if "tenants" in self.db.tables:
            tenants_table = self.db.table("tenants")
            tenants = await tenants_table.list_all()
            if len(tenants) == 0 and hasattr(tenants_table, "ensure_default"):
                await tenants_table.ensure_default()

    async def close(self) -> None:
        """Close database connection."""
        await self.db.close()

    # -------------------------------------------------------------------------
    # Discovery helpers (private)
    # -------------------------------------------------------------------------

    def _find_entity_modules(self, base_package: str, module_name: str) -> dict[str, Any]:
        """Scan package for entity subpackages containing module_name."""
        result: dict[str, Any] = {}
        try:
            package = importlib.import_module(base_package)
        except ImportError:
            return result

        package_path = getattr(package, "__path__", None)
        if not package_path:
            return result

        for _, name, is_pkg in pkgutil.iter_modules(package_path):
            if not is_pkg:
                continue
            full_module_name = f"{base_package}.{name}.{module_name}"
            try:
                module = importlib.import_module(full_module_name)
                result[name] = module
            except ImportError:
                pass
        return result

    def _get_class_from_module(self, module: Any, class_suffix: str) -> type | None:
        """Extract Table/Endpoint class by suffix (excludes _EE mixins)."""
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            obj = getattr(module, attr_name)
            if isinstance(obj, type) and attr_name.endswith(class_suffix):
                if "_EE" in attr_name or "Mixin" in attr_name:
                    continue
                if attr_name == "Table":
                    continue
                if not hasattr(obj, "name"):
                    continue
                return obj
        return None

    def _get_ee_mixin_from_module(self, module: Any, class_suffix: str) -> type | None:
        """Extract EE mixin class (suffix _EE) for composition with CE class."""
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if isinstance(obj, type) and name.endswith(class_suffix):
                return obj
        return None

    # -------------------------------------------------------------------------
    # Interface factories (lazy properties)
    # -------------------------------------------------------------------------

    @property
    def api(self) -> "FastAPI":
        """FastAPI app with all endpoints, auth middleware, and lifespan.

        Created on first access. Override _create_api() in subclass to customize.
        """
        if self._api is None:
            self._api = self._create_api()
        return self._api

    def _create_api(self) -> "FastAPI":
        """Create FastAPI application. Override in subclass to customize."""
        from .interface.api_base import ApiBase

        api_factory = ApiBase(self)
        return api_factory.app

    @property
    def cli(self) -> "click.Group":
        """Click CLI group with endpoint commands and service commands.

        Created on first access. Override _create_cli() in subclass to customize.
        """
        if self._cli is None:
            self._cli = self._create_cli()
        return self._cli

    def _create_cli(self) -> "click.Group":
        """Build Click CLI: endpoint commands + service commands."""
        import click

        @click.group()
        @click.version_option()
        def cli() -> None:
            """Genro Proxy service."""
            pass

        # Register endpoint-based commands
        from .interface.cli_base import register_cli_endpoint

        for endpoint in self.endpoints.values():
            register_cli_endpoint(cli, endpoint)

        # Add serve command
        @cli.command("serve")
        @click.option("--host", default="0.0.0.0", help="Bind host")
        @click.option("--port", "-p", default=self.config.port, help="Bind port")
        @click.option("--reload", is_flag=True, help="Enable auto-reload")
        def serve_cmd(host: str, port: int, reload: bool) -> None:
            """Start the API server."""
            import uvicorn

            uvicorn.run(
                self._get_server_module(),
                host=host,
                port=port,
                reload=reload,
            )

        return cli

    def _get_server_module(self) -> str:
        """Get the server module path for uvicorn. Override in subclass."""
        return "proxy.server:app"


__all__ = ["ProxyBase"]
