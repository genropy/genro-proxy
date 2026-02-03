# Analisi Metodi SQL Subsystem

**Data**: 2026-02-03
**Status**: 🔴 DA REVISIONARE

## Obiettivo

Analisi critica dei metodi nelle tre classi principali del sottosistema SQL:
- `DbAdapter` (base.py)
- `SqlDb` (sqldb.py)
- `Table` (table.py)

Valutazione di: utilità, valore aggiunto, duplicazioni, collocazione.

---

## 1. Riepilogo Duplicazioni

| Metodo | DbAdapter | SqlDb | Table | Note |
|--------|-----------|-------|-------|------|
| `execute()` | ✅ Implementa | ✅ Passthrough | ✅ Passthrough | SqlDb e Table sono wrapper |
| `fetch_one()` | ✅ Implementa | ✅ Passthrough | ✅ +decode JSON | Table aggiunge decode |
| `fetch_all()` | ✅ Implementa | ✅ Passthrough | ✅ +decode JSON | Table aggiunge decode |
| `commit()` | ✅ Implementa | ✅ Passthrough | - | SqlDb wrapper inutile |
| `rollback()` | ✅ Implementa | ✅ Passthrough | - | SqlDb wrapper inutile |
| `insert()` | ✅ Implementa | - | ✅ +trigger/encoding | Table aggiunge valore |
| `select()` | ✅ Implementa | - | ✅ +decrypt/decode | Table aggiunge valore |
| `select_one()` | ✅ Implementa | - | ✅ +decrypt/decode | Table aggiunge valore |
| `update()` | ✅ Implementa | - | ✅ +trigger/encoding | Table aggiunge valore |
| `delete()` | ✅ Implementa | - | ✅ +trigger | Table aggiunge valore |
| `exists()` | ✅ Implementa | - | ✅ Passthrough | Table è wrapper |
| `count()` | ✅ Implementa | - | ✅ Passthrough | Table è wrapper |

---

## 2. Analisi per Classe

### 2.1 DbAdapter (base.py) - 280 righe

Layer corretto per query SQL. Nessuna duplicazione interna.

#### Metodi con Alto Valore

| Metodo | Linee | Descrizione | Valore |
|--------|-------|-------------|--------|
| `connect()` | 43-50 | Acquisisce connessione + BEGIN | ALTO |
| `close()` | 53-59 | COMMIT + rilascia | ALTO |
| `shutdown()` | 62-69 | Chiude pool/file | ALTO |
| `commit()` | 101-107 | Commit esplicito mid-transaction | MEDIO |
| `rollback()` | 110-116 | ROLLBACK + rilascia | ALTO |
| `execute()` | 72-74 | Query raw | ALTO |
| `fetch_one()` | 82-85 | Select singola riga | ALTO |
| `fetch_all()` | 88-93 | Select multiple righe | ALTO |
| `insert()` | 134-148 | INSERT helper | ALTO |
| `select()` | 170-205 | SELECT con WHERE/ORDER/LIMIT | ALTO |
| `select_one()` | 207-215 | SELECT LIMIT 1 | ALTO |
| `update()` | 217-237 | UPDATE helper | ALTO |
| `delete()` | 239-251 | DELETE helper | ALTO |
| `exists()` | 253-258 | EXISTS check | ALTO |
| `count()` | 260-279 | COUNT query | ALTO |

#### Metodi con Basso Utilizzo

| Metodo | Linee | Descrizione | Utilizzo |
|--------|-------|-------------|----------|
| `execute_many()` | 77-79 | Batch insert | RARO |
| `execute_script()` | 96-98 | Multi-statement | SOLO SCHEMA |
| `insert_returning_id()` | 150-168 | Per autoincrement | SPECIFICO |

#### Metodi Polimorfici (Override in Subclass)

| Metodo | SQLite | PostgreSQL |
|--------|--------|------------|
| `pk_column()` | `INTEGER PRIMARY KEY` | `SERIAL PRIMARY KEY` |
| `for_update_clause()` | `""` | `" FOR UPDATE"` |
| `placeholder` | `:name` | `%(name)s` |

**Conclusione DbAdapter**: Ben progettato, nessuna rimozione necessaria.

---

### 2.2 SqlDb (sqldb.py) - 257 righe

Manager del database con registry tabelle e context manager transazioni.

