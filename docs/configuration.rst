Configuration
=============

This guide covers configuration options for genro-proxy.

Environment Variables
---------------------

genro-proxy uses environment variables for configuration:

.. list-table::
   :header-rows: 1
   :widths: 30 50 20

   * - Variable
     - Description
     - Default
   * - ``GENRO_PROXY_DB``
     - Database path (SQLite file) or PostgreSQL URL
     - Required
   * - ``GENRO_PROXY_INSTANCE``
     - Instance name for display
     - ``"proxy"``
   * - ``GENRO_PROXY_PORT``
     - Server port (used by CLI serve)
     - ``8000``
   * - ``GENRO_PROXY_API_TOKEN``
     - API authentication token
     - None (no auth)

Database Configuration
----------------------

SQLite (Development)
^^^^^^^^^^^^^^^^^^^^

For development, use a file path:

.. code-block:: bash

    export GENRO_PROXY_DB=/path/to/proxy.db

Or in-memory for testing:

.. code-block:: bash

    export GENRO_PROXY_DB=":memory:"

PostgreSQL (Production)
^^^^^^^^^^^^^^^^^^^^^^^

For production, use a PostgreSQL URL:

.. code-block:: bash

    export GENRO_PROXY_DB="postgresql://user:password@host:5432/database"

With connection options:

.. code-block:: bash

    export GENRO_PROXY_DB="postgresql://user:pass@host:5432/db?sslmode=require"

PostgreSQL requires the extra dependency:

.. code-block:: bash

    pip install genro-proxy[postgresql]

Programmatic Configuration
--------------------------

For custom proxies, use ProxyConfigBase:

.. code-block:: python

    from proxy import ProxyBase, ProxyConfigBase

    config = ProxyConfigBase(
        db_path="/data/proxy.db",
        instance_name="my-proxy",
        port=8080,
    )
    proxy = ProxyBase(config=config)

Extending Configuration
-----------------------

Create custom config classes for domain-specific settings:

.. code-block:: python

    from proxy import ProxyConfigBase


    class MyProxyConfig(ProxyConfigBase):
        \"\"\"Custom configuration.\"\"\"

        # Custom settings
        custom_timeout: int = 30
        custom_retries: int = 3
        custom_feature: bool = False


    # Load from environment
    def config_from_env() -> MyProxyConfig:
        import os
        return MyProxyConfig(
            db_path=os.environ["MY_PROXY_DB"],
            instance_name=os.environ.get("MY_PROXY_INSTANCE", "my-proxy"),
            custom_timeout=int(os.environ.get("CUSTOM_TIMEOUT", "30")),
        )

Encryption Key
--------------

For field encryption (passwords, secrets), set:

.. code-block:: bash

    export GENRO_PROXY_ENCRYPTION_KEY="your-32-byte-encryption-key"

If not set, a default key is used (not secure for production).

Generate a secure key:

.. code-block:: python

    import secrets
    print(secrets.token_hex(16))

Logging
-------

genro-proxy uses standard Python logging. Configure via:

.. code-block:: python

    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

Or with uvicorn:

.. code-block:: bash

    uvicorn proxy.server:app --log-level info

Production Recommendations
--------------------------

For production deployments:

1. **Use PostgreSQL** - More robust than SQLite
2. **Set encryption key** - Don't use default key
3. **Use HTTPS** - Put behind a reverse proxy (nginx, traefik)
4. **Set API token** - Protect the admin API
5. **Enable logging** - Monitor for errors

Example docker-compose:

.. code-block:: yaml

    version: "3.8"
    services:
      proxy:
        image: genro-proxy:latest
        environment:
          - GENRO_PROXY_DB=postgresql://user:pass@db:5432/proxy
          - GENRO_PROXY_INSTANCE=production
          - GENRO_PROXY_ENCRYPTION_KEY=${ENCRYPTION_KEY}
          - GENRO_PROXY_API_TOKEN=${API_TOKEN}
        ports:
          - "8000:8000"
        depends_on:
          - db

      db:
        image: postgres:15
        environment:
          - POSTGRES_USER=user
          - POSTGRES_PASSWORD=pass
          - POSTGRES_DB=proxy
        volumes:
          - pgdata:/var/lib/postgresql/data

    volumes:
      pgdata:
