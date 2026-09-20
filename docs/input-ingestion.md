# Input / Ingestion

There is **one** ingestion interface: `/operations/input`. It replaces the two
competing screens that existed before (the tabs-and-panels page that lived at
this URL, and the CLI-styled `/upload` page) — one page, one pipeline, one set
of words. `/upload` is kept as a 302 alias so bookmarks, shortcuts and links in
older documentation still land on it; it is still governed by the `upload_files`
interface toggle (disabled → the alias redirects to the dashboard, exactly as it
did before). The CLI (`run_cli.py`) is a compatibility adapter over the same
`IngestionService`.

## Input sources

* **This computer** — drag & drop, *Choose files*, or *Choose folder*
  (folder uploads keep their structure: the browser's relative path is stored,
  so two same-named files in different folders both survive).
  Files are streamed to the application-managed staging area
  (`APP_DATA_DIR/uploads/<id>/`), bounded by `OPERATIONS_MAX_UPLOAD_MB`
  (default 512 MB per request).
  Staged paths are plain files the engine then processes like any other input —
  path safety, archive safety, hashing and duplicate detection all apply;
  uploading bypasses nothing.
* **Server path** — a file/folder on the server. Restricted to
  `INGESTION_ROOTS` (semicolon-separated). With no roots configured,
  server-path input is **disabled** (fail-closed) and the page says so; the
  roots that *are* configured are listed as chips that fill the field.

The browser cannot browse server filesystems by design; use the server-path
field for operator-known locations or upload files.

## Large files (chunked staging)

A single request has a ceiling, so files above it are staged in chunks and the
result is identical: a plain file in the staging directory that a job then
ingests. `OPERATIONS_MAX_CHUNKED_UPLOAD_MB` (default 20480 MB) bounds the whole
file, `OPERATIONS_UPLOAD_CHUNK_MB` (default 8 MB) the chunk size.

| Step | Request |
| --- | --- |
| open | `POST /api/input/uploads/chunked/start` `{filename, size, sha256?}` |
| send | `POST /api/input/uploads/chunked/<upload_id>/chunk/<index>` (multipart `chunk`, optional `sha256`) |
| check | `GET /api/input/uploads/chunked/<upload_id>` → received bytes, uploaded and missing chunks |
| finish | `POST /api/input/uploads/chunked/<upload_id>/complete` → `staged_path`, `bytes`, `sha256` |
| abandon | `DELETE /api/input/uploads/chunked/<upload_id>` |

Session state lives on disk (one directory per upload), so an interrupted
transfer resumes instead of starting over, and a restarted server does not lose
it. The declared size and the SHA-256 are verified before a file is accepted;
chunks carry their own hash, so corruption is caught at the chunk that suffered
it. The page retries a failed chunk a few times and reports real progress in
bytes; while a transfer runs, the primary button becomes *Stop staging* and
abandoning it leaves already-staged files in place, reusable by the next run.

## Classification

Source and Side are mandatory (the engine has always required them) and become
part of every file's identity — the same content under a different source is
not a duplicate. Both are searchable pickers with inline creation, so a new
source or side does not send the operator to another page.

## Processing options

* **Workers** — engine thread count (0 = configured default; clamped by the
  resource coordinator).
* **Checkpoints** — resume (default) / fresh / off. Checkpoints enable
  resume-after-crash without reprocessing finished files.
* **Monitoring** — engine thread monitoring for the run.

Always-on engine capabilities are stated as facts, not fake toggles: streamed
SHA-256 hashing, content deduplication (identity = hash + source + side), safe
archive extraction (zip/tar/gz/bz2 and more with traversal protection), nested
container extraction with parent/child links, text & metadata extraction and
indexing, OCR when an engine is available.

## Dry run, then start

* **Dry run** (or <kbd>Ctrl</kbd>+<kbd>D</kbd>) walks the input and reports
  files discovered, eligible, unsupported, the volume, and a sample — it writes
  nothing.
* **Start Analysis** (or <kbd>Ctrl</kbd>+<kbd>Enter</kbd>) stages whatever is
  needed and creates the job: `POST /api/input/jobs` → 202 with the job id,
  and the browser opens the job page.

The rail on the left, the readiness line in the dock and the telemetry column
all read from the same state, so what the operator sees is what the API will
accept: the dock names the *one* thing that is missing rather than listing
everything.

## Where results go

Jobs appear in the Jobs Center (`/operations/jobs`) with live progress, events,
errors and warnings, pause/resume/cancel, and the search index is updated as
files complete. The ingestion page's telemetry column shows what is running and
what finished recently, polled from `/api/jobs` and `/api/jobs/summary`.

## What was removed

* `templates/file/upload.html`, `static/js/pages/upload-page.js` — the second
  interface. Its capabilities are all present above.
* `static/js/modules/upload/chunked-upload.js`, `static/css/chunked-upload.css`
  — an upload widget that posted to endpoints which no longer existed
  (`/upload/chunked/complete`); replaced by real chunked staging (above).
* `POST /upload/process-path` — the deleted page's path-ingestion entry point,
  a second, differently-shaped way to start the ingestion that
  `POST /api/input/jobs` owns. Path containment (SEC-06) is unchanged: it is
  still enforced for every ingestion path in `IngestionService.validate()`.

The processing-task API (`/upload/active-tasks`, `/upload/progress/<id>`,
`/upload/pause|resume|cancel/<id>`) is **not** part of the upload interface and
was not removed: it is the HTTP surface of `Api/task_manager.py`, whose tasks
are created by the import flows and shown by the dashboard's progress tracker.
