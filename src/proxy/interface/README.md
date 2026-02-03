# Interface Layer - Multi-Channel Endpoint Exposure

This package provides infrastructure for exposing proxy endpoints through multiple channels (REST API, CLI, REPL) via automatic method introspection.

## Architecture Overview

### Multi-Channel Pattern

The same endpoint method is automatically exposed on multiple interfaces:

```
                    ┌─────────────┐
                    │  Endpoint   │
                    │  Methods    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
        │  API      │ │  CLI    │ │   REPL    │
        │ (FastAPI) │ │ (Click) │ │ (wrapped) │
        └───────────┘ └─────────┘ └───────────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼──────┐
                    │   invoke()  │ ← Pydantic validation
                    └─────────────┘
                           │
                    ┌──────▼──────┐
                    │  DB Transaction │
                    └─────────────┘
```

### Unified Validation Flow

All channels converge on `endpoint.invoke(method_name, params)`:

1. **Pydantic model generation** from method signature
2. **Parameter validation** and type coercion
3. **Method execution** within a DB transaction
4. **Auto commit/rollback** on success/failure

This ensures consistent behavior regardless of the entry point (API, CLI, or REPL).

### Discovery & Composition

- `EndpointManager.discover()` scans `entities/*/endpoint.py` modules
- Supports CE/EE (Community/Enterprise Edition) composition via MRO
- EE mixins extend CE endpoints without modifying original code

---

## Modules

### endpoint_base.py - Core Introspection

The foundation of the multi-channel pattern.

#### POST Decorator

Marks methods as HTTP POST (default is GET):

```python
from proxy.interface import BaseEndpoint, POST

class ItemEndpoint(BaseEndpoint):
    name = "items"

    async def list(self) -> list[dict]:
        """GET /api/items/list"""
        return await self.table.select()

    @POST
    async def add(self, id: str, name: str) -> dict:
        """POST /api/items/add with JSON body"""
        await self.table.insert({"id": id, "name": name})
        return {"id": id, "name": name}
```

#### BaseEndpoint Class

| Method | Description |
|--------|-------------|
| `get_methods()` | Returns all public async methods for API/CLI generation |
| `get_http_method(name)` | Returns "GET" or "POST" based on decorator |
| `create_request_model(name)` | Generates Pydantic model from method signature |
| `is_simple_params(name)` | True if all params are primitives (suitable for query string) |
| `count_params(name)` | Count of parameters excluding `self` |
| `invoke(method_name, params)` | **Unified entry point**: validates and executes within transaction |

#### Base CRUD Methods

BaseEndpoint provides default CRUD methods that subclasses can override:

```python
async def list(self) -> list[dict]        # table.select()
async def get(self, id: str) -> dict      # table.select_one() + ValueError if not found
async def add(self, id: str, **data)      # table.insert()
async def delete(self, id: str) -> bool   # table.delete()
```

#### EndpointManager Class

Manages endpoint discovery and instantiation with dict-like access:

```python
manager = EndpointManager(proxy)
manager.discover("myapp.entities")

# Access endpoints
items_endpoint = manager["items"]
for name, endpoint in manager.items():
    print(f"{name}: {endpoint.get_methods()}")
```

| Method | Description |
|--------|-------------|
| `discover(*packages, ee_packages)` | Scan packages and instantiate endpoints |
| `__getitem__(name)` | Get endpoint by name |
| `__contains__(name)` | Check if endpoint exists |
| `values()` | Return all endpoint instances |
| `items()` | Return (name, endpoint) pairs |

---

### api_base.py - FastAPI Integration

#### register_api_endpoint()

Registers all endpoint methods as FastAPI routes:

```python
from fastapi import APIRouter
from proxy.interface import register_api_endpoint

router = APIRouter(prefix="/api")
register_api_endpoint(router, items_endpoint)
```

Generated routes:
```
GET  /api/items/list
GET  /api/items/get?id=123
POST /api/items/add     {"id": "1", "name": "test"}
POST /api/items/delete  {"id": "1"}
```

Route naming: underscores become dashes (`add_batch` → `add-batch`).

#### ApiManager Class

Lazy-creates FastAPI application with:
- Health endpoint at `/health`
- All endpoint routes under `/api`
- Optional UI mounting at `/ui`
- Lifespan management (calls `proxy.init()` / `proxy.close()`)

```python
class ApiManager:
    @property
    def app(self) -> FastAPI:
        """Lazy-create FastAPI application."""
        ...
```

---

### cli_base.py - Click CLI Generation

#### register_endpoint()

Generates Click commands from endpoint introspection:

```python
import click
from proxy.interface import register_endpoint, CliContext

@click.group()
def cli():
    pass

# Pass CliContext explicitly for tenant resolution
ctx = CliContext()
register_endpoint(cli, items_endpoint, cli_context=ctx)
```

Generated commands:
```bash
myservice items list                     # uses tenant from context
myservice items list acme                # explicit tenant
myservice items add main --name "Test"   # positional + option
myservice items delete 123               # positional argument
```

#### Parameter Mapping

