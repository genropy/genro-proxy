# SQL Subsystem

Async SQL layer with adapter pattern, table registration, and transaction support.

## Overview

The SQL subsystem provides a lightweight ORM-like interface for SQLite and PostgreSQL with:

- **Adapter Pattern**: Unified interface for different databases
- **Table Registration**: Schema definition with automatic migration
- **Transaction Support**: Connection-per-transaction with automatic commit/rollback
- **CRUD Helpers**: High-level methods for common operations
- **Encryption**: Field-level encryption for sensitive data
- **JSON Encoding**: Automatic JSON serialization for complex fields

## Architecture

```
sql/
├── __init__.py          # Package exports
├── sqldb.py             # SqlDb: Database manager with transaction support
├── table.py             # Table: Base class with CRUD and hooks
├── column.py            # Column/Columns: Schema definition
└── adapters/
    ├── __init__.py      # Adapter registry and factory
    ├── base.py          # DbAdapter: Abstract base class
    ├── sqlite.py        # SqliteAdapter: SQLite implementation
    └── postgresql.py    # PostgresAdapter: PostgreSQL implementation
```

## Transaction Model

The SQL layer uses a **connection-per-transaction** model:

```
connect()  → Acquires connection + BEGIN (implicit)
... N operations on same connection ...
close()    → COMMIT + releases connection
rollback() → ROLLBACK + releases connection
shutdown() → Closes pool/file (application shutdown only)
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `connect()` | Acquire connection, begin transaction |
| `close()` | COMMIT and release connection |
| `commit()` | COMMIT without releasing (explicit mid-transaction) |
| `rollback()` | ROLLBACK and release connection |
| `shutdown()` | Close pool (PostgreSQL) or file (SQLite) |
| `connection()` | Context manager for automatic commit/rollback |

### Why This Model?

1. **Atomicity**: Multiple operations either all succeed or all fail
2. **Consistency**: No partial updates on error
3. **Resource Management**: Connections properly released
4. **Simplicity**: Context manager handles commit/rollback automatically

## Usage

### SqlDb with Context Manager (Recommended)

```python
from proxy.sql import SqlDb, Table, String, Integer

class UsersTable(Table):
    name = "users"
    pkey = "id"

    def configure(self):
        self.columns.column("id", String)
        self.columns.column("name", String)
        self.columns.column("active", Integer, default=1)

# Initialize
db = SqlDb("/data/app.db")
await db.connect()
db.add_table(UsersTable)
await db.check_structure()
await db.close()  # COMMIT schema

# Operations with automatic commit/rollback
async with db.connection():
    await db.table("users").insert({"id": "u1", "name": "Alice"})
    await db.table("users").update({"active": 0}, where={"id": "u1"})
# COMMIT on success, ROLLBACK on exception

# Application shutdown
await db.shutdown()
```

### Adapter Direct Usage

```python
from proxy.sql.adapters import get_adapter

adapter = get_adapter("postgresql://user:pass@localhost/db")
await adapter.connect()
try:
    await adapter.execute("INSERT INTO users (id) VALUES (:id)", {"id": "u1"})
    await adapter.execute("UPDATE users SET active = 1 WHERE id = :id", {"id": "u1"})
    await adapter.close()  # COMMIT
except Exception:
    await adapter.rollback()  # ROLLBACK
    raise
```

### Table Operations

```python
table = db.table("users")

# CRUD operations
await table.insert({"id": "u1", "name": "Alice"})
users = await table.select(where={"active": 1})
user = await table.select_one(where={"id": "u1"})
await table.update({"active": 0}, where={"id": "u1"})
await table.delete(where={"id": "u1"})

# Utilities
exists = await table.exists(where={"id": "u1"})
count = await table.count(where={"active": 1})

# Record context manager (upsert pattern)
async with table.record("u1", insert_missing=True) as rec:
    rec["name"] = "Alice"
    rec["active"] = 1
# Automatically inserts or updates
```

## Query Builder (Fluent API)

The `query()` method provides a fluent API similar to the old Genropy ORM.

### Simple Queries (dict WHERE)

```python
# Dict = AND with equality
rows = await table.query(where={"active": True}).fetch()
row = await table.query(where={"id": "u1"}).fetch_one()
count = await table.query(where={"status": "active"}).count()
exists = await table.query(where={"email": "test@example.com"}).exists()

