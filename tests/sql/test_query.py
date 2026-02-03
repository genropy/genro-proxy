# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tests for Query builder and WhereBuilder."""

from __future__ import annotations

import pytest
import pytest_asyncio

from genro_proxy.sql import SqlDb, Table, String, Integer
from genro_proxy.sql.query import Query, WhereBuilder, parse_where_kwargs


# ---------------------------------------------------------------------------
# Test Table for Query tests
# ---------------------------------------------------------------------------


class QueryTestTable(Table):
    """Test table for query builder tests."""

    name = "query_test"
    pkey = "id"

    def configure(self):
        self.columns.column("id", String)
        self.columns.column("name", String)
        self.columns.column("status", String, default="active")
        self.columns.column("score", Integer, default=0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def query_db(sqlite_db: SqlDb):
    """Setup test table for query tests."""
    sqlite_db.add_table(QueryTestTable)
    await sqlite_db.check_structure()
    await sqlite_db.commit()
    yield sqlite_db


# ---------------------------------------------------------------------------
# parse_where_kwargs Tests
# ---------------------------------------------------------------------------


class TestParseWhereKwargs:
    """Test parse_where_kwargs function."""

    def test_empty(self):
        """Empty dict returns empty conditions."""
        assert parse_where_kwargs({}) == {}

    def test_dict_style(self):
        """Dict-style conditions (where_a={...})."""
        result = parse_where_kwargs({
            "a": {"column": "status", "op": "=", "value": "active"},
            "b": {"column": "name", "op": "LIKE", "value": "%test%"},
        })
        assert result == {
            "a": {"column": "status", "op": "=", "value": "active"},
            "b": {"column": "name", "op": "LIKE", "value": "%test%"},
        }

    def test_flat_style(self):
        """Flat-style conditions (where_a_column, where_a_op, where_a_value)."""
        result = parse_where_kwargs({
            "a_column": "status",
            "a_op": "=",
            "a_value": "active",
            "b_column": "name",
            "b_op": "LIKE",
            "b_value": "%test%",
        })
        assert result == {
            "a": {"column": "status", "op": "=", "value": "active"},
            "b": {"column": "name", "op": "LIKE", "value": "%test%"},
        }

    def test_mixed_style(self):
        """Mixed dict and flat styles."""
        result = parse_where_kwargs({
            "a": {"column": "status", "op": "=", "value": "active"},
            "b_column": "name",
            "b_op": "LIKE",
            "b_value": "%test%",
        })
        assert result == {
            "a": {"column": "status", "op": "=", "value": "active"},
            "b": {"column": "name", "op": "LIKE", "value": "%test%"},
        }

    def test_flat_without_column_ignored(self):
        """Flat style without 'column' field is ignored."""
        result = parse_where_kwargs({
            "a_op": "=",
            "a_value": "active",  # Missing a_column
        })
        assert result == {}


# ---------------------------------------------------------------------------
# WhereBuilder Tests
# ---------------------------------------------------------------------------


class TestWhereBuilder:
    """Test WhereBuilder class."""

    def test_empty_where(self, sqlite_db: SqlDb):
        """Empty where returns empty string."""
        builder = WhereBuilder(sqlite_db.adapter)
        sql, params = builder.build(None, {}, {})
        assert sql == ""
        assert params == {}

    def test_empty_dict(self, sqlite_db: SqlDb):
        """Empty dict returns empty string."""
        builder = WhereBuilder(sqlite_db.adapter)
        sql, params = builder.build({}, {}, {})
        assert sql == ""
        assert params == {}

    def test_simple_dict_single(self, sqlite_db: SqlDb):
        """Simple dict with single condition."""
        builder = WhereBuilder(sqlite_db.adapter)
        sql, params = builder.build({"status": "active"}, {}, {})
        assert "status = " in sql
        assert params["w_status"] == "active"

    def test_simple_dict_multiple(self, sqlite_db: SqlDb):
        """Simple dict with multiple conditions (AND)."""
        builder = WhereBuilder(sqlite_db.adapter)
        sql, params = builder.build({"status": "active", "name": "test"}, {}, {})
        assert "status = " in sql
        assert "name = " in sql
        assert " AND " in sql
        assert params["w_status"] == "active"
        assert params["w_name"] == "test"

    def test_expression_single_condition(self, sqlite_db: SqlDb):
        """Expression with single named condition."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "status", "op": "=", "value": "active"}}
        sql, params = builder.build("$a", conditions, {})
        assert "status = " in sql
        assert params["c_a"] == "active"

    def test_expression_multiple_conditions(self, sqlite_db: SqlDb):
        """Expression with multiple named conditions."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {
            "a": {"column": "status", "op": "=", "value": "active"},
            "b": {"column": "score", "op": ">", "value": 10},
        }
        sql, params = builder.build("$a AND $b", conditions, {})
        assert "status = " in sql
        assert "score > " in sql
        assert params["c_a"] == "active"
        assert params["c_b"] == 10

    def test_expression_with_not(self, sqlite_db: SqlDb):
        """Expression with NOT operator."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {
            "a": {"column": "status", "op": "=", "value": "active"},
            "b": {"column": "status", "op": "=", "value": "deleted"},
        }
        sql, _ = builder.build("$a AND NOT $b", conditions, {})
        assert "AND NOT" in sql

    def test_expression_with_or(self, sqlite_db: SqlDb):
        """Expression with OR operator."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {
            "a": {"column": "status", "op": "=", "value": "active"},
            "b": {"column": "status", "op": "=", "value": "pending"},
        }
        sql, _ = builder.build("$a OR $b", conditions, {})
        assert " OR " in sql

    def test_expression_with_parentheses(self, sqlite_db: SqlDb):
        """Expression with parentheses for precedence."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {
            "a": {"column": "status", "op": "=", "value": "active"},
            "b": {"column": "score", "op": ">", "value": 50},
            "c": {"column": "name", "op": "LIKE", "value": "%test%"},
        }
        sql, _ = builder.build("($a OR $b) AND $c", conditions, {})
        assert "(" in sql
        assert ")" in sql
        assert " AND " in sql
        assert " OR " in sql

    def test_is_null_operator(self, sqlite_db: SqlDb):
        """IS NULL operator (no value needed)."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "deleted_at", "op": "IS NULL"}}
        sql, params = builder.build("$a", conditions, {})
        assert "deleted_at IS NULL" in sql
        # No param for IS NULL
        assert "c_a" not in params

    def test_is_not_null_operator(self, sqlite_db: SqlDb):
        """IS NOT NULL operator."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "email", "op": "IS NOT NULL"}}
        sql, _ = builder.build("$a", conditions, {})
        assert "email IS NOT NULL" in sql

    def test_in_operator(self, sqlite_db: SqlDb):
        """IN operator with list."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "status", "op": "IN", "value": ["a", "b", "c"]}}
        sql, params = builder.build("$a", conditions, {})
        assert "status IN (" in sql
        assert params["c_a_0"] == "a"
        assert params["c_a_1"] == "b"
        assert params["c_a_2"] == "c"

    def test_not_in_operator(self, sqlite_db: SqlDb):
        """NOT IN operator with list."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "status", "op": "NOT IN", "value": ["x", "y"]}}
        sql, params = builder.build("$a", conditions, {})
        assert "status NOT IN (" in sql
        assert params["c_a_0"] == "x"
        assert params["c_a_1"] == "y"

    def test_in_empty_list(self, sqlite_db: SqlDb):
        """IN with empty list returns always-false condition."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "status", "op": "IN", "value": []}}
        sql, _ = builder.build("$a", conditions, {})
        assert "1=0" in sql

    def test_not_in_empty_list(self, sqlite_db: SqlDb):
        """NOT IN with empty list returns always-true condition."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "status", "op": "NOT IN", "value": []}}
        sql, _ = builder.build("$a", conditions, {})
        assert "1=1" in sql

    def test_like_operator(self, sqlite_db: SqlDb):
        """LIKE operator."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "name", "op": "LIKE", "value": "%test%"}}
        sql, params = builder.build("$a", conditions, {})
        assert "name LIKE " in sql
        assert params["c_a"] == "%test%"

    def test_ilike_operator(self, sqlite_db: SqlDb):
        """ILIKE operator (case-insensitive LIKE)."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "name", "op": "ILIKE", "value": "%TEST%"}}
        sql, params = builder.build("$a", conditions, {})
        assert "name ILIKE " in sql
        assert params["c_a"] == "%TEST%"

    def test_between_operator(self, sqlite_db: SqlDb):
        """BETWEEN operator."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "score", "op": "BETWEEN", "value": [10, 50]}}
        sql, params = builder.build("$a", conditions, {})
        assert "score BETWEEN " in sql
        assert " AND " in sql
        assert params["c_a_low"] == 10
        assert params["c_a_high"] == 50

    def test_param_reference(self, sqlite_db: SqlDb):
        """Value with :param references external parameter."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "name", "op": "ILIKE", "value": ":pattern"}}
        sql, params = builder.build("$a", conditions, {"pattern": "%mario%"})
        assert "name ILIKE " in sql
        assert params["pattern"] == "%mario%"

    def test_comparison_operators(self, sqlite_db: SqlDb):
        """Test <, >, <=, >= operators."""
        builder = WhereBuilder(sqlite_db.adapter)

        for op in ["<", ">", "<=", ">="]:
            conditions = {"a": {"column": "score", "op": op, "value": 100}}
            sql, _ = builder.build("$a", conditions, {})
            assert f"score {op} " in sql

    def test_unknown_operator_raises(self, sqlite_db: SqlDb):
        """Unknown operator raises ValueError."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "x", "op": "UNKNOWN", "value": 1}}
        with pytest.raises(ValueError, match="non supportato"):
            builder.build("$a", conditions, {})

    def test_missing_condition_raises(self, sqlite_db: SqlDb):
        """Reference to missing condition raises ValueError."""
        builder = WhereBuilder(sqlite_db.adapter)
        with pytest.raises(ValueError, match="non trovata"):
            builder.build("$missing", {}, {})

    def test_in_with_non_list_raises(self, sqlite_db: SqlDb):
        """IN with non-list value raises ValueError."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "status", "op": "IN", "value": "not_a_list"}}
        with pytest.raises(ValueError, match="richiede lista"):
            builder.build("$a", conditions, {})

    def test_between_with_wrong_length_raises(self, sqlite_db: SqlDb):
        """BETWEEN with wrong list length raises ValueError."""
        builder = WhereBuilder(sqlite_db.adapter)
        conditions = {"a": {"column": "score", "op": "BETWEEN", "value": [1, 2, 3]}}
        with pytest.raises(ValueError, match="2 elementi"):
            builder.build("$a", conditions, {})


# ---------------------------------------------------------------------------
# Query Integration Tests
# ---------------------------------------------------------------------------


class TestQuery:
    """Test Query class with actual database operations."""

    @pytest.mark.asyncio
    async def test_fetch_all(self, query_db: SqlDb):
        """fetch() returns all matching rows."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Alice", "status": "active"})
        await table.insert({"id": "2", "name": "Bob", "status": "active"})
        await table.insert({"id": "3", "name": "Charlie", "status": "deleted"})
        await query_db.commit()

        rows = await table.query(where={"status": "active"}).fetch()
        assert len(rows) == 2
        names = {r["name"] for r in rows}
        assert names == {"Alice", "Bob"}

    @pytest.mark.asyncio
    async def test_fetch_one(self, query_db: SqlDb):
        """fetch_one() returns single row or None."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Alice"})
        await query_db.commit()

        row = await table.query(where={"id": "1"}).fetch_one()
        assert row is not None
        assert row["name"] == "Alice"

        row = await table.query(where={"id": "nonexistent"}).fetch_one()
        assert row is None

    @pytest.mark.asyncio
    async def test_count(self, query_db: SqlDb):
        """count() returns number of matching rows."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active"})
        await table.insert({"id": "2", "status": "active"})
        await table.insert({"id": "3", "status": "deleted"})
        await query_db.commit()

        count = await table.query(where={"status": "active"}).count()
        assert count == 2

        count = await table.query(where={"status": "deleted"}).count()
        assert count == 1

        count = await table.query().count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_exists(self, query_db: SqlDb):
        """exists() returns True if any row matches."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active"})
        await query_db.commit()

        assert await table.query(where={"status": "active"}).exists() is True
        assert await table.query(where={"status": "deleted"}).exists() is False

    @pytest.mark.asyncio
    async def test_order_by(self, query_db: SqlDb):
        """ORDER BY clause."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Charlie", "score": 30})
        await table.insert({"id": "2", "name": "Alice", "score": 10})
        await table.insert({"id": "3", "name": "Bob", "score": 20})
        await query_db.commit()

        rows = await table.query(order_by="name ASC").fetch()
        assert [r["name"] for r in rows] == ["Alice", "Bob", "Charlie"]

        rows = await table.query(order_by="score DESC").fetch()
        assert [r["name"] for r in rows] == ["Charlie", "Bob", "Alice"]

    @pytest.mark.asyncio
    async def test_limit_offset(self, query_db: SqlDb):
        """LIMIT and OFFSET clauses."""
        table = query_db.table("query_test")
        for i in range(5):
            await table.insert({"id": str(i), "name": f"User{i}", "score": i * 10})
        await query_db.commit()

        rows = await table.query(order_by="score ASC", limit=2).fetch()
        assert len(rows) == 2
        assert rows[0]["name"] == "User0"

        rows = await table.query(order_by="score ASC", limit=2, offset=2).fetch()
        assert len(rows) == 2
        assert rows[0]["name"] == "User2"

    @pytest.mark.asyncio
    async def test_select_columns(self, query_db: SqlDb):
        """Select specific columns."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Alice", "status": "active", "score": 100})
        await query_db.commit()

        rows = await table.query(columns=["id", "name"]).fetch()
        assert len(rows) == 1
        assert "id" in rows[0]
        assert "name" in rows[0]

    # -------------------------------------------------------------------------
    # Tests with where_ prefix (dict style)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_expression_with_or_dict_style(self, query_db: SqlDb):
        """Expression with OR operator using where_ dict style."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active"})
        await table.insert({"id": "2", "status": "pending"})
        await table.insert({"id": "3", "status": "deleted"})
        await query_db.commit()

        rows = await table.query(
            where_a={"column": "status", "op": "=", "value": "active"},
            where_b={"column": "status", "op": "=", "value": "pending"},
            where="$a OR $b",
        ).fetch()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_expression_with_not_dict_style(self, query_db: SqlDb):
        """Expression with NOT operator using where_ dict style."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active"})
        await table.insert({"id": "2", "status": "deleted"})
        await query_db.commit()

        rows = await table.query(
            where_deleted={"column": "status", "op": "=", "value": "deleted"},
            where="NOT $deleted",
        ).fetch()
        assert len(rows) == 1
        assert rows[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_expression_with_in_dict_style(self, query_db: SqlDb):
        """Expression with IN operator using where_ dict style."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "a"})
        await table.insert({"id": "2", "status": "b"})
        await table.insert({"id": "3", "status": "c"})
        await query_db.commit()

        rows = await table.query(
            where_s={"column": "status", "op": "IN", "value": ["a", "c"]},
            where="$s",
        ).fetch()
        assert len(rows) == 2
        statuses = {r["status"] for r in rows}
        assert statuses == {"a", "c"}

    @pytest.mark.asyncio
    async def test_expression_with_like_dict_style(self, query_db: SqlDb):
        """Expression with LIKE operator using where_ dict style."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Mario Rossi"})
        await table.insert({"id": "2", "name": "Luigi Bianchi"})
        await table.insert({"id": "3", "name": "Anna Maria"})
        await query_db.commit()

        rows = await table.query(
            where_name={"column": "name", "op": "LIKE", "value": "%Mari%"},
            where="$name",
        ).fetch()
        assert len(rows) == 2
        names = {r["name"] for r in rows}
        assert names == {"Mario Rossi", "Anna Maria"}

    @pytest.mark.asyncio
    async def test_expression_with_param_reference_dict_style(self, query_db: SqlDb):
        """Expression with :param reference using where_ dict style."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Mario Rossi"})
        await table.insert({"id": "2", "name": "Luigi Bianchi"})
        await query_db.commit()

        rows = await table.query(
            where_name={"column": "name", "op": "LIKE", "value": ":pattern"},
            where="$name",
            pattern="%Mario%",
        ).fetch()
        assert len(rows) == 1
        assert rows[0]["name"] == "Mario Rossi"

    @pytest.mark.asyncio
    async def test_complex_expression_dict_style(self, query_db: SqlDb):
        """Complex expression with multiple conditions using where_ dict style."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Alice", "status": "active", "score": 80})
        await table.insert({"id": "2", "name": "Bob", "status": "active", "score": 30})
        await table.insert({"id": "3", "name": "Charlie", "status": "deleted", "score": 90})
        await table.insert({"id": "4", "name": "Diana", "status": "pending", "score": 50})
        await query_db.commit()

        # (active AND score > 50) OR (status = pending)
        rows = await table.query(
            where_active={"column": "status", "op": "=", "value": "active"},
            where_high={"column": "score", "op": ">", "value": 50},
            where_pending={"column": "status", "op": "=", "value": "pending"},
            where="($active AND $high) OR $pending",
        ).fetch()
        assert len(rows) == 2
        names = {r["name"] for r in rows}
        assert names == {"Alice", "Diana"}

    # -------------------------------------------------------------------------
    # Tests with where_ prefix (flat style)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_expression_flat_style(self, query_db: SqlDb):
        """Expression using where_a_column, where_a_op, where_a_value flat style."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active"})
        await table.insert({"id": "2", "status": "pending"})
        await table.insert({"id": "3", "status": "deleted"})
        await query_db.commit()

        rows = await table.query(
            where_a_column="status",
            where_a_op="=",
            where_a_value="active",
            where_b_column="status",
            where_b_op="=",
            where_b_value="pending",
            where="$a OR $b",
        ).fetch()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_complex_expression_flat_style(self, query_db: SqlDb):
        """Complex expression using flat style."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Alice", "status": "active", "score": 80})
        await table.insert({"id": "2", "name": "Bob", "status": "active", "score": 30})
        await table.insert({"id": "3", "name": "Charlie", "status": "deleted", "score": 90})
        await table.insert({"id": "4", "name": "Diana", "status": "pending", "score": 50})
        await query_db.commit()

        # (active AND score > 50) OR (status = pending)
        rows = await table.query(
            where_active_column="status",
            where_active_op="=",
            where_active_value="active",
            where_high_column="score",
            where_high_op=">",
            where_high_value=50,
            where_pending_column="status",
            where_pending_op="=",
            where_pending_value="pending",
            where="($active AND $high) OR $pending",
        ).fetch()
        assert len(rows) == 2
        names = {r["name"] for r in rows}
        assert names == {"Alice", "Diana"}

    @pytest.mark.asyncio
    async def test_mixed_dict_and_flat_style(self, query_db: SqlDb):
        """Mixed dict and flat style conditions."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active", "score": 80})
        await table.insert({"id": "2", "status": "active", "score": 30})
        await table.insert({"id": "3", "status": "deleted", "score": 90})
        await query_db.commit()

        rows = await table.query(
            where_a={"column": "status", "op": "=", "value": "active"},
            where_b_column="score",
            where_b_op=">",
            where_b_value=50,
            where="$a AND $b",
        ).fetch()
        assert len(rows) == 1
        assert rows[0]["score"] == 80


