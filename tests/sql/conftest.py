# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""PostgreSQL and SQLite fixtures for database tests.

PostgreSQL fixtures connect to a container running on port 5433.
Start the container with: docker compose up -d

Connection: postgresql://proxy:testpassword@localhost:5433/proxy

Connection model:
- Each fixture opens a connection via `async with db.connection()`
- The connection stays open for the entire test
- Tests can use db methods directly (execute, fetch_one, etc.)
- Cleanup happens in a separate connection context
"""

from __future__ import annotations

import contextlib
import os
import socket
import tempfile
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from genro_proxy.proxy_base import ProxyBase, ProxyConfigBase
from genro_proxy.sql import SqlDb

# Default PostgreSQL URL for tests (can be overridden via environment)
PG_URL = os.environ.get(
    "GENRO_PROXY_TEST_PG_URL",
    "postgresql://proxy:testpassword@localhost:5433/proxy",
)


def pytest_configure(config):
    """Register postgres marker."""
    config.addinivalue_line("markers", "postgres: marks tests requiring PostgreSQL database")


def _is_postgres_available() -> bool:
    """Check if PostgreSQL is available on port 5433."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 5433))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.fixture(autouse=True)
def skip_if_postgres_unavailable(request):
    """Auto-skip postgres-marked tests if PostgreSQL is not available."""
    if request.node.get_closest_marker("postgres"):
        if not _is_postgres_available():
            pytest.skip("PostgreSQL not available at localhost:5433")


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Return PostgreSQL connection URL."""
    return PG_URL


@pytest_asyncio.fixture
async def sqlite_db() -> AsyncGenerator[SqlDb, None]:
    """Create a SQLite database for testing.

    Opens a connection that stays active for the entire test.
    Tests can use db.execute(), db.fetch_one(), etc. directly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = SqlDb(db_path)
        async with db.connection():
            yield db
        await db.shutdown()


@pytest_asyncio.fixture
async def pg_db(pg_url: str) -> AsyncGenerator[SqlDb, None]:
    """Create a SqlDb instance connected to PostgreSQL.

    Creates a fresh test schema for each test run to ensure isolation.
    Drops all tables before and after each test.
    Opens a connection that stays active for the entire test.
    """
    # Create proxy to get database with proper configuration
    proxy = ProxyBase(ProxyConfigBase(db_path=pg_url))

    # Tables that may be created by tests
    test_tables = [
        "test_items",
        "auto_items",
        "no_pk_items",
        "command_log",
        "storages",
        "accounts",
        "tenants",
        "instance",
    ]

    # Setup: drop tables and create schema
    async with proxy.db.connection():
        # Drop all tables first to ensure clean state (CASCADE handles FK order)
        for table_name in test_tables:
            with contextlib.suppress(Exception):
                await proxy.db.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')

        # Create base tables in FK dependency order
        table_order = ["instance", "command_log", "tenants", "accounts", "storages"]
        for table_name in table_order:
            if table_name in proxy.db.tables:
                await proxy.db.tables[table_name].create_schema()

    # Test execution: open connection for the test
    async with proxy.db.connection():
        yield proxy.db

    # Cleanup: drop all tables in new connection
    async with proxy.db.connection():
        for table_name in test_tables:
            with contextlib.suppress(Exception):
                await proxy.db.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')

    await proxy.shutdown()


@pytest_asyncio.fixture
async def pg_proxy(pg_url: str) -> AsyncGenerator[ProxyBase, None]:
    """Create a full ProxyBase instance with PostgreSQL backend.

    Useful for testing complete workflows with the proxy.
    Opens a connection that stays active for the entire test.
    """
    config = ProxyConfigBase(db_path=pg_url, test_mode=True, start_active=False)
    proxy = ProxyBase(config)

    # Tables that may be created by tests
    test_tables = [
        "test_items",
        "auto_items",
        "no_pk_items",
        "command_log",
        "storages",
        "accounts",
        "tenants",
        "instance",
    ]

    # Setup: drop tables and create schema
    async with proxy.db.connection():
        # Drop all tables first
        for table_name in test_tables:
            with contextlib.suppress(Exception):
                await proxy.db.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')

        # Create tables in FK dependency order
        table_order = ["instance", "command_log", "tenants", "accounts", "storages"]
        for table_name in table_order:
            if table_name in proxy.db.tables:
                await proxy.db.tables[table_name].create_schema()

    # Test execution: open connection for the test
    async with proxy.db.connection():
        yield proxy

    # Cleanup: drop all tables
    async with proxy.db.connection():
        for table_name in test_tables:
            with contextlib.suppress(Exception):
                await proxy.db.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')

    await proxy.shutdown()
