# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Base class for endpoint introspection and command dispatch.

This module provides the foundation for automatic API/CLI generation
from endpoint classes via method introspection.

Components:
    POST: Decorator to mark methods as HTTP POST.
    BaseEndpoint: Base class with introspection capabilities.

Example:
    Define an endpoint::

        from proxy.interface.endpoint_base import BaseEndpoint, POST

        class MyEndpoint(BaseEndpoint):
            name = "items"

            async def list(self, active_only: bool = False) -> list[dict]:
                \"\"\"List all items.\"\"\"
                return await self.table.list_all(active_only=active_only)

            @POST
            async def add(self, id: str, name: str) -> dict:
                \"\"\"Add a new item.\"\"\"
                return await self.table.add({"id": id, "name": name})

Note:
    BaseEndpoint.discover() scans entity packages for endpoint classes
    and composes them when both exist for an entity.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Callable
from typing import Any, get_origin, get_type_hints

from pydantic import create_model


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

    def get_methods(self) -> list[tuple[str, Callable]]:
        """Return all public async methods for API/CLI generation.

        Returns:
            List of (method_name, method) tuples for all public
            async methods (excluding those starting with underscore).
        """
        methods = []
        for method_name in dir(self):
            if method_name.startswith("_"):
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

        if type(ann).__name__ == "UnionType":
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

    @classmethod
    def discover(
        cls,
        ce_package: str = "proxy.entities",
        ee_package: str | None = None,
    ) -> list[type[BaseEndpoint]]:
        """Autodiscover all endpoint classes from entities/ directories.

        Scans CE and optionally EE packages for endpoint.py and endpoint_ee.py modules.
        When both exist for an entity, composes them with EE mixin first.

        Args:
            ce_package: Base package for CE entity endpoints.
            ee_package: Optional EE package for extended endpoints.

        Returns:
            List of endpoint classes ready for instantiation.

        Example:
            ::

                for endpoint_class in BaseEndpoint.discover():
                    table = db.table(endpoint_class.name)
                    endpoint = endpoint_class(table)
                    register_endpoint(app, endpoint)
        """
        ce_modules = cls._find_entity_modules(ce_package, "endpoint")
        ee_modules = cls._find_entity_modules(ee_package, "endpoint_ee") if ee_package else {}

        endpoints: list[type[BaseEndpoint]] = []
        for entity_name, ce_module in ce_modules.items():
            ce_class = cls._get_class_from_module(ce_module, "Endpoint")
            if not ce_class:
                continue

            ee_module = ee_modules.get(entity_name)
            if ee_module:
                ee_mixin = cls._get_ee_mixin_from_module(ee_module, "_EE")
                if ee_mixin:
                    composed_class = type(
                        ce_class.__name__, (ee_mixin, ce_class), {"__module__": ce_class.__module__}
                    )
                    endpoints.append(composed_class)
                    continue

            endpoints.append(ce_class)

        return endpoints

    @classmethod
    def _find_entity_modules(cls, base_package: str, module_name: str) -> dict[str, Any]:
        """Find entity modules in a package."""
        result: dict[str, Any] = {}
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

    @classmethod
    def _get_class_from_module(cls, module: Any, class_suffix: str) -> type | None:
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

    @classmethod
    def _get_ee_mixin_from_module(cls, module: Any, class_suffix: str) -> type | None:
        """Extract an EE mixin class from module."""
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if isinstance(obj, type) and name.endswith(class_suffix):
                return obj
        return None


__all__ = ["BaseEndpoint", "POST"]
