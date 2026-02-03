# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Base class for endpoint introspection and command dispatch.

This module provides the foundation for automatic API/CLI generation
from endpoint classes via method introspection.

Components:
    POST: Decorator to mark methods as HTTP POST.
    BaseEndpoint: Base class with introspection capabilities.
    EndpointManager: Discovery and instantiation of endpoints.

Example:
    Define an endpoint::

        from proxy.interface.endpoint_base import BaseEndpoint, POST

        class MyEndpoint(BaseEndpoint):
            name = "items"

            async def list(self, active_only: bool = False) -> list[dict]:
                \"\"\"List all items.\"\"\"
                return await self.table.select(where={"active": active_only})

            @POST
            async def add(self, id: str, name: str) -> dict:
                \"\"\"Add a new item.\"\"\"
                await self.table.insert({"id": id, "name": name})
                return {"id": id, "name": name}

Note:
    Use EndpointManager.discover() to scan entity packages and instantiate
    endpoint classes with their corresponding tables.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, get_origin, get_type_hints

from pydantic import create_model

if TYPE_CHECKING:
    from proxy.proxy_base import ProxyBase


def POST(method: Callable) -> Callable:
    """Decorator to mark an endpoint method as POST.

    POST methods receive parameters via JSON request body
    instead of query parameters.

    Args:
        method: The async method to decorate.

    Returns:
        The decorated method with _http_post attribute set.

    Example:
        ::

            @POST
            async def add(self, id: str, data: dict) -> dict:
                \"\"\"Add item with complex data.\"\"\"
                ...
    """
    method._http_post = True  # type: ignore[attr-defined]
    return method


