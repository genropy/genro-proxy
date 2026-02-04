# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for interface.endpoint_base module."""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from typing import Any

import pytest

from genro_proxy.interface.endpoint_base import POST, BaseEndpoint


class MockDb:
    """Mock database for testing with connection() context manager."""

    @asynccontextmanager
    async def connection(self):
        """Mock connection context manager (no-op for tests)."""
        yield self


class RecordNotFoundError(Exception):
    """Mock exception for record not found."""

    pass


class MockTable:
    """Mock table for testing."""

    def __init__(self):
        self.db = MockDb()
        self.pkey = "id"
        self._records = {"1": {"id": "1", "name": "test"}}
        self._inserted = []
        self._deleted = []

    async def list_all(self, **kwargs):
        return [{"id": "1"}]

    async def get(self, pk: str):
        return {"id": pk, "name": "test"}

    async def select(self):
        return list(self._records.values())

    async def record(self, pkey=None, **kwargs):
        if pkey and pkey in self._records:
            return self._records[pkey]
        raise RecordNotFoundError(f"Record '{pkey}' not found")

    async def insert(self, record):
        self._inserted.append(record)
        self._records[record["id"]] = record

    async def delete(self, where=None):
        if where and "id" in where:
            self._deleted.append(where["id"])


class TestPOSTDecorator:
    """Tests for POST decorator."""

    def test_marks_method_as_post(self):
        """POST decorator should set _http_post attribute."""

        @POST
        async def my_method():
            pass

        assert hasattr(my_method, "_http_post")
        assert my_method._http_post is True

    def test_preserves_function(self):
        """POST decorator should not change function behavior."""

        @POST
        async def my_method(x: int) -> int:
            return x * 2

        assert my_method.__name__ == "my_method"
        assert inspect.iscoroutinefunction(my_method)


class SampleEndpoint(BaseEndpoint):
    """Sample endpoint for testing."""

    name = "samples"

    async def list(self, active_only: bool = False) -> list[dict]:
        """List all samples."""
        return await self.table.list_all(active_only=active_only)

    async def get(self, sample_id: str) -> dict:
        """Get a sample by ID."""
        return await self.table.get(sample_id)

    @POST
    async def add(self, id: str, name: str, data: dict | None = None) -> dict:
        """Add a new sample."""
        return {"id": id, "name": name}

    async def complex_params(
        self, items: list[str], config: dict[str, Any] | None = None
    ) -> dict:
        """Method with complex parameters."""
        return {"items": items}

    def _private_method(self):
        """Private method should not be discovered."""
        pass

    def sync_method(self):
        """Sync method should not be discovered."""
        pass


class TestBaseEndpoint:
    """Tests for BaseEndpoint class."""

    @pytest.fixture
    def endpoint(self):
        """Create a sample endpoint."""
        table = MockTable()
        return SampleEndpoint(table)

    def test_init_stores_table(self, endpoint):
        """Should store table reference."""
        assert endpoint.table is not None

    def test_name_attribute(self, endpoint):
        """Should have name attribute."""
        assert endpoint.name == "samples"

    def test_get_methods_returns_async_public_methods(self, endpoint):
        """get_methods should return only public async methods."""
        methods = endpoint.get_methods()
        method_names = [name for name, _ in methods]

        assert "list" in method_names
        assert "get" in method_names
        assert "add" in method_names
        assert "complex_params" in method_names

        # Private and sync methods should not be included
        assert "_private_method" not in method_names
        assert "sync_method" not in method_names

    def test_get_http_method_returns_get_by_default(self, endpoint):
        """Methods without @POST should return GET."""
        assert endpoint.get_http_method("list") == "GET"
        assert endpoint.get_http_method("get") == "GET"

    def test_get_http_method_returns_post_for_decorated(self, endpoint):
        """Methods with @POST should return POST."""
        assert endpoint.get_http_method("add") == "POST"

    def test_create_request_model_creates_pydantic_model(self, endpoint):
        """create_request_model should create a valid Pydantic model."""
        model = endpoint.create_request_model("add")

        assert model.__name__ == "AddRequest"
        # Check that model has expected fields
        fields = model.model_fields
        assert "id" in fields
        assert "name" in fields
        assert "data" in fields

    def test_create_request_model_required_vs_optional(self, endpoint):
        """Required params should have no default, optional should have default."""
        model = endpoint.create_request_model("add")
        fields = model.model_fields

        # id and name are required (no default)
        assert fields["id"].is_required()
        assert fields["name"].is_required()

        # data has default (Optional[dict])
        assert not fields["data"].is_required()

    def test_is_simple_params_true_for_primitives(self, endpoint):
        """Methods with only primitive params should be simple."""
        assert endpoint.is_simple_params("list") is True
        assert endpoint.is_simple_params("get") is True

    def test_is_simple_params_false_for_complex_types(self, endpoint):
        """Methods with list/dict params should not be simple."""
        assert endpoint.is_simple_params("add") is False  # has dict param
        assert endpoint.is_simple_params("complex_params") is False

    def test_count_params(self, endpoint):
        """count_params should return correct count excluding self."""
        assert endpoint.count_params("list") == 1  # active_only
        assert endpoint.count_params("get") == 1  # sample_id
        assert endpoint.count_params("add") == 3  # id, name, data


