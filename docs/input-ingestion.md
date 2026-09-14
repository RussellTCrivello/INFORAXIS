# Input / Ingestion

The Input page (`/operations/input`) is the primary ingestion surface. The
CLI (`run_cli.py`) is a deprecated compatibility adapter over the same
`IngestionService`.

## Input sources

* **Upload files** — drag & drop or browse; files are streamed to the
  application-managed staging area (`APP_DATA_DIR/uploads/<id>/`, size limit
  `OPERATIONS_MAX_UPLOAD_MB`). Staged paths are plain files the engine then
  processes like any other input (path safety, archive safety, hashing all
  apply — uploading bypasses nothing).
* **Server path** — a file/folder on the server. Restricted to
  `INGESTION_ROOTS` (semicolon-separated). With no roots configured,
  server-path input is **disabled** (fail-closed); the UI says so.

The browser cannot browse server filesystems by design; use the server-path
field for operator-known locations or upload files.

## Basic mode

Source + Side (mandatory taxonomy — the engine has always required them),
recursive checkbox, Start Analysis. A Dry run button shows what *would* be
processed before committing.

## Advanced mode

* **Workers** — engine thread count (0 = configured default; clamped by the
  resource coordinator).
* **Checkpoint** — auto (resume) / fresh (discard) / off. Checkpoints enable
  pause/resume and crash-resume without reprocessing.
* **Monitoring** — engine thread monitoring.

Always-on engine capabilities (labeled as such, not fake toggles): streamed
SHA-256 hashing, content deduplication (identity = hash+source+side), safe
archive extraction (zip/tar/gz/bz2 with traversal protection), text
extraction & indexing, metadata extraction, OCR when Tesseract is installed.

## Dry run

`POST /api/input/jobs` with `"dry_run": true` returns files discovered,
eligible, unsupported, estimated bytes and a sample — no database writes.

## Where results go

Jobs appear in the Jobs Center (`/operations/jobs`) with live progress,
events, errors and warnings; the search index is updated as files complete.