class BaseEndpoint:
    """Base class for all endpoints with introspection capabilities.

    Provides method discovery, HTTP method inference, and Pydantic model
    generation from signatures for automatic API/CLI generation.

    Attributes:
        name: Endpoint name used in URL paths and CLI groups.
        table: Database table instance for operations.

    Example:
        Create a custom endpoint::

            class ItemEndpoint(BaseEndpoint):
                name = "items"

                async def get(self, item_id: str) -> dict:
                    item = await self.table.get(item_id)
                    if not item:
                        raise ValueError(f"Item '{item_id}' not found")
                    return item

                @POST
                async def add(self, id: str, name: str) -> dict:
                    return await self.table.add({"id": id, "name": name})

            # Register with FastAPI
            endpoint = ItemEndpoint(db.table("items"))
            register_endpoint(app, endpoint)
    """

    name: str = ""

    def __init__(self, table: Any):
        """Initialize endpoint with table reference.

        Args:
            table: Database table instance for operations.
        """
        self.table = table

    # =========================================================================
    # Base CRUD methods - subclasses can override for custom logic
    # =========================================================================

    async def list(self) -> list[dict[str, Any]]:
        """List all records."""
        return await self.table.select()

    async def get(self, id: str) -> dict[str, Any]:
        """Get single record by primary key.

        Args:
            id: Primary key value.

        Returns:
            Record dict.

        Raises:
            ValueError: If record not found.
        """
        from proxy.sql import RecordNotFoundError

        try:
            return await self.table.record(pkey=id)
        except RecordNotFoundError:
            raise ValueError(f"{self.name} '{id}' not found")

    @POST
    async def add(self, id: str, **data: Any) -> dict[str, Any]:
        """Add new record.

        Args:
            id: Primary key value.
            **data: Additional fields.

        Returns:
            Created record dict.
        """
        pkey = self.table.pkey or "id"
        record = {pkey: id, **data}
        await self.table.insert(record)
        return record

    @POST
    async def delete(self, id: str) -> bool:
        """Delete record by primary key.

        Args:
            id: Primary key value.

        Returns:
            True if deleted.
        """
        pkey = self.table.pkey or "id"
        await self.table.delete(where={pkey: id})
        return True

    # =========================================================================
    # Introspection methods for API/CLI generation
    # =========================================================================

    # Methods excluded from API/CLI generation (internal use only)
    _internal_methods = {"invoke"}

    def get_methods(self) -> list[tuple[str, Callable]]:
        """Return all public async methods for API/CLI generation.

        Returns:
            List of (method_name, method) tuples for all public
            async methods (excluding private and internal methods).
        """
        methods = []
        for method_name in dir(self):
            if method_name.startswith("_"):
                continue
            if method_name in self._internal_methods:
                continue
            method = getattr(self, method_name)
            if callable(method) and inspect.iscoroutinefunction(method):
                methods.append((method_name, method))
        return methods

    def get_http_method(self, method_name: str) -> str:
        """Determine HTTP method for an endpoint method.

        Args:
            method_name: Name of the endpoint method.

        Returns:
            "POST" if decorated with @POST, otherwise "GET".
        """
        method = getattr(self, method_name)
        if getattr(method, "_http_post", False):
            return "POST"
        return "GET"

    def create_request_model(self, method_name: str) -> type:
        """Create Pydantic model from method signature.

        Used by API layer to validate and parse request bodies.

        Args:
            method_name: Name of the method to introspect.

        Returns:
            Dynamically created Pydantic model class.
        """
        method = getattr(self, method_name)
        sig = inspect.signature(method)

        try:
            hints = get_type_hints(method)
        except Exception:
            hints = {}

        fields = {}
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            annotation = hints.get(param_name, param.annotation)
            if annotation is inspect.Parameter.empty:
                annotation = Any

            fields[param_name] = self._annotation_to_field(annotation, param.default)

        model_name = f"{method_name.title().replace('_', '')}Request"
        return create_model(model_name, **fields)

    def is_simple_params(self, method_name: str) -> bool:
        """Check if method has only simple params suitable for query string.

        Args:
            method_name: Name of the method to check.

        Returns:
            False if any parameter is list or dict (including Optional[list]).
        """
        method = getattr(self, method_name)

        try:
            hints = get_type_hints(method)
        except Exception:
            hints = {}

        sig = inspect.signature(method)
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            ann = hints.get(param_name, param.annotation)
            if self._is_complex_type(ann):
                return False
        return True

    def _is_complex_type(self, ann: Any) -> bool:
        """Check if annotation is a complex type (list, dict, or contains them)."""
        import types
        from typing import Union, get_args

        if ann in (list, dict):
            return True

        origin = get_origin(ann)
        if origin in (list, dict):
            return True

        if origin is Union or isinstance(origin, type) and origin is types.UnionType:
            for arg in get_args(ann):
                if arg is type(None):
                    continue
                if self._is_complex_type(arg):
                    return True

        return False

    def count_params(self, method_name: str) -> int:
        """Count non-self parameters for a method.

        Args:
            method_name: Name of the method.

        Returns:
            Number of parameters excluding 'self'.
        """
        method = getattr(self, method_name)
        sig = inspect.signature(method)
        return sum(1 for p in sig.parameters if p != "self")

    def _annotation_to_field(self, annotation: Any, default: Any) -> tuple[Any, Any]:
        """Convert Python annotation to Pydantic field tuple (type, default)."""
        if default is inspect.Parameter.empty:
            return (annotation, ...)  # Required field
        return (annotation, default)

    async def invoke(self, method_name: str, params: dict[str, Any]) -> Any:
        """Validate parameters and call endpoint method within a transaction.

        Single entry point for all channels (CLI, API, UI, etc.).
        Validates input with Pydantic before executing method.
        Wraps execution in a database transaction: COMMIT on success,
        ROLLBACK on exception.

        Args:
            method_name: Name of the method to call.
            params: Raw parameters dict (may contain strings from CLI).

        Returns:
            Method result.

        Raises:
            ValidationError: If params don't match method signature.
            ValueError: If method not found.
        """
        method = getattr(self, method_name, None)
        if method is None or not callable(method):
            raise ValueError(f"Method '{method_name}' not found on {self.name}")

        # Create and validate with Pydantic model
        model_class = self.create_request_model(method_name)
        validated = model_class.model_validate(params)

        # Call method within transaction (auto commit/rollback)
        async with self.table.db.connection():
            return await method(**validated.model_dump())