class TestComplexTypeDetection:
    """Tests for _is_complex_type method."""

    @pytest.fixture
    def endpoint(self):
        """Create endpoint for testing."""
        return SampleEndpoint(MockTable())

    def test_list_is_complex(self, endpoint):
        """list type should be detected as complex."""
        assert endpoint._is_complex_type(list) is True
        assert endpoint._is_complex_type(list[str]) is True

    def test_dict_is_complex(self, endpoint):
        """dict type should be detected as complex."""
        assert endpoint._is_complex_type(dict) is True
        assert endpoint._is_complex_type(dict[str, Any]) is True

    def test_primitives_are_simple(self, endpoint):
        """Primitive types should not be complex."""
        assert endpoint._is_complex_type(str) is False
        assert endpoint._is_complex_type(int) is False
        assert endpoint._is_complex_type(bool) is False

    def test_optional_list_is_complex(self, endpoint):
        """Optional[list] should be detected as complex."""
        from typing import Optional

        assert endpoint._is_complex_type(Optional[list[str]]) is True
        assert endpoint._is_complex_type(list[str] | None) is True

    def test_optional_primitive_is_simple(self, endpoint):
        """Optional[str] should not be complex."""
        from typing import Optional

        assert endpoint._is_complex_type(Optional[str]) is False
        assert endpoint._is_complex_type(str | None) is False


class TestCreateRequestModelEdgeCases:
    """Tests for create_request_model edge cases."""

    def test_create_request_model_without_type_hints(self):
        """create_request_model should handle methods without type hints."""

        class NoHintsEndpoint(BaseEndpoint):
            name = "nohints"

            async def simple_method(self, param1, param2=None):
                return {"ok": True}

        endpoint = NoHintsEndpoint(MockTable())
        model = endpoint.create_request_model("simple_method")

        # Should create model even without type hints
        assert model is not None
        assert "param1" in model.model_fields
        assert "param2" in model.model_fields


class TestIsSimpleParamsEdgeCases:
    """Tests for is_simple_params edge cases."""

    def test_is_simple_params_without_type_hints(self):
        """is_simple_params should handle methods without type hints."""

        class NoHintsEndpoint(BaseEndpoint):
            name = "nohints"

            async def method_no_hints(self, param1, param2):
                return {"ok": True}

        endpoint = NoHintsEndpoint(MockTable())
        # Methods without hints are considered simple
        assert endpoint.is_simple_params("method_no_hints") is True


class MockProxy:
    """Mock proxy for EndpointManager testing."""

    def __init__(self):
        self.db = MockDb()


class TestEndpointDiscoveryFilters:
    """Tests for endpoint discovery filtering logic in EndpointManager."""

    @pytest.fixture
    def manager(self):
        """Create EndpointManager with mock proxy."""
        from genro_proxy.interface.endpoint_base import EndpointManager

        return EndpointManager(MockProxy())

    def test_get_class_from_module_filters_base_classes(self, manager):
        """_get_class_from_module should filter out BaseEndpoint."""
        mock_module = type('MockModule', (), {})()
        mock_module.BaseEndpoint = BaseEndpoint

        result = manager._get_class_from_module(mock_module, "Endpoint")
        assert result is None

    def test_get_class_from_module_filters_private_classes(self, manager):
        """_get_class_from_module should filter out private classes."""
        mock_module = type('MockModule', (), {})()

        class _PrivateEndpoint(BaseEndpoint):
            name = "private"

        mock_module._PrivateEndpoint = _PrivateEndpoint

        result = manager._get_class_from_module(mock_module, "Endpoint")
        assert result is None

    def test_get_class_from_module_filters_ee_classes(self, manager):
        """_get_class_from_module should filter out _EE classes."""
        mock_module = type('MockModule', (), {})()

        class TestEndpoint_EE:
            name = "test"

        mock_module.TestEndpoint_EE = TestEndpoint_EE

        result = manager._get_class_from_module(mock_module, "Endpoint")
        assert result is None

    def test_get_class_from_module_filters_classes_without_name(self, manager):
        """_get_class_from_module should filter out classes without name attr."""
        mock_module = type('MockModule', (), {})()

        class NoNameEndpoint:
            pass  # No name attribute

        mock_module.NoNameEndpoint = NoNameEndpoint

        result = manager._get_class_from_module(mock_module, "Endpoint")
        assert result is None

    def test_get_ee_mixin_from_module_returns_mixin(self, manager):
        """_get_ee_mixin_from_module should find _EE mixin."""
        mock_module = type('MockModule', (), {})()

        class MyEndpoint_EE:
            pass

        mock_module.MyEndpoint_EE = MyEndpoint_EE

        result = manager._get_ee_mixin_from_module(mock_module, "_EE")
        assert result is MyEndpoint_EE

    def test_get_ee_mixin_from_module_filters_private(self, manager):
        """_get_ee_mixin_from_module should filter private classes."""
        mock_module = type('MockModule', (), {})()

        class _PrivateEndpoint_EE:
            pass

        mock_module._PrivateEndpoint_EE = _PrivateEndpoint_EE

        result = manager._get_ee_mixin_from_module(mock_module, "_EE")
        assert result is None

    def test_get_ee_mixin_from_module_returns_none_when_not_found(self, manager):
        """_get_ee_mixin_from_module should return None if no mixin."""
        mock_module = type('MockModule', (), {})()

        class SomeClass:
            pass

        mock_module.SomeClass = SomeClass

        result = manager._get_ee_mixin_from_module(mock_module, "_EE")
        assert result is None


