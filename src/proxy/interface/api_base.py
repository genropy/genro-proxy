# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""FastAPI application manager with UI serving."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from proxy.proxy_base import ProxyBase  # noqa: F401


class ApiManager:
    """Manager for FastAPI application. Creates app lazily on first access."""

    def __init__(self, parent: "ProxyBase"):
        self.proxy = parent
        self._app: FastAPI | None = None

    @property
    def app(self) -> FastAPI:
        """Lazy-create FastAPI application."""
        if self._app is None:
            self._app = self._create_app()
        return self._app

    def _create_app(self) -> FastAPI:
        """Create and configure FastAPI application."""
        app = FastAPI(
            title=f"{self.proxy.config.instance_name} API",
            version="0.1.0",
            lifespan=self._lifespan,
        )

        # Health endpoint
        @app.get("/health")
        async def health():
            return {"status": "ok"}

        # Mount UI if directory exists
        ui_path = self._get_ui_path()
        if ui_path and ui_path.exists():
            # Serve index.html at /ui
            @app.get("/ui")
            @app.get("/ui/")
            async def ui_index():
                return FileResponse(ui_path / "index.html")

            # Serve static files
            app.mount("/ui", StaticFiles(directory=ui_path, html=True), name="ui")

        return app

    def _get_ui_path(self) -> Path | None:
        """Get path to UI directory.

        Override in subclass to customize UI location.
        """
        # Default: look for ui/ relative to package
        package_root = Path(__file__).parent.parent.parent.parent
        ui_path = package_root / "ui"
        if ui_path.exists():
            return ui_path
        return None

    @asynccontextmanager
    async def _lifespan(self, _app: Any):
        """Manage application lifecycle."""
        # Startup
        await self.proxy.init()
        yield
        # Shutdown
        await self.proxy.close()
