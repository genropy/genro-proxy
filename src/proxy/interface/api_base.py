# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""FastAPI application manager with automatic route generation from endpoints."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

if TYPE_CHECKING:
    from proxy.proxy_base import ProxyBase

from .endpoint_base import BaseEndpoint


def register_api_endpoint(router: APIRouter, endpoint: BaseEndpoint) -> None:
    """Register all methods of an endpoint as API routes.

    Creates routes for each public async method:
    - GET methods: /{endpoint_name}/{method_name}
    - POST methods: /{endpoint_name}/{method_name}

    Uses endpoint.invoke() for unified Pydantic validation.

    Args:
        router: FastAPI router to add routes to.
        endpoint: Endpoint instance with async methods.
    """
    import inspect

    for method_name, method in endpoint.get_methods():
        http_method = endpoint.get_http_method(method_name)
        path = f"/{endpoint.name}/{method_name.replace('_', '-')}"

        # Create route handler
        if http_method == "POST":
            _add_post_route(router, endpoint, method_name, path, method)
        else:
            _add_get_route(router, endpoint, method_name, path, method)


def _add_post_route(
    router: APIRouter,
    endpoint: BaseEndpoint,
    method_name: str,
    path: str,
    method: Any,
) -> None:
    """Add POST route that reads params from JSON body."""

    async def route_handler(request: Request) -> JSONResponse:
        try:
            body = await request.json() if await request.body() else {}
        except Exception:
            body = {}

        try:
            result = await endpoint.invoke(method_name, body)
            return JSONResponse(content={"data": result})
        except ValidationError as e:
            return JSONResponse(status_code=422, content={"error": e.errors()})
        except ValueError as e:
            return JSONResponse(status_code=404, content={"error": str(e)})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    route_handler.__doc__ = method.__doc__
    router.add_api_route(path, route_handler, methods=["POST"])


def _add_get_route(
    router: APIRouter,
    endpoint: BaseEndpoint,
    method_name: str,
    path: str,
    method: Any,
) -> None:
    """Add GET route that reads params from query string."""

    async def route_handler(request: Request) -> JSONResponse:
        params = dict(request.query_params)

        try:
            result = await endpoint.invoke(method_name, params)
            return JSONResponse(content={"data": result})
        except ValidationError as e:
            return JSONResponse(status_code=422, content={"error": e.errors()})
        except ValueError as e:
            return JSONResponse(status_code=404, content={"error": str(e)})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    route_handler.__doc__ = method.__doc__
    router.add_api_route(path, route_handler, methods=["GET"])


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

        # Register endpoint routes
        router = APIRouter(prefix="/api")
        for endpoint in self.proxy.endpoints.values():
            register_api_endpoint(router, endpoint)
        app.include_router(router)

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
