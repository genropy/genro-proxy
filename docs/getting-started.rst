Getting Started
===============

This guide will help you understand genro-proxy and get it running.

What is genro-proxy?
--------------------

genro-proxy is a **base package** for building Genro microservices. It provides:

- **Multi-tenant architecture**: Tenants, accounts, and storages out of the box
- **Automatic API generation**: FastAPI routes from endpoint methods
- **Automatic CLI generation**: Click commands from endpoint methods
- **Unified validation**: Pydantic validation across API, CLI, and UI
- **Database abstraction**: SQLite and PostgreSQL with async support
- **Admin UI**: Built-in SPA for configuration management

Who should use it?
------------------

genro-proxy is designed for developers who need to build:

- **Proxy services** that mediate between clients and backend systems
- **Multi-tenant microservices** with shared infrastructure
- **Admin APIs** with automatic CRUD operations

It's used as the base for:

- genro-mail-proxy (email dispatcher)
- genro-wopi (Office integration)
- Custom domain-specific proxies

Installation
------------

Basic installation:

.. code-block:: bash

    pip install genro-proxy

With PostgreSQL support:

.. code-block:: bash

    pip install genro-proxy[postgresql]

With cloud storage (S3, GCS, Azure):

.. code-block:: bash

    pip install genro-proxy[cloud]

All extras:

.. code-block:: bash

    pip install genro-proxy[all]

Requirements
------------

- Python 3.11+
- FastAPI
- Click
- Pydantic
- aiosqlite (for SQLite)
- psycopg (for PostgreSQL, optional)

Next Steps
----------

- :doc:`quickstart` - Run the base proxy and explore the API
- :doc:`architecture` - Understand the component structure
- :doc:`extending/overview` - Build your own domain-specific proxy
