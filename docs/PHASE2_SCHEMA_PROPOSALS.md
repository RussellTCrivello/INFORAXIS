# Phase 2 — Schema Change Proposals (approval required)

Nothing in this document has been applied. Per §18, schema modifications
require explicit approval, so these are proposals only. Every claim below was
verified against the repository and, where stated, against a live database in
this session.

Migration mechanism (from `database/migrations/__init__.py`): each module
defines `version`, `name`, `upgrade(conn)`, optional `downgrade(conn)`; the
runner records applied versions in `schema_migrations` and runs each upgrade in
one transaction. `m0005_paths_error_message.py` is the closest precedent — it
adds a nullable `paths` column guarded by an `information_schema` check. The
next free version is **0007**.

Current verified `paths` columns:

```
id, file_name, file_path, file_size, file_type, file_status,
file_date, date_creation, hash_id, coordinates, error_message
```

---

## Proposal A — Extraction provenance (unblocks 2A display, then 2B–2E)

### Evidence

The readers now produce OCR provenance — `ocr_engine`, `ocr_engine_version`,
`ocr_confidence`, `ocr_derived`, `ocr_input_variant` — verified end to end:

```
page[method]             = ocr_rapidocr
page[ocr_engine]         = rapidocr
page[ocr_engine_version] = 1.4.4 (PP-OCRv4 onnx)
page[ocr_derived]        = True
page[ocr_confidence]     = 0.9762983572098517
```

None of it is persisted. Verified against a live database:

```
ocr_* columns in paths/contents: NONE
```

So §2A's "visible in file-details" and §11's "traceable to source" cannot be
met for OCR today, and 2B/2C/2D/2E will each hit the same wall.

### Option A1 — one JSONB column on `paths` (recommended)

```sql
ALTER TABLE paths
  ADD COLUMN extraction_provenance JSONB NULL;

COMMENT ON COLUMN paths.extraction_provenance IS
  'Per-extractor provenance: {extractor: {engine, version, confidence, derived,
   method, input_variant, warnings[], extracted_at}}';
```

Shape written by the pipeline:

```json
{
  "ocr": {
    "engine": "rapidocr",
    "engine_version": "1.4.4 (PP-OCRv4 onnx)",
    "confidence": 0.9763,
    "derived": true,
    "input_variant": "original",
    "extracted_at": "2026-09-12T04:10:08Z"
  },
  "exif":  { "extractor": "pillow", "version": "10.4.0", "fields": 24 },
  "email": { "attachment_count": 2, "nested": 1 }
}
```

* **Why one column:** JSONB is already established here (`m0001:204
  metadata JSONB`; `m0006` has five JSONB columns). One migration covers OCR
  now and image/document/email/media provenance later, instead of a migration
  per workstream.
* **Cost:** fields are not individually typed. Queryable with
  `extraction_provenance->'ocr'->>'engine'`, and indexable later with an
  expression index if a query pattern emerges. I would **not** add indexes
  speculatively — §16 says measure first.

### Option A2 — typed columns

```sql
ALTER TABLE paths ADD COLUMN ocr_engine         TEXT NULL;
ALTER TABLE paths ADD COLUMN ocr_engine_version TEXT NULL;
ALTER TABLE paths ADD COLUMN ocr_confidence     REAL NULL
  CHECK (ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1));
ALTER TABLE paths ADD COLUMN ocr_derived        BOOLEAN NOT NULL DEFAULT FALSE;
```

Directly indexable and self-documenting. But it repeats for 2B–2E, and `paths`
already has 11 columns.

### Option A3 — separate table

```sql
CREATE TABLE extraction_provenance (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    path_id       INTEGER NOT NULL,
    extractor     TEXT NOT NULL,
    engine        TEXT NULL,
    engine_version TEXT NULL,
    confidence    REAL NULL,
    derived       BOOLEAN NOT NULL DEFAULT FALSE,
    location      TEXT NULL,
    detail        JSONB NULL,
    extracted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (path_id) REFERENCES paths(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX idx_prov_path_extractor ON extraction_provenance (path_id, extractor);
```

Normalised, records **failed** attempts too (which §10 and §14 both want), and
keeps `paths` narrow. Cost: a join on every detail view.

**Recommendation: A1 now**, revisit A3 only if provenance needs to record
per-attempt history rather than per-file state.

### Compatibility, existing records, rollback

* New nullable column; **no existing row is rewritten**. Reads that do not know
  the column are unaffected.
