# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Base class for endpoint introspection and command dispatch.

This module provides the foundation for automatic API/CLI/REPL generation
from endpoint classes via method introspection.

Components:
    endpoint: Decorator to configure method channels and HTTP method.
    BaseEndpoint: Base class with introspection capabilities.
    EndpointManager: Discovery and instantiation of endpoints.

Example:
    Define an endpoint::

        from genro_proxy.interface.endpoint_base import BaseEndpoint, endpoint

        class MyEndpoint(BaseEndpoint):
            name = "items"

            async def list(self, active_only: bool = False) -> list[dict]:
                \"\"\"List all items (default: all channels, GET).\"\"\"
                return await self.table.select(where={"active": active_only})

            @endpoint(post=True)
            async def add(self, id: str, name: str) -> dict:
                \"\"\"Add a new item (POST on all channels).\"\"\"
                await self.table.insert({"id": id, "name": name})
                return {"id": id, "name": name}

            @endpoint(api=False)
            async def serve(self, host: str = "0.0.0.0") -> None:
                \"\"\"Start server (CLI/REPL only).\"\"\"
                ...

Note:
    Use EndpointManager.discover() to scan entity packages and instantiate
    endpoint classes with their corresponding tables.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, get_args, get_origin, get_type_hints

from pydantic import create_model

if TYPE_CHECKING:
    from genro_proxy.proxy_base import ProxyBase


class InvalidTokenError(Exception):
    """Raised when API token is invalid (not admin, not valid tenant token)."""


def endpoint(
    *,
    api: bool | None = None,
    cli: bool | None = None,
    repl: bool | None = None,
    post: bool | None = None,
) -> Callable[[Callable], Callable]:
    """Configure endpoint method channels and HTTP method.

    When a parameter is None, the class default is used.
    Class defaults are defined via _default_api, _default_cli, etc.

    Args:
        api: Expose via REST API. None = use class default.
        cli: Expose via CLI command. None = use class default.
        repl: Expose in REPL. None = use class default.
        post: Use HTTP POST instead of GET. None = use class default.

    Returns:
        Decorator function that sets method attributes.

    Example:
        ::

            @endpoint(post=True)
            async def add(self, id: str, data: dict) -> dict:
                \"\"\"POST method on all channels.\"\"\"
                ...

            @endpoint(api=False)
            async def serve(self, host: str) -> None:
                \"\"\"CLI and REPL only.\"\"\"
                ...
    """

    def decorator(method: Callable) -> Callable:
        if api is not None:
            method._endpoint_api = api  # type: ignore[attr-defined]
        if cli is not None:
            method._endpoint_cli = cli  # type: ignore[attr-defined]
        if repl is not None:
            method._endpoint_repl = repl  # type: ignore[attr-defined]
        if post is not None:
            method._endpoint_post = post  # type: ignore[attr-defined]
        return method

    return decorator


