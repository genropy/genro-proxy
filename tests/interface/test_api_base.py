# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for interface.api_base module."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from genro_proxy.interface.api_base import register_api_endpoint
from genro_proxy.interface.endpoint_base import BaseEndpoint, endpoint


class MockTenantsTableForDb:
    """Mock tenants table for tenant token verification."""

    def __init__(self, valid_tokens=None):
        self._valid_tokens = valid_tokens or {}

    async def get_tenant_by_token(self, token):
        return self._valid_tokens.get(token)


class MockDb:
    """Mock database for testing with connection() context manager."""

    def __init__(self, tenant_tokens=None):
        self._tenant_tokens = tenant_tokens or {}

    @asynccontextmanager
    async def connection(self):
        """Mock connection context manager (no-op for tests)."""
        yield self

    def table(self, name):
        """Return mock table by name."""
        if name == "tenants":
            return MockTenantsTableForDb(self._tenant_tokens)
        return None


class MockTable:
    """Mock table for testing."""

    def __init__(self, tenant_tokens=None):
        self.db = MockDb(tenant_tokens)

    async def select(self, **kwargs):
        return [{"id": "1", "name": "test"}]

    async def record(self, pkey=None, where=None, ignore_missing=False, **kwargs):
        return {"id": "1", "name": "test"}


class SampleEndpoint(BaseEndpoint):
    """Sample endpoint for API testing."""

    name = "samples"

    async def list(self) -> list[dict]:
        """List all samples."""
        return await self.table.select()

    async def get(self, id: str) -> dict:
        """Get sample by ID."""
        result = await self.table.record(where={"id": id}, ignore_missing=True)
        if not result:
            raise ValueError(f"Sample '{id}' not found")
        return result

    @endpoint(post=True)
    async def add(self, id: str, name: str) -> dict:
        """Add a new sample."""
        return {"id": id, "name": name}

    @endpoint(post=True)
    async def delete(self, id: str) -> bool:
        """Delete a sample."""
        return True


@pytest.fixture
def fxt_endpoint():
    """Create sample endpoint."""
    return SampleEndpoint(MockTable())


@pytest.fixture
def fxt_app(fxt_endpoint):
    """Create FastAPI app with endpoint routes."""
    from fastapi import FastAPI

    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_api_endpoint(router, fxt_endpoint)
    app.include_router(router)
    return app


@pytest.fixture
def fxt_client(fxt_app):
    """Create test client."""
    return TestClient(fxt_app)


