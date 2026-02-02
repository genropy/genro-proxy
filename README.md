# genro-proxy

Base infrastructure package for building Genro microservices and proxies.

## Overview

`genro-proxy` provides a complete foundation for building multi-tenant microservices:

- **Multi-tenant architecture** - Tenants, accounts, and storages out of the box
- **Automatic API generation** - FastAPI routes generated from endpoint methods
- **Automatic CLI generation** - Click commands generated from endpoint methods
- **Unified validation** - Pydantic validation across all interfaces (API, CLI, UI)
- **Database abstraction** - SQLite and PostgreSQL with async support
- **Admin UI** - Built-in SPA for managing tenants, accounts, and storages

## Quick Start

### Installation

```bash
pip install genro-proxy

# With PostgreSQL support
pip install genro-proxy[postgresql]

# With cloud storage (S3, GCS, Azure)
pip install genro-proxy[cloud]
```

### Running the Base Proxy

```bash
# Set database path
export GENRO_PROXY_DB=/path/to/proxy.db

# Start server
python -m uvicorn proxy.server:app --host 0.0.0.0 --port 8000

# Access UI at http://localhost:8000/ui
# API at http://localhost:8000/api/
# Health check at http://localhost:8000/health
```

### Using as a Library

```python
import asyncio
from proxy import ProxyBase, ProxyConfigBase

async def main():
    # Create proxy with SQLite
    config = ProxyConfigBase(
        db_path="/tmp/my_proxy.db",
        instance_name="My Proxy"
    )
    proxy = ProxyBase(config=config)
    await proxy.init()

    # Use endpoints
    tenants = proxy.endpoints["tenants"]
    await tenants.add(id="acme", name="ACME Corp", active=True)

    await proxy.close()

asyncio.run(main())
```

## Architecture

### Components

```
genro-proxy/
├── proxy/
│   ├── proxy_base.py      # ProxyBase - main entry point
│   ├── server.py          # ASGI app for uvicorn
│   │
│   ├── sql/               # Database layer
│   │   ├── sqldb.py       # SqlDb - database manager
│   │   ├── table.py       # Table - base table with CRUD
│   │   ├── column.py      # Column definitions
│   │   └── adapters/      # SQLite, PostgreSQL
│   │
│   ├── entities/          # Domain entities
│   │   ├── tenant/        # Multi-tenant support
│   │   ├── account/       # Generic accounts
│   │   ├── storage/       # Storage configurations
│   │   └── instance/      # Instance metadata
│   │
│   └── interface/         # API/CLI generation
│       ├── endpoint_base.py   # BaseEndpoint
│       ├── api_base.py        # FastAPI route generation
│       └── cli_base.py        # Click command generation
│
└── ui/                    # Admin SPA (Shoelace)
    └── index.html
```

### Key Concepts

**Endpoints** expose async methods that are automatically turned into:
- FastAPI routes (`POST /api/{endpoint}/{method}` or `GET /api/{endpoint}/{method}`)
- Click CLI commands (`proxy {endpoint} {method} [args]`)

**Tables** provide database operations with:
- JSON column encoding/decoding
- Field encryption
- Async context manager for record updates

**ProxyBase** orchestrates:
- Database initialization and schema management
- Endpoint registration
- API and CLI managers

## Extending genro-proxy

### Creating a Domain-Specific Proxy

```python
# my_mail_proxy/proxy.py
from proxy import ProxyBase, ProxyConfigBase
from proxy.sql import SqlDb

from .entities.mail_account import MailAccountsTable, MailAccountEndpoint


class MailProxyConfig(ProxyConfigBase):
    """Configuration for mail proxy."""
    smtp_timeout: int = 30
    max_retries: int = 3


class MailProxy(ProxyBase):
    """Mail-specific proxy with SMTP account support."""

    def __init__(self, config: MailProxyConfig):
        super().__init__(config)

    def _configure_db(self, db: SqlDb) -> None:
        """Register domain-specific tables."""
        super()._configure_db(db)
        # Replace generic accounts with mail-specific
        db.add_table(MailAccountsTable)

    def _register_endpoints(self) -> None:
        """Register domain-specific endpoints."""
        super()._register_endpoints()
        # Replace generic account endpoint
        self.endpoints["accounts"] = MailAccountEndpoint(
            self.db.tables["accounts"]
        )
```

