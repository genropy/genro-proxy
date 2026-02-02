Quickstart
==========

This guide shows how to run the base proxy and use its API.

Running the Server
------------------

Set the database path and start the server:

.. code-block:: bash

    # SQLite (development)
    export GENRO_PROXY_DB=/tmp/proxy.db
    python -m uvicorn proxy.server:app --host 0.0.0.0 --port 8000

    # PostgreSQL (production)
    export GENRO_PROXY_DB="postgresql://user:pass@localhost:5432/proxy"
    python -m uvicorn proxy.server:app --host 0.0.0.0 --port 8000

Access points:

- **Admin UI**: http://localhost:8000/ui
- **API**: http://localhost:8000/api/
- **Health check**: http://localhost:8000/health

Using the Admin UI
------------------

Open http://localhost:8000/ui in your browser:

1. The UI shows the tenant list in the sidebar
2. Click **+** to add a new tenant
3. Select a tenant to see its accounts and storages
4. Use **+** buttons to add accounts/storages to the selected tenant

Using the API
-------------

List tenants:

.. code-block:: bash

    curl http://localhost:8000/api/tenants/list

Add a tenant:

.. code-block:: bash

    curl -X POST http://localhost:8000/api/tenants/add \
      -H "Content-Type: application/json" \
      -d '{"id": "acme", "name": "ACME Corp", "active": true}'

Get tenant details:

.. code-block:: bash

    curl "http://localhost:8000/api/tenants/get?tenant_id=acme"

Add an account to a tenant:

.. code-block:: bash

    curl -X POST http://localhost:8000/api/accounts/add \
      -H "Content-Type: application/json" \
      -d '{"tenant_id": "acme", "id": "main", "name": "Main Account"}'

List accounts for a tenant:

.. code-block:: bash

    curl "http://localhost:8000/api/accounts/list?tenant_id=acme"

Using as a Library
------------------

You can use genro-proxy programmatically:

.. code-block:: python

    import asyncio
    from proxy import ProxyBase, ProxyConfigBase

    async def main():
        # Create proxy
        config = ProxyConfigBase(
            db_path="/tmp/proxy.db",
            instance_name="My Proxy"
        )
        proxy = ProxyBase(config=config)
        await proxy.init()

        # Add tenant
        tenants = proxy.endpoints["tenants"]
        await tenants.add(id="acme", name="ACME Corp", active=True)

        # List tenants
        all_tenants = await tenants.list()
        print(f"Found {len(all_tenants)} tenants")

        # Add account
        accounts = proxy.endpoints["accounts"]
        await accounts.add(
            tenant_id="acme",
            id="main",
            name="Main Account",
            config={"custom": "data"}
        )

        await proxy.close()

    asyncio.run(main())

Response Format
---------------

All API responses wrap data in a ``data`` field:

.. code-block:: json

    {
      "data": {
        "id": "acme",
        "name": "ACME Corp",
        "active": true
      }
    }

Errors return an ``error`` field:

.. code-block:: json

    {
      "error": "Tenant 'unknown' not found"
    }

Validation errors (422) return detailed information:

.. code-block:: json

    {
      "error": [
        {
          "loc": ["id"],
          "msg": "Field required",
          "type": "missing"
        }
      ]
    }

Next Steps
----------

- :doc:`architecture` - Understand the component structure
- :doc:`extending/overview` - Build your own domain-specific proxy