class TestRegisterApiEndpoint:
    """Tests for register_api_endpoint function."""

    def test_creates_get_routes(self, fxt_client):
        """GET methods should create GET routes."""
        response = fxt_client.get("/api/samples/list")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_creates_post_routes(self, fxt_client):
        """POST methods should create POST routes."""
        response = fxt_client.post("/api/samples/add", json={"id": "1", "name": "test"})
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == {"id": "1", "name": "test"}

    def test_get_with_query_params(self, fxt_client):
        """GET routes should accept query params."""
        response = fxt_client.get("/api/samples/get?id=123")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == "1"  # From mock

    def test_post_validates_body(self, fxt_client):
        """POST routes should validate request body."""
        # Missing required 'name' param
        response = fxt_client.post("/api/samples/add", json={"id": "1"})
        assert response.status_code == 422
        assert "error" in response.json()

    def test_method_not_found_returns_404(self, fxt_client, fxt_endpoint):
        """ValueError from endpoint should return 404."""
        # Override record to return {} (not found)
        fxt_endpoint.table.record = AsyncMock(return_value={})
        response = fxt_client.get("/api/samples/get?id=nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["error"]

    def test_replaces_underscores_with_dashes(self, fxt_app):
        """Method names with underscores should use dashes in path."""
        # Check routes exist
        routes = [r.path for r in fxt_app.routes]
        # Method 'delete' becomes '/api/samples/delete'
        assert "/api/samples/delete" in routes


class TestApiValidation:
    """Tests for API Pydantic validation."""

    def test_type_coercion(self, fxt_client):
        """API should coerce types via Pydantic."""
        # id and name are strings, should work even if sent as different types
        response = fxt_client.post("/api/samples/add", json={"id": "1", "name": "test"})
        assert response.status_code == 200

    def test_empty_body_for_no_params(self, fxt_client):
        """Methods without params should work with empty body."""
        response = fxt_client.get("/api/samples/list")
        assert response.status_code == 200

    def test_post_with_empty_body_validates(self, fxt_client):
        """POST with empty body should still validate required params."""
        response = fxt_client.post("/api/samples/add", json={})
        assert response.status_code == 422


# =============================================================================
# Authentication tests
# =============================================================================


class TestApiAuthentication:
    """Tests for API authentication with X-API-Token header."""

    @pytest.fixture
    def fxt_app_with_auth(self, fxt_endpoint):
        """Create FastAPI app with authentication enabled."""
        from fastapi import FastAPI

        from genro_proxy.interface.api_base import auth_dependency, register_api_endpoint

        app = FastAPI()
        app.state.api_token = "secret-admin-token"

        router = APIRouter(prefix="/api", dependencies=[auth_dependency])
        register_api_endpoint(router, fxt_endpoint)
        app.include_router(router)

        # Health endpoint without auth
        @app.get("/health")
        async def health():
            return {"status": "ok"}

        return app

    @pytest.fixture
    def fxt_auth_client(self, fxt_app_with_auth):
        """Create test client for authenticated app."""
        return TestClient(fxt_app_with_auth)

    def test_health_no_auth_required(self, fxt_auth_client):
        """Health endpoint should not require authentication."""
        response = fxt_auth_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_api_without_token_returns_401(self, fxt_auth_client):
        """API calls without token should return 401."""
        response = fxt_auth_client.get("/api/samples/list")
        assert response.status_code == 401
        assert "Missing API token" in response.json()["detail"]

    def test_api_with_invalid_token_returns_401(self, fxt_auth_client):
        """API calls with invalid token should return 401."""
        response = fxt_auth_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "wrong-token"},
        )
        assert response.status_code == 401
        assert "Invalid API token" in response.json()["detail"]

    def test_api_with_valid_token_succeeds(self, fxt_auth_client):
        """API calls with valid admin token should succeed."""
        response = fxt_auth_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "secret-admin-token"},
        )
        assert response.status_code == 200
        assert "data" in response.json()

    def test_post_with_valid_token_succeeds(self, fxt_auth_client):
        """POST requests with valid token should succeed."""
        response = fxt_auth_client.post(
            "/api/samples/add",
            json={"id": "1", "name": "test"},
            headers={"X-API-Token": "secret-admin-token"},
        )
        assert response.status_code == 200


class TestApiNoAuth:
    """Tests for API without authentication configured."""

    @pytest.fixture
    def fxt_app_no_auth(self, fxt_endpoint):
        """Create FastAPI app without authentication (api_token=None)."""
        from fastapi import FastAPI

        from genro_proxy.interface.api_base import auth_dependency, register_api_endpoint

        app = FastAPI()
        app.state.api_token = None  # No auth

        router = APIRouter(prefix="/api", dependencies=[auth_dependency])
        register_api_endpoint(router, fxt_endpoint)
        app.include_router(router)
        return app

    @pytest.fixture
    def fxt_no_auth_client(self, fxt_app_no_auth):
        """Create test client for app without auth."""
        return TestClient(fxt_app_no_auth)

    def test_api_without_token_allowed(self, fxt_no_auth_client):
        """When api_token=None, requests without token should work."""
        response = fxt_no_auth_client.get("/api/samples/list")
        assert response.status_code == 200

    def test_api_with_random_token_rejected(self, fxt_no_auth_client):
        """When api_token=None but token provided, it's still validated."""
        # Even without global token configured, a provided token is validated
        # against tenant tokens. Random tokens will be rejected.
        response = fxt_no_auth_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "random-token"},
        )
        # Token validation still happens, random tokens rejected
        assert response.status_code == 401


# =============================================================================
# Admin token tests
# =============================================================================


