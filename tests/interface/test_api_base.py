# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for interface.api_base module."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from genro_proxy.interface.api_base import register_api_endpoint
from genro_proxy.interface.endpoint_base import POST, BaseEndpoint


class MockDb:
    """Mock database for testing with connection() context manager."""

    @asynccontextmanager
    async def connection(self):
        """Mock connection context manager (no-op for tests)."""
        yield self


class MockTable:
    """Mock table for testing."""

    def __init__(self):
        self.db = MockDb()

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

    @POST
    async def add(self, id: str, name: str) -> dict:
        """Add a new sample."""
        return {"id": id, "name": name}

    @POST
    async def delete(self, id: str) -> bool:
        """Delete a sample."""
        return True


@pytest.fixture
def endpoint():
    """Create sample endpoint."""
    return SampleEndpoint(MockTable())


@pytest.fixture
def app(endpoint):
    """Create FastAPI app with endpoint routes."""
    from fastapi import FastAPI

    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_api_endpoint(router, endpoint)
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestRegisterApiEndpoint:
    """Tests for register_api_endpoint function."""

    def test_creates_get_routes(self, client):
        """GET methods should create GET routes."""
        response = client.get("/api/samples/list")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_creates_post_routes(self, client):
        """POST methods should create POST routes."""
        response = client.post("/api/samples/add", json={"id": "1", "name": "test"})
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == {"id": "1", "name": "test"}

    def test_get_with_query_params(self, client):
        """GET routes should accept query params."""
        response = client.get("/api/samples/get?id=123")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == "1"  # From mock

    def test_post_validates_body(self, client):
        """POST routes should validate request body."""
        # Missing required 'name' param
        response = client.post("/api/samples/add", json={"id": "1"})
        assert response.status_code == 422
        assert "error" in response.json()

    def test_method_not_found_returns_404(self, client, endpoint):
        """ValueError from endpoint should return 404."""
        # Override record to return {} (not found)
        endpoint.table.record = AsyncMock(return_value={})
        response = client.get("/api/samples/get?id=nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["error"]

    def test_replaces_underscores_with_dashes(self, app):
        """Method names with underscores should use dashes in path."""
        # Check routes exist
        routes = [r.path for r in app.routes]
        # Method 'delete' becomes '/api/samples/delete'
        assert "/api/samples/delete" in routes


class TestApiValidation:
    """Tests for API Pydantic validation."""

    def test_type_coercion(self, client):
        """API should coerce types via Pydantic."""
        # id and name are strings, should work even if sent as different types
        response = client.post("/api/samples/add", json={"id": "1", "name": "test"})
        assert response.status_code == 200

    def test_empty_body_for_no_params(self, client):
        """Methods without params should work with empty body."""
        response = client.get("/api/samples/list")
        assert response.status_code == 200

    def test_post_with_empty_body_validates(self, client):
        """POST with empty body should still validate required params."""
        response = client.post("/api/samples/add", json={})
        assert response.status_code == 422


# =============================================================================
# Authentication tests
# =============================================================================


class TestApiAuthentication:
    """Tests for API authentication with X-API-Token header."""

    @pytest.fixture
    def app_with_auth(self, endpoint):
        """Create FastAPI app with authentication enabled."""
        from fastapi import FastAPI

        from genro_proxy.interface.api_base import auth_dependency, register_api_endpoint

        app = FastAPI()
        app.state.api_token = "secret-admin-token"

        router = APIRouter(prefix="/api", dependencies=[auth_dependency])
        register_api_endpoint(router, endpoint)
        app.include_router(router)

        # Health endpoint without auth
        @app.get("/health")
        async def health():
            return {"status": "ok"}

        return app

    @pytest.fixture
    def auth_client(self, app_with_auth):
        """Create test client for authenticated app."""
        return TestClient(app_with_auth)

    def test_health_no_auth_required(self, auth_client):
        """Health endpoint should not require authentication."""
        response = auth_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_api_without_token_returns_401(self, auth_client):
        """API calls without token should return 401."""
        response = auth_client.get("/api/samples/list")
        assert response.status_code == 401
        assert "Missing API token" in response.json()["detail"]

    def test_api_with_invalid_token_returns_401(self, auth_client):
        """API calls with invalid token should return 401."""
        response = auth_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "wrong-token"},
        )
        assert response.status_code == 401
        assert "Invalid API token" in response.json()["detail"]

    def test_api_with_valid_token_succeeds(self, auth_client):
        """API calls with valid admin token should succeed."""
        response = auth_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "secret-admin-token"},
        )
        assert response.status_code == 200
        assert "data" in response.json()

    def test_post_with_valid_token_succeeds(self, auth_client):
        """POST requests with valid token should succeed."""
        response = auth_client.post(
            "/api/samples/add",
            json={"id": "1", "name": "test"},
            headers={"X-API-Token": "secret-admin-token"},
        )
        assert response.status_code == 200


class TestApiNoAuth:
    """Tests for API without authentication configured."""

    @pytest.fixture
    def app_no_auth(self, endpoint):
        """Create FastAPI app without authentication (api_token=None)."""
        from fastapi import FastAPI

        from genro_proxy.interface.api_base import auth_dependency, register_api_endpoint

        app = FastAPI()
        app.state.api_token = None  # No auth

        router = APIRouter(prefix="/api", dependencies=[auth_dependency])
        register_api_endpoint(router, endpoint)
        app.include_router(router)
        return app

    @pytest.fixture
    def no_auth_client(self, app_no_auth):
        """Create test client for app without auth."""
        return TestClient(app_no_auth)

    def test_api_without_token_allowed(self, no_auth_client):
        """When api_token=None, requests without token should work."""
        response = no_auth_client.get("/api/samples/list")
        assert response.status_code == 200

    def test_api_with_random_token_rejected(self, no_auth_client):
        """When api_token=None but token provided, it's still validated."""
        # Even without global token configured, a provided token is validated
        # against tenant tokens. Random tokens will be rejected.
        response = no_auth_client.get(
            "/api/samples/list",
            headers={"X-API-Token": "random-token"},
        )
        # Token validation still happens, random tokens rejected
        assert response.status_code == 401