* Existing records: `NULL` is correct and means "ingested before provenance was
  captured". Do not backfill — we cannot know how old files were extracted, and
  inventing a value would be worse than NULL.
* Rollback: `ALTER TABLE paths DROP COLUMN extraction_provenance;` — additive,
  so downgrade loses only the new data.

### Application changes

1. `pipeline/storage_pipeline.py` — populate from the reader result (image
   branch at `:1601`/`:1608`, PDF page loop).
2. `database/database/queries/path_queries.py:107` — `INSERT INTO paths` gains
   the column (currently 9 columns).
3. `database/database/repository/paths_repo.py` — accept the parameter.
4. File-details API — expose it.
5. Frontend — render under a provenance section.

### Tests

Unit: builder maps reader result → JSONB. Database: written and read back, NULL
for pre-existing rows. Integration: OCR'd file's provenance survives
ingest→store→read. E2E: file-details response contains engine, version,
confidence. Regression: a reader that omits provenance must not fail the insert.

---

## Proposal B — Archive hierarchy / parent linkage (§9)

### Evidence

`hierarchy_path` is accepted and threaded through the pipeline but never
persisted:

* accepted at `pipeline/storage_pipeline.py:227`, `:2864`, `:2905`
* constructed in `apps/cli/main.py:553`, `:584`, `:632`, `:662`
  (`f"{parent_path}::{extracted_path}"`)
* **zero occurrences anywhere in `database/`**

`INSERT INTO paths` (`path_queries.py:107-110`) has nine columns and includes
neither `hierarchy_path` nor `parent_path_id`.

`parent_path_id` is accepted at `storage_pipeline.py:226` but its only uses are
computing `title_status` at `:2748` and passing it to
`_store_title_pipeline` — which is **dead code**. Verified:

```
hasattr(DatabaseHub, 'title_operations') -> False
LOG: Error in title storage pipeline: 'DatabaseHub' object has no attribute 'word_operations'
_store_title_pipeline returned: False
```

Measured effect on a live database, ingesting `container.zip -> child.pdf`:

```
titles_content:
  (1, 'Main', None, 1)    <- child.pdf
  (2, 'Main', None, 2)    <- container.zip
rows with parent linkage (title_content_id NOT NULL): 0
```

**So archive→child lineage is persisted nowhere.** (PARENT-02, already fixed
and pushed, repaired the storage layer's dropped parameter — but nothing
upstream supplies a parent yet.)

### Proposed schema

```sql
ALTER TABLE paths ADD COLUMN parent_path_id INTEGER NULL;
ALTER TABLE paths ADD COLUMN hierarchy_path  TEXT NULL;

ALTER TABLE paths ADD CONSTRAINT fk_paths_parent
  FOREIGN KEY (parent_path_id) REFERENCES paths(id) ON DELETE SET NULL;

CREATE INDEX idx_paths_parent_path_id ON paths (parent_path_id);
```

`parent_path_id` is the queryable relationship; `hierarchy_path` is the
human-readable `archive.zip::child.pdf::image.jpg` string the CLI already
builds. Keeping both means lineage queries stay cheap while the display string
does not have to be recomputed by walking the tree.

`ON DELETE SET NULL` rather than CASCADE: deleting an archive must not silently
delete extracted children, which are independently indexed records.

### Compatibility, existing records, rollback

* Both columns nullable; no existing row rewritten.
* Existing records: `NULL` parent is truthful — we do not know their ancestry
  retroactively. Do **not** attempt to reconstruct it from filenames.
* Rollback: drop the FK and both columns. No other object depends on them.

### Application changes

1. `INSERT INTO paths` gains both columns; `paths_repo` accepts them.
2. `storage_pipeline` passes the `parent_path_id` it already receives, instead
   of only using it to pick a `title_status` string.
3. Repair or delete `_store_title_pipeline`. It is dead code that logs an error
   on every file with a title. Now that PARENT-02 made
   `titles_content.title_content_id` writable, either wire it to the real
   repository or remove it — leaving it silently failing is the worst option.
4. `contents_db_service.py:1554` calls `create_title_content(title_words,
   path_id)` with no parent; decide whether titles should carry lineage too.

### Tests

Database: child row stores `parent_path_id`; the FK rejects a bogus parent;
deleting a parent nulls rather than cascades. Integration: `container.zip →
child.pdf` yields a child whose parent resolves to the archive. E2E: the
hierarchy string matches the actual parent chain. Regression: a top-level file
gets `NULL`, not a self-reference.

