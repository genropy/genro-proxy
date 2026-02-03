# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Async query builder with fluent API and advanced WHERE conditions."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .adapters.base import DbAdapter
    from .table import Table


def parse_where_kwargs(where_kwargs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Parse where_kwargs into named conditions.

    Converts flat kwargs like:
        {'a_column': 'status', 'a_op': '=', 'a_value': 'active',
         'b_column': 'name', 'b_op': 'ILIKE', 'b_value': ':pattern'}

    Into structured conditions:
        {'a': {'column': 'status', 'op': '=', 'value': 'active'},
         'b': {'column': 'name', 'op': 'ILIKE', 'value': ':pattern'}}

    Also supports dict-style conditions:
        {'a': {'column': 'status', 'op': '=', 'value': 'active'}}
    """
    conditions: dict[str, dict[str, Any]] = {}
    flat_parts: dict[str, dict[str, Any]] = defaultdict(dict)

    for key, value in where_kwargs.items():
        if isinstance(value, dict) and 'column' in value:
            # Already a condition dict: where_a={'column': ..., 'op': ..., 'value': ...}
            conditions[key] = value
        elif '_' in key:
            # Flat style: where_a_column, where_a_op, where_a_value
            parts = key.split('_', 1)
            if len(parts) == 2:
                cond_name, field = parts
                flat_parts[cond_name][field] = value

    # Merge flat parts into conditions
    for cond_name, fields in flat_parts.items():
        if 'column' in fields:
            conditions[cond_name] = fields

    return conditions


class WhereBuilder:
    """Costruisce clausole WHERE da condizioni nominate ed espressioni.

    Supporta due modalità:
    1. Dict semplice: {'col1': 'val1', 'col2': 'val2'} → col1 = 'val1' AND col2 = 'val2'
    2. Condizioni nominate + espressione: where_x={...}, where="$x AND NOT $y"

    Struttura condizione singola:
        {'column': 'nome', 'op': '=', 'value': 'valore'}
        {'column': 'nome', 'op': 'ILIKE', 'value': ':param'}  # parametro
        {'column': 'deleted_at', 'op': 'IS NULL'}  # senza value
    """

    OPERATORS = frozenset({
        '=', '!=', '<>', '<', '>', '<=', '>=',
        'LIKE', 'ILIKE', 'NOT LIKE', 'NOT ILIKE',
        'IN', 'NOT IN',
        'IS NULL', 'IS NOT NULL',
        'BETWEEN',
    })

    def __init__(self, adapter: DbAdapter):
        self.adapter = adapter

    def build(
        self,
        where: dict[str, Any] | str | None,
        conditions: dict[str, dict[str, Any]],
        params: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Costruisce WHERE clause e parametri.

        Args:
            where: Dict semplice o stringa espressione
            conditions: Dict di condizioni nominate {nome: {column, op, value}}
            params: Parametri aggiuntivi per :param

        Returns:
            (where_sql, params_dict)
        """
        if where is None:
            return "", {}

        # Caso 1: Dict semplice → AND con =
        if isinstance(where, dict):
            return self._build_simple(where)

        # Caso 2: Stringa espressione → parse e sostituisci
        return self._build_expression(where, conditions, params)

    def _build_simple(self, where: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Dict semplice: tutte uguaglianze con AND."""
        if not where:
            return "", {}

        parts = []
        params = {}
        for col, val in where.items():
            param_name = f"w_{col}"
            parts.append(f"{col} = {self.adapter._placeholder(param_name)}")
            params[param_name] = val

        return " AND ".join(parts), params

    def _build_expression(
        self,
        expr: str,
        conditions: dict[str, dict[str, Any]],
        params: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Espressione con $riferimenti a condizioni nominate."""
        result_params = dict(params)

        def replace_cond(match: re.Match[str]) -> str:
            name = match.group(1)
            cond = conditions.get(name)
            if not cond:
                raise ValueError(f"Condizione '{name}' non trovata")
            return f"({self._condition_to_sql(cond, name, result_params)})"

        sql = re.sub(r'\$(\w+)', replace_cond, expr)

        return sql, result_params

    def _condition_to_sql(
        self,
        cond: dict[str, Any],
        name: str,
        params: dict[str, Any],
    ) -> str:
        """Converte una condizione singola in SQL."""
        column = cond['column']
        op = cond.get('op', '=').upper()
        value = cond.get('value')

        if op not in self.OPERATORS:
            raise ValueError(f"Operatore '{op}' non supportato")

        # IS NULL / IS NOT NULL
        if op in ('IS NULL', 'IS NOT NULL'):
            return f"{column} {op}"

        # IN / NOT IN
        if op in ('IN', 'NOT IN'):
            if isinstance(value, (list, tuple)):
                if not value:
                    # Empty list: IN () is always false, NOT IN () is always true
                    return "1=0" if op == 'IN' else "1=1"
                placeholders = []
                for i, v in enumerate(value):
                    param_name = f"c_{name}_{i}"
                    placeholders.append(self.adapter._placeholder(param_name))
                    params[param_name] = v
                return f"{column} {op} ({', '.join(placeholders)})"
            raise ValueError(f"IN/NOT IN richiede lista, ricevuto {type(value)}")

        # BETWEEN
        if op == 'BETWEEN':
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError("BETWEEN richiede lista di 2 elementi [low, high]")
            low_param = f"c_{name}_low"
            high_param = f"c_{name}_high"
            params[low_param] = value[0]
            params[high_param] = value[1]
            return (
                f"{column} BETWEEN "
                f"{self.adapter._placeholder(low_param)} AND "
                f"{self.adapter._placeholder(high_param)}"
            )

        # Valore con :param (riferimento a parametro esterno)
        if isinstance(value, str) and value.startswith(':'):
            param_name = value[1:]
            return f"{column} {op} {self.adapter._placeholder(param_name)}"

        # Valore diretto
        param_name = f"c_{name}"
        params[param_name] = value
        return f"{column} {op} {self.adapter._placeholder(param_name)}"


class Query:
    """Async query builder con API fluent.

    Simile a SqlQuery del vecchio ORM Genropy ma async e semplificato.

    Usage semplice (dict = AND + uguaglianze):
        rows = await table.query(where={'active': True}).fetch()
        row = await table.query(where={'id': 'uuid'}).fetch_one()
        count = await table.query(where={'active': True}).count()

    Usage avanzato (condizioni nominate + espressione):
        # Style 1: dict conditions
        rows = await table.query(
            where_a={'column': 'status', 'op': '=', 'value': 'active'},
            where_b={'column': 'name', 'op': 'ILIKE', 'value': ':pattern'},
            where="$a AND $b",
            pattern='%test%'
        ).fetch()

        # Style 2: flat kwargs (via extract_kwargs)
        rows = await table.query(
            where_a_column='status', where_a_op='!=', where_a_value='deleted',
            where_b_column='name', where_b_op='ILIKE', where_b_value=':pattern',
            where="$a AND $b",
            pattern='%test%'
        ).fetch()
    """

    def __init__(
        self,
        table: Table,
        columns: list[str] | None = None,
        where: dict[str, Any] | str | None = None,
        where_kwargs: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        for_update: bool = False,
        **kwargs: Any,
    ):
        """Initialize Query.

        Args:
            table: Table instance.
            columns: Columns to select (None = all).
            where: WHERE - dict per AND+uguaglianze, stringa per espressione.
            where_kwargs: Named conditions from extract_kwargs(where=True).
            order_by: ORDER BY clause.
            limit: LIMIT clause.
            offset: OFFSET clause.
            for_update: If True, use SELECT FOR UPDATE.
            **kwargs: Parametri per :param references.
        """
        self.table = table
        self.columns = columns
        self.order_by = order_by
        self.limit = limit
        self.offset = offset
        self.for_update = for_update

        # Parse where_kwargs into conditions
        self.conditions = parse_where_kwargs(where_kwargs or {})
        self.params = kwargs

        self.where = where
        self._where_builder = WhereBuilder(table.db.adapter)

    def _build_where(self) -> tuple[str, dict[str, Any]]:
        """Costruisce WHERE clause."""
        return self._where_builder.build(self.where, self.conditions, self.params)

    async def fetch(self) -> list[dict[str, Any]]:
        """Execute query and return all rows."""
        where_sql, params = self._build_where()
        return await self._execute_select(where_sql, params)

    async def fetch_one(self) -> dict[str, Any] | None:
        """Execute query and return first row."""
        where_sql, params = self._build_where()
        rows = await self._execute_select(where_sql, params, limit=1)
        return rows[0] if rows else None

    async def count(self) -> int:
        """Return count of matching rows."""
        where_sql, params = self._build_where()
        return await self._execute_count(where_sql, params)

    async def exists(self) -> bool:
        """Return True if any matching row exists."""
        return await self.count() > 0

    async def _execute_select(
        self,
        where_sql: str,
        params: dict[str, Any],
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Esegue SELECT."""
        cols = ", ".join(self.columns) if self.columns else "*"
        sql = f"SELECT {cols} FROM {self.table.name}"

        if where_sql:
            sql += f" WHERE {where_sql}"
        if self.order_by:
            sql += f" ORDER BY {self.order_by}"

        effective_limit = limit or self.limit
        if effective_limit:
            sql += f" LIMIT {effective_limit}"
        if self.offset:
            sql += f" OFFSET {self.offset}"
        if self.for_update:
            sql += self.table.db.adapter.for_update_clause()

        rows = await self.table.db.adapter.fetch_all(sql, params)
        return [
            self.table._decrypt_fields(self.table._decode_json_fields(row))
            for row in rows
        ]

    async def _execute_count(self, where_sql: str, params: dict[str, Any]) -> int:
        """Esegue COUNT."""
        sql = f"SELECT COUNT(*) as cnt FROM {self.table.name}"
        if where_sql:
            sql += f" WHERE {where_sql}"

        row = await self.table.db.adapter.fetch_one(sql, params)
        return row['cnt'] if row else 0

    async def delete(self, raw: bool = False) -> int:
        """Delete matching rows.

        Args:
            raw: If True, bypass triggers.

        Returns:
            Number of deleted rows.

        Example:
            # Delete with simple condition
            deleted = await table.query(where={'status': 'deleted'}).delete()

            # Delete with complex condition
            deleted = await table.query(
                where_old={'column': 'created_at', 'op': '<', 'value': ':threshold'},
                where="$old",
                threshold='2024-01-01'
            ).delete()

            # Preview then delete (reusable query)
            q = table.query(where={'status': 'archived'})
            records = await q.fetch()  # See what will be deleted
            deleted = await q.delete()  # Then delete
        """
        where_sql, params = self._build_where()

        if raw:
            return await self._execute_delete_raw(where_sql, params)

        return await self._execute_delete_with_triggers(where_sql, params)

    async def _execute_delete_raw(self, where_sql: str, params: dict[str, Any]) -> int:
        """Execute DELETE without triggers."""
        sql = f"DELETE FROM {self.table.name}"
        if where_sql:
            sql += f" WHERE {where_sql}"

        return await self.table.db.adapter.execute(sql, params)

    async def _execute_delete_with_triggers(
        self, where_sql: str, params: dict[str, Any]
    ) -> int:
        """Execute DELETE with triggers for each row."""
        # First fetch rows to get records for triggers
        rows = await self._execute_select(where_sql, params)
        if not rows:
            return 0

        deleted = 0
        for record in rows:
            await self.table.trigger_on_deleting(record)

            # Delete this specific row by primary key
            if self.table.pkey:
                pk_value = record.get(self.table.pkey)
                if pk_value is not None:
                    result = await self.table.db.adapter.delete(
                        self.table.name, {self.table.pkey: pk_value}
                    )
                    if result > 0:
                        await self.table.trigger_on_deleted(record)
                        deleted += 1
            else:
                # No primary key - delete by all columns (risky, but fallback)
                result = await self.table.db.adapter.delete(self.table.name, record)
                if result > 0:
                    await self.table.trigger_on_deleted(record)
                    deleted += 1

        return deleted

    async def update(self, values: dict[str, Any], raw: bool = False) -> int:
        """Update matching rows.

        Args:
            values: Column-value pairs to update.
            raw: If True, bypass triggers and encoding/encryption.

        Returns:
            Number of updated rows.

        Example:
            # Update with simple condition
            updated = await table.query(where={'status': 'pending'}).update({'status': 'processed'})

            # Update with complex condition
            updated = await table.query(
                where_inactive={'column': 'last_login', 'op': '<', 'value': ':date'},
                where="$inactive",
                date='2023-01-01'
            ).update({'status': 'archived'})

            # Preview then update (reusable query)
            q = table.query(where={'status': 'active'})
            records = await q.fetch()  # See what will be updated
            updated = await q.update({'verified': True})  # Then update
        """
        where_sql, params = self._build_where()

        if raw:
            return await self._execute_update_raw(where_sql, params, values)

        return await self._execute_update_with_triggers(where_sql, params, values)

    async def _execute_update_raw(
        self, where_sql: str, params: dict[str, Any], values: dict[str, Any]
    ) -> int:
        """Execute UPDATE without triggers or encoding."""
        adapter = self.table.db.adapter

        # Build SET clause
        set_parts = []
        update_params = dict(params)
        for col, val in values.items():
            param_name = f"upd_{col}"
            set_parts.append(f"{col} = {adapter._placeholder(param_name)}")
            update_params[param_name] = val

        sql = f"UPDATE {self.table.name} SET {', '.join(set_parts)}"
        if where_sql:
            sql += f" WHERE {where_sql}"

        return await adapter.execute(sql, update_params)

    async def _execute_update_with_triggers(
        self, where_sql: str, params: dict[str, Any], values: dict[str, Any]
    ) -> int:
        """Execute UPDATE with triggers for each row."""
        # First fetch rows to get old records for triggers
        rows = await self._execute_select(where_sql, params)
        if not rows:
            return 0

        updated = 0
        for old_record in rows:
            # Create new record with updates
            new_record = dict(old_record)
            new_record.update(values)

            # Trigger and encode
            new_record = await self.table.trigger_on_updating(new_record, old_record)
            encoded = self.table._encrypt_fields(self.table._encode_json_fields(new_record))

            # Update this specific row by primary key
            if self.table.pkey:
                pk_value = old_record.get(self.table.pkey)
                if pk_value is not None:
                    result = await self.table.db.adapter.update(
                        self.table.name, encoded, {self.table.pkey: pk_value}
                    )
                    if result > 0:
                        await self.table.trigger_on_updated(new_record, old_record)
                        updated += 1
            else:
                # No primary key - update by all old columns (risky, but fallback)
                result = await self.table.db.adapter.update(
                    self.table.name, encoded, old_record
                )
                if result > 0:
                    await self.table.trigger_on_updated(new_record, old_record)
                    updated += 1

        return updated


__all__ = ['Query', 'WhereBuilder', 'parse_where_kwargs']
