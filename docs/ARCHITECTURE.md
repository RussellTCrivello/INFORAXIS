# Architecture

Single-source-of-truth boundaries that every feature must respect:

| Concern | Owner | Description |
|---|---|---|
| Config | `settings/` (`SettingsManager`, `settings_models`, `config.py`) | defaults < persisted file < environment (`DB_*`, `FLASK_*`). Env wins at read time. |
| DB connectivity | `database/database/database.py` + `database/database/config.py` | pooled connections; `get_db_config()` is the only credential resolver. |
| Schema | `database/bootstrap.py` + `database/migration_runner.py` + `database/migrations/` | versioned, transactional migrations; no import-time DDL. |
| Paths | `core/path_safety.py` | filesystem-boundary validation. |
| Archives | `core/archive_safety.py` | the only extraction path. |
| Hashing | `core/hashing.py` | streamed SHA-256, no fallback identities. |
| Dedup | `database/services/dedup_service.py` | identity = (hash, source, side); live-path check. |
| Serialization | `core/serialization.py` | JSON blobs; restricted unpickler for legacy reads. |
| SQL | `core/sql_safety.py` | parameterized values; identifier allowlist. |
| AuthN/AuthZ | `core/services/auth_service.py`, `core/security/flask_ext.py` | middleware default-deny + decorators. |
| Errors | `core/errors.py` | sanitized client messages + correlation ids. |
| Readers | `reader_file/readers/registry.py` | `@register_reader` with declared extensions; router derives supported set. |
| Search | `Api/services/search_service.py` | word-index + BM25-style ranking. |
| Metrics | `core/monitoring/metrics.py` | `record_discovered/record_completed/…`; dashboards read only this. |

## Request lifecycle

`apps.web.app` factory → security headers → CSRF → auth middleware
(default-deny, public allow-list) → rate limiter → blueprint route → service
layer → pooled DB connection → sanitized error path on failure.

## Operations layer (unified frontend)

`services/` is the single service layer shared by the web frontend, the
operations API and the CLI compatibility adapters:

| Concern | Owner |
|---|---|
| Ingestion requests/engine | `services/ingesting/` (wraps `pipeline.integrated_reader`) |
| Source/side management | `services/sources.py` (wraps `database.queries`) |
| Domain import | `services/importing/domain_import_service.py` (wraps `apps.importing`) |
| Backup/batch import | `services/importing/backup_import_service.py` (wraps `Api.services.import_service`) |
| Jobs (persistence, workers, cancel/pause/retry, recovery, events) | `services/jobs/` |

Pages (`templates/Operations/*`) and the API (`Api/routes/operations_api.py`)
are thin presentation over these services. The CLIs (`run_cli.py`,
`run_import.py`) are deprecated adapters constructing the same request
objects. No service depends on argparse, terminal I/O or exit codes.

## Ingestion lifecycle

source/side row → `IntegratedFileReader.process_batch` →
`FileRouterService.process_file` → registered reader → metadata rows →
`FileStatisticsService.record_completed` → dashboard truth.