class TestBaseEndpointCRUD:
    """Tests for BaseEndpoint CRUD methods."""

    @pytest.fixture
    def endpoint(self):
        """Create base endpoint for testing."""

        class CrudEndpoint(BaseEndpoint):
            name = "items"

        return CrudEndpoint(MockTable())

    async def test_list_returns_all_records(self, endpoint, monkeypatch):
        """list() should return all records from table."""
        # Patch the import inside the method
        import genro_proxy.sql

        monkeypatch.setattr(genro_proxy.sql, "RecordNotFoundError", RecordNotFoundError)
        result = await endpoint.list()
        assert result == [{"id": "1", "name": "test"}]

    async def test_get_returns_record(self, endpoint, monkeypatch):
        """get() should return record by id."""
        import genro_proxy.sql

        monkeypatch.setattr(genro_proxy.sql, "RecordNotFoundError", RecordNotFoundError)
        result = await endpoint.get("1")
        assert result == {"id": "1", "name": "test"}

    async def test_get_raises_valueerror_when_not_found(self, endpoint, monkeypatch):
        """get() should raise ValueError when record not found."""
        import genro_proxy.sql

        monkeypatch.setattr(genro_proxy.sql, "RecordNotFoundError", RecordNotFoundError)
        with pytest.raises(ValueError, match="items '999' not found"):
            await endpoint.get("999")

    async def test_add_inserts_record(self, endpoint, monkeypatch):
        """add() should insert record via table."""
        import genro_proxy.sql

        monkeypatch.setattr(genro_proxy.sql, "RecordNotFoundError", RecordNotFoundError)
        result = await endpoint.add("new_id", name="new_name")
        assert result == {"id": "new_id", "name": "new_name"}
        assert endpoint.table._inserted[-1] == {"id": "new_id", "name": "new_name"}

    async def test_delete_removes_record(self, endpoint, monkeypatch):
        """delete() should delete record via table."""
        import genro_proxy.sql

        monkeypatch.setattr(genro_proxy.sql, "RecordNotFoundError", RecordNotFoundError)
        result = await endpoint.delete("1")
        assert result is True
        assert "1" in endpoint.table._deleted


class TestEndpointInvoke:
    """Tests for endpoint.invoke() unified validation."""

    @pytest.fixture
    def endpoint(self):
        """Create endpoint for testing."""
        return SampleEndpoint(MockTable())

    async def test_invoke_validates_and_executes(self, endpoint):
        """invoke() should validate params and execute method."""
        result = await endpoint.invoke("get", {"sample_id": "123"})
        assert result == {"id": "123", "name": "test"}

    async def test_invoke_coerces_types(self, endpoint):
        """invoke() should coerce string to correct type via Pydantic."""
        # active_only is bool, but we pass string - Pydantic coerces it
        result = await endpoint.invoke("list", {"active_only": "false"})
        assert isinstance(result, list)

    async def test_invoke_with_optional_params(self, endpoint):
        """invoke() should handle optional params."""
        result = await endpoint.invoke("add", {"id": "1", "name": "test"})
        assert result == {"id": "1", "name": "test"}

    async def test_invoke_with_all_params(self, endpoint):
        """invoke() should pass all params including optional."""
        result = await endpoint.invoke("add", {"id": "1", "name": "test", "data": {"key": "val"}})
        assert result == {"id": "1", "name": "test"}

    async def test_invoke_raises_on_missing_required(self, endpoint):
        """invoke() should raise ValidationError on missing required params."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            await endpoint.invoke("add", {"id": "1"})  # missing 'name'

    async def test_invoke_raises_on_unknown_method(self, endpoint):
        """invoke() should raise ValueError for unknown method."""
        with pytest.raises(ValueError, match="not found"):
            await endpoint.invoke("nonexistent", {})

    async def test_invoke_raises_on_invalid_type(self, endpoint):
        """invoke() should raise ValidationError on wrong type."""
        from pydantic import ValidationError

        # list expected but dict provided
        with pytest.raises(ValidationError):
            await endpoint.invoke("complex_params", {"items": {"not": "a list"}})