# With ordering and pagination
rows = await table.query(
    where={"active": True},
    order_by="created_at DESC",
    limit=10,
    offset=20
).fetch()
```

### Advanced Queries (Named Conditions + Expression)

For complex WHERE clauses, use named conditions with a logical expression:

```python
# Named conditions with dict style
rows = await table.query(
    where_a={'column': 'status', 'op': '=', 'value': 'active'},
    where_b={'column': 'name', 'op': 'ILIKE', 'value': ':pattern'},
    where="$a AND $b",
    pattern='%mario%'
).fetch()
# → WHERE (status = 'active') AND (name ILIKE '%mario%')

# Named conditions with flat kwargs style
rows = await table.query(
    where_a_column='status', where_a_op='!=', where_a_value='deleted',
    where_b_column='created_at', where_b_op='>', where_b_value=':since',
    where="$a AND $b",
    since='2024-01-01'
).fetch()

# Complex logical expressions
rows = await table.query(
    where_active={'column': 'status', 'op': '=', 'value': 'active'},
    where_deleted={'column': 'deleted_at', 'op': 'IS NOT NULL'},
    where_admin={'column': 'role', 'op': '=', 'value': 'admin'},
    where="($active AND NOT $deleted) OR $admin"
).fetch()
```

### Condition Structure

Each named condition is a dict with:

```python
{
    'column': 'column_name',   # Required: column to filter
    'op': '=',                 # Optional: operator (default '=')
    'value': 'some_value'      # Required for most operators
}
```

### Supported Operators

| Operator | Example | SQL Generated |
|----------|---------|---------------|
| `=` | `{'column': 'id', 'op': '=', 'value': 'x'}` | `id = 'x'` |
| `!=`, `<>` | `{'column': 'status', 'op': '!=', 'value': 'del'}` | `status != 'del'` |
| `<`, `>`, `<=`, `>=` | `{'column': 'age', 'op': '>', 'value': 18}` | `age > 18` |
| `LIKE` | `{'column': 'name', 'op': 'LIKE', 'value': '%test%'}` | `name LIKE '%test%'` |
| `ILIKE` | `{'column': 'name', 'op': 'ILIKE', 'value': ':pat'}` | `name ILIKE :pat` |
| `IN` | `{'column': 'status', 'op': 'IN', 'value': ['a','b']}` | `status IN ('a','b')` |
| `NOT IN` | `{'column': 'id', 'op': 'NOT IN', 'value': [1,2]}` | `id NOT IN (1,2)` |
| `IS NULL` | `{'column': 'deleted_at', 'op': 'IS NULL'}` | `deleted_at IS NULL` |
| `IS NOT NULL` | `{'column': 'email', 'op': 'IS NOT NULL'}` | `email IS NOT NULL` |
| `BETWEEN` | `{'column': 'age', 'op': 'BETWEEN', 'value': [18,65]}` | `age BETWEEN 18 AND 65` |

### Parameter References

Use `:param_name` in values to reference external parameters:

```python
rows = await table.query(
    where_search={'column': 'name', 'op': 'ILIKE', 'value': ':pattern'},
    where_date={'column': 'created_at', 'op': '>=', 'value': ':since'},
    where="$search AND $date",
    pattern='%test%',    # Referenced by :pattern
    since='2024-01-01'   # Referenced by :since
).fetch()
```

### Expression Syntax

The `where` string supports:

- `$name` → reference to `where_name` condition
- `AND`, `OR` → logical operators
- `NOT` → negation
- `( )` → parentheses for precedence

```python
where="($a AND $b) OR (NOT $c AND $d)"
```

### Query Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `fetch()` | `list[dict]` | All matching rows |
| `fetch_one()` | `dict` or `None` | First matching row |
| `count()` | `int` | Count of matching rows |
| `exists()` | `bool` | True if any row matches |
| `delete(raw=False)` | `int` | Delete matching rows, return count |
| `update(values, raw=False)` | `int` | Update matching rows, return count |

### Delete and Update

The query object can be reused for preview and then mutation:

```python
# Preview what will be deleted
q = table.query(where={'status': 'deleted'})
records = await q.fetch()
print(f"Will delete {len(records)} records")

# Then delete
deleted = await q.delete()

# Or with complex conditions
deleted = await table.query(
    where_old={'column': 'created_at', 'op': '<', 'value': ':threshold'},
    where_inactive={'column': 'active', 'op': '=', 'value': 0},
    where="$old AND $inactive",
    threshold='2024-01-01'
).delete()
```

Update works the same way:

```python
# Preview what will be updated
q = table.query(where={'status': 'pending'})
records = await q.fetch()

# Then update
updated = await q.update({'status': 'processed', 'processed_at': now})

# With complex conditions
updated = await table.query(
    where_inactive={'column': 'last_login', 'op': '<', 'value': ':date'},
    where="$inactive",
    date='2023-01-01'
).update({'status': 'archived'})
```

The `raw=True` parameter bypasses triggers and encoding/encryption for bulk operations:

```python
# Fast bulk delete without triggers
deleted = await table.query(where={'temp': True}).delete(raw=True)

# Fast bulk update without triggers
updated = await table.query(where={'batch_id': 123}).update({'processed': True}, raw=True)
```

## Adapters

### SqliteAdapter

- Uses `aiosqlite` for async operations
- Persistent connection per transaction
- File-based or in-memory (`:memory:`)
- Boolean normalization (0/1 → False/True)

```python
adapter = get_adapter("/data/app.db")
adapter = get_adapter("sqlite::memory:")
```

### PostgresAdapter

- Uses `psycopg3` with connection pooling
- Connection acquired from pool per transaction
- Supports `FOR UPDATE` row locking
- Uses `SERIAL` for autoincrement

```python
adapter = get_adapter("postgresql://user:pass@localhost:5432/mydb")
```

## Connection Strings

| Format | Database |
|--------|----------|
| `/path/to/db.sqlite` | SQLite (absolute path) |
| `./path/to/db.sqlite` | SQLite (relative path) |
| `sqlite:/path/to/db` | SQLite |
| `sqlite::memory:` | SQLite in-memory |
| `postgresql://user:pass@host:port/db` | PostgreSQL |
| `postgres://user:pass@host:port/db` | PostgreSQL (alias) |

## Table Definition

```python
from proxy.sql import Table, String, Integer, Timestamp

class MyTable(Table):
    name = "my_table"           # Table name in database
    pkey = "id"                 # Primary key column (optional)

    def configure(self):
        c = self.columns
        c.column("id", String)
        c.column("name", String, nullable=False)
        c.column("count", Integer, default=0)
        c.column("config", String, json_encoded=True)      # Auto JSON encode/decode
        c.column("secret", String, encrypted=True)         # Field encryption
        c.column("created_at", Timestamp, default="CURRENT_TIMESTAMP")
        c.column("tenant_id", String).relation("tenants")  # Foreign key
```

## Hooks

Tables support hooks for custom logic:

```python
class MyTable(Table):
    def trigger_on_inserting(self, record: dict) -> dict:
        """Called before insert. Can modify record."""
        record["created_at"] = datetime.now()
        return record

    def trigger_on_inserted(self, record: dict) -> None:
        """Called after insert."""
        logger.info(f"Inserted: {record['id']}")

    def trigger_on_updating(self, record: dict, old_record: dict) -> dict:
        """Called before update. Can modify record."""
        record["updated_at"] = datetime.now()
        return record

    def trigger_on_updated(self, record: dict, old_record: dict) -> None:
        """Called after update."""
        pass

    def trigger_on_deleting(self, record: dict) -> None:
        """Called before delete."""
        pass

    def trigger_on_deleted(self, record: dict) -> None:
        """Called after delete."""
        pass
```

## Schema Sync

Tables support automatic schema migration:

```python
# Add new columns to definition
table.columns.column("new_field", String)

# Sync adds missing columns (safe for existing tables)
await table.sync_schema()
```

## Encryption

Field-level encryption requires an encryption key:

```python
# Via environment variable
os.environ["PROXY_ENCRYPTION_KEY"] = "your-32-byte-key-here..."

# Or via parent proxy
proxy = ProxyBase(config)  # Loads key from env
db = proxy.db  # Tables get key via db.encryption_key

# Encrypted fields are automatically encrypted on write, decrypted on read
await table.insert({"id": "1", "secret": "sensitive data"})
record = await table.select_one(where={"id": "1"})
print(record["secret"])  # "sensitive data" (decrypted)
```

## Best Practices

1. **Use context manager** for transactions: `async with db.connection():`
2. **Call shutdown()** on application exit to release resources
3. **Use Table classes** instead of raw adapter for schema management
4. **Define hooks** for audit logging, timestamps, validation
5. **Use record()** context manager for upsert patterns
6. **Encrypt sensitive fields** with `encrypted=True`

## Testing

```bash
# Run all SQL tests
pytest tests/sql/ -v

# Run with PostgreSQL (requires docker-compose up)
pytest tests/sql/ -v -m postgres
```

## Dependencies

- `aiosqlite`: SQLite async support (always installed)
- `psycopg[pool]`: PostgreSQL support (optional)

Install PostgreSQL support:
```bash
pip install genro-proxy[postgresql]
```
