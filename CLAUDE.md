# Claude Code Instructions - genro-proxy

**Parent Document**: This project follows all policies from the central [meta-genro-modules CLAUDE.md](https://github.com/softwellsrl/meta-genro-modules/blob/main/CLAUDE.md)

## Project-Specific Context

### Current Status

- Development Status: Beta
- Has Implementation: Yes

### Project Description

Base proxy package for Genro microservices. Provides common infrastructure:

- SQL layer (SqlDb, Table, Column, adapters)
- Storage layer (StorageManager, StorageNode with local + cloud support)
- Tools (encryption, http_client, prometheus, repl)
- Interface (ApiManager, CliManager, BaseEndpoint)
- Base entities (instance, tenant, account, storage, command_log)
- ProxyBase class for building domain-specific proxies
- ProxyEndpoint for server/instance process management

### Architecture Document

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete architecture plan.

---

## Special Commands

### "mostra righe" / "mostra le righe" / "rimetti qui le righe" (show lines)

When the user asks to show code lines:

1. Show **only** the requested code snippet with some context lines
2. Number the lines
3. **DO NOT** add considerations, evaluations, or explanations
4. Copy the code directly into the chat

---

## Critical Safety Rules

### NEVER Remove or Move Files Without Explicit Consent

**RULE**: MAI MAI MAI rimuovere cartelle, spostare documenti o fare `rm -rf` senza consenso esplicito dell'utente.

Prima di qualsiasi operazione distruttiva:
1. **FERMARSI** e chiedere conferma esplicita
2. **ELENCARE** esattamente cosa verrà rimosso/spostato
3. **ASPETTARE** un "sì" o "ok" esplicito

Questo include:
- `rm`, `rm -rf`, `rm -r`
- `mv` di cartelle
- `git clean`
- Qualsiasi comando che elimina o sposta file/cartelle

**NON FARE MAI** assunzioni tipo "sistemo tutto" o "ripristino lo stato originale" che comportano eliminazioni.

---

## SQL Layer Rules

### Type Conversions Are Automatic

**NEVER do manual type conversions when using the SQL layer.**

The SQL layer (Table class) handles all type conversions automatically:
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

---

## Endpoint Decorator

### @endpoint() - Unified Method Configuration

Use the `@endpoint()` decorator to configure endpoint methods:

```python
from genro_proxy.interface import BaseEndpoint, endpoint

class MyEndpoint(BaseEndpoint):
    name = "items"

    # GET method (default)
    async def list(self) -> list[dict]:
        return await self.table.select()

    # POST method
    @endpoint(post=True)
    async def add(self, id: str, name: str) -> dict:
        return await self.table.insert({"id": id, "name": name})

    # CLI-only method (not exposed via API)
    @endpoint(api=False)
    async def serve(self, port: int = 8000) -> dict:
        return {"status": "starting", "port": port}

    # API-only method (not exposed via CLI)
    @endpoint(cli=False)
    async def internal_sync(self) -> dict:
        return {"synced": True}
```

**Decorator parameters:**

- `post=True/False` - HTTP method (default: False = GET)
- `api=True/False` - Expose via REST API (default: True)
- `cli=True/False` - Expose via CLI (default: True)
- `repl=True/False` - Expose via REPL (default: True)

**Class-level defaults:**

```python
class CliOnlyEndpoint(BaseEndpoint):
    name = "tools"
    _default_api = False  # All methods CLI-only by default

    async def cleanup(self) -> dict:
        # This is CLI-only (inherits from class default)
        return {"ok": True}

    @endpoint(api=True)  # Override: also expose via API
    async def status(self) -> dict:
        return {"running": True}
```

---

## ProxyEndpoint

### Subclassing ProxyEndpoint for Custom Commands

`ProxyEndpoint` manages server processes and instances. Subclass it to add custom proxy-level commands:

```python
from genro_proxy import ProxyEndpoint
from genro_proxy.interface import endpoint

class MyProxyEndpoint(ProxyEndpoint):
    name = "myproxy"  # Optional: override name

    @endpoint(api=False)  # CLI-only
    async def init_db(self, force: bool = False) -> dict:
        """Initialize database schema."""
        # Custom initialization logic
        return {"ok": True, "tables_created": 5}

    async def version(self) -> dict:
        """Return proxy version info."""
        return {"version": "1.0.0", "name": "MyProxy"}
```

**Built-in ProxyEndpoint methods:**

- `serve(name, host, port, background)` - Start server instance
- `stop(name, force)` - Stop running instance(s)
- `restart(name, force)` - Restart instance(s)
- `list_instances()` - List all configured instances

---

**All general policies are inherited from the parent document.**
