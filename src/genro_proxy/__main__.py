# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""CLI entry point for genro-proxy (gproxy command).

Usage:
    gproxy --help
    gproxy instance list-all
    gproxy tenants list
    gproxy serve --port 8000
"""

from .proxy_base import ProxyBase, config_from_env


def main() -> None:
    """CLI entry point."""
    config = config_from_env()
    proxy = ProxyBase(config=config)
    proxy.cli.cli()


if __name__ == "__main__":
    main()
