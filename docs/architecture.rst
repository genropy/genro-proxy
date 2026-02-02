Architecture
============

This document describes the component architecture of genro-proxy.

Overview
--------

genro-proxy is organized into four main layers:

.. code-block:: text

    ┌─────────────────────────────────────────────────────────┐
    │                    Interface Layer                       │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
    │  │ FastAPI  │  │  Click   │  │  Admin   │              │
    │  │  Routes  │  │   CLI    │  │   UI     │              │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
    │       │             │             │                     │
    │       └─────────────┼─────────────┘                     │
    │                     ▼                                   │
    │            ┌────────────────┐                           │
    │            │   Endpoints    │ ◄── Pydantic validation   │
    │            └────────┬───────┘                           │
    └─────────────────────┼───────────────────────────────────┘
                          │
    ┌─────────────────────┼───────────────────────────────────┐
    │                     ▼                                   │
    │            ┌────────────────┐                           │
    │            │    Tables      │ ◄── JSON/encryption       │
    │            └────────┬───────┘                           │
    │                     │           Entity Layer            │
    └─────────────────────┼───────────────────────────────────┘
                          │
    ┌─────────────────────┼───────────────────────────────────┐
    │                     ▼                                   │
    │            ┌────────────────┐                           │
    │            │     SqlDb      │                           │
    │            └────────┬───────┘                           │
    │                     │                                   │
    │       ┌─────────────┴─────────────┐                     │
    │       ▼                           ▼                     │
    │  ┌─────────┐               ┌────────────┐              │
    │  │ SQLite  │               │ PostgreSQL │   SQL Layer   │
    │  └─────────┘               └────────────┘              │
    └─────────────────────────────────────────────────────────┘

Components
----------

ProxyBase
^^^^^^^^^

The main orchestrator class that:

- Creates and configures the database (SqlDb)
- Registers entity tables
- Creates endpoint instances
- Provides API and CLI managers

.. code-block:: python

    from proxy import ProxyBase, ProxyConfigBase

    config = ProxyConfigBase(db_path="proxy.db", instance_name="my-proxy")
    proxy = ProxyBase(config=config)
    await proxy.init()

    # Access components
    proxy.db          # SqlDb instance
    proxy.endpoints   # Dict of endpoint instances
    proxy.api         # ApiManager (FastAPI)
    proxy.cli         # CliManager (Click)

SqlDb
^^^^^

Database manager that:

- Manages table registration
- Handles schema creation and migration
- Provides the appropriate adapter (SQLite or PostgreSQL)

.. code-block:: python

    from proxy.sql import SqlDb

    db = SqlDb("proxy.db")  # or PostgreSQL URL
    await db.init()

    # Access tables
    tenants_table = db.tables["tenants"]
    await tenants_table.select()

Table
^^^^^

Base class for database tables with:

- Column definitions with type checking
- JSON encoding/decoding for complex fields
- Field encryption for sensitive data
- Async context manager for record updates

.. code-block:: python

    from proxy.sql import Table, String, Integer

    class MyTable(Table):
        name = "my_table"
        pkey = "id"

        def configure(self):
            c = self.columns
            c.column("id", String)
            c.column("data", String, json_encoded=True)
            c.column("secret", String, encrypted=True)

BaseEndpoint
^^^^^^^^^^^^

Base class for REST endpoints that:

- Defines async methods for CRUD operations
- Provides ``invoke()`` for unified Pydantic validation
- Marks POST methods with ``@POST`` decorator
- Returns methods via ``get_methods()`` for auto-registration

.. code-block:: python

    from proxy.interface import BaseEndpoint, POST

    class MyEndpoint(BaseEndpoint):
        name = "items"

        async def list(self) -> list[dict]:
            return await self.table.select()

        @POST
        async def add(self, id: str, name: str) -> dict:
            await self.table.insert({"id": id, "name": name})
            return await self.table.select_one(where={"id": id})

ApiManager
^^^^^^^^^^

Creates FastAPI application with:

- Automatic route generation from endpoints
- Health endpoint at ``/health``
- Admin UI at ``/ui``
- Lifespan management (init/close)

CliManager
^^^^^^^^^^

Creates Click CLI application with:

- Automatic command generation from endpoints
- Context management for tenant selection
- ``serve`` command for running the server

Data Flow
---------

Request flow through the system:

1. **API Request** arrives at FastAPI route
2. **Route handler** extracts parameters from body/query
3. **Endpoint.invoke()** validates with Pydantic model
4. **Endpoint method** executes business logic
5. **Table methods** perform database operations
6. **Adapter** executes SQL against database
7. **Response** is returned wrapped in ``{"data": ...}``

The same flow applies to CLI:

1. **CLI Command** parses arguments with Click
2. **Command handler** collects kwargs
3. **Endpoint.invoke()** validates with Pydantic model
4. (rest is the same)

Built-in Entities
-----------------

genro-proxy provides these entities:

**Instance**
    Metadata about the proxy instance (name, version).

**Tenant**
    Multi-tenant container with activation status.

**Account**
    Generic account configuration (id, name, config JSON).

**Storage**
    Storage configuration (protocol, config JSON).

Each entity has a Table class and an Endpoint class that can be
extended for domain-specific needs.

Extension Points
----------------

To create a domain-specific proxy:

1. **Subclass ProxyBase** to add custom initialization
2. **Subclass Table classes** to add domain-specific columns
3. **Subclass Endpoint classes** to add domain-specific methods
4. **Override _configure_db()** to register custom tables
5. **Override _register_endpoints()** to use custom endpoints

See :doc:`extending/overview` for detailed instructions.
