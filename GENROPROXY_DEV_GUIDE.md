# Claude Instructions for genro-proxy Users

This document contains **mandatory rules and patterns** for projects that use `genro-proxy` as a dependency.

**Include in your project's CLAUDE.md:**

```markdown
**genro-proxy Dependency**: This project uses genro-proxy. Read and follow:
[CLAUDE_FOR_GENROPROXY_USERS.md](https://github.com/softwellsrl/meta-genro-modules/blob/main/sub-projects/genro-proxy/CLAUDE_FOR_GENROPROXY_USERS.md)
```

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Creating a New Proxy](#creating-a-new-proxy)
4. [Entities: Table + Endpoint](#entities-table--endpoint)
5. [SQL Layer Rules](#sql-layer-rules)
6. [Extending Base Tables](#extending-base-tables)
7. [Creating Custom Endpoints](#creating-custom-endpoints)
8. [CLI Commands](#cli-commands)
9. [API Routes](#api-routes)
10. [Configuration](#configuration)
11. [Testing](#testing)

---

## Architecture Overview

genro-proxy provides a layered architecture for building microservices:

```
┌─────────────────────────────────────────────────────────────┐
│                     Your Proxy (e.g., WopiProxy)            │
│   - Subclasses ProxyBase                                    │
│   - Defines entity_packages for autodiscovery               │
│   - Adds domain-specific logic                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        ProxyBase                            │
│   - config: ProxyConfigBase                                 │
│   - encryption: EncryptionManager                           │
│   - db: SqlDb (autodiscovers Table classes)                 │
│   - endpoints: EndpointManager (autodiscovers Endpoints)    │
│   - api: ApiManager (creates FastAPI app)                   │
│   - cli: CliManager (creates Click commands)                │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   SQL Layer   │     │   Endpoints   │     │   Interface   │
│               │     │               │     │               │
│ SqlDb         │     │ BaseEndpoint  │     │ ApiManager    │
│ Table         │     │ POST decorator│     │ CliManager    │
│ Column        │     │ invoke()      │     │ register_*    │
│ Adapters      │     │ introspection │     │               │
└───────────────┘     └───────────────┘     └───────────────┘
```

### Key Concepts

1. **Autodiscovery**: Tables and Endpoints are discovered automatically from `entity_packages`
2. **Single Entry Point**: All operations go through `endpoint.invoke()` (CLI, API, UI)
3. **Introspection**: API routes and CLI commands are generated from method signatures
4. **Multi-tenant**: Built-in tenant isolation via `tenant_id` parameter

---

## Project Structure

A project using genro-proxy should follow this structure:

```
genro-myproxy/
├── src/
│   └── genro_myproxy/
│       ├── __init__.py
│       ├── __main__.py           # CLI entry point
│       ├── server.py             # API entry point
│       ├── proxy.py              # Your proxy class
│       └── entities/
│           ├── __init__.py
│           ├── my_entity/
│           │   ├── __init__.py
│           │   ├── table.py      # MyEntityTable(Table)
│           │   └── endpoint.py   # MyEntityEndpoint(BaseEndpoint)
│           └── another_entity/
│               ├── __init__.py
│               ├── table.py
│               └── endpoint.py
├── tests/
├── pyproject.toml
├── CLAUDE.md                     # Must reference this document
└── README.md
```

---

## Creating a New Proxy

### 1. Define Your Proxy Class

```python
# src/genro_myproxy/proxy.py
from dataclasses import dataclass
from genro_proxy import ProxyBase, ProxyConfigBase


@dataclass
class MyProxyConfig(ProxyConfigBase):
    """Configuration for MyProxy service."""

    # Add your custom config fields
    my_custom_setting: str = "default"
    background_interval: int = 60


class MyProxy(ProxyBase):
    """My domain-specific proxy service."""

    # CRITICAL: List your entity packages for autodiscovery
    entity_packages = [
        "genro_proxy.entities",      # Base entities (tenant, account, etc.)
        "genro_myproxy.entities",    # Your custom entities
    ]

    # Environment variable for encryption key
    encryption_key_env = "MYPROXY_ENCRYPTION_KEY"

    def __init__(self, config: MyProxyConfig | None = None):
        super().__init__(config or MyProxyConfig())
        # Add your custom initialization here

    async def init(self) -> None:
        """Initialize proxy."""
        await super().init()
        # Add your custom initialization (e.g., ensure default tenant)
        async with self.db.connection():
            await self.db.table("tenants").ensure_default()
```

### 2. Create the Server Entry Point

```python
# src/genro_myproxy/server.py
from .proxy import MyProxy, MyProxyConfig

# Create proxy instance
config = MyProxyConfig(
    db_path="/data/myproxy.db",
    instance_name="myproxy",
)
proxy = MyProxy(config=config)

# Export FastAPI app for uvicorn
app = proxy.api.app
```

### 3. Create the CLI Entry Point

```python
# src/genro_myproxy/__main__.py
from .proxy import MyProxy, MyProxyConfig

def main():
    config = MyProxyConfig()
    proxy = MyProxy(config=config)
    proxy.cli.cli()

if __name__ == "__main__":
    main()
```

### 4. Register CLI Command in pyproject.toml

```toml
[project.scripts]
myproxy = "genro_myproxy.__main__:main"
```

---

## Entities: Table + Endpoint

An **entity** is a logical unit consisting of:

- **Table**: Database schema and CRUD operations
- **Endpoint**: API/CLI interface methods

Both are autodiscovered from `entity_packages`.

### Entity Package Structure

```
entities/
└── wopi_session/           # Entity name (snake_case)
    ├── __init__.py
    ├── table.py            # Contains WopiSessionsTable
    └── endpoint.py         # Contains WopiSessionEndpoint
```

### Naming Convention

| Component | Class Name | File |
|-----------|------------|------|
| Table | `{EntityName}Table` (e.g., `WopiSessionsTable`) | `table.py` |
| Endpoint | `{EntityName}Endpoint` (e.g., `WopiSessionEndpoint`) | `endpoint.py` |

The `name` attribute must match between Table and Endpoint:

```python
# table.py
class WopiSessionsTable(Table):
    name = "wopi_sessions"  # ← Must match endpoint.name

# endpoint.py
class WopiSessionEndpoint(BaseEndpoint):
    name = "wopi_sessions"  # ← Must match table.name
```

---

## SQL Layer Rules

### Type Conversions Are Automatic (CRITICAL)

**NEVER do manual type conversions when using the SQL layer.**

The SQL layer handles all type conversions automatically:

- `datetime`, `Decimal`, `date`, `time` are preserved in JSON columns via TYTX
- `Timestamp` columns handle Python datetime ↔ database format automatically

```python
# ❌ WRONG - manual serialization
await table.insert({"created_at": datetime.now().isoformat()})
record = await table.record(pk)
dt = datetime.fromisoformat(record["created_at"])

# ✅ CORRECT - pass native Python types directly
await table.insert({"created_at": datetime.now()})
record = await table.record(pk)
record["created_at"]  # → datetime object, ready to use
```

**This applies to:**

- All Table CRUD operations (insert, update, select, record)
- JSON columns (`json_encoded=True`)
- Timestamp columns

**DO NOT** use `.isoformat()`, `datetime.fromisoformat()`, or any manual conversion.

### Column Types

```python
from genro_proxy.sql import String, Integer, Timestamp

# Available types
c.column("name", String)              # TEXT
c.column("count", Integer)            # INTEGER
c.column("created", Timestamp)        # TIMESTAMP
```

### Column Options

```python
# Required field
c.column("host", String, nullable=False)

# With default value
c.column("port", Integer, default=587)

# JSON-encoded (auto serialize/deserialize with TYTX)
c.column("metadata", String, json_encoded=True)

# Encrypted at rest
c.column("password", String, encrypted=True)

# Both JSON and encrypted
c.column("secrets", String, json_encoded=True, encrypted=True)

# Foreign key relation
c.column("tenant_id", String).relation("tenants", sql=True)
```

---

## Extending Base Tables

When extending a base table (e.g., `AccountsTable`), **always call `super().configure()`**.

### Example: Adding Custom Columns

```python
# src/genro_myproxy/entities/account/table.py
from genro_proxy.entities.account import AccountsTable
from genro_proxy.sql import Integer, String, Timestamp


class MyAccountsTable(AccountsTable):
    """Account with SMTP-specific fields."""

    def configure(self) -> None:
        # CRITICAL: Keep base columns
        super().configure()

        # Add custom columns
        c = self.columns
        c.column("host", String, nullable=False)
        c.column("port", Integer, default=587)
        c.column("use_tls", Integer, default=1)
        c.column("last_used", Timestamp)

    async def sync_schema(self) -> None:
        """Add missing columns to existing table."""
        await super().sync_schema()

        # Add columns that might be missing (for migrations)
        await self.add_column_if_missing("host")
        await self.add_column_if_missing("port")
        await self.add_column_if_missing("use_tls")
        await self.add_column_if_missing("last_used")
```

### Example: Adding Custom Methods

```python
class MyAccountsTable(AccountsTable):

    def configure(self) -> None:
        super().configure()
        # ... columns ...

    async def get_active_accounts(self, tenant_id: str) -> list[dict]:
        """Get only active accounts for a tenant."""
        return await self.select(
            where={"tenant_id": tenant_id, "active": 1},
            order_by="name"
        )

    async def update_last_used(self, tenant_id: str, account_id: str) -> None:
        """Update last_used timestamp."""
        async with self.record_to_update(
            {"tenant_id": tenant_id, "id": account_id}
        ) as rec:
            rec["last_used"] = datetime.now()  # Pass datetime directly!
```

---

## Creating Custom Endpoints

Endpoints expose Table operations via API and CLI.

### Basic Endpoint

```python
# src/genro_myproxy/entities/my_entity/endpoint.py
from typing import Any
from genro_proxy.interface import BaseEndpoint, endpoint


class MyEntityEndpoint(BaseEndpoint):
    """API endpoint for my entity."""

    name = "my_entities"  # URL path and CLI group name

    # GET methods (default)
    async def list(self, tenant_id: str) -> list[dict]:
        """List all entities for a tenant."""
        return await self.table.select(where={"tenant_id": tenant_id})

    async def get(self, tenant_id: str, entity_id: str) -> dict:
        """Get a single entity."""
        return await self.table.record(
            where={"tenant_id": tenant_id, "id": entity_id}
        )

    # POST methods (JSON body)
    @endpoint(post=True)
    async def add(
        self,
        tenant_id: str,
        id: str,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> dict:
        """Create a new entity."""
        async with self.table.record_to_update(
            {"tenant_id": tenant_id, "id": id},
            insert_missing=True,
        ) as rec:
            rec["name"] = name
            rec["config"] = config

        return await self.get(tenant_id, id)

    @endpoint(post=True)
    async def delete(self, tenant_id: str, entity_id: str) -> int:
        """Delete an entity."""
        return await self.table.delete(
            where={"tenant_id": tenant_id, "id": entity_id}
        )

    # CLI-only method (not exposed via REST API)
    @endpoint(api=False)
    async def import_from_file(self, tenant_id: str, path: str) -> dict:
        """Import entities from a file (CLI only)."""
        # ... implementation ...
        return {"imported": 10}

    # API-only method (not exposed via CLI)
    @endpoint(cli=False)
    async def internal_sync(self, tenant_id: str) -> dict:
        """Internal sync endpoint (API only)."""
        return {"synced": True}
```

### The @endpoint() Decorator

The `@endpoint()` decorator configures how methods are exposed:

```python
from genro_proxy.interface import endpoint

# POST method (receives params from JSON body)
@endpoint(post=True)
async def add(self, ...): ...

# CLI-only method (not exposed via REST API)
@endpoint(api=False)
async def serve(self, ...): ...

# API-only method (not exposed via CLI)
@endpoint(cli=False)
async def webhook(self, ...): ...

# REPL-only method
@endpoint(api=False, cli=False, repl=True)
async def debug_info(self, ...): ...

# Multiple options combined
@endpoint(post=True, cli=False)
async def batch_update(self, ...): ...
```

**Decorator parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `post` | `False` | Use POST method (params from JSON body) instead of GET (query params) |
| `api` | `True` | Expose method via REST API |
| `cli` | `True` | Expose method via CLI commands |
| `repl` | `True` | Expose method via REPL |

### Class-Level Defaults

Set default channel availability at class level:

```python
class CliOnlyEndpoint(BaseEndpoint):
    """Endpoint exposed only via CLI by default."""

    name = "tools"
    _default_api = False  # All methods CLI-only by default

    async def cleanup(self) -> dict:
        """CLI-only (inherits class default)."""
        return {"ok": True}

    @endpoint(api=True)  # Override: also expose via API
    async def status(self) -> dict:
        """Available on both CLI and API."""
        return {"running": True}
```

**Available class defaults:**

- `_default_api = True` - Expose via REST API
- `_default_cli = True` - Expose via CLI
- `_default_repl = True` - Expose via REPL
- `_default_post = False` - Use POST method

### Extending Base Endpoints

```python
# src/genro_myproxy/entities/account/endpoint.py
from genro_proxy.entities.account import AccountEndpoint
from genro_proxy.interface import endpoint


class MyAccountEndpoint(AccountEndpoint):
    """Extended account endpoint with SMTP-specific parameters."""

    @endpoint(post=True)
    async def add(
        self,
        tenant_id: str,
        id: str,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        name: str | None = None,
    ) -> dict:
        """Add SMTP account with server configuration."""
        async with self.table.record_to_update(
            {"tenant_id": tenant_id, "id": id},
            insert_missing=True,
        ) as rec:
            rec["name"] = name or id
            rec["host"] = host
            rec["port"] = port
            rec["use_tls"] = 1 if use_tls else 0
            rec["config"] = {
                "username": username,
                "password": password,
            }

        return await self.get(tenant_id, id)
```

### Method Introspection

Methods are introspected to generate API routes and CLI commands:

| Method | HTTP | CLI |
|--------|------|-----|
| `async def list(self, tenant_id: str)` | `GET /api/my_entities/list?tenant_id=X` | `myproxy my-entities list X` |
| `@endpoint(post=True) async def add(self, ...)` | `POST /api/my_entities/add` | `myproxy my-entities add ...` |
| `@endpoint(api=False) async def serve(...)` | Not exposed | `myproxy my-entities serve ...` |

**Rules:**

- Methods without `@endpoint(post=True)` → GET (params from query string)
- Methods with `@endpoint(post=True)` → POST (params from JSON body)
- Method names with `_` → CLI uses `-` (e.g., `add_batch` → `add-batch`)
- `tenant_id` is special: becomes optional positional argument in CLI with context fallback

---

## ProxyEndpoint

`ProxyEndpoint` provides server/instance process management commands. Subclass it to add custom proxy-level commands.

### Subclassing ProxyEndpoint

```python
# src/genro_myproxy/proxy.py
from genro_proxy import ProxyEndpoint
from genro_proxy.interface import endpoint


class MyProxyEndpoint(ProxyEndpoint):
    """Extended proxy endpoint with custom commands."""

    name = "myproxy"  # Optional: override default "proxy" name

    @endpoint(api=False)  # CLI-only
    async def init_db(self, force: bool = False) -> dict:
        """Initialize database schema."""
        # Custom initialization logic
        return {"ok": True, "tables_created": 5}

    async def version(self) -> dict:
        """Return proxy version info."""
        return {"version": "1.0.0", "name": "MyProxy"}

    @endpoint(post=True)
    async def reload_config(self) -> dict:
        """Reload configuration from disk."""
        # Reload logic
        return {"ok": True, "reloaded": True}
```

### Built-in ProxyEndpoint Methods

| Method | Description | Default Channels |
|--------|-------------|------------------|
| `serve(name, host, port, background)` | Start server instance | CLI only |
| `stop(name, force)` | Stop running instance(s) | CLI + API |
| `restart(name, force)` | Restart instance(s) | CLI + API |
| `list_instances()` | List all configured instances | CLI + API |

### CLI Commands from ProxyEndpoint

```bash
# Start server
myproxy proxy serve default --port 8000

# List instances
myproxy proxy list-instances

# Stop instance
myproxy proxy stop dev-instance

# Stop all instances
myproxy proxy stop "*"

# Custom commands from your subclass
myproxy myproxy init-db --force
myproxy myproxy version
```

---

## CLI Commands

CLI commands are auto-generated from endpoints.

### Generated Command Structure

```bash
myproxy <endpoint-name> <method-name> [args] [--options]

# Examples:
myproxy accounts list acme                    # tenant_id as positional
myproxy accounts add acme main --host smtp.example.com --port 587
myproxy accounts get acme main
myproxy accounts delete acme main
```

### Custom CLI Commands

Add custom commands in `CliManager`:

```python
# In your proxy class
class MyProxy(ProxyBase):

    def __init__(self, config):
        super().__init__(config)
        # Add custom CLI commands
        self._register_custom_cli_commands()

    def _register_custom_cli_commands(self):
        import click

        @self.cli.cli.command("status")
        def status_cmd():
            """Show service status."""
            click.echo(f"Instance: {self.config.instance_name}")
            click.echo(f"Database: {self.config.db_path}")
```

---

## API Routes

API routes are auto-generated from endpoints.

### Generated Routes

```
GET  /health                          # Always available, no auth
GET  /api/accounts/list?tenant_id=X   # Requires auth if configured
POST /api/accounts/add                # JSON body
GET  /api/accounts/get?tenant_id=X&account_id=Y
POST /api/accounts/delete             # JSON body
```

### Authentication

Authentication is via `X-API-Token` header:

- **Admin token**: Full access (configured via `GENRO_PROXY_API_TOKEN`)
- **Tenant token**: Access restricted to own tenant (via `tenants.api_key_hash`)

```python
# Create tenant API key
async with proxy.db.connection():
    api_key = await proxy.db.table("tenants").create_api_key("acme")
    # Store api_key securely - only returned once!
```

### Custom API Routes

Add custom routes to the FastAPI app:

```python
# In your server.py
from fastapi import APIRouter

router = APIRouter(prefix="/custom")

@router.get("/my-route")
async def my_custom_route():
    return {"status": "ok"}

# Add to app
proxy.api.app.include_router(router)
```

---

## Configuration

### Environment Variables

```bash
# Database
GENRO_PROXY_DB=/data/myproxy.db        # SQLite path or PostgreSQL URL

# Authentication
GENRO_PROXY_API_TOKEN=secret123        # Admin API token

# Server
GENRO_PROXY_INSTANCE=myproxy           # Instance name
GENRO_PROXY_PORT=8000                  # Server port

# Encryption
MYPROXY_ENCRYPTION_KEY=base64key...    # Field encryption key

# Optional
GENRO_PROXY_TEST_MODE=1                # Disable background processing
GENRO_PROXY_START_ACTIVE=1             # Start processing immediately
```

### Programmatic Configuration

```python
config = MyProxyConfig(
    db_path="/data/myproxy.db",
    instance_name="myproxy",
    port=8000,
    api_token="secret123",
    test_mode=False,
    start_active=True,
    # Custom fields
    my_custom_setting="value",
)
proxy = MyProxy(config=config)
```

---

## Testing

### Database Fixtures

```python
import pytest
from genro_proxy.sql import SqlDb

@pytest.fixture
async def db():
    """In-memory database for testing."""
    db = SqlDb(":memory:")
    db.add_table(MyTable)

    async with db.connection():
        await db.check_structure()
        yield db

@pytest.fixture
async def table(db):
    """Table instance for testing."""
    async with db.connection():
        yield db.table("my_entities")
```

### Testing Tables

```python
async def test_insert_and_get(table):
    # Insert
    await table.insert({
        "id": "test-1",
        "tenant_id": "acme",
        "name": "Test Entity",
        "created_at": datetime.now(),  # Pass datetime directly!
    })

    # Get
    record = await table.record(where={"id": "test-1"})
    assert record["name"] == "Test Entity"
    assert isinstance(record["created_at"], datetime)  # Type preserved!
```

### Testing Endpoints

```python
async def test_endpoint_add(db):
    endpoint = MyEntityEndpoint(db.table("my_entities"))

    async with db.connection():
        result = await endpoint.invoke("add", {
            "tenant_id": "acme",
            "id": "test-1",
            "name": "Test",
        })

    assert result["id"] == "test-1"
```

### Testing with Proxy

```python
@pytest.fixture
async def proxy():
    """Full proxy for integration tests."""
    config = MyProxyConfig(db_path=":memory:", test_mode=True)
    proxy = MyProxy(config=config)
    await proxy.init()
    yield proxy
    await proxy.shutdown()

async def test_full_flow(proxy):
    async with proxy.db.connection():
        # Add entity via endpoint
        endpoint = proxy.endpoints["my_entities"]
        await endpoint.invoke("add", {"tenant_id": "acme", "id": "test"})

        # Verify in database
        record = await proxy.db.table("my_entities").record(
            where={"id": "test"}
        )
        assert record is not None
```

---

## Quick Reference

### Table Methods

```python
# CRUD
await table.insert(data)
await table.update(data, where={...})
await table.delete(where={...})
await table.select(where={...}, order_by="...")
await table.record(pkey=id)  # or where={...}

# Context manager for atomic updates
async with table.record_to_update(pkey_or_where, insert_missing=True) as rec:
    rec["field"] = value  # Changes committed on exit
```

### Endpoint Decorators

```python
from genro_proxy.interface.endpoint_base import POST

@POST  # Method receives params from JSON body instead of query string
async def my_method(self, ...):
    ...
```

### Column Types

```python
from genro_proxy.sql import String, Integer, Timestamp

c.column("name", String)
c.column("count", Integer)
c.column("created", Timestamp)
c.column("data", String, json_encoded=True)
c.column("secret", String, encrypted=True)
c.column("fk", String).relation("other_table", sql=True)
```

---

## Common Mistakes

### ❌ DON'T: Manual datetime conversion

```python
# WRONG
await table.insert({"created_at": datetime.now().isoformat()})
```

### ✅ DO: Pass native types

```python
# CORRECT
await table.insert({"created_at": datetime.now()})
```

### ❌ DON'T: Forget super().configure()

```python
# WRONG - loses base columns!
class MyTable(AccountsTable):
    def configure(self):
        c = self.columns
        c.column("custom", String)  # Base columns missing!
```

### ✅ DO: Always call super

```python
# CORRECT
class MyTable(AccountsTable):
    def configure(self):
        super().configure()  # Keep base columns
        c = self.columns
        c.column("custom", String)
```

### ❌ DON'T: Mismatched names

```python
# WRONG - table.name != endpoint.name
class MyTable(Table):
    name = "my_things"

class MyEndpoint(BaseEndpoint):
    name = "things"  # Different name!
```

### ✅ DO: Match names exactly

```python
# CORRECT
class MyTable(Table):
    name = "my_things"

class MyEndpoint(BaseEndpoint):
    name = "my_things"  # Same name
```

---

## Documentation Reference

- [docs/extending/tables.rst](https://github.com/softwellsrl/meta-genro-modules/blob/main/sub-projects/genro-proxy/docs/extending/tables.rst) - Table extension guide
- Table class docstring in `genro_proxy.sql.table`
- BaseEndpoint class docstring in `genro_proxy.interface.endpoint_base`

---

**Last Updated**: 2025-02-04