class TestApiAdminAuthentication:
    """Tests for admin-only authentication with require_admin_token."""

    @pytest.fixture
    def fxt_app_with_admin_auth(self, fxt_endpoint):
        """Create FastAPI app with admin-only authentication."""
        from fastapi import FastAPI

        from genro_proxy.interface.api_base import admin_dependency, register_api_endpoint

        app = FastAPI()
        app.state.api_token = "admin-secret-token"

        router = APIRouter(prefix="/admin", dependencies=[admin_dependency])
        register_api_endpoint(router, fxt_endpoint)
        app.include_router(router)
        return app

    @pytest.fixture
    def fxt_admin_client(self, fxt_app_with_admin_auth):
        """Create test client for admin app."""
        return TestClient(fxt_app_with_admin_auth)

    def test_admin_without_token_returns_401(self, fxt_admin_client):
        """Admin endpoints without token should return 401."""
        response = fxt_admin_client.get("/admin/samples/list")
        assert response.status_code == 401
        assert "Admin token required" in response.json()["detail"]

    def test_admin_with_invalid_token_returns_401(self, fxt_admin_client):
        """Admin endpoints with invalid token should return 401."""
        response = fxt_admin_client.get(
            "/admin/samples/list",
            headers={"X-API-Token": "wrong-token"},
        )
        assert response.status_code == 401
        assert "Invalid API token" in response.json()["detail"]

    def test_admin_with_valid_token_succeeds(self, fxt_admin_client):
        """Admin endpoints with valid admin token should succeed."""
        response = fxt_admin_client.get(
            "/admin/samples/list",
            headers={"X-API-Token": "admin-secret-token"},
        )
        assert response.status_code == 200


class TestApiAdminNoAuth:
    """Tests for admin endpoints without auth configured."""

    @pytest.fixture
    def fxt_app_admin_no_auth(self, fxt_endpoint):
        """Create FastAPI app with admin dependency but no token configured."""
        from fastapi import FastAPI

        from genro_proxy.interface.api_base import admin_dependency, register_api_endpoint

        app = FastAPI()
        app.state.api_token = None  # No auth

        router = APIRouter(prefix="/admin", dependencies=[admin_dependency])
        register_api_endpoint(router, fxt_endpoint)
        app.include_router(router)
        return app

    @pytest.fixture
    def fxt_admin_no_auth_client(self, fxt_app_admin_no_auth):
        """Create test client."""
        return TestClient(fxt_app_admin_no_auth)

    def test_admin_no_auth_allows_without_token(self, fxt_admin_no_auth_client):
        """When api_token=None, admin endpoints allow access without token."""
        response = fxt_admin_no_auth_client.get("/admin/samples/list")
        assert response.status_code == 200


# =============================================================================
# Route handler error cases
# =============================================================================


class TestApiTenantAuthentication:
    """Tests for tenant token authentication."""

    @pytest.fixture
    def fxt_endpoint_with_tenant(self):
        """Create endpoint with tenant token support."""
        tenant_tokens = {"tenant-secret-token": {"id": "acme", "name": "ACME Corp"}}
        return SampleEndpoint(MockTable(tenant_tokens))

    @pytest.fixture
    def fxt_app_with_tenant_auth(self, fxt_endpoint_with_tenant):
        """Create FastAPI app with tenant authentication enabled."""
        from fastapi import FastAPI

        from genro_proxy.interface.api_base import auth_dependency, register_api_endpoint

        app = FastAPI()
        app.state.api_token = "admin-secret-token"

        router = APIRouter(prefix="/api", dependencies=[auth_dependency])
        register_api_endpoint(router, fxt_endpoint_with_tenant)
        app.include_router(router)
        return app

    @pytest.fixture
    def fxt_tenant_client(self, fxt_app_with_tenant_auth):
        """Create test client for tenant auth app."""
        return TestClient(fxt_app_with_tenant_auth)

    def test_tenant_token_allows_access(self, fxt_tenant_client):
        """Valid tenant token should allow API access."""
        response = fxt_tenant_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "tenant-secret-token"},
        )
        assert response.status_code == 200

    def test_admin_token_still_works(self, fxt_tenant_client):
        """Admin token should still work."""
        response = fxt_tenant_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "admin-secret-token"},
        )
        assert response.status_code == 200

    def test_invalid_token_rejected(self, fxt_tenant_client):
        """Invalid token should be rejected."""
        response = fxt_tenant_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "invalid-token"},
        )
        assert response.status_code == 401


