# Import Center

`/operations/import` — structured data imports (a distinct operation from
file ingestion). Three import types, all running as monitored jobs:

## Domain data import

Imports domain classification data (Excel/CSV/JSON) from the application
import-data directories (`apps/importing/data/`, `data/`, `classification/`).
* `POST /api/import/validate` `{type: "domain_import", data_file}` — checks
  the file exists/parseable.
* `POST /api/import/preview` — dry-run job: parses and counts
  words/categories/keywords without writing.
* `POST /api/import/jobs` — real import (the former `run_import.py`, now a
  thin adapter over `DomainImportService`).

## Backup restore (admin only)

Restores a previously exported application backup (allowlist-validated JSON
inside the export ZIP; transactional; see docs/SECURITY.md SEC-04).
* Analysts receive HTTP 403 — enforced server-side, independent of UI.
* Validate performs full validation without restoring.
* Backups contain the evidence tables only (`ALLOWED_TABLES`): system tables
  (users, sessions, audit_log, jobs, schema_migrations) are never exported
  and never restored.
* Restore is FK-aware: children are deleted before parents and parents are
  inserted before children (order derived from the live pg_catalog
  constraints); identity (`GENERATED ALWAYS`) columns are restored with
  `OVERRIDING SYSTEM VALUE` and their sequences are resynced afterwards.
* The legacy `/api/import-export/backup/*` surface is admin-only as well
  (blueprint registered in `AUTH_ADMIN_BLUEPRINTS` + endpoint decorators).

## Server file batch import

A list of server-side files ingested through the engine as one job.
* `POST /api/import/validate` returns accepted/rejected per path (SEC-06
  roots allowlist).
* Confirming creates a `batch_import` job with source/side taxonomy.

## Preview → confirm flow

Validate and Preview never write; the actual import runs as a job you can
watch and cancel. Large/destructive imports always show a preview before the
Start button does anything.