class BaseEndpoint:
    """Base class for all endpoints with introspection capabilities.

    Provides method discovery, HTTP method inference, and Pydantic model
    generation from signatures for automatic API/CLI/REPL generation.

    Class Attributes (defaults for all methods):
        name: Endpoint name used in URL paths and CLI groups.
        _default_api: Expose methods via REST API (default True).
        _default_cli: Expose methods via CLI (default True).
        _default_repl: Expose methods in REPL (default True).
        _default_post: Use HTTP POST (default False, i.e. GET).

    Instance Attributes:
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

                @endpoint(post=True)
                async def add(self, id: str, name: str) -> dict:
                    return await self.table.add({"id": id, "name": name})

            # Register with FastAPI
            endpoint = ItemEndpoint(db.table("items"))
            register_endpoint(app, endpoint)

        CLI-only endpoint::

            class ProxyEndpoint(BaseEndpoint):
                name = "proxy"
                _default_api = False  # CLI/REPL only by default

                async def serve(self, host: str = "0.0.0.0") -> None:
                    ...
    """

    name: str = ""

    # Class-level defaults for method channel availability
    _default_api: bool = True
    _default_cli: bool = True
    _default_repl: bool = True
    _default_post: bool = False

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
        from genro_proxy.sql import RecordNotFoundError

        try:
            return await self.table.record(pkey=id)
        except RecordNotFoundError:
            raise ValueError(f"{self.name} '{id}' not found")

    @endpoint(post=True)
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

    @endpoint(post=True)
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

        Checks method attribute first, then falls back to class default.

        Args:
            method_name: Name of the endpoint method.

        Returns:
            "POST" if post=True, otherwise "GET".
        """
        method = getattr(self, method_name)
        # Check method-level setting first
        if hasattr(method, "_endpoint_post"):
            return "POST" if method._endpoint_post else "GET"
        # Fall back to class default
        return "POST" if self._default_post else "GET"

    def is_available_for_channel(self, method_name: str, channel: str) -> bool:
        """Check if method is available for a specific channel.

        Checks method attribute first, then falls back to class default.

        Args:
            method_name: Name of the endpoint method.
            channel: One of "api", "cli", "repl".

        Returns:
            True if method should be exposed on this channel.
        """
        method = getattr(self, method_name)
        attr_name = f"_endpoint_{channel}"
        default_name = f"_default_{channel}"

        # Check method-level setting first
        if hasattr(method, attr_name):
            return getattr(method, attr_name)
        # Fall back to class default
        return getattr(self, default_name, True)

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
        from typing import Union

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

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[None]:
        """Provide database connection context for invoke().

        Subclasses can override to provide different behavior
        (e.g., ProxyEndpoint yields without DB connection).
        """
        async with self.table.db.connection():
            yield

    def _coerce_json_params(self, method_name: str, params: dict[str, Any]) -> None:
        """Parse JSON strings into dict/list for parameters that expect them.

        CLI passes all values as strings. When a method parameter is annotated
        as dict or list (including Optional variants), and the value is a string,
        attempt JSON parsing in-place.
        """
        method = getattr(self, method_name)
        try:
            hints = get_type_hints(method)
        except Exception:
            return

        for param_name, value in params.items():
            if not isinstance(value, str):
                continue
            ann = hints.get(param_name)
            if ann is None:
                continue
            if self._is_complex_type(ann):
                try:
                    params[param_name] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass  # Let Pydantic report the validation error

    async def invoke(
        self,
        method_name: str,
        params: dict[str, Any],
        *,
        api_token: str | None = None,
        is_admin: bool = False,
    ) -> Any:
        """Validate parameters and call endpoint method within a transaction.

        Single entry point for all channels (CLI, API, UI, etc.).
        Validates input with Pydantic before executing method.
        Wraps execution in a database transaction: COMMIT on success,
        ROLLBACK on exception.

        For API calls with tenant tokens, resolves tenant_id from token after
        opening DB connection. Admin tokens must pass tenant_id explicitly.

        Args:
            method_name: Name of the method to call.
            params: Raw parameters dict (may contain strings from CLI).
            api_token: Optional API token for tenant resolution.
            is_admin: True if admin token was used (skip tenant resolution).

        Returns:
            Method result.

        Raises:
            ValidationError: If params don't match method signature.
            ValueError: If method not found or invalid token.
        """
        method = getattr(self, method_name, None)
        if method is None or not callable(method):
            raise ValueError(f"Method '{method_name}' not found on {self.name}")

        # Call method within transaction (auto commit/rollback)
        async with self._connection():
            # Resolve tenant_id from token if needed (non-admin token)
            if api_token and not is_admin and "tenant_id" not in params:
                tenant_id = await self._resolve_tenant_from_token(api_token)
                if tenant_id:
                    params["tenant_id"] = tenant_id

            # Parse JSON strings for dict/list params (CLI passes strings)
            self._coerce_json_params(method_name, params)

            # Create and validate with Pydantic model
            model_class = self.create_request_model(method_name)
            validated = model_class.model_validate(params)

            return await method(**validated.model_dump())

    async def _resolve_tenant_from_token(self, api_token: str) -> str | None:
        """Resolve tenant_id from API token by checking DB.

        Args:
            api_token: The API token to look up.

        Returns:
            tenant_id if valid tenant token, None otherwise.

        Raises:
            InvalidTokenError: If token is invalid (not admin, not tenant).
        """
        try:
            tenants_table = self.table.db.table("tenants")
            tenant = await tenants_table.get_tenant_by_token(api_token)
            if tenant:
                return tenant["id"]
        except (AttributeError, KeyError):
            pass
        raise InvalidTokenError("Invalid API token")


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

        When multiple packages define endpoints with the same name, the most
        derived class (per MRO) is used.

        Args:
            *packages: CE packages to scan for endpoints.
            ee_packages: Optional EE packages for mixin composition.

        Returns:
            List of instantiated endpoint instances.
        """
        ee_package = ee_packages[0] if ee_packages else None

        # Phase 1: Collect all endpoint classes from all packages
        all_classes: dict[str, type] = {}
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

                name = endpoint_class.name
                existing = all_classes.get(name)
                if existing is None:
                    all_classes[name] = endpoint_class
                elif issubclass(endpoint_class, existing):
                    # New class is more derived, replace
                    all_classes[name] = endpoint_class
                # else: existing is same or more derived, keep it

        # Phase 2: Instantiate or replace with more derived classes
        for endpoint_class in all_classes.values():
            name = endpoint_class.name
            existing = self._endpoints.get(name)
            if existing is None:
                # New endpoint
                table = self.proxy.db.table(name)
                self._endpoints[name] = endpoint_class(table)
            elif endpoint_class is not type(existing) and issubclass(endpoint_class, type(existing)):
                # New class is strictly more derived, replace existing
                table = self.proxy.db.table(name)
                self._endpoints[name] = endpoint_class(table)
            # else: existing is same or more derived, keep it

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
        """Extract a class from module by suffix pattern.

        Prefers classes defined in the module itself (obj.__module__ == module.__name__)
        over imported classes. This ensures derived classes are found even when
        they import their parent class.
        """
        candidates: list[type] = []
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
                candidates.append(obj)

        if not candidates:
            return None

        # Prefer class defined in this module over imported classes
        for cls in candidates:
            if cls.__module__ == module.__name__:
                return cls

        # Fallback to first candidate
        return candidates[0]

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


__all__ = ["BaseEndpoint", "EndpointManager", "InvalidTokenError", "endpoint"]
