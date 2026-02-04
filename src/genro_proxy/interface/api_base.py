# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""FastAPI application manager with automatic route generation from endpoints.

Provides API authentication via X-API-Token header with two access levels:
- Global admin token: full access to all resources
- Tenant token: access restricted to own tenant resources

Components:
    ApiManager: FastAPI application factory and lifecycle manager.
    register_api_endpoint: Register endpoint methods as API routes.
    require_token: Authentication dependency for general access.
    require_admin_token: Authentication dependency for admin-only endpoints.
"""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from genro_tytx import to_tytx
from pydantic import ValidationError

if TYPE_CHECKING:
    from genro_proxy.proxy_base import ProxyBase

from .endpoint_base import BaseEndpoint, InvalidTokenError

# =============================================================================
# Authentication
# =============================================================================

API_TOKEN_HEADER = "X-API-Token"
api_key_scheme = APIKeyHeader(name=API_TOKEN_HEADER, auto_error=False)

# Global proxy reference (set by ApiManager)
_proxy: "ProxyBase | None" = None


async def require_token(
    request: Request,
    api_token: str | None = Depends(api_key_scheme),
) -> None:
    """Validate API token from X-API-Token header.

    Checks admin token immediately (string comparison, no DB).
    For non-admin tokens, stores raw token for later DB verification
    inside the route handler where a DB connection is available.

    Args:
        request: FastAPI request object.
        api_token: Token from X-API-Token header (via Depends).

    Raises:
        HTTPException: 401 if token is missing (when auth configured).
    """
    request.state.api_token = api_token
    request.state.is_admin = False
    request.state.token_tenant_id = None  # Will be resolved in route handler

    expected = getattr(request.app.state, "api_token", None)

    # No token provided
    if not api_token:
        if expected is not None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing API token")
        return  # No auth configured = open access

    # Check global admin token (no DB needed)
    if expected is not None and secrets.compare_digest(api_token, expected):
        request.state.is_admin = True
        return

    # Non-admin token: will be verified as tenant token in route handler
    # (requires DB connection which isn't available here)


async def require_admin_token(
    request: Request,
    api_token: str | None = Depends(api_key_scheme),
) -> None:
    """Require global admin token for admin-only endpoints.

    Admin-only endpoints include tenant management, instance configuration,
    and other privileged operations.

    Args:
        request: FastAPI request object.
        api_token: Token from X-API-Token header (via Depends).

    Raises:
        HTTPException: 401 if missing, 403 if tenant token used.
    """
    expected = getattr(request.app.state, "api_token", None)

    if not api_token:
        if expected is not None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin token required")
        return  # No auth configured = open access

    if expected is not None and secrets.compare_digest(api_token, expected):
        return

    # Check if it's a valid tenant token (forbidden for admin endpoints)
    if _proxy:
        tenants_table = _proxy.db.table("tenants")
        tenant = await tenants_table.get_tenant_by_token(api_token)
        if tenant:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Admin token required, tenant tokens not allowed",
            )

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API token")


# Dependency shortcuts
auth_dependency = Depends(require_token)
admin_dependency = Depends(require_admin_token)


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

    async def route_handler(request: Request) -> Response:
        try:
            body = await request.json() if await request.body() else {}
        except Exception:
            body = {}

        try:
            # Use invoke - handles connection, tenant resolution, validation
            result = await endpoint.invoke(
                method_name,
                body,
                api_token=getattr(request.state, "api_token", None),
                is_admin=getattr(request.state, "is_admin", False),
            )
            return Response(
                content=to_tytx({"data": result}),
                media_type="application/json",
            )
        except HTTPException:
            raise
        except InvalidTokenError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
        except ValidationError as e:
            return Response(
                content=to_tytx({"error": e.errors()}),
                status_code=422,
                media_type="application/json",
            )
        except ValueError as e:
            return Response(
                content=to_tytx({"error": str(e)}),
                status_code=404,
                media_type="application/json",
            )
        except Exception as e:
            return Response(
                content=to_tytx({"error": str(e)}),
                status_code=500,
                media_type="application/json",
            )

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

    async def route_handler(request: Request) -> Response:
        params = dict(request.query_params)

        try:
            # Use invoke - handles connection, tenant resolution, validation
            result = await endpoint.invoke(
                method_name,
                params,
                api_token=getattr(request.state, "api_token", None),
                is_admin=getattr(request.state, "is_admin", False),
            )
            return Response(
                content=to_tytx({"data": result}),
                media_type="application/json",
            )
        except HTTPException:
            raise
        except InvalidTokenError as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
        except ValidationError as e:
            return Response(
                content=to_tytx({"error": e.errors()}),
                status_code=422,
                media_type="application/json",
            )
        except ValueError as e:
            return Response(
                content=to_tytx({"error": str(e)}),
                status_code=404,
                media_type="application/json",
            )
        except Exception as e:
            return Response(
                content=to_tytx({"error": str(e)}),
                status_code=500,
                media_type="application/json",
            )

    route_handler.__doc__ = method.__doc__
    router.add_api_route(path, route_handler, methods=["GET"])


class ApiManager:
    """Manager for FastAPI application. Creates app lazily on first access.

    Authentication is controlled by proxy.config.api_token:
    - If set: X-API-Token header required for all /api/* routes
    - If None: open access (development mode)

    Attributes:
        proxy: Parent ProxyBase instance.
    """

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
        """Create and configure FastAPI application with authentication."""
        global _proxy
        _proxy = self.proxy

        app = FastAPI(
            title=f"{self.proxy.config.instance_name} API",
            version="0.1.0",
            lifespan=self._lifespan,
        )

        # Store API token in app state for authentication
        app.state.api_token = self.proxy.config.api_token

        # Health endpoint (no auth required)
        @app.get("/health")
        async def health():
            return {"status": "ok"}

        # Register endpoint routes with authentication
        router = APIRouter(prefix="/api", dependencies=[auth_dependency])
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
        await self.proxy.shutdown()
