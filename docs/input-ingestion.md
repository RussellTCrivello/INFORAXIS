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
  The response carries `staged[]` (path, name, bytes) and `failed[]`
  (name, code, message): a file the host cannot store is reported on its own
  row, and the rest of the selection still stages.
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

## On Windows (and on every other platform)

Windows is the primary production platform, so the three ways of choosing input
are specified for it explicitly:

| Input | Windows | macOS / Linux |
| --- | --- | --- |
| **A single file** | *Choose files* (or drag one file) | same |
| **A whole folder** | *Choose folder*, or drag the folder from Explorer | *Choose folder*, or drag the folder from Finder/Explorer |
| **A path on the server** | `C:\\data\\evidence` or `\\\\server\\share\\cases`, inside `INGESTION_ROOTS` | `/data/evidence`, inside `INGESTION_ROOTS` |

* **Roots syntax.** `INGESTION_ROOTS` is semicolon-separated on every platform
  (a semicolon is not a legal path character on Windows, a colon is) and
  entries may be quoted:
  `set INGESTION_ROOTS=C:\data\evidence;D:\inbox` and
  `set INGESTION_ROOTS="\\server\share\cases"` both work.
* **Separators and case.** Windows accepts `\` and `/` in the field and its
  paths are compared case-insensitively; on macOS/Linux `/` separates and the
  comparison is case-sensitive. The page states the containment rule the way
  the host will apply it — it never promises a path the server would refuse.
* **Folder selections** keep their tree on all three platforms: the browser
  reports each file's path inside the chosen folder (always with `/`), the
  server stores it below the staged batch directory, and the file's place in
  the tree is what the engine sees. Dragging a folder works in Chrome, Edge
  and Safari; in a browser without the directory-drop API the page says so and
  points at *Choose folder* rather than queueing something that is not a file.
* **Names Windows refuses** (reserved device names such as `CON`, `NUL`,
  `LPT1`, trailing dots or spaces, `: * ? " < > |`, over-long components) are
  defused, never dropped — a folder collected on macOS or Linux still arrives,
  and the queue shows the name it was stored under. The rule is the same one
  the archive extractor uses for member names, so an upload and an archive
  member behave identically.
* **Path length.** Windows still enforces `MAX_PATH` (260) unless long paths
  are enabled for the process, so a stored path longer than
  `OPERATIONS_MAX_STAGED_PATH_CHARS` (240 on Windows, 4096 elsewhere) is
  refused *for that file only*, with the actual length and the limit in the
  message. The other files in the same selection still stage — one impossible
  name never costs the operator the batch.


### What the browser must support

Every browser that implements the folder picker (Edge and Chrome on Windows,
Firefox, Safari) reports where each selected file sits inside the chosen folder,
and the page preserves that structure. A browser that does not sends bare
names: the files are then placed without their folders, and the page says so
once rather than quietly losing the tree. Dropping a folder from Explorer goes
through the same structure-preserving path (`webkitGetAsEntry`); a browser
without it is told to use "Choose folder" instead of being handed something
that is not a file.

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
* `static/css/upload.css` — the old page's CLI chrome (`.cli-container` and
  friends), unreferenced by any template once that page was gone.
* `POST /upload/process-path` — the deleted page's path-ingestion entry point,
  a second, differently-shaped way to start the ingestion that
  `POST /api/input/jobs` owns. Path containment (SEC-06) is unchanged: it is
  still enforced for every ingestion path in `IngestionService.validate()`.

The processing-task API (`/upload/active-tasks`, `/upload/progress/<id>`,
`/upload/pause|resume|cancel/<id>`) is **not** part of the upload interface and
was not removed: it is the HTTP surface of `Api/task_manager.py`, whose tasks
are created by the import flows and shown by the dashboard's progress tracker.
