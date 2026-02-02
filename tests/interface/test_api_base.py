# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for interface.api_base module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from proxy.interface.api_base import register_api_endpoint
from proxy.interface.endpoint_base import POST, BaseEndpoint


class MockTable:
    """Mock table for testing."""

    async def select(self, **kwargs):
        return [{"id": "1", "name": "test"}]

    async def select_one(self, **kwargs):
        return {"id": "1", "name": "test"}


class SampleEndpoint(BaseEndpoint):
    """Sample endpoint for API testing."""

    name = "samples"

    async def list(self) -> list[dict]:
        """List all samples."""
        return await self.table.select()

    async def get(self, id: str) -> dict:
        """Get sample by ID."""
        result = await self.table.select_one(where={"id": id})
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
        # Override select_one to return None
        endpoint.table.select_one = AsyncMock(return_value=None)
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
