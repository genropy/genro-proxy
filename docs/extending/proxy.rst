Extending ProxyBase
===================

This guide covers how to extend ProxyBase for domain-specific proxies.

ProxyBase Overview
------------------

ProxyBase is the main orchestrator that:

- Creates and initializes the database
- Registers tables and endpoints
- Provides API and CLI managers
- Manages lifecycle (init/close)

Subclassing ProxyBase
---------------------

The basic pattern:

.. code-block:: python

    from proxy import ProxyBase, ProxyConfigBase


    class MyProxy(ProxyBase):
        \"\"\"Domain-specific proxy.\"\"\"

        def __init__(self, config: ProxyConfigBase):
            super().__init__(config)
            # Custom initialization

Extension Points
----------------

ProxyBase provides these override points:

``_configure_db(db)``
    Register custom tables before database init.

``_register_endpoints()``
    Create endpoint instances after database init.

``init()``
    Called during startup (after db init).

``close()``
    Called during shutdown.

Custom Configuration
--------------------

Extend ProxyConfigBase for domain-specific settings:

.. code-block:: python

    from proxy import ProxyConfigBase


    class MailProxyConfig(ProxyConfigBase):
        \"\"\"Mail proxy configuration.\"\"\"

        # SMTP settings
        smtp_timeout: int = 30
        smtp_retries: int = 3

        # Queue settings
        queue_batch_size: int = 100
        queue_poll_interval: float = 1.0


    class MailProxy(ProxyBase):

        def __init__(self, config: MailProxyConfig):
            super().__init__(config)
            self.smtp_timeout = config.smtp_timeout

Registering Custom Tables
-------------------------

Override ``_configure_db()`` to register domain tables:

.. code-block:: python

    from proxy.sql import SqlDb
    from .entities.mail_account import MailAccountsTable
    from .entities.mail_queue import MailQueueTable


    class MailProxy(ProxyBase):

        def _configure_db(self, db: SqlDb) -> None:
            \"\"\"Register mail-specific tables.\"\"\"
            # Call parent to register base tables
            super()._configure_db(db)

            # Replace generic accounts with mail-specific
            db.add_table(MailAccountsTable)

            # Add new table
            db.add_table(MailQueueTable)

Registering Custom Endpoints
----------------------------

Override ``_register_endpoints()`` to use custom endpoints:

.. code-block:: python

    from .entities.mail_account import MailAccountEndpoint
    from .entities.mail_queue import MailQueueEndpoint


    class MailProxy(ProxyBase):

        def _register_endpoints(self) -> None:
            \"\"\"Register mail-specific endpoints.\"\"\"
            # Call parent to register base endpoints
            super()._register_endpoints()

            # Replace generic accounts endpoint
            self.endpoints["accounts"] = MailAccountEndpoint(
                self.db.tables["accounts"]
            )

            # Add new endpoint
            self.endpoints["queue"] = MailQueueEndpoint(
                self.db.tables["mail_queue"]
            )

Custom Initialization
---------------------

Override ``init()`` for startup logic:

.. code-block:: python

    class MailProxy(ProxyBase):

        async def init(self) -> None:
            \"\"\"Initialize mail proxy.\"\"\"
            # Call parent (initializes db, endpoints)
            await super().init()

            # Custom initialization
            self._smtp_pool = await create_smtp_pool(
                timeout=self.config.smtp_timeout
            )
            self._worker = asyncio.create_task(self._process_queue())

        async def close(self) -> None:
            \"\"\"Cleanup mail proxy.\"\"\"
            # Stop worker
            if self._worker:
                self._worker.cancel()

            # Close pool
            if self._smtp_pool:
                await self._smtp_pool.close()

            # Call parent (closes db)
            await super().close()

Adding Custom Methods
---------------------

Add proxy-level methods for cross-cutting operations:

.. code-block:: python

    class MailProxy(ProxyBase):

        async def send_email(
            self,
            tenant_id: str,
            account_id: str,
            to: str,
            subject: str,
            body: str
        ) -> dict:
            \"\"\"High-level email send operation.\"\"\"
            # Get account
            account = await self.endpoints["accounts"].get(
                tenant_id, account_id
            )

            # Add to queue
            return await self.endpoints["queue"].add(
                tenant_id=tenant_id,
                account_id=account_id,
                to=to,
                subject=subject,
                body=body
            )

        async def get_queue_stats(self, tenant_id: str) -> dict:
            \"\"\"Get queue statistics for a tenant.\"\"\"
            queue = self.endpoints["queue"]
            return {
                "pending": await queue.count_pending(tenant_id),
                "sent": await queue.count_sent(tenant_id),
                "failed": await queue.count_failed(tenant_id),
            }

Server Entry Point
------------------

Create a server module for uvicorn:

.. code-block:: python

    # my_mail_proxy/server.py
    import os
    from .proxy import MailProxy, MailProxyConfig


    def config_from_env() -> MailProxyConfig:
        \"\"\"Load configuration from environment.\"\"\"
        return MailProxyConfig(
            db_path=os.environ.get("MAIL_PROXY_DB", "mail.db"),
            instance_name=os.environ.get("MAIL_PROXY_INSTANCE", "mail"),
            smtp_timeout=int(os.environ.get("SMTP_TIMEOUT", "30")),
        )


    _proxy = MailProxy(config=config_from_env())
    app = _proxy.api.app

Run with:

.. code-block:: bash

    MAIL_PROXY_DB=/data/mail.db uvicorn my_mail_proxy.server:app

CLI Entry Point
---------------

Create a CLI entry point:

.. code-block:: python

    # my_mail_proxy/__main__.py
    from .server import _proxy


    def main():
        _proxy.cli.cli()


    if __name__ == "__main__":
        main()

In ``pyproject.toml``:

.. code-block:: toml

    [project.scripts]
    mail-proxy = "my_mail_proxy.__main__:main"

Testing the Proxy
-----------------

.. code-block:: python

    import pytest
    from my_mail_proxy import MailProxy, MailProxyConfig


    @pytest.fixture
    async def proxy():
        config = MailProxyConfig(
            db_path=":memory:",
            instance_name="test"
        )
        proxy = MailProxy(config=config)
        await proxy.init()
        yield proxy
        await proxy.close()


    async def test_send_email(proxy):
        # Add tenant and account
        await proxy.endpoints["tenants"].add(
            id="test", name="Test", active=True
        )
        await proxy.endpoints["accounts"].add(
            tenant_id="test",
            id="main",
            host="smtp.example.com",
            port=587
        )

        # Test send
        result = await proxy.send_email(
            tenant_id="test",
            account_id="main",
            to="user@example.com",
            subject="Test",
            body="Hello"
        )
        assert result["status"] == "queued"

Complete Example
----------------

See the `genro-mail-proxy <https://github.com/genropy/genro-mail-proxy>`_
repository for a complete example of extending genro-proxy.
