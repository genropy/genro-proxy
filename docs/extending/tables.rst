Extending Tables
================

This guide covers how to extend base tables with domain-specific columns.

Table Basics
------------

Tables in genro-proxy:

- Define database schema via ``configure()``
- Provide CRUD operations (select, insert, update, delete)
- Handle JSON encoding/decoding automatically
- Support field encryption

Base Table Structure
--------------------

The base ``AccountsTable`` provides:

.. code-block:: python

    class AccountsTable(Table):
        name = "accounts"
        pkey = "pk"

        def configure(self) -> None:
            c = self.columns
            c.column("pk", String)           # UUID primary key
            c.column("id", String)           # Business identifier
            c.column("tenant_id", String)    # FK to tenants
            c.column("name", String)         # Display name
            c.column("config", String, json_encoded=True, encrypted=True)
            c.column("created_at", Timestamp)
            c.column("updated_at", Timestamp)

Adding Columns
--------------

To add domain-specific columns, override ``configure()`` and call super:

.. code-block:: python

    from proxy.entities.account import AccountsTable
    from proxy.sql import Integer, String, Timestamp


    class MyAccountsTable(AccountsTable):
        \"\"\"Account with custom fields.\"\"\"

        def configure(self) -> None:
            # Keep base columns
            super().configure()

            # Add custom columns
            c = self.columns
            c.column("host", String, nullable=False)
            c.column("port", Integer, nullable=False)
            c.column("last_used", Timestamp)

Column Types
------------

Available column types:

.. code-block:: python

    from proxy.sql import String, Integer, Timestamp

    c.column("name", String)                    # TEXT
    c.column("count", Integer)                  # INTEGER
    c.column("created", Timestamp)              # TIMESTAMP
    c.column("amount", Integer)                 # Use Integer for decimals too

Column Options
--------------

.. code-block:: python

    # Required field
    c.column("host", String, nullable=False)

    # With default value
    c.column("port", Integer, default=587)

    # JSON-encoded (auto serialize/deserialize)
    c.column("metadata", String, json_encoded=True)

    # Encrypted at rest
    c.column("password", String, encrypted=True)

    # Both JSON and encrypted
    c.column("secrets", String, json_encoded=True, encrypted=True)

    # Foreign key relation
    c.column("tenant_id", String).relation("tenants", sql=True)

Overriding Methods
------------------

You can override table methods for custom logic:

.. code-block:: python

    class MyAccountsTable(AccountsTable):

        async def add(self, data: dict) -> str:
            \"\"\"Custom add with validation.\"\"\"
            # Custom validation
            if data.get("port", 0) < 1:
                raise ValueError("Port must be positive")

            # Add timestamp
            data["last_used"] = None

            # Call parent
            return await super().add(data)

        async def get(self, tenant_id: str, account_id: str) -> dict:
            \"\"\"Get with computed fields.\"\"\"
            account = await super().get(tenant_id, account_id)

            # Add computed field
            account["connection_string"] = (
                f"{account['host']}:{account['port']}"
            )

            return account

Custom Queries
--------------

For complex queries, use the adapter directly:

.. code-block:: python

    class MyAccountsTable(AccountsTable):

        async def list_active(self, tenant_id: str) -> list[dict]:
            \"\"\"List only active accounts.\"\"\"
            return await self.select(
                where={"tenant_id": tenant_id, "active": 1},
                order_by="name"
            )

        async def count_by_tenant(self) -> list[dict]:
            \"\"\"Count accounts per tenant.\"\"\"
            query = '''
                SELECT tenant_id, COUNT(*) as count
                FROM accounts
                GROUP BY tenant_id
            '''
            return await self.db.adapter.fetch_all(query)

Schema Migration
----------------

When you add columns to an existing table:

1. **New deployments**: Columns are created automatically
2. **Existing deployments**: Use ``sync_schema()`` for ALTER TABLE

.. code-block:: python

    class MyAccountsTable(AccountsTable):

        async def sync_schema(self) -> None:
            \"\"\"Add missing columns to existing table.\"\"\"
            await super().sync_schema()

            # Add columns that might be missing
            await self.add_column_if_missing("host")
            await self.add_column_if_missing("port")

The ``sync_schema()`` is called during ``proxy.init()`` if the table exists.

Record Context Manager
----------------------

For atomic updates, use the record context manager:

.. code-block:: python

    async def update_last_used(self, tenant_id: str, account_id: str) -> None:
        \"\"\"Update last_used timestamp atomically.\"\"\"
        async with self.record(
            {"tenant_id": tenant_id, "id": account_id}
        ) as rec:
            if rec:
                rec["last_used"] = datetime.now().isoformat()

    async def upsert(self, data: dict) -> str:
        \"\"\"Insert or update.\"\"\"
        async with self.record(
            {"tenant_id": data["tenant_id"], "id": data["id"]},
            insert_missing=True
        ) as rec:
            if "pk" not in rec:
                rec["pk"] = get_uuid()
            rec["host"] = data["host"]
            rec["port"] = data["port"]
            return rec["pk"]

Testing Tables
--------------

.. code-block:: python

    import pytest
    from proxy.sql import SqlDb

    @pytest.fixture
    async def db():
        db = SqlDb(":memory:")  # In-memory SQLite
        db.add_table(MyAccountsTable)
        await db.init()
        yield db
        await db.close()

    async def test_add_account(db):
        table = db.tables["accounts"]
        pk = await table.add({
            "tenant_id": "test",
            "id": "main",
            "host": "smtp.example.com",
            "port": 587
        })
        assert pk is not None

        account = await table.get("test", "main")
        assert account["host"] == "smtp.example.com"
