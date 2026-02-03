# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for AccountsTable schema and base operations."""

import pytest_asyncio

from proxy.entities.account.table import AccountsTable
from proxy.sql import SqlDb


@pytest_asyncio.fixture
async def accounts_table(sqlite_db: SqlDb) -> AccountsTable:
    """Create an AccountsTable with SQLite for testing."""
    table = AccountsTable(sqlite_db)
    await table.create_schema()
    return table


class TestCreateTableSql:
    """Tests for AccountsTable.create_table_sql() method."""

    async def test_includes_unique_constraint(self, accounts_table: AccountsTable):
        """create_table_sql includes UNIQUE constraint on (tenant_id, id)."""
        sql = accounts_table.create_table_sql()
        assert 'UNIQUE ("tenant_id", "id")' in sql


class TestSchema:
    """Tests for AccountsTable schema."""

    async def test_insert_generates_pk(self, accounts_table: AccountsTable):
        """insert() generates pk via new_pkey_value()."""
        await accounts_table.insert({
            "tenant_id": "t1",
            "id": "acc1",
            "name": "Test",
        })

        account = await accounts_table.record(where={"tenant_id": "t1", "id": "acc1"})
        assert account is not None
        assert account["pk"] is not None
        assert len(account["pk"]) > 10  # UUID format

    async def test_insert_with_config(self, accounts_table: AccountsTable):
        """insert() stores JSON config (encrypted)."""
        config = {"key": "value", "nested": {"a": 1}}
        await accounts_table.insert({
            "tenant_id": "t1",
            "id": "acc1",
            "name": "Test",
            "config": config,
        })

        account = await accounts_table.record(where={"tenant_id": "t1", "id": "acc1"})
        assert account is not None
        assert account["config"] == config


class TestSyncSchema:
    """Tests for AccountsTable.sync_schema() method."""

    async def test_sync_schema_creates_index(self, accounts_table: AccountsTable):
        """sync_schema() creates unique index."""
        await accounts_table.sync_schema()

        # Insert two different accounts
        await accounts_table.insert({"tenant_id": "t1", "id": "acc1", "name": "A1"})
        await accounts_table.insert({"tenant_id": "t1", "id": "acc2", "name": "A2"})

        accounts = await accounts_table.select()
        assert len(accounts) == 2
