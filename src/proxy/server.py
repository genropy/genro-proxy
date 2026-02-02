# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""ASGI application entry point for uvicorn.

This module provides the FastAPI application instance for deployment
with ASGI servers like uvicorn, hypercorn, or gunicorn+uvicorn.

Configuration via environment variables:
    GENRO_PROXY_DB: Database path (SQLite file or PostgreSQL URL)
    GENRO_PROXY_API_TOKEN: API authentication token
    GENRO_PROXY_INSTANCE: Instance name for display
    GENRO_PROXY_PORT: Server port (default: 8000)

Components:
    app: FastAPI application with full Proxy lifecycle management.
    _proxy: Internal Proxy instance (use app instead).

Example:
    Run with uvicorn::

        GENRO_PROXY_DB=/data/proxy.db GENRO_PROXY_API_TOKEN=secret \\
            uvicorn proxy.server:app --host 0.0.0.0 --port 8000

    Run with Docker::

        docker run -e GENRO_PROXY_DB=/data/proxy.db -e GENRO_PROXY_API_TOKEN=secret ...

    Or via CLI (reads from ~/.gproxy/<name>/config.ini)::

        genro-proxy serve --port 8000

Note:
    The application includes a lifespan context manager that calls
    proxy.start() on startup and proxy.stop() on shutdown, ensuring
    proper initialization of background tasks and graceful cleanup.
"""

from .proxy_base import ProxyBase, config_from_env

# Create proxy and expose its API (includes lifespan management)
_proxy = ProxyBase(config=config_from_env())
app = _proxy.api
