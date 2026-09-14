# Database Documentation

## Connectivity & configuration

One configuration path: `settings.config.get_db_config()` (environment-over-
settings precedence) feeding `database.bootstrap` for lifecycle operations and
the connection pools for runtime access. See `docs/ARCHITECTURE.md`.

## Schema bootstrap (DB-01)

The single authoritative mechanism is `database.bootstrap.bootstrap_database(cfg)`:

1. Creates the database if missing (UTF8, template0) — never drops anything.
2. Verifies extension preflight (`plpgsql`; `pg_trgm` deliberately **not**
   required — see below).
3. Runs all pending versioned migrations in order, each in its own
   transaction, recorded in `schema_migrations`.

There is no import-time DDL anywhere; nothing touches the database until an
entry point explicitly calls the bootstrap. The legacy `createsTables.py`
module (import-time DDL with hardcoded credentials and a broken creation
order that violated foreign-key dependencies) was removed.

## Migrations (DB-02)

`database/migrations/` contains ordered migrations (`m0001` … `m0009`). Each
module defines `version`, `name` and `upgrade(conn)`. The runner
(`database/migration_runner.py`) applies pending migrations transactionally
and records versions. Downgrades are best-effort where practical.

| Version | Name | Purpose |
|---|---|---|
| 0001 | initial_schema | all application tables in dependency order |
| 0002 | performance_indexes | DB-06 indexes (below) |
| 0003 | auth_tables | users, sessions, audit_log |
| 0004 | remove_pg_trgm | DB-07 option B |
| 0005 | paths_error_message | column used by re-analysis |
| 0006 | job_infrastructure | job queue tables |
| 0007 | provenance_hierarchy_status | provenance hierarchy columns |
| 0008 | widen_file_size | paths.file_size BIGINT |
| 0009 | analyst_categorization | analyst (manual) categorization layer — see below |

### Upgrades (existing installations)

Migrations run at two moments:

1. **First install** — the setup wizard calls `bootstrap_database()`
   (create database if missing + apply all migrations).
2. **Every subsequent startup** — `ensure_system_initialized()`
   (`core/initialization.py`) calls `upgrade_database_schema()`, which
   applies any *pending* migrations through the same runner. Pulling new
   code and restarting (`start.bat` / `python run_web.py`) is therefore
   the entire upgrade procedure; no manual step is required. The check is
   idempotent (no-op when the schema is current) and tolerant: if the
   database is unreachable at startup the application still boots and the
   problem is surfaced by the setup gate / health checks /
   `python verify_readiness.py` (which reports pending migrations).

To apply pending migrations manually without starting the server, from the
repository root with the virtual environment active:

```
python -c "from settings.config import get_database_config; from database.bootstrap import bootstrap_database; db = get_database_config(); print(bootstrap_database({'host': db.host, 'port': int(db.port), 'user': db.user, 'password': db.password, 'database': db.database}))"
```

## Analyst categorization tables (0009)

`analyst_categories`, `analyst_file_categories` and
`analyst_categorization_log` implement the analyst-driven **manual**
categorization layer. They share no table, column or FK with the smart
classification taxonomy (`categorys` / `words_categorys` / `keywords`) — the
two category systems are deliberately unmergeable. Full design:
[ANALYST_CATEGORIZATION.md](ANALYST_CATEGORIZATION.md).

## Content identity & deduplication (DB-03/DB-04)

* **Hashing** (`core/hashing.py`): streamed SHA-256 of file bytes, constant
  memory for any file size. Failures raise `HashingError` — the pipeline
  never substitutes metadata-derived or time-based pseudo-identifiers.
* **Identity model**: `identity = (content_hash, source_id, side_id)`,
  enforced by `UNIQUE (hash, source_id, side_id)` on `hashs`.
* **Duplicate semantics** (`database/services/dedup_service.py` — the only
  dedup path): content is a duplicate iff a `hashs` row with the same
  identity exists **and has at least one live `paths` row**. Orphaned hash
  rows (all paths deleted) do not make content a duplicate.
* Concurrency: `ON CONFLICT DO NOTHING` hash registration + the unique
  constraint make concurrent ingestion of identical content safe.

## Delete / re-ingest lifecycle (DB-05)

`DeduplicationService.delete_path(path_id)` deletes the path and its child
rows and removes the hash in the **same transaction** when no other path
references it. The HTTP delete endpoints perform the same refcount cleanup
(the audit found a tuple-vs-int comparison bug that never cleaned orphans).
Acceptance workflow (automated test): ingest → verify → delete → re-ingest
identical file → new valid record exists.

## Indexes (DB-06)

| Index | Purpose |
|---|---|
| `words_paths(path_id)` | per-file word listing, cascade deletes |
| `words_paths(word_id)` | inverted lookup: files containing a word (search) |
| `words_paths(path_id, word_id)` | uniqueness checks / upserts |
| `paths(hash_id)` | dedup join paths↔hashs |
| `paths(file_name)` | file-name search |
| `paths(file_path)` | ingestion existence checks |
| `paths(file_type)` | taxonomy filters, analytics grouping |
| `titles_content(path_id)` | title joins in listings |
| `hashs(hash, source_id, side_id)` | identity lookups |
| `audit_log(created_at DESC)` | recent-activity queries |

Each index was verified with `EXPLAIN` on the disposable test database
(scripts/performance_benchmarks.py); no redundant duplicates are created.

## pg_trgm decision (DB-07)

**Option B — removed.** No runtime query path used trigram similarity; the
GIN trigram index only added an operational dependency unavailable on minimal
PostgreSQL installs. Migration 0004 drops the index and the extension. Search
uses the application's word-index tables (words/words_paths) and BM25-style
Python ranking, which is the architecture the data model was built for.

## Blob serialization (DB-08)

`core/serialization.py` is the only blob codec. New writes are JSON. Legacy
pickle payloads remain readable solely through a restricted unpickler that
permits only plain built-in data (no globals, no reduction → no code
execution). `scripts/repair_data.py` rewrites legacy blobs to JSON.

## Backup & disaster recovery (Phase 21)

```bash
# backup (custom format, compressed)
pg_dump -Fc -U "$DB_USER" -h "$DB_HOST" "$DB_NAME" > backup_$(date +%F).dump

# restore (verify first with --list)
pg_restore --list backup_$(date +%F).dump
pg_restore -U "$DB_USER" -h "$DB_HOST" -d "$DB_NAME" --clean --if-exists backup_$(date +%F).dump
```

Policy guidance: nightly `pg_dump -Fc`, 14-day retention, off-host storage,
encrypted at rest (filesystem/disk level), and a quarterly restore drill —
a backup that has never been restored is not a verified backup. The JSON
backup export/import endpoints complement (not replace) `pg_dump`: they are
for selective data recovery, are allowlist-validated and transactional.

## Data repair (Phase 22)

`python scripts/repair_data.py [--dry-run] [--backup]`:

* detects double-stored content and metadata-polluted records,
* removes orphaned hash rows (the delete/re-ingest defect),
* rewrites legacy pickle blobs to JSON,
* reports everything; `--dry-run` prints the plan without changing data,
  `--backup` dumps affected tables first. Historical data is never modified
  silently.