#### Metodi con Alto Valore

| Metodo | Linee | Descrizione | Valore |
|--------|-------|-------------|--------|
| `__init__()` | 60-70 | Setup con adapter | ALTO |
| `encryption_key` | 72-77 | Property da parent | ALTO |
| `connect()` | 83-85 | Passthrough necessario | ALTO |
| `close()` | 87-89 | Passthrough necessario | ALTO |
| `shutdown()` | 91-93 | Passthrough necessario | ALTO |
| `connection()` | 95-115 | Context manager | ALTO |
| `add_table()` | 121-135 | Registry tabelle | ALTO |
| `discover()` | 137-161 | Auto-discovery | ALTO |
| `table()` | 163-177 | Get table by name | ALTO |
| `check_structure()` | 179-182 | Create all tables | ALTO |

#### Metodi Passthrough (Candidati a Rimozione)

| Metodo | Linee | Codice | Alternativa |
|--------|-------|--------|-------------|
| `execute()` | 188-190 | `return await self.adapter.execute(...)` | `db.adapter.execute()` |
| `fetch_one()` | 192-196 | `return await self.adapter.fetch_one(...)` | `db.adapter.fetch_one()` |
| `fetch_all()` | 198-202 | `return await self.adapter.fetch_all(...)` | `db.adapter.fetch_all()` |
| `commit()` | 204-206 | `await self.adapter.commit()` | `db.adapter.commit()` |
| `rollback()` | 208-210 | `await self.adapter.rollback()` | `db.adapter.rollback()` |

**Analisi Passthrough:**

```python
# SqlDb.execute() - PASSTHROUGH PURO
async def execute(self, query: str, params: dict[str, Any] | None = None) -> int:
    return await self.adapter.execute(query, params)

# Stesso pattern per fetch_one, fetch_all, commit, rollback
```

**Pro rimozione:**
- Elimina 23 righe di codice
- API più esplicita (`db.adapter.execute()` invece di `db.execute()`)
- Riduce superficie API di SqlDb

**Contro rimozione:**
- Breaking change per codice esistente
- `db.execute()` è più breve di `db.adapter.execute()`

**Conclusione SqlDb**: 5 metodi passthrough eliminabili. Valutare breaking change.

---

### 2.3 Table (table.py) - 575 righe

Base class per tabelle con trigger, encoding, encryption.

#### Metodi con Alto Valore

| Metodo | Linee | Descrizione | Valore Aggiunto |
|--------|-------|-------------|-----------------|
| `__init__()` | 105-111 | Setup con Columns | ALTO |
| `configure()` | 113-115 | Hook per definizione colonne | ALTO |
| `pkey_value()` | 121-123 | Estrae PK da record | MEDIO |
| `new_pkey_value()` | 125-130 | Genera UUID per PK | ALTO |
| `trigger_on_inserting()` | 136-145 | Pre-insert hook | ALTO |
| `trigger_on_inserted()` | 147-149 | Post-insert hook | ALTO |
| `trigger_on_updating()` | 151-155 | Pre-update hook | ALTO |
| `trigger_on_updated()` | 157-159 | Post-update hook | ALTO |
| `trigger_on_deleting()` | 161-163 | Pre-delete hook | ALTO |
| `trigger_on_deleted()` | 165-167 | Post-delete hook | ALTO |
| `create_table_sql()` | 173-196 | Genera DDL | ALTO |
| `create_schema()` | 198-200 | CREATE TABLE | ALTO |
| `sync_schema()` | 213-231 | Migration helper | ALTO |
| `insert()` | 316-340 | INSERT + trigger + encoding | ALTO |
| `select()` | 342-351 | SELECT + decrypt + decode | ALTO |
| `select_one()` | 353-360 | SELECT one + decrypt + decode | ALTO |
| `select_for_update()` | 362-385 | SELECT FOR UPDATE | ALTO |
| `record()` | 387-424 | Context manager upsert | ALTO |
| `update()` | 426-437 | UPDATE + trigger + encoding | ALTO |
| `update_batch()` | 439-493 | Batch con trigger | MEDIO |
| `delete()` | 533-542 | DELETE + trigger | ALTO |

#### Metodi Passthrough (Candidati a Rimozione)