# ---------------------------------------------------------------------------
# Query.delete() Tests
# ---------------------------------------------------------------------------


class TestQueryDelete:
    """Test Query.delete() method."""

    @pytest.mark.asyncio
    async def test_delete_simple_where(self, query_db: SqlDb):
        """Delete with simple dict where."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active"})
        await table.insert({"id": "2", "status": "deleted"})
        await table.insert({"id": "3", "status": "deleted"})
        await query_db.commit()

        deleted = await table.query(where={"status": "deleted"}).delete()
        assert deleted == 2

        remaining = await table.query().fetch()
        assert len(remaining) == 1
        assert remaining[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_delete_complex_expression(self, query_db: SqlDb):
        """Delete with complex expression."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active", "score": 10})
        await table.insert({"id": "2", "status": "active", "score": 90})
        await table.insert({"id": "3", "status": "deleted", "score": 50})
        await query_db.commit()

        # Delete active with low score
        deleted = await table.query(
            where_active={"column": "status", "op": "=", "value": "active"},
            where_low={"column": "score", "op": "<", "value": 50},
            where="$active AND $low",
        ).delete()
        assert deleted == 1

        remaining = await table.query().fetch()
        assert len(remaining) == 2
        ids = {r["id"] for r in remaining}
        assert ids == {"2", "3"}

    @pytest.mark.asyncio
    async def test_delete_raw_mode(self, query_db: SqlDb):
        """Delete with raw=True (no triggers)."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "old"})
        await table.insert({"id": "2", "status": "old"})
        await table.insert({"id": "3", "status": "new"})
        await query_db.commit()

        deleted = await table.query(where={"status": "old"}).delete(raw=True)
        assert deleted == 2

        remaining = await table.query().fetch()
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_delete_no_match(self, query_db: SqlDb):
        """Delete with no matching rows."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active"})
        await query_db.commit()

        deleted = await table.query(where={"status": "nonexistent"}).delete()
        assert deleted == 0

        remaining = await table.query().fetch()
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_delete_preview_then_delete(self, query_db: SqlDb):
        """Preview with fetch, then delete (reusable query)."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "to_delete"})
        await table.insert({"id": "2", "status": "to_delete"})
        await table.insert({"id": "3", "status": "keep"})
        await query_db.commit()

        q = table.query(where={"status": "to_delete"})

        # Preview
        preview = await q.fetch()
        assert len(preview) == 2

        # Delete
        deleted = await q.delete()
        assert deleted == 2

        remaining = await table.query().fetch()
        assert len(remaining) == 1


# ---------------------------------------------------------------------------
# Query.update() Tests
# ---------------------------------------------------------------------------


class TestQueryUpdate:
    """Test Query.update() method."""

    @pytest.mark.asyncio
    async def test_update_simple_where(self, query_db: SqlDb):
        """Update with simple dict where."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "pending"})
        await table.insert({"id": "2", "status": "pending"})
        await table.insert({"id": "3", "status": "done"})
        await query_db.commit()

        updated = await table.query(where={"status": "pending"}).update({"status": "processed"})
        assert updated == 2

        processed = await table.query(where={"status": "processed"}).fetch()
        assert len(processed) == 2

    @pytest.mark.asyncio
    async def test_update_complex_expression(self, query_db: SqlDb):
        """Update with complex expression."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active", "score": 10})
        await table.insert({"id": "2", "status": "active", "score": 90})
        await table.insert({"id": "3", "status": "inactive", "score": 50})
        await query_db.commit()

        # Update active with high score
        updated = await table.query(
            where_active={"column": "status", "op": "=", "value": "active"},
            where_high={"column": "score", "op": ">=", "value": 50},
            where="$active AND $high",
        ).update({"status": "premium"})
        assert updated == 1

        premium = await table.query(where={"status": "premium"}).fetch()
        assert len(premium) == 1
        assert premium[0]["id"] == "2"

    @pytest.mark.asyncio
    async def test_update_raw_mode(self, query_db: SqlDb):
        """Update with raw=True (no triggers, no encoding)."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "old"})
        await table.insert({"id": "2", "status": "old"})
        await query_db.commit()

        updated = await table.query(where={"status": "old"}).update({"status": "new"}, raw=True)
        assert updated == 2

        new_rows = await table.query(where={"status": "new"}).fetch()
        assert len(new_rows) == 2

    @pytest.mark.asyncio
    async def test_update_no_match(self, query_db: SqlDb):
        """Update with no matching rows."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "active"})
        await query_db.commit()

        updated = await table.query(where={"status": "nonexistent"}).update({"score": 999})
        assert updated == 0

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, query_db: SqlDb):
        """Update multiple fields at once."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "name": "Old Name", "status": "pending", "score": 0})
        await query_db.commit()

        updated = await table.query(where={"id": "1"}).update({
            "name": "New Name",
            "status": "active",
            "score": 100,
        })
        assert updated == 1

        row = await table.query(where={"id": "1"}).fetch_one()
        assert row is not None
        assert row["name"] == "New Name"
        assert row["status"] == "active"
        assert row["score"] == 100

    @pytest.mark.asyncio
    async def test_update_preview_then_update(self, query_db: SqlDb):
        """Preview with fetch, then update (reusable query)."""
        table = query_db.table("query_test")
        await table.insert({"id": "1", "status": "to_update", "score": 10})
        await table.insert({"id": "2", "status": "to_update", "score": 20})
        await table.insert({"id": "3", "status": "keep", "score": 30})
        await query_db.commit()

        q = table.query(where={"status": "to_update"})

        # Preview
        preview = await q.fetch()
        assert len(preview) == 2

        # Update
        updated = await q.update({"status": "updated"})
        assert updated == 2

        updated_rows = await table.query(where={"status": "updated"}).fetch()
        assert len(updated_rows) == 2