---

## Proposal C — Processing status model (§10)

### Evidence

```sql
-- m0001_initial_schema.py:123
file_status VARCHAR(10) NOT NULL
  CHECK (file_status IN ('Read', 'Unread')) DEFAULT 'Unread'
```

Two states. `Read` means content was extracted; `Unread` means it was not. The
schema cannot express *failed*, *unsupported*, *skipped*, or *partially
processed*, so a corrupt file and a legitimately empty file are
indistinguishable. The `VARCHAR(10)` width is itself a blocker: measured,
`unsupported` is 11 characters and `partially_processed` is 19, so neither
fits the existing column (`processing` and `discovered` are exactly 10).

`paths.error_message` (added by `m0005`) exists but is free text with no
controlled vocabulary.

### Proposed schema — additive, not a rewrite

```sql
ALTER TABLE paths ADD COLUMN processing_status VARCHAR(24) NOT NULL
  DEFAULT 'discovered'
  CHECK (processing_status IN (
    'discovered','queued','processing','processed','partially_processed',
    'failed','unsupported','skipped','retrying'));

ALTER TABLE paths ADD COLUMN status_detail    TEXT NULL;
ALTER TABLE paths ADD COLUMN attempts         INTEGER NOT NULL DEFAULT 0;
ALTER TABLE paths ADD COLUMN status_updated_at TIMESTAMPTZ NULL;

CREATE INDEX idx_paths_processing_status ON paths (processing_status);
```

**`file_status` is deliberately kept.** Rewriting it would break 57 references
across 12 project files plus 44 in templates/JS (measured):
`Api/blueprints/analytics.py`, `Api/blueprints/files.py`, `Api/models/paths.py`,
`Api/routes/{analysis,api,notifications}.py`, `database/__init__.py`,
`database/database/queries/path_queries.py`,
`database/database/repository/paths_repo.py`,
`database/services/contents_db_service.py`, `pipeline/storage_pipeline.py`.

Instead the two coexist during transition, with `file_status` derived:

| processing_status                             | file_status |
|-----------------------------------------------|-------------|
| `processed`                                   | `Read`      |
| `partially_processed`                         | `Read`      |
| `discovered`, `queued`, `processing`, `retrying` | `Unread` |
| `failed`, `unsupported`, `skipped`            | `Unread`    |

A CHECK constraint or trigger can enforce the mapping so the two cannot drift.
Once every consumer is migrated, a **separate, later** migration can drop
`file_status` — as its own approved change, not bundled here.

### Existing-record migration strategy

One idempotent statement, no row deleted:

```sql
UPDATE paths SET processing_status = CASE
    WHEN file_status = 'Read'   THEN 'processed'
    WHEN file_status = 'Unread' THEN 'discovered'
  END
WHERE processing_status = 'discovered';
```

This is the one place an existing row is rewritten, and it is a pure
restatement of information already stored. Run it in the same transaction as
the `ALTER`, and report the affected row count.

### Rollback

```sql
DROP INDEX IF EXISTS idx_paths_processing_status;
ALTER TABLE paths DROP COLUMN status_updated_at;
ALTER TABLE paths DROP COLUMN attempts;
ALTER TABLE paths DROP COLUMN status_detail;
ALTER TABLE paths DROP COLUMN processing_status;
```

Safe because `file_status` was never altered — the pre-existing behaviour is
fully intact after rollback.

### Application changes

`path_queries.py` insert/update, `paths_repo.py`, `storage_pipeline.py` status
transitions, and the analytics/notification queries that currently group by
`file_status`. Frontend status labels.

### Tests

Unit: every legal transition allowed, illegal ones rejected. Database: CHECK
rejects `'exploded'`; the mapping to `file_status` holds; the existing-record
UPDATE is idempotent when run twice. Integration: a corrupt file lands as
`failed` with `status_detail`, and a legitimately empty file as `processed`.
Regression: pre-migration rows read back with a sane status.

---

## What I am asking for

1. **Proposal A** — A1, A2, or A3? This unblocks the last piece of 2A (OCR
   provenance in file-details) and every later workstream's metadata.
2. **Proposal B** — approve adding `parent_path_id` + `hierarchy_path` to
   `paths`? And should `_store_title_pipeline` be repaired or deleted?
3. **Proposal C** — approve the additive status model that keeps `file_status`
   alongside `processing_status`?

Until these are decided I am continuing on work that needs no schema change.