| Metodo | Linee | Codice | Alternativa |
|--------|-------|--------|-------------|
| `exists()` | 544-546 | `return await self.db.adapter.exists(...)` | `table.db.adapter.exists()` |
| `count()` | 548-550 | `return await self.db.adapter.count(...)` | `table.db.adapter.count()` |

#### Metodi con Valore Parziale (Incoerenti)

| Metodo | Linee | Problema |
|--------|-------|----------|
| `fetch_one()` | 556-561 | Decodifica JSON ma **NON decripta** |
| `fetch_all()` | 563-568 | Decodifica JSON ma **NON decripta** |
| `execute()` | 570-572 | Puro passthrough |

**Incoerenza API:**

```python
# Table.select_one() - CORRETTO
row = await self.db.adapter.select_one(self.name, columns, where)
return self._decrypt_fields(self._decode_json_fields(row)) if row else None
# ✅ Decripta + Decodifica

# Table.fetch_one() - INCOERENTE
row = await self.db.adapter.fetch_one(query, params)
return self._decode_json_fields(row) if row else None
# ❌ Solo Decodifica, NO decrypt!
```

**Conseguenza:** Un utente che usa `table.fetch_one()` per query custom non ottiene i campi decriptati, mentre `table.select_one()` li decripta.

#### Metodi Poco Usati

| Metodo | Linee | Utilizzo |
|--------|-------|----------|
| `update_batch_raw()` | 495-531 | RARO - bypassa trigger |
| `add_column_if_missing()` | 202-211 | RARO - sostituito da sync_schema |

**Conclusione Table**:
- 2 passthrough eliminabili (exists, count)
- 3 metodi incoerenti (fetch_one, fetch_all, execute) da fixare o rimuovere
- 1 metodo deprecabile (add_column_if_missing)

---

## 3. Raccomandazioni

### 3.1 Decisioni su SqlDb

#### MANTENERE i passthrough (execute, fetch_one, fetch_all, commit, rollback)

**Motivazioni:**

1. **Incapsulamento**: `db.adapter` non deve essere esposto esternamente
2. **Estensibilità**: Possibilità futura di aggiungere logica pre/post chiamata
3. **API stabile**: Se l'adapter cambia internamente, l'API di SqlDb resta invariata
4. **Semplicità d'uso**: `db.execute()` è più naturale di `db.adapter.execute()`

**Esempio di estensibilità futura:**

```python
async def execute(self, query: str, params: dict | None = None) -> int:
    # Pre-processing futuro (es. logging, metrics)
    self._log_query(query)
    result = await self.adapter.execute(query, params)
    # Post-processing futuro (es. audit)
    return result
```

### 3.2 Decisioni su Table.exists() e Table.count()

#### MANTENERE per estensibilità futura

**Stato attuale:**
```python
async def exists(self, where: dict) -> bool:
    return await self.db.adapter.exists(self.name, where)

async def count(self, where: dict | None = None) -> int:
    return await self.db.adapter.count(self.name, where)
```

**Motivazioni per mantenerli:**

1. **Coerenza API**: Stessa logica di SqlDb - non esporre l'adapter direttamente
2. **Estensibilità**: Punto di estensione per parametri aggiuntivi futuri
3. **Comodità**: `table.exists({"id": "1"})` vs `db.adapter.exists("tablename", {"id": "1"})`

**Possibile estensione futura:**
```python
async def count(
    self,
    where: dict | None = None,
    distinct: str | None = None,  # COUNT(DISTINCT column)
) -> int

async def exists(
    self,
    where: dict | None = None,
    or_where: dict | None = None,  # OR conditions
) -> bool
```

### 3.3 Decisioni su Table.fetch_one/fetch_all/execute

#### Opzione A: Rimuovere Table.fetch_one/fetch_all/execute

L'utente usa direttamente `table.db.adapter.fetch_one()` per query raw.

#### Opzione B: Rendere coerenti (aggiungere decrypt)

```python
async def fetch_one(self, query, params=None):
    row = await self.db.adapter.fetch_one(query, params)
    return self._decrypt_fields(self._decode_json_fields(row)) if row else None
    #      ^^^^^^^^^^^^^^^^^ aggiunto
```

**Raccomandazione:** Opzione A - rimuovere. Query raw dovrebbero usare l'adapter direttamente.

### 3.4 Parametro `raw` nei Metodi CRUD

Aggiungere parametro `raw: bool = False` ai metodi CRUD per bypassare trigger/encoding/encryption in situazioni di fix/migration:

```python
async def insert(self, data: dict, raw: bool = False) -> int
async def update(self, values: dict, where: dict, raw: bool = False) -> int
async def delete(self, where: dict, raw: bool = False) -> int
async def batch_update(self, pkeys: list, updater=None, raw: bool = False) -> int
```

Con `raw=True`:
- **Niente trigger** (inserting/inserted, updating/updated, deleting/deleted)
- **Niente encoding** JSON
- **Niente encryption**
- Accesso diretto all'adapter

**Uso**: Solo per fix, migration, situazioni eccezionali. Da usare con cautela.

### 3.5 Refactoring `batch_update`

Rinominare `update_batch` → `batch_update` e unificare con `update_batch_raw`:

```python
async def batch_update(
    self,
    pkeys: list[Any],
    updater: dict[str, Any] | Callable[[dict], bool | None] | None = None,
    raw: bool = False,
) -> int:
```

**Comportamento `updater`:**

| Tipo | Esempio | Descrizione |
|------|---------|-------------|
| `dict` | `{"status": "archived", "count": 0}` | Valori statici per tutti i record |
| `Callable` | `lambda r: r.update({"x": r["x"]+1})` | Logica custom per-record |

**Comportamento Callable:**
- Riceve record mutabile, può modificare più campi
- Ritorna `False` → **salta** update per questo record
- Ritorna `None`/`True`/niente → **procede** con update

**Modalità:**

| `raw` | Accessi DB | Trigger | Note |
|-------|------------|---------|------|
| `False` | N+1 (1 SELECT + N UPDATE) | ✅ Sì | Normale |
| `True` | 1 (single UPDATE...WHERE IN) | ❌ No | Solo dict, no callable |

**Esempio:**
```python
# Dict - valori statici
await table.batch_update(pkeys, {"archived": True})

# Callable - logica per-record con skip
def update_if_active(rec):
    if not rec["active"]:
        return False  # Skip
    rec["processed"] = True
    rec["count"] = rec["count"] + 1

await table.batch_update(pkeys, update_if_active)

# Raw - single query, niente trigger
await table.batch_update(pkeys, {"archived": True}, raw=True)
```

### 3.6 Deprecazioni

| Metodo | Motivo | Sostituto |
|--------|--------|-----------|
| `Table.add_column_if_missing()` | Sostituito da sync_schema | `sync_schema()` |
| `Table.update_batch()` | Rinominato | `batch_update()` |
| `Table.update_batch_raw()` | Unificato | `batch_update(..., raw=True)` |
| `Table.fetch_one()` | Incoerente (no decrypt) | `table.db.fetch_one()` |
| `Table.fetch_all()` | Incoerente (no decrypt) | `table.db.fetch_all()` |
| `Table.execute()` | Passthrough inutile | `table.db.execute()` |

---

## 4. Impatto Breaking Changes

### Se si rimuovono i passthrough da SqlDb:

```python
# PRIMA
await db.execute("INSERT INTO ...")
await db.commit()

# DOPO
await db.adapter.execute("INSERT INTO ...")
await db.adapter.commit()
```

**File da aggiornare:**
- `tests/sql/conftest.py` - usa `db.execute()` per DROP TABLE
- Eventuali altri test e codice applicativo

### Se si rimuovono exists/count da Table:

```python
# PRIMA
exists = await table.exists({"id": "123"})

# DOPO
exists = await table.db.adapter.exists(table.name, {"id": "123"})
```

---

## 5. Metriche Finali

| Classe | Righe Attuali | Righe Dopo Cleanup | Riduzione |
|--------|---------------|-------------------|-----------|
| DbAdapter | 280 | 280 | 0% |
| SqlDb | 257 | 234 | -9% |
| Table | 575 | 551 | -4% |
| **Totale** | **1112** | **1065** | **-4%** |

---

## 6. Decisioni Richieste

1. **Rimuovere passthrough da SqlDb?** (execute, fetch_one, fetch_all, commit, rollback)
2. **Rimuovere passthrough da Table?** (exists, count)
3. **Rimuovere o fixare Table.fetch_one/fetch_all/execute?**
4. **Deprecare Table.add_column_if_missing e update_batch_raw?**

---

**Prossimi passi:** Attendere decisione dell'utente prima di procedere con modifiche.
