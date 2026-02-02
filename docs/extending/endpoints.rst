Extending Endpoints
===================

This guide covers how to extend endpoints with domain-specific methods.

Endpoint Basics
---------------

Endpoints in genro-proxy:

- Expose async methods as API routes and CLI commands
- Use ``@POST`` decorator for mutation methods
- Validate parameters via Pydantic (auto-generated models)
- Return dicts that are JSON-serialized

Base Endpoint Structure
-----------------------

The base ``AccountEndpoint`` provides:

.. code-block:: python

    class AccountEndpoint(BaseEndpoint):
        name = "accounts"

        @POST
        async def add(self, id: str, tenant_id: str, ...) -> dict:
            ...

        async def get(self, tenant_id: str, account_id: str) -> dict:
            ...

        async def list(self, tenant_id: str) -> list[dict]:
            ...

        @POST
        async def delete(self, tenant_id: str, account_id: str) -> None:
            ...

Adding Methods
--------------

To add domain-specific methods, subclass and add:

.. code-block:: python

    from proxy.entities.account import AccountEndpoint
    from proxy.interface import POST


    class MailAccountEndpoint(AccountEndpoint):
        \"\"\"Mail account with SMTP operations.\"\"\"

        @POST
        async def test_connection(
            self, tenant_id: str, account_id: str
        ) -> dict:
            \"\"\"Test SMTP connection to server.\"\"\"
            account = await self.table.get(tenant_id, account_id)
            # Your test logic
            return {"status": "ok", "message": f"Connected to {account['host']}"}

        @POST
        async def send_test_email(
            self,
            tenant_id: str,
            account_id: str,
            to: str,
            subject: str = "Test Email"
        ) -> dict:
            \"\"\"Send a test email through this account.\"\"\"
            account = await self.table.get(tenant_id, account_id)
            # Your send logic
            return {"status": "sent", "to": to}

This automatically creates:

- ``POST /api/accounts/test-connection``
- ``POST /api/accounts/send-test-email``
- CLI: ``proxy accounts test-connection --tenant-id X --account-id Y``
- CLI: ``proxy accounts send-test-email --tenant-id X --account-id Y --to email``

Overriding Methods
------------------

Override existing methods to change parameters or behavior:

.. code-block:: python

    class MailAccountEndpoint(AccountEndpoint):

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
        ) -> dict:
            \"\"\"Add SMTP account with mail-specific fields.\"\"\"
            data = {k: v for k, v in locals().items() if k != "self"}
            await self.table.add(data)
            return await self.table.get(tenant_id, id)

The new signature defines what parameters the API accepts.

HTTP Method Selection
---------------------

By default:

- Methods without ``@POST`` → GET routes
- Methods with ``@POST`` → POST routes

Use ``@POST`` for methods that:

- Create or modify data
- Have side effects
- Accept complex parameters (body vs query)

.. code-block:: python

    from proxy.interface import POST

    class MyEndpoint(BaseEndpoint):

        # GET /api/items/list
        async def list(self) -> list[dict]:
            return await self.table.select()

        # GET /api/items/get?id=xxx
        async def get(self, id: str) -> dict:
            return await self.table.select_one(where={"id": id})

        # POST /api/items/add (body: {"id": "...", "name": "..."})
        @POST
        async def add(self, id: str, name: str) -> dict:
            await self.table.insert({"id": id, "name": name})
            return await self.table.select_one(where={"id": id})

        # POST /api/items/delete (body: {"id": "..."})
        @POST
        async def delete(self, id: str) -> None:
            await self.table.delete(where={"id": id})

Parameter Types
---------------

Supported parameter types and their validation:

.. code-block:: python

    async def my_method(
        self,
        # Required string
        name: str,

        # Optional string
        description: str | None = None,

        # Integer with default
        port: int = 587,

        # Boolean flag
        active: bool = True,

        # Literal choices
        status: Literal["active", "inactive"] = "active",

        # Dict (for JSON body)
        config: dict[str, Any] | None = None,
    ) -> dict:
        ...

These become Pydantic fields with automatic validation.

Return Types
------------

Methods should return:

- ``dict`` - Single record
- ``list[dict]`` - Multiple records
- ``None`` - No content (for delete operations)

.. code-block:: python

    async def get(self, id: str) -> dict:
        \"\"\"Returns: {\"data\": {...}}\"\"\"
        return await self.table.get(id)

    async def list(self) -> list[dict]:
        \"\"\"Returns: {\"data\": [...]}\"\"\"
        return await self.table.select()

    @POST
    async def delete(self, id: str) -> None:
        \"\"\"Returns: {\"data\": null}\"\"\"
        await self.table.delete(where={"id": id})

Error Handling
--------------

Raise appropriate exceptions:

.. code-block:: python

    async def get(self, tenant_id: str, account_id: str) -> dict:
        account = await self.table.select_one(
            where={"tenant_id": tenant_id, "id": account_id}
        )
        if not account:
            # Returns 404
            raise ValueError(f"Account '{account_id}' not found")
        return account

    @POST
    async def add(self, id: str, name: str) -> dict:
        if not name.strip():
            # Returns 422 via Pydantic
            raise ValueError("Name cannot be empty")
        ...

Exception mapping:

- ``ValueError`` → 404 Not Found
- ``pydantic.ValidationError`` → 422 Unprocessable Entity
- Other exceptions → 500 Internal Server Error

Using invoke()
--------------

The ``invoke()`` method provides unified validation:

.. code-block:: python

    # Direct call (no validation)
    result = await endpoint.get("tenant", "account")

    # Via invoke (with Pydantic validation)
    result = await endpoint.invoke("get", {
        "tenant_id": "tenant",
        "account_id": "account"
    })

This is used internally by API routes and CLI commands.

Testing Endpoints
-----------------

.. code-block:: python

    import pytest
    from unittest.mock import AsyncMock, MagicMock

    @pytest.fixture
    def mock_table():
        table = MagicMock()
        table.get = AsyncMock(return_value={"id": "test", "name": "Test"})
        table.add = AsyncMock(return_value="pk123")
        return table

    @pytest.fixture
    def endpoint(mock_table):
        return MailAccountEndpoint(mock_table)

    async def test_get_account(endpoint, mock_table):
        result = await endpoint.get("tenant", "account")
        assert result["id"] == "test"
        mock_table.get.assert_called_once_with("tenant", "account")

    async def test_invoke_validates(endpoint):
        # Missing required parameter
        with pytest.raises(ValidationError):
            await endpoint.invoke("get", {"tenant_id": "t"})  # missing account_id