### Extending Tables

```python
# my_mail_proxy/entities/mail_account/table.py
from proxy.entities.account import AccountsTable
from proxy.sql import Integer, String


class MailAccountsTable(AccountsTable):
    """Mail account with SMTP-specific fields."""

    def configure(self) -> None:
        """Add SMTP fields to base account schema."""
        super().configure()
        c = self.columns
        c.column("host", String, nullable=False)
        c.column("port", Integer, nullable=False)
        c.column("user", String)
        c.column("password", String, encrypted=True)
        c.column("use_tls", Integer, default=1)
        c.column("timeout", Integer, default=30)
```

### Extending Endpoints

```python
# my_mail_proxy/entities/mail_account/endpoint.py
from proxy.entities.account import AccountEndpoint
from proxy.interface import POST


class MailAccountEndpoint(AccountEndpoint):
    """Mail account endpoint with SMTP parameters."""

    @POST
    async def add(
        self,
        id: str,
        tenant_id: str,
        host: str,
        port: int,
        user: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: int = 30,
    ) -> dict:
        """Add SMTP account configuration."""
        data = {k: v for k, v in locals().items() if k != "self"}
        await self.table.add(data)
        return await self.table.get(tenant_id, id)

    @POST
    async def test_connection(self, tenant_id: str, account_id: str) -> dict:
        """Test SMTP connection to account server."""
        account = await self.table.get(tenant_id, account_id)
        # Custom logic to test SMTP connection
        return {"status": "ok", "message": f"Connected to {account['host']}"}
```

### Custom Server Entry Point

```python
# my_mail_proxy/server.py
from .proxy import MailProxy, MailProxyConfig

def config_from_env() -> MailProxyConfig:
    import os
    return MailProxyConfig(
        db_path=os.environ.get("MAIL_PROXY_DB", "mail_proxy.db"),
        instance_name=os.environ.get("MAIL_PROXY_INSTANCE", "mail-proxy"),
        smtp_timeout=int(os.environ.get("SMTP_TIMEOUT", "30")),
    )

_proxy = MailProxy(config=config_from_env())
app = _proxy.api.app
```

## API Reference

### Endpoints

All endpoints automatically generate these routes:

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/{endpoint}/list` | List all records |
| GET | `/api/{endpoint}/get` | Get single record |
| POST | `/api/{endpoint}/add` | Create/update record |
| POST | `/api/{endpoint}/delete` | Delete record |

### Built-in Endpoints

- **`/api/instance/`** - Instance metadata
- **`/api/tenants/`** - Tenant management
- **`/api/accounts/`** - Generic account management
- **`/api/storages/`** - Storage configuration

### Response Format

All API responses wrap data in a `data` field:

```json
{
  "data": { ... }
}
```

Errors return:

```json
{
  "error": "Error message or validation details"
}
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GENRO_PROXY_DB` | Database path (SQLite file or PostgreSQL URL) | Required |
| `GENRO_PROXY_INSTANCE` | Instance name | `"proxy"` |
| `GENRO_PROXY_PORT` | Server port | `8000` |
| `GENRO_PROXY_API_TOKEN` | API authentication token | None |

### PostgreSQL Connection

```bash
export GENRO_PROXY_DB="postgresql://user:pass@host:5432/dbname"
```

## Admin UI

The built-in admin UI at `/ui` provides:

- Tenant management (list, add, view details)
- Account management per tenant
- Storage configuration per tenant
- API token configuration

The UI uses [Shoelace](https://shoelace.style/) web components and requires no build step.

## License

Apache License 2.0 - See [LICENSE](LICENSE) for details.

Copyright 2025 Softwell S.r.l.
