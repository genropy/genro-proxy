# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Table base class with Columns-based schema (async version)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from genro_toolbox import get_uuid

from .column import Columns

if TYPE_CHECKING:
    from .query import Query
    from .sqldb import SqlDb


class RecordNotFoundError(Exception):
    """Raised when record() finds no matching record and ignore_missing=False."""

    def __init__(self, table: str, pkey: Any = None, where: dict[str, Any] | None = None):
        self.table = table
        self.pkey = pkey
        self.where = where
        if pkey is not None:
            msg = f"Record not found in '{table}' with pkey={pkey!r}"
        elif where:
            msg = f"Record not found in '{table}' with where={where!r}"
        else:
            msg = f"Record not found in '{table}'"
        super().__init__(msg)


class RecordDuplicateError(Exception):
    """Raised when record() finds multiple records and ignore_duplicate=False."""

    def __init__(self, table: str, count: int, pkey: Any = None, where: dict[str, Any] | None = None):
        self.table = table
        self.count = count
        self.pkey = pkey
        self.where = where
        if pkey is not None:
            msg = f"Expected 1 record in '{table}' with pkey={pkey!r}, found {count}"
        elif where:
            msg = f"Expected 1 record in '{table}' with where={where!r}, found {count}"
        else:
            msg = f"Expected 1 record in '{table}', found {count}"
        super().__init__(msg)


class RecordUpdater:
    """Async context manager for record update with locking and triggers.

    Usage:
        async with table.record_to_update(pk) as record:
            record['field'] = 'value'
        # → triggers update() with old_record

        async with table.record_to_update(pk, insert_missing=True) as record:
            record['field'] = 'value'
        # → insert() if not exists, update() if exists

        # With initial values via kwargs:
        async with table.record_to_update(pk, insert_missing=True, name='Test') as record:
            record['other'] = 'value'
        # → record already has name='Test'

    The context manager:
    - __aenter__: SELECT FOR UPDATE (PostgreSQL) or SELECT (SQLite), saves old_record
    - __aexit__: calls insert() or update() with proper trigger chain
    Supports both single-column keys and composite keys (dict).

    Single key: record("uuid-123") or record("uuid-123", pkey="pk")
    Composite:  record({"tenant_id": "t1", "id": "acc1"})

    Args:
        pkey_value: Primary key value or dict for composite keys.
        insert_missing: If True, insert new record if not found (upsert).
        ignore_missing: If True, return empty dict if not found (no error).
        for_update: If True, use SELECT FOR UPDATE (PostgreSQL).
        raw: If True, bypass triggers (use raw_insert/raw_update).
        **kwargs: Initial values to set on the record.
    """

    def __init__(
        self,
        table: Table,
        pkey: str | None,
        pkey_value: Any,
        insert_missing: bool = False,
        ignore_missing: bool = False,
        for_update: bool = True,
        raw: bool = False,
        **kwargs: Any,
    ):
        self.table = table
        self.insert_missing = insert_missing
        self.ignore_missing = ignore_missing
        self.for_update = for_update
        self.raw = raw
        self.kwargs = kwargs
        self.record: dict[str, Any] | None = None
        self.old_record: dict[str, Any] | None = None
        self.is_insert = False

        # Support composite keys: record({"tenant_id": "t1", "id": "acc1"})
        if isinstance(pkey_value, dict):
            self.where: dict[str, Any] = pkey_value
        else:
            self.where = {pkey: pkey_value}  # type: ignore[dict-item]

    async def __aenter__(self) -> dict[str, Any]:
        if self.for_update:
            self.old_record = await self.table.record(
                where=self.where, ignore_missing=True, for_update=True
            )
        else:
            self.old_record = await self.table.record(where=self.where, ignore_missing=True)

        if not self.old_record:
            if self.insert_missing:
                self.record = dict(self.where)  # Initialize with key columns
                self.is_insert = True
            elif self.ignore_missing:
                self.record = {}
            else:
                self.record = {}
            self.old_record = None  # Mark as not found for later checks
        else:
            self.record = dict(self.old_record)

        # Apply kwargs as initial values
        if self.record is not None:
            for k, v in self.kwargs.items():
                if v is not None:
                    self.record[k] = v

        return self.record  # type: ignore[return-value]

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            return

        if not self.record:
            return

        if self.is_insert:
            await self.table.insert(self.record, raw=self.raw)
        elif self.old_record:
            await self.table.update(self.record, self.where, raw=self.raw)


