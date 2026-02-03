# genro-proxy - Architecture Plan

**Version**: 0.1.0
**Status**: 🔴 DA REVISIONARE
**Last Updated**: 2026-02-02

---

## Obiettivo

Creare `genro-proxy` come package base che contenga tutto il codice comune tra i proxy Genro (mail-proxy, wopi, futuri).

---

## Dipendenze Risultanti

```
genro-proxy          ← package base (Apache 2.0, nessuna dipendenza genro-*)
    ↑
    ├── genro-mail-proxy    ← dipende da genro-proxy, aggiunge smtp/email
    └── genro-wopi          ← dipende da genro-proxy, aggiunge wopi/sessions
```

---

## Struttura Target

```
genro-proxy/src/proxy/
├── __init__.py
├── py.typed
├── proxy_base.py          # ProxyBase class
├── proxy_config.py        # ProxyConfigBase dataclass
├── sql/                   # Layer database completo
│   ├── __init__.py
│   ├── sqldb.py           # SqlDb manager
│   ├── table.py           # Table base class
│   ├── column.py          # Column definitions
│   └── adapters/
│       ├── __init__.py
│       ├── base.py        # Abstract adapter
│       ├── sqlite.py      # SQLite implementation
│       └── postgresql.py  # PostgreSQL implementation
├── storage/               # Layer storage completo (include cloud - Apache 2.0)
│   ├── __init__.py
│   ├── manager.py         # StorageManager
│   └── node.py            # StorageNode (local + s3/gcs/azure)
├── tools/                 # Utilities
│   ├── __init__.py
│   ├── encryption.py      # AES-256-GCM
│   ├── repl.py            # Interactive REPL
│   ├── http_client/
│   │   ├── __init__.py
│   │   └── client.py      # Async HTTP client
│   └── prometheus/
│       ├── __init__.py
│       └── metrics.py     # Prometheus metrics base
├── interface/             # API/CLI base
│   ├── __init__.py
│   ├── api_base.py        # FastAPI factory
│   ├── cli_base.py        # Click CLI factory
│   ├── cli_context.py     # CLI context resolution (instance/tenant)
│   └── endpoint_base.py   # BaseEndpoint class
└── entities/              # Entità base
    ├── __init__.py
    ├── instance/
    │   ├── __init__.py
    │   ├── table.py       # InstanceTableBase
    │   └── endpoint.py    # InstanceEndpointBase
    ├── tenant/
    │   ├── __init__.py
    │   ├── table.py       # TenantsTableBase
    │   └── endpoint.py    # TenantEndpointBase
    ├── account/
    │   ├── __init__.py
    │   ├── table.py       # AccountsTableBase
    │   └── endpoint.py    # AccountEndpointBase
    ├── storage/
    │   ├── __init__.py
    │   ├── table.py       # StoragesTableBase
    │   └── endpoint.py    # StorageEndpointBase
    └── command_log/
        ├── __init__.py
        ├── table.py       # CommandLogTable (completo)
        └── endpoint.py    # CommandLogEndpoint (completo)
```

---

## Componenti da Estrarre

### 1. sql/ - Layer Database

**Sorgente**: `genro-mail-proxy/src/sql/`
**Destinazione**: `genro-proxy/src/proxy/sql/`

Copiare integralmente:
- `sqldb.py` - SqlDb manager con registry, autodiscovery, schema management
- `table.py` - Table base con CRUD async, triggers, encryption, JSON encoding
- `column.py` - Column, Columns, tipi SQL
- `adapters/` - SQLite e PostgreSQL

---

### 2. storage/ - Layer Storage (INCLUDE CLOUD)

**Sorgente**:
- `genro-mail-proxy/src/storage/` (CE)
- `genro-mail-proxy/src/enterprise/mail_proxy/storage/` (EE → diventa CE in proxy)

**Destinazione**: `genro-proxy/src/proxy/storage/`

**IMPORTANTE**: Il supporto cloud (S3, GCS, Azure) che in mail-proxy è EE diventa parte base di genro-proxy con licenza Apache 2.0.