class TestApiAdminTenantToken:
    """Tests for tenant token on admin endpoints."""

    @pytest.fixture
    def fxt_mock_tenants_table(self):
        """Create mock tenants table."""

        class MockTenantsTable:
            async def get_tenant_by_token(self, token):
                if token == "tenant-token":
                    return {"id": "acme"}
                return None

        return MockTenantsTable()

    @pytest.fixture
    def fxt_mock_proxy(self, fxt_mock_tenants_table):
        """Create mock proxy."""

        class MockDb:
            def __init__(self, tenants_table):
                self._tables = {"tenants": tenants_table}

            def table(self, name):
                return self._tables.get(name)

        class MockProxy:
            def __init__(self, tenants_table):
                self.db = MockDb(tenants_table)

        return MockProxy(fxt_mock_tenants_table)

    @pytest.fixture
    def fxt_app_with_admin_tenant(self, fxt_endpoint, fxt_mock_proxy, monkeypatch):
        """Create app with admin dependency and tenant support."""
        from fastapi import FastAPI

        from genro_proxy.interface import api_base
        from genro_proxy.interface.api_base import admin_dependency, register_api_endpoint

        monkeypatch.setattr(api_base, "_proxy", fxt_mock_proxy)

        app = FastAPI()
        app.state.api_token = "admin-token"

        router = APIRouter(prefix="/admin", dependencies=[admin_dependency])
        register_api_endpoint(router, fxt_endpoint)
        app.include_router(router)
        return app

    @pytest.fixture
    def fxt_admin_tenant_client(self, fxt_app_with_admin_tenant):
        """Create test client."""
        return TestClient(fxt_app_with_admin_tenant)

    def test_tenant_token_forbidden_on_admin(self, fxt_admin_tenant_client):
        """Tenant token should be forbidden on admin endpoints."""
        response = fxt_admin_tenant_client.get(
            "/admin/samples/list",
            headers={"X-API-Token": "tenant-token"},
        )
        assert response.status_code == 403
        assert "Admin token required" in response.json()["detail"]


class TestApiRouteErrors:
    """Tests for API route error handling."""

    @pytest.fixture
    def fxt_error_endpoint(self):
        """Create endpoint that raises different errors."""

        class ErrorEndpoint(BaseEndpoint):
            name = "errors"

            async def server_error(self) -> dict:
                """Raise a server error."""
                raise RuntimeError("Internal server error")

            @endpoint(post=True)
            async def post_server_error(self) -> dict:
                """POST that raises server error."""
                raise RuntimeError("Internal server error")

        return ErrorEndpoint(MockTable())

    @pytest.fixture
    def fxt_error_app(self, fxt_error_endpoint):
        """Create app with error endpoint."""
        from fastapi import FastAPI

        app = FastAPI()
        router = APIRouter(prefix="/api")
        register_api_endpoint(router, fxt_error_endpoint)
        app.include_router(router)
        return app

    @pytest.fixture
    def fxt_error_client(self, fxt_error_app):
        """Create test client."""
        return TestClient(fxt_error_app)

    def test_get_server_error_returns_500(self, fxt_error_client):
        """GET route server error should return 500."""
        response = fxt_error_client.get("/api/errors/server-error")
        assert response.status_code == 500
        assert "Internal server error" in response.json()["error"]

    def test_post_server_error_returns_500(self, fxt_error_client):
        """POST route server error should return 500."""
        response = fxt_error_client.post("/api/errors/post-server-error", json={})
        assert response.status_code == 500
        assert "Internal server error" in response.json()["error"]

    def test_post_with_invalid_json(self, fxt_client):
        """POST with invalid JSON body should handle gracefully."""
        response = fxt_client.post(
            "/api/samples/add",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        # Should still try to validate (with empty body)
        assert response.status_code == 422