class EndpointManager:
    """Manager for endpoint discovery and instantiation.

    Holds reference to proxy and manages all endpoint instances.
    Provides dict-like access to endpoints by name.

    Attributes:
        proxy: Parent proxy instance (access db via proxy.db).
        _endpoints: Internal dict of endpoint instances.
    """

    def __init__(self, parent: ProxyBase):
        """Initialize manager with proxy reference.

        Args:
            parent: Proxy instance (provides access to db).
        """
        self.proxy = parent
        self._endpoints: dict[str, BaseEndpoint] = {}

    def discover(self, *packages: str, ee_packages: list[str] | None = None) -> list[BaseEndpoint]:
        """Discover and instantiate endpoints from entity packages.

        Args:
            *packages: CE packages to scan for endpoints.
            ee_packages: Optional EE packages for mixin composition.

        Returns:
            List of instantiated endpoint instances.
        """
        ee_package = ee_packages[0] if ee_packages else None

        for package in packages:
            ce_modules = self._find_entity_modules(package, "endpoint")
            ee_modules = self._find_entity_modules(ee_package, "endpoint_ee") if ee_package else {}

            for entity_name, ce_module in ce_modules.items():
                ce_class = self._get_class_from_module(ce_module, "Endpoint")
                if not ce_class:
                    continue

                ee_module = ee_modules.get(entity_name)
                endpoint_class = ce_class
                if ee_module:
                    ee_mixin = self._get_ee_mixin_from_module(ee_module, "_EE")
                    if ee_mixin:
                        endpoint_class = type(
                            ce_class.__name__, (ee_mixin, ce_class), {"__module__": ce_class.__module__}
                        )

                # Instantiate endpoint with table from db
                table = self.proxy.db.table(endpoint_class.name)
                endpoint = endpoint_class(table)
                self._endpoints[endpoint_class.name] = endpoint

        return list(self._endpoints.values())

    def _find_entity_modules(self, base_package: str | None, module_name: str) -> dict[str, Any]:
        """Find entity modules in a package."""
        result: dict[str, Any] = {}
        if not base_package:
            return result
        try:
            package = importlib.import_module(base_package)
        except ImportError:
            return result

        package_path = getattr(package, "__path__", None)
        if not package_path:
            return result

        for _, name, is_pkg in pkgutil.iter_modules(package_path):
            if not is_pkg:
                continue
            full_module_name = f"{base_package}.{name}.{module_name}"
            try:
                module = importlib.import_module(full_module_name)
                result[name] = module
            except ImportError:
                pass
        return result

    def _get_class_from_module(self, module: Any, class_suffix: str) -> type | None:
        """Extract a class from module by suffix pattern."""
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            obj = getattr(module, attr_name)
            if isinstance(obj, type) and attr_name.endswith(class_suffix):
                if "_EE" in attr_name or "Mixin" in attr_name:
                    continue
                if attr_name in ("BaseEndpoint", "Endpoint"):
                    continue
                if not hasattr(obj, "name"):
                    continue
                return obj
        return None

    def _get_ee_mixin_from_module(self, module: Any, class_suffix: str) -> type | None:
        """Extract an EE mixin class from module."""
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if isinstance(obj, type) and name.endswith(class_suffix):
                return obj
        return None

    def __getitem__(self, name: str) -> BaseEndpoint:
        """Get endpoint by name."""
        if name not in self._endpoints:
            raise KeyError(f"Endpoint '{name}' not found")
        return self._endpoints[name]

    def __contains__(self, name: str) -> bool:
        """Check if endpoint exists."""
        return name in self._endpoints

    def __iter__(self):
        """Iterate over endpoint names."""
        return iter(self._endpoints)

    def values(self):
        """Return endpoint instances."""
        return self._endpoints.values()

    def items(self):
        """Return (name, endpoint) pairs."""
        return self._endpoints.items()


__all__ = ["BaseEndpoint", "EndpointManager", "POST"]
