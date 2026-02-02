# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Base configuration dataclasses for Genro Proxy.

This module defines the base configuration hierarchy for genro-proxy.
ProxyConfigBase is the foundation for all proxy services, providing
common settings like database path, API token, and test mode.

Domain-specific proxies (mail, wopi) extend these dataclasses with
their own configuration groups.

Usage:
    config = ProxyConfigBase(
        db_path="/data/service.db",
        instance_name="my-proxy",
    )
    proxy = MyProxy(config=config)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProxyConfigBase:
    """Base configuration for all Genro proxy services.

    This provides the minimal configuration needed by ProxyBase.
    Domain-specific proxies should extend this with their own settings.

    Attributes:
        db_path: SQLite/PostgreSQL database path for persistence.
        instance_name: Service identifier for display.
        port: Default port for API server.
        api_token: API authentication token. If None, no auth required.
        test_mode: Enable test mode (disables automatic processing).
        start_active: Whether to start processing immediately.

    Example:
        config = ProxyConfigBase(
            db_path="/data/service.db",
            instance_name="my-proxy",
            port=8080,
        )
        proxy = MyProxy(config=config)
    """

    db_path: str = "/data/service.db"
    """SQLite database path for persistence."""

    instance_name: str = "proxy"
    """Instance name for display and identification."""

    port: int = 8000
    """Default port for API server."""

    api_token: str | None = None
    """API authentication token. If None, no auth required."""

    test_mode: bool = False
    """Enable test mode (disables automatic processing)."""

    start_active: bool = False
    """Whether to start processing immediately."""


__all__ = ["ProxyConfigBase"]