| Python | CLI |
|--------|-----|
| Required param | Positional argument |
| Optional param | `--option` flag |
| `bool` param | `--flag/--no-flag` toggle |
| `tenant_id` (special) | Optional positional with context fallback |

#### CliManager Class

Lazy-creates Click CLI with:
- Endpoint-based command groups
- Built-in `serve` command for starting the server
- Optional `CliContext` for tenant resolution

```python
class CliManager:
    def __init__(self, parent, cli_context: CliContext | None = None):
        ...

    @property
    def cli(self) -> click.Group:
        """Lazy-create Click CLI group."""
        ...
```

---

### cli_context.py - Context Management

Handles instance/tenant resolution for multi-instance deployments.

#### Resolution Priority

**Instance:**
1. Explicit argument
2. Environment variable (`GPROXY_INSTANCE`)
3. `.current` file in base directory
4. Auto-select if only one instance exists

**Tenant:**
1. Explicit argument
2. Environment variable (`GPROXY_TENANT`)
3. `.current` file (tenant part)

#### CliContext Class

Configurable context manager - always use as instance, not module-level functions:

```python
from pathlib import Path
from proxy.interface import CliContext

# Custom configuration for a specific proxy
ctx = CliContext(
    base_dir=Path.home() / ".mail-proxy",
    env_instance="MAIL_INSTANCE",
    env_tenant="MAIL_TENANT",
    db_name="mail.db",
    cli_name="mail-proxy",
)

instance, tenant = ctx.resolve_context()
instance, tenant = ctx.require_context(require_tenant=True)  # exits on error
```

| Method | Description |
|--------|-------------|
| `resolve_context(explicit_instance, explicit_tenant)` | Resolve using priority chain |
| `require_context(..., require_tenant)` | Resolve or exit with error |
| `list_instances()` | List all configured instances |
| `get_current_context()` | Read from `.current` file |
| `set_current_context(instance, tenant)` | Write to `.current` file |

---

### repl.py - REPL Protection

Prevents access to sensitive methods in interactive REPL sessions.

#### @reserved Decorator

Marks methods as not accessible from REPL:

```python
from proxy.interface import reserved

class MyService:
    @reserved
    def get_secret_key(self):
        return self._secret

    def public_method(self):
        return "hello"
```

#### REPLWrapper / repl_wrap()

Wraps objects to block reserved methods:

```python
from proxy.interface import repl_wrap

# In REPL setup
service = MyService()
namespace = {"service": repl_wrap(service)}

# Now in REPL:
>>> service.public_method()    # Works
'hello'
>>> service.get_secret_key()   # Blocked
AttributeError: 'get_secret_key' is reserved and not accessible in REPL
```

The wrapper also filters `dir()` output to hide reserved methods.

---

## Usage Examples

### Defining a Custom Endpoint

```python
from proxy.interface import BaseEndpoint, POST

class AccountEndpoint(BaseEndpoint):
    name = "accounts"

    async def list(self, active: bool = True) -> list[dict]:
        """List all accounts."""
        where = {"active": active} if active else {}
        return await self.table.select(where=where)

    async def get(self, email: str) -> dict:
        """Get account by email."""
        record = await self.table.select_one(where={"email": email})
        if not record:
            raise ValueError(f"Account '{email}' not found")
        return record

    @POST
    async def create(self, email: str, name: str, role: str = "user") -> dict:
        """Create new account."""
        record = {"email": email, "name": name, "role": role}
        await self.table.insert(record)
        return record

    @POST
    async def deactivate(self, email: str) -> bool:
        """Deactivate an account."""
        await self.table.update({"active": False}, where={"email": email})
        return True
```

### Using invoke() Directly

```python
# Unified entry point - validates params and handles transaction
result = await endpoint.invoke("create", {
    "email": "test@example.com",
    "name": "Test User",
    "role": "admin"
})

# Type coercion happens automatically
result = await endpoint.invoke("list", {"active": "true"})  # string → bool
```

### Registering on Both API and CLI

```python
from fastapi import APIRouter
import click
from proxy.interface import register_api_endpoint, register_endpoint, CliContext

# API registration
router = APIRouter(prefix="/api")
register_api_endpoint(router, account_endpoint)

# CLI registration with explicit context
ctx = CliContext()

@click.group()
def cli():
    pass

register_endpoint(cli, account_endpoint, cli_context=ctx)
```

---

## API Reference

### Public Exports

| Export | Type | Description |
|--------|------|-------------|
| `BaseEndpoint` | class | Base class for endpoints with introspection |
| `EndpointManager` | class | Discovery and instantiation of endpoints |
| `POST` | decorator | Marks methods as HTTP POST |
| `ApiManager` | class | Creates FastAPI application |
| `CliManager` | class | Creates Click CLI |
| `CliContext` | class | Configurable context resolution |
| `register_api_endpoint` | function | Registers endpoint on FastAPI router |
| `register_endpoint` | function | Registers endpoint on Click group |
| `REPLWrapper` | class | Wrapper blocking @reserved methods |
| `repl_wrap` | function | Factory for REPLWrapper |
| `reserved` | decorator | Marks methods as REPL-reserved |
| `console` | object | Rich console for CLI output |