class Table:
    """Base class for async table managers.

    Subclasses define columns via configure() hook and implement
    domain-specific operations.

    Attributes:
        name: Table name in database.
        pkey: Primary key column name (e.g., "pk" or "id").
        db: SqlDb instance reference.
        columns: Column definitions.
    """

    name: str
    pkey: str | None = None

    def __init__(self, db: SqlDb) -> None:
        self.db = db
        if not hasattr(self, "name") or not self.name:
            raise ValueError(f"{type(self).__name__} must define 'name'")

        self.columns = Columns()
        self.configure()

    def configure(self) -> None:
        """Override to define columns. Called during __init__."""
        pass

    # -------------------------------------------------------------------------
    # Primary Key
    # -------------------------------------------------------------------------

    def pkey_value(self, record: dict[str, Any]) -> Any:
        """Get primary key value from a record."""
        return record.get(self.pkey) if self.pkey else None

    def new_pkey_value(self) -> Any:
        """Generate a new primary key value. Override in subclasses for custom pk.

        Default: returns UUID. Tables with autoincrement pk should return None.
        """
        return get_uuid()

    # -------------------------------------------------------------------------
    # Trigger Hooks
    # -------------------------------------------------------------------------

    async def trigger_on_inserting(self, record: dict[str, Any]) -> dict[str, Any]:
        """Called before insert. Can modify record. Return the record to insert.

        Auto-generates pk via new_pkey_value() if pk column is not in record.
        """
        if self.pkey and self.pkey not in record:
            pk_value = self.new_pkey_value()
            if pk_value is not None:
                record[self.pkey] = pk_value
        return record

    async def trigger_on_inserted(self, record: dict[str, Any]) -> None:
        """Called after successful insert."""
        pass

    async def trigger_on_updating(
        self, record: dict[str, Any], old_record: dict[str, Any]
    ) -> dict[str, Any]:
        """Called before update. Can modify record. Return the record to update."""
        return record

    async def trigger_on_updated(self, record: dict[str, Any], old_record: dict[str, Any]) -> None:
        """Called after successful update."""
        pass

    async def trigger_on_deleting(self, record: dict[str, Any]) -> None:
        """Called before delete."""
        pass

    async def trigger_on_deleted(self, record: dict[str, Any]) -> None:
        """Called after successful delete."""
        pass

    # -------------------------------------------------------------------------
    # Schema
    # -------------------------------------------------------------------------

    def create_table_sql(self) -> str:
        """Generate CREATE TABLE IF NOT EXISTS statement."""
        # Check if pk is autoincrement (new_pkey_value returns None)
        is_autoincrement = self.pkey and self.new_pkey_value() is None

        col_defs = []
        for col in self.columns.values():
            if col.name == self.pkey and is_autoincrement and col.type_ == "INTEGER":
                # Use adapter's pk_column for autoincrement primary key
                col_defs.append(self.db.adapter.pk_column(col.name))
            elif col.name == self.pkey:
                # UUID or other non-autoincrement primary key
                col_defs.append(col.to_sql(primary_key=True))
            else:
                col_defs.append(col.to_sql())

        # Add foreign key constraints
        for col in self.columns.values():
            if col.relation_sql and col.relation_table:
                col_defs.append(
                    f'FOREIGN KEY ("{col.name}") REFERENCES {col.relation_table}("{col.relation_pk}")'
                )

        return f"CREATE TABLE IF NOT EXISTS {self.name} (\n    " + ",\n    ".join(col_defs) + "\n)"

    async def create_schema(self) -> None:
        """Create table if not exists."""
        await self.db.execute(self.create_table_sql())

    async def add_column_if_missing(self, column_name: str) -> None:
        """Add column if it doesn't exist (migration helper)."""
        col = self.columns.get(column_name)
        if not col:
            raise ValueError(f"Column '{column_name}' not defined in {self.name}")

        try:
            await self.db.execute(f"ALTER TABLE {self.name} ADD COLUMN {col.to_sql()}")
        except Exception:
            pass  # Column already exists

    async def sync_schema(self) -> None:
        """Sync table schema by adding any missing columns.

        Iterates over all columns defined in configure() and adds them
        if they don't exist in the database. This enables automatic
        schema migration when new columns are added to the codebase.

        Safe to call on every startup - existing columns are ignored.
        Works with both SQLite and PostgreSQL.
        """
        for col in self.columns.values():
            if col.name == self.pkey:
                continue  # Skip primary key, it's created with the table
            # Use IF NOT EXISTS to avoid transaction abort in PostgreSQL
            sql = f"ALTER TABLE {self.name} ADD COLUMN IF NOT EXISTS {col.to_sql()}"
            try:
                await self.db.execute(sql)
            except Exception:
                pass  # SQLite < 3.35 doesn't support IF NOT EXISTS for ADD COLUMN

    # -------------------------------------------------------------------------
    # JSON Encoding/Decoding
    # -------------------------------------------------------------------------

    def _encode_json_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Encode JSON fields for storage."""
        result = dict(data)
        for col_name in self.columns.json_columns():
            if col_name in result and result[col_name] is not None:
                result[col_name] = json.dumps(result[col_name])
        return result

    def _decode_json_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        """Decode JSON fields from storage."""
        result = dict(row)
        for col_name in self.columns.json_columns():
            if col_name in result and result[col_name] is not None:
                result[col_name] = json.loads(result[col_name])
        return result

    def _decode_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Decode JSON fields in multiple rows."""
        return [self._decode_json_fields(row) for row in rows]

    # -------------------------------------------------------------------------
    # Encryption
    # -------------------------------------------------------------------------

    def _encrypt_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Encrypt fields marked with encrypted=True before storage.

        Uses AES-256-GCM encryption. If no encryption key is configured,
        fields are stored as plaintext.
        """
        encrypted_cols = self.columns.encrypted_columns()
        if not encrypted_cols:
            return data

        key = self.db.encryption_key
        if key is None:
            return data

        from proxy.encryption import encrypt_value_with_key

        result = dict(data)
        for col_name in encrypted_cols:
            if col_name in result and result[col_name] is not None:
                value = result[col_name]
                if isinstance(value, str) and not value.startswith("ENC:"):
                    result[col_name] = encrypt_value_with_key(value, key)
        return result

    def _decrypt_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        """Decrypt fields marked with encrypted=True after reading.

        If decryption fails (wrong key, corrupted data), returns the
        encrypted value as-is.
        """
        encrypted_cols = self.columns.encrypted_columns()
        if not encrypted_cols:
            return row

        key = self.db.encryption_key
        if key is None:
            return row

        from proxy.encryption import decrypt_value_with_key

        result = dict(row)
        for col_name in encrypted_cols:
            if col_name in result and result[col_name] is not None:
                value = result[col_name]
                if isinstance(value, str) and value.startswith("ENC:"):
                    try:
                        result[col_name] = decrypt_value_with_key(value, key)
                    except Exception:
                        pass  # Keep encrypted value if decryption fails
        return result

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    async def insert(self, data: dict[str, Any], raw: bool = False) -> int:
        """Insert a row.

        Args:
            data: Record data to insert.
            raw: If True, bypass triggers and encoding/encryption.

        The data dict is mutated: if the pk is auto-generated (UUID or autoincrement),
        it will be populated in data after insert.
        """
        if raw:
            await self.db.insert(self.name, data)
            return 1

        record = await self.trigger_on_inserting(data)
        encoded = self._encrypt_fields(self._encode_json_fields(record))

        # Check if pk is autoincrement (new_pkey_value returns None)
        if self.pkey and self.pkey not in record:
            # Autoincrement: use insert_returning_id to get the generated id
            generated_id = await self.db.insert_returning_id(self.name, encoded, self.pkey)
            if generated_id is not None:
                data[self.pkey] = generated_id
                record[self.pkey] = generated_id
        else:
            # UUID pk already in record from trigger_on_inserting, or no pk
            await self.db.insert(self.name, encoded)
            # Ensure data has the pk (trigger may have added it to record)
            if self.pkey and self.pkey in record and self.pkey not in data:
                data[self.pkey] = record[self.pkey]

        await self.trigger_on_inserted(record)
        return 1

    async def select(
        self,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        raw: bool = False,
    ) -> list[dict[str, Any]]:
        """Select rows.

        Args:
            columns: Columns to select (None = all).
            where: WHERE conditions.
            order_by: ORDER BY clause.
            limit: LIMIT clause.
            raw: If True, skip JSON decoding and decryption.

        Returns:
            List of row dicts.
        """
        rows = await self.db.select(self.name, columns, where, order_by, limit)
        if raw:
            return rows
        return [self._decrypt_fields(self._decode_json_fields(row)) for row in rows]

    async def record(
        self,
        pkey: Any = None,
        where: dict[str, Any] | None = None,
        ignore_missing: bool = False,
        ignore_duplicate: bool = False,
        for_update: bool = False,
        columns: list[str] | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """Fetch a single record by primary key or where conditions.

        This method expects exactly one record. Behavior on edge cases:
        - No record found: raises RecordNotFoundError (or returns {} if ignore_missing=True)
        - Multiple records: raises RecordDuplicateError (or returns first if ignore_duplicate=True)

        Args:
            pkey: Primary key value (uses self.pkey column).
            where: WHERE conditions dict (alternative to pkey).
            ignore_missing: If True, return {} instead of raising RecordNotFoundError.
            ignore_duplicate: If True, return first record instead of raising RecordDuplicateError.
            for_update: If True, use SELECT FOR UPDATE (PostgreSQL).
            columns: Columns to select (None = all).
            raw: If True, skip JSON decoding and decryption.

        Returns:
            Record dict, or {} if not found and ignore_missing=True.

        Raises:
            RecordNotFoundError: If no record found and ignore_missing=False.
            RecordDuplicateError: If multiple records found and ignore_duplicate=False.
            ValueError: If neither pkey nor where is provided.

        Examples:
            # By primary key
            rec = await table.record('uuid-123')

            # By where conditions
            rec = await table.record(where={'email': 'user@example.com'})

            # With ignore_missing (returns {} if not found)
            rec = await table.record('maybe-exists', ignore_missing=True)
            if not rec:
                print("Not found")

            # For update (PostgreSQL lock)
            rec = await table.record('uuid-123', for_update=True)
        """
        # Build where clause
        if pkey is not None:
            if self.pkey is None:
                raise ValueError(f"Table {self.name} has no primary key defined")
            effective_where = {self.pkey: pkey}
        elif where is not None:
            effective_where = where
        else:
            raise ValueError("record() requires either pkey or where argument")

        # Execute query
        if for_update:
            # select_for_update already handles decoding/decryption
            row = await self.select_for_update(effective_where, columns)
            if row is None:
                rows: list[dict[str, Any]] = []
            else:
                rows = [row]
        else:
            # Fetch with limit 2 to detect duplicates
            rows = await self.db.select(self.name, columns, effective_where, limit=2)
            if not raw:
                rows = [self._decrypt_fields(self._decode_json_fields(r)) for r in rows]

        # Handle results
        if len(rows) == 0:
            if ignore_missing:
                return {}
            raise RecordNotFoundError(self.name, pkey, where)

        if len(rows) > 1:
            if ignore_duplicate:
                return rows[0]
            # Count actual duplicates for error message
            count = await self.db.count(self.name, effective_where)
            raise RecordDuplicateError(self.name, count, pkey, where)

        return rows[0]

    async def select_for_update(
        self,
        where: dict[str, Any],
        columns: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Select single row with FOR UPDATE lock (PostgreSQL) or regular select (SQLite).

        Args:
            where: WHERE conditions to identify the row.
            columns: Columns to select (None = all).

        Returns:
            Row dict or None if not found.
        """
        cols_sql = ", ".join(columns) if columns else "*"

        conditions = [f"{k} = {self.db._placeholder(k)}" for k in where]
        where_sql = " AND ".join(conditions)
        lock_clause = self.db.adapter.for_update_clause()

        query = f"SELECT {cols_sql} FROM {self.name} WHERE {where_sql}{lock_clause}"
        row = await self.db.fetch_one(query, where)
        return self._decrypt_fields(self._decode_json_fields(row)) if row else None

    def record_to_update(
        self,
        pkey_value: Any,
        insert_missing: bool = False,
        ignore_missing: bool = False,
        for_update: bool = True,
        raw: bool = False,
        **kwargs: Any,
    ) -> RecordUpdater:
        """Return async context manager for record update.

        Args:
            pkey_value: Primary key value, or dict for composite keys.
            insert_missing: If True, insert new record if not found (upsert).
            ignore_missing: If True, return empty dict if not found (no error).
            for_update: If True, use SELECT FOR UPDATE (PostgreSQL).
            raw: If True, bypass triggers (use raw insert/update).
            **kwargs: Initial values to set on the record.

        Returns:
            RecordUpdater context manager.

        Usage:
            # Single key:
            async with table.record_to_update('uuid-123') as rec:
                rec['name'] = 'New Name'

            # Composite key (dict):
            async with table.record_to_update({'tenant_id': 't1', 'id': 'acc1'}) as rec:
                rec['host'] = 'smtp.example.com'

            # Upsert (insert if missing):
            async with table.record_to_update({'tenant_id': 't1', 'id': 'new'}, insert_missing=True) as rec:
                rec['host'] = 'smtp.new.com'

            # With initial values:
            async with table.record_to_update('pk', insert_missing=True, name='Test') as rec:
                rec['other'] = 'value'
        """
        # For composite keys (dict), pkey is not needed
        if isinstance(pkey_value, dict):
            return RecordUpdater(
                self, None, pkey_value, insert_missing, ignore_missing, for_update, raw, **kwargs
            )

        # For single key, use self.pkey
        if self.pkey is None:
            raise ValueError(f"Table {self.name} has no primary key defined")

        return RecordUpdater(
            self, self.pkey, pkey_value, insert_missing, ignore_missing, for_update, raw, **kwargs
        )

    async def update(
        self, values: dict[str, Any], where: dict[str, Any], raw: bool = False
    ) -> int:
        """Update rows.

        Args:
            values: Column-value pairs to update.
            where: WHERE conditions.
            raw: If True, bypass triggers, encoding, and encryption.

        Returns:
            Number of affected rows.
        """
        if raw:
            return await self.db.update(self.name, values, where)

        old_record = await self.select_for_update(where)
        record = await self.trigger_on_updating(values, old_record or {})
        encoded = self._encrypt_fields(self._encode_json_fields(record))
        result = await self.db.update(self.name, encoded, where)
        if result > 0 and old_record:
            await self.trigger_on_updated(record, old_record)
        return result

    async def batch_update(
        self,
        pkeys: list[Any],
        updater: dict[str, Any] | None = None,
        raw: bool = False,
    ) -> int:
        """Update multiple records by primary key.

        Two modes based on raw parameter:
        - raw=False (default): 1 SELECT + N UPDATE with triggers for each record.
          The updater can be a dict or callable.
        - raw=True: Single UPDATE...WHERE IN, no triggers, no encoding/encryption.
          The updater must be a dict.

        When updater is a callable (raw=False only):
        - Receives the mutable record dict
        - Can modify multiple fields in place
        - Return False to skip this record's update
        - Return True/None to proceed with update

        Args:
            pkeys: List of primary key values to update.
            updater: Dict of field:value, or callable(record) -> bool|None.
            raw: If True, bypass triggers/encoding/encryption (single SQL).

        Returns:
            Number of records updated.
        """
        if not pkeys:
            return 0

        pkey = self.pkey
        if pkey is None:
            raise ValueError(f"Table {self.name} has no primary key defined")

        # Raw mode: single UPDATE statement, no triggers
        if raw:
            if updater is None or callable(updater):
                raise ValueError("raw=True requires updater to be a dict")

            set_parts = [f"{k} = {self.db._placeholder(k)}" for k in updater]
            set_clause = ", ".join(set_parts)

            params: dict[str, Any] = dict(updater)
            params.update({f"pk_{i}": pk for i, pk in enumerate(pkeys)})
            placeholders = ", ".join(
                f"{self.db._placeholder(f'pk_{i}')}" for i in range(len(pkeys))
            )

            query = f"UPDATE {self.name} SET {set_clause} WHERE {pkey} IN ({placeholders})"
            return await self.db.execute(query, params)

        # Normal mode: SELECT + N updates with triggers
        params = {}
        params.update({f"pk_{i}": pk for i, pk in enumerate(pkeys)})
        placeholders = ", ".join(
            f"{self.db._placeholder(f'pk_{i}')}" for i in range(len(pkeys))
        )
        query = f"SELECT * FROM {self.name} WHERE {pkey} IN ({placeholders})"
        rows = await self.db.fetch_all(query, params)

        records_by_pk = {row[pkey]: dict(row) for row in rows}

        updated = 0
        for pk_value in pkeys:
            old_record = records_by_pk.get(pk_value)
            if not old_record:
                continue

            new_record = dict(old_record)

            # Apply updater
            if updater is not None:
                if callable(updater):
                    result = updater(new_record)
                    if result is False:
                        continue  # Skip this record
                else:
                    new_record.update(updater)

            # Triggers and encoding
            new_record = await self.trigger_on_updating(new_record, old_record)
            encoded = self._encrypt_fields(self._encode_json_fields(new_record))
            result = await self.db.update(self.name, encoded, {pkey: pk_value})
            if result > 0:
                await self.trigger_on_updated(new_record, old_record)
                updated += 1

        return updated

    async def delete(self, where: dict[str, Any], raw: bool = False) -> int:
        """Delete rows.

        Args:
            where: WHERE conditions.
            raw: If True, bypass triggers.

        Returns:
            Number of deleted rows.
        """
        if raw:
            return await self.db.delete(self.name, where)

        rec = await self.record(where=where, ignore_missing=True)
        if rec:
            await self.trigger_on_deleting(rec)
        result = await self.db.delete(self.name, where)
        if result > 0 and rec:
            await self.trigger_on_deleted(rec)
        return result

    async def exists(self, where: dict[str, Any]) -> bool:
        """Check if row exists."""
        return await self.db.exists(self.name, where)

    async def count(self, where: dict[str, Any] | None = None) -> int:
        """Count rows."""
        return await self.db.count(self.name, where)

    # -------------------------------------------------------------------------
    # Query Builder (fluent API)
    # -------------------------------------------------------------------------

    def query(
        self,
        columns: list[str] | None = None,
        where: dict[str, Any] | str | None = None,
        where_kwargs: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        for_update: bool = False,
        **kwargs: Any,
    ) -> "Query":
        """Return a Query object for fluent API.

        Similar to the old Genropy ORM's query() method.

        Args:
            columns: Columns to select (None = all).
            where: WHERE - dict per AND+uguaglianze, stringa per espressione.
            where_kwargs: Named conditions (from @extract_kwargs(where=True)).
            order_by: ORDER BY clause.
            limit: LIMIT clause.
            offset: OFFSET clause.
            for_update: If True, use SELECT FOR UPDATE.
            **kwargs: Parametri per :param references.

        Returns:
            Query object with fetch(), fetch_one(), count(), exists() methods.

        Examples:
            # Simple (dict = AND with equality)
            rows = await table.query(where={'active': True}).fetch()
            row = await table.query(where={'id': pk}).fetch_one()

            # Advanced with dict conditions
            rows = await table.query(
                where_a={'column': 'status', 'op': '!=', 'value': 'deleted'},
                where_b={'column': 'name', 'op': 'ILIKE', 'value': ':search'},
                where="$a AND $b",
                search='%test%'
            ).fetch()

            # Advanced with flat kwargs (via @extract_kwargs(where=True))
            rows = await table.query(
                where_a_column='status', where_a_op='!=', where_a_value='deleted',
                where_b_column='name', where_b_op='ILIKE', where_b_value=':search',
                where="$a AND $b",
                search='%test%'
            ).fetch()
        """
        from .query import Query

        # Parse where_* kwargs manually if where_kwargs not provided
        if where_kwargs is None:
            where_kwargs = {}
            remaining_kwargs = {}
            for k, v in kwargs.items():
                if k.startswith('where_'):
                    where_kwargs[k[6:]] = v  # Remove 'where_' prefix
                else:
                    remaining_kwargs[k] = v
            kwargs = remaining_kwargs

        return Query(
            table=self,
            columns=columns,
            where=where,
            where_kwargs=where_kwargs,
            order_by=order_by,
            limit=limit,
            offset=offset,
            for_update=for_update,
            **kwargs,
        )

    # -------------------------------------------------------------------------
    # Raw Query
    # -------------------------------------------------------------------------

    async def fetch_one(
        self, query: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Execute query, return single row with JSON decode and decryption."""
        row = await self.db.fetch_one(query, params)
        if row is None:
            return None
        return self._decrypt_fields(self._decode_json_fields(row))

    async def fetch_all(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute query, return all rows with JSON decode and decryption."""
        rows = await self.db.fetch_all(query, params)
        return [self._decrypt_fields(self._decode_json_fields(row)) for row in rows]

    async def execute(self, query: str, params: dict[str, Any] | None = None) -> int:
        """Execute raw query, return affected row count."""
        return await self.db.execute(query, params)


__all__ = ["Table", "RecordUpdater", "RecordNotFoundError", "RecordDuplicateError"]