Contenuto finale:
- `manager.py` - StorageManager con mount points, URL parsing (local, s3://, gs://, az://)
- `node.py` - StorageNode completo con:
  - I/O locale (filesystem)
  - I/O cloud (S3, GCS, Azure via fsspec)
  - URL con token firmati HMAC-SHA256

---

### 3. tools/ - Utilities

**Sorgente**: `genro-mail-proxy/src/tools/`
**Destinazione**: `genro-proxy/src/proxy/tools/`

Copiare integralmente:
- `encryption.py` - AES-256-GCM per field encryption
- `repl.py` - REPL interattivo
- `http_client/client.py` - Client HTTP asincrono
- `prometheus/metrics.py` - Metriche Prometheus base

---

### 4. interface/ - API e CLI Base

**Sorgente**: `genro-mail-proxy/src/core/mail_proxy/interface/`
**Destinazione**: `genro-proxy/src/proxy/interface/`

Copiare e generalizzare:
- `api_base.py` → `ApiBase` con parametri configurabili (app_name, ecc.)
- `cli_base.py` → `CliBase` con parametri configurabili
- `endpoint_base.py` → `BaseEndpoint` con autodiscovery parametrizzato

---

### 5. ProxyBase e ProxyConfig

#### ProxyConfigBase

```python
@dataclass
class ProxyConfigBase:
    """Configurazione base per tutti i proxy."""
    db_path: str = "service.db"
    instance_name: str = "proxy"
    port: int = 8000
    api_token: str | None = None
    test_mode: bool = False
    start_active: bool = True
```

#### ProxyBase

```python
class ProxyBase:
    """Classe base per tutti i proxy Genro."""

    config: ProxyConfigBase
    db: SqlDb
    endpoints: dict[str, BaseEndpoint]

    # Configurazione estensione
    entity_packages: list[str]      # Package dove cercare entities
    encryption_key_env: str         # Nome env var per chiave encryption

    # Properties lazy
    @property
    def api(self) -> FastAPI: ...

    @property
    def cli(self) -> click.Group: ...

    # Lifecycle
    async def init(self) -> None: ...
    async def close(self) -> None: ...

    # Autodiscovery CE/EE
    def _discover_tables(self) -> None: ...
    def _discover_endpoints(self) -> None: ...
```

---

## Entities Base - Schema Colonne

### InstanceTableBase

| Colonna | Tipo | Note |
|---------|------|------|
| `id` | INTEGER | PK, sempre 1 (singleton) |
| `name` | STRING | Nome istanza |
| `api_token` | STRING | Token autenticazione |
| `edition` | STRING | "ce" o "ee" |
| `config` | STRING (JSON) | Configurazione flessibile |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Metodi base**: `get_instance()`, `ensure_instance()`, `get_config()`, `set_config()`

---

### TenantsTableBase

| Colonna | Tipo | Note |
|---------|------|------|
| `id` | STRING | PK, tenant identifier |
| `name` | STRING | Display name |
| `client_auth` | STRING (JSON) | Auth per callbacks |
| `client_base_url` | STRING | Base URL callbacks |
| `config` | STRING (JSON) | Configurazione flessibile |
| `active` | INTEGER | 0/1 status |
| `api_key_hash` | STRING | SHA256 hash API key |
| `api_key_expires_at` | TIMESTAMP | Scadenza API key |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Metodi base**: `get()`, `add()`, `remove()`, `list_all()`, `update_fields()`, `ensure_default()`, `create_api_key()`, `get_tenant_by_token()`

---

### AccountsTableBase

| Colonna | Tipo | Note |
|---------|------|------|
| `pk` | STRING | UUID primary key |
| `id` | STRING | Client account ID |
| `tenant_id` | STRING | FK → tenants |
| `name` | STRING | Display name |
| `config` | STRING (JSON) | Configurazione flessibile |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Metodi base**: `get()`, `add()`, `remove()`, `list_all()`

---

### StoragesTableBase

| Colonna | Tipo | Note |
|---------|------|------|
| `pk` | STRING | UUID primary key |
| `tenant_id` | STRING | FK → tenants |
| `name` | STRING | Storage name |
| `protocol` | STRING | "local", "s3", "gcs", "azure" |
| `config` | STRING (JSON, encrypted) | Config specifico protocollo |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Constraint**: UNIQUE(tenant_id, name)

**Metodi base**: `get()`, `add()`, `remove()`, `list_all()`, `get_storage_manager()`

---

### CommandLogTable (completo)

| Colonna | Tipo | Note |
|---------|------|------|
| `id` | INTEGER | PK auto-increment |
| `command_ts` | INTEGER | Unix timestamp |
| `endpoint` | STRING | HTTP method + path |
| `tenant_id` | STRING | Tenant context |
| `payload` | STRING (JSON) | Request body |
| `response_status` | INTEGER | HTTP status |
| `response_body` | STRING (JSON) | Response summary |

**Metodi**: `log_command()`, `list_commands()`, `get_command()`, `export_commands()`, `purge_before()`

---

## Pattern Ereditarietà

### Table (colonne)

```python
# genro-proxy: base
class AccountsTableBase(Table):
    table_name = "accounts"
    columns = Columns(
        pk=Column(String, primary_key=True),
        id=Column(String),
        tenant_id=Column(String).relation("tenants.id"),
        name=Column(String),
        config=Column(String, json_encoded=True),
        created_at=Column(Timestamp),
        updated_at=Column(Timestamp),
    )

# mail-proxy: estende con colonne SMTP
class AccountsTable(AccountsTableBase):
    columns = AccountsTableBase.columns + Columns(
        host=Column(String),
        port=Column(Integer),
        user=Column(String),
        password=Column(String, encrypted=True),
        use_tls=Column(Integer),
        active=Column(Integer, default=1),  # mail-specific: enable/disable account
        limit_per_minute=Column(Integer),
        # ... altre colonne SMTP
    )
```

### Endpoint (API + CLI)

```python
# genro-proxy: base
class AccountEndpointBase(BaseEndpoint):
    entity_name = "accounts"
    # CRUD base: GET, POST, DELETE
    # CLI: list, add, remove

# mail-proxy: estende
class AccountEndpoint(AccountEndpointBase):
    # Aggiunge: test-connection, rate-status
```

---

## Fasi di Implementazione

| Fase | Descrizione | Stima |
|------|-------------|-------|
| **1. Setup** | Creare repo con struttura base, pyproject.toml | Rapido |
| **2. Estrazione core** | Copiare sql/, storage/ (con cloud), tools/ | Rapido |
| **3. Interface** | Copiare e generalizzare api_base, cli_base, endpoint_base | Medio |
| **4. Entities base** | Creare versioni base delle 5 entities | Medio |
| **5. ProxyBase** | Generalizzare proxy_base.py e proxy_config.py | Medio |
| **6. Test** | Test unitari per genro-proxy | Medio |
| **7. Migrazione mail-proxy** | Rimuovere duplicati, dipendenza da genro-proxy | Medio-lungo |
| **8. Migrazione wopi** | Rimuovere duplicati, dipendenza da genro-proxy | Rapido |

---

## Note Licenza

- **genro-proxy**: Apache 2.0 (tutto il codice, incluso storage cloud)
- **genro-mail-proxy**: Dual license (CE Apache / EE BSL) - solo per features email enterprise
- **genro-wopi**: Dual license (CE Apache / EE BSL) - solo per features WOPI enterprise

Il supporto storage cloud (S3, GCS, Azure) è parte del proxy base con Apache 2.0.

---

## Dipendenze Python

```toml
dependencies = [
    "aiosqlite>=0.20.0",
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
    "pydantic>=2.8.0",
    "click>=8.1.0",
    "rich>=13.0.0",
    "prometheus-client>=0.20.0",
    "cryptography>=41.0.0",
]

[project.optional-dependencies]
postgresql = ["psycopg[binary]>=3.1.0", "psycopg-pool>=3.1.0"]
s3 = ["s3fs>=2024.1.0"]
gcs = ["gcsfs>=2024.1.0"]
azure = ["adlfs>=2024.1.0"]
cloud = ["genro-proxy[s3,gcs,azure]"]
all = ["genro-proxy[postgresql,cloud]"]
```
