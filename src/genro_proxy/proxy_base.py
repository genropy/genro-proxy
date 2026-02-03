# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Base configuration and class for Genro Proxy services.

This module defines:
- ProxyConfigBase: Configuration dataclass for all proxy services
- config_from_env(): Factory to build config from GENRO_PROXY_* env vars
- ProxyBase: Foundation class with database, endpoints, and interfaces

Configuration via environment variables:
    GENRO_PROXY_DB: Database path (SQLite file or PostgreSQL URL)
    GENRO_PROXY_API_TOKEN: API authentication token
    GENRO_PROXY_INSTANCE: Instance name for display
    GENRO_PROXY_PORT: Server port (default: 8000)
    GENRO_PROXY_HOST: Server host (default: 0.0.0.0)

ProxyBase provides:
1. Configuration: ProxyConfigBase instance at self.config
2. Encryption: EncryptionManager at self.encryption (loads key from env/secrets)
3. Database: SqlDb at self.db with autodiscovered Table classes
4. Endpoints: EndpointManager at self.endpoints with autodiscovered Endpoint classes
5. API: ApiManager at self.api (creates FastAPI app lazily)
6. CLI: CliManager at self.cli (creates Click group lazily)

Class Hierarchy:
    ProxyBase (this class)
        └── MailProxy (genro-mail-proxy): adds SMTP sender, background loops
        └── WopiProxy (genro-wopi): adds WOPI protocol handlers

Usage:
    # From environment (Docker/production):
    config = config_from_env()
    proxy = MyProxy(config=config)

    # Explicit configuration:
    config = ProxyConfigBase(
        db_path="/data/service.db",
        instance_name="my-proxy",
    )
    proxy = MyProxy(config=config)
    await proxy.init()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from .interface.api_base import ApiManager
from .interface.cli_base import CliManager
from .interface.endpoint_base import EndpointManager
from .sql import SqlDb
from .encryption import EncryptionManager

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfigBase:
    """Base configuration for all Genro proxy services.

    Attributes:
        db_path: SQLite/PostgreSQL database path for persistence.
        instance_name: Service identifier for display.
        port: Default port for API server.
        api_token: API authentication token. If None, no auth required.
        test_mode: Enable test mode (disables automatic processing).
        start_active: Whether to start processing immediately.
    """

    db_path: str = "/data/service.db"
    instance_name: str = "proxy"
    port: int = 8000
    api_token: str | None = None
    test_mode: bool = False
    start_active: bool = False


def config_from_env() -> ProxyConfigBase:
    """Build ProxyConfigBase from GENRO_PROXY_* environment variables.

    Environment variables:
        GENRO_PROXY_DB: Database path (default: /data/service.db)
        GENRO_PROXY_API_TOKEN: API token (default: None, no auth)
        GENRO_PROXY_INSTANCE: Instance name (default: "proxy")
        GENRO_PROXY_PORT: Server port (default: 8000)
        GENRO_PROXY_TEST_MODE: Enable test mode (default: false)
        GENRO_PROXY_START_ACTIVE: Start active (default: false)

    Returns:
        ProxyConfigBase instance populated from environment.
    """
    return ProxyConfigBase(
        db_path=os.environ.get("GENRO_PROXY_DB", "/data/service.db"),
        instance_name=os.environ.get("GENRO_PROXY_INSTANCE", "proxy"),
        port=int(os.environ.get("GENRO_PROXY_PORT", "8000")),
        api_token=os.environ.get("GENRO_PROXY_API_TOKEN"),
        test_mode=os.environ.get("GENRO_PROXY_TEST_MODE", "").lower() in ("1", "true", "yes"),
        start_active=os.environ.get("GENRO_PROXY_START_ACTIVE", "").lower() in ("1", "true", "yes"),
    )


class ProxyBase:
    """Foundation layer: config, encryption, database, tables, endpoints, interfaces.

    Attributes:
        config: ProxyConfigBase instance with all configuration
        encryption: EncryptionManager for field encryption
        db: SqlDb with autodiscovered Table classes
        endpoints: EndpointManager with autodiscovered Endpoint instances
        api: ApiManager (creates FastAPI app lazily)
        cli: CliManager (creates Click group lazily)

    Class Attributes (override in subclass):
        entity_packages: List of package names to scan for entities
        ee_entity_packages: List of EE package names for mixin composition
        encryption_key_env: Environment variable name for encryption key
    """

    # Override in subclass to specify entity discovery packages
    entity_packages: list[str] = ["genro_proxy.entities"]
    ee_entity_packages: list[str] = []
    encryption_key_env: str = "PROXY_ENCRYPTION_KEY"

    def __init__(self, config: ProxyConfigBase | None = None):
        """Initialize base proxy with config and all managers."""
        self.config = config or ProxyConfigBase()

        self.encryption = EncryptionManager(parent=self, env_var=self.encryption_key_env)

        self.db = SqlDb(self.config.db_path, parent=self)
        self.db.discover(*self.entity_packages)

        self.endpoints = EndpointManager(parent=self)
        self.endpoints.discover(*self.entity_packages, ee_packages=self.ee_entity_packages)

        self.api = ApiManager(parent=self)
        self.cli = CliManager(parent=self)

    @property
    def encryption_key(self) -> bytes | None:
        """Encryption key for database field encryption. None if not configured."""
        return self.encryption.key

    async def init(self) -> None:
        """Initialize database: create tables within a transaction.

        This uses a single transaction to set up schema. The connection is
        committed and released after initialization, ready for per-request use.
        """
        async with self.db.connection():
            await self.db.check_structure()

            # Sync schema for base tables
            for table_name in self.db.tables:
                table = self.db.table(table_name)
                if hasattr(table, "sync_schema"):
                    await table.sync_schema()

    async def shutdown(self) -> None:
        """Shutdown application: close database pool/connection."""
        await self.db.shutdown()


__all__ = ["ProxyBase", "ProxyConfigBase", "config_from_env"]
