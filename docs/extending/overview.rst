Extending genro-proxy
=====================

This guide explains how to build domain-specific proxies on top of genro-proxy.

Why Extend?
-----------

The base genro-proxy provides:

- Generic multi-tenant infrastructure
- Generic accounts with JSON config
- Generic storages with protocol/config

For domain-specific needs (mail, API gateway, file sync), you extend:

- **Tables** to add domain-specific columns
- **Endpoints** to add domain-specific methods and validation
- **ProxyBase** to orchestrate your custom components

Extension Strategy
------------------

The recommended approach:

1. **Start with base** - Use genro-proxy as-is for prototyping
2. **Identify needs** - What fields/methods does your domain require?
3. **Extend tables** - Add columns for your specific data
4. **Extend endpoints** - Add methods with proper parameters
5. **Extend proxy** - Wire everything together

File Structure
--------------

A typical domain proxy project:

.. code-block:: text

    my-domain-proxy/
    ├── src/
    │   └── my_domain_proxy/
    │       ├── __init__.py
    │       ├── proxy.py           # MyDomainProxy(ProxyBase)
    │       ├── server.py          # ASGI entry point
    │       │
    │       └── entities/
    │           └── account/
    │               ├── __init__.py
    │               ├── table.py   # DomainAccountsTable
    │               └── endpoint.py # DomainAccountEndpoint
    │
    ├── tests/
    ├── ui/                        # Custom UI (optional)
    └── pyproject.toml

Example: Mail Proxy
-------------------

Here's a complete example of extending genro-proxy for email:

**Table extension** (``entities/mail_account/table.py``):

.. code-block:: python

    from proxy.entities.account import AccountsTable
    from proxy.sql import Integer, String


    class MailAccountsTable(AccountsTable):
        \"\"\"SMTP account with mail-specific fields.\"\"\"

        def configure(self) -> None:
            super().configure()
            c = self.columns
            # Add SMTP-specific fields
            c.column("host", String, nullable=False)
            c.column("port", Integer, nullable=False)
            c.column("user", String)
            c.column("password", String, encrypted=True)
            c.column("use_tls", Integer, default=1)
            c.column("timeout", Integer, default=30)
            c.column("batch_size", Integer, default=100)

**Endpoint extension** (``entities/mail_account/endpoint.py``):

.. code-block:: python

    from proxy.entities.account import AccountEndpoint
    from proxy.interface import POST


    class MailAccountEndpoint(AccountEndpoint):
        \"\"\"SMTP account endpoint with connection testing.\"\"\"

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
            \"\"\"Add SMTP account configuration.\"\"\"
            data = {k: v for k, v in locals().items() if k != "self"}
            await self.table.add(data)
            return await self.table.get(tenant_id, id)

        @POST
        async def test_connection(
            self, tenant_id: str, account_id: str
        ) -> dict:
            \"\"\"Test SMTP connection.\"\"\"
            account = await self.table.get(tenant_id, account_id)
            # Your SMTP test logic here
            return {"status": "ok", "host": account["host"]}

**Proxy class** (``proxy.py``):

.. code-block:: python

    from proxy import ProxyBase, ProxyConfigBase
    from proxy.sql import SqlDb

    from .entities.mail_account import MailAccountsTable, MailAccountEndpoint


    class MailProxyConfig(ProxyConfigBase):
        \"\"\"Mail proxy configuration.\"\"\"
        smtp_timeout: int = 30


    class MailProxy(ProxyBase):
        \"\"\"Mail-specific proxy.\"\"\"

        def _configure_db(self, db: SqlDb) -> None:
            super()._configure_db(db)
            # Replace generic accounts table
            db.add_table(MailAccountsTable)

        def _register_endpoints(self) -> None:
            super()._register_endpoints()
            # Replace generic accounts endpoint
            self.endpoints["accounts"] = MailAccountEndpoint(
                self.db.tables["accounts"]
            )

**Server entry point** (``server.py``):

.. code-block:: python

    import os
    from .proxy import MailProxy, MailProxyConfig

    def config_from_env() -> MailProxyConfig:
        return MailProxyConfig(
            db_path=os.environ.get("MAIL_PROXY_DB", "mail.db"),
            instance_name=os.environ.get("MAIL_PROXY_INSTANCE", "mail-proxy"),
        )

    _proxy = MailProxy(config=config_from_env())
    app = _proxy.api.app

**Run it**:

.. code-block:: bash

    MAIL_PROXY_DB=/tmp/mail.db uvicorn my_domain_proxy.server:app

Auto-Generated Features
-----------------------

When you extend an endpoint, these are auto-generated:

**API Routes** (from endpoint methods):

- ``POST /api/accounts/add`` - from ``add()`` method
- ``GET /api/accounts/list`` - from ``list()`` method
- ``GET /api/accounts/get`` - from ``get()`` method
- ``POST /api/accounts/delete`` - from ``delete()`` method
- ``POST /api/accounts/test-connection`` - from ``test_connection()``

**CLI Commands** (from endpoint methods):

.. code-block:: bash

    my-proxy accounts add --tenant-id acme --id main --host smtp.example.com --port 587
    my-proxy accounts list --tenant-id acme
    my-proxy accounts test-connection --tenant-id acme --account-id main

**Pydantic Validation**:

- Method parameters become Pydantic model fields
- Type annotations define validation rules
- Default values are respected
- Validation errors return 422 with details

Best Practices
--------------

1. **Call super() in configure()** - Don't replace base columns
2. **Keep base entity semantics** - Accounts are still accounts
3. **Add domain methods** - Like ``test_connection()`` for mail
4. **Use @POST for mutations** - GET for reads, POST for writes
5. **Return dicts from methods** - They're JSON-serialized automatically

See Also
--------

- :doc:`tables` - Detailed table extension guide
- :doc:`endpoints` - Detailed endpoint extension guide
- :doc:`proxy` - Detailed proxy extension guide
