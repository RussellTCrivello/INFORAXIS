# Operations Guide

## Normal operation (no terminal required)

1. Log in.
2. **Input / Ingestion** (`/operations/input`) — upload or point at a
   server folder, pick source/side, dry-run if desired, Start.
3. **Jobs** (`/operations/jobs`) — watch progress live; cancel/pause/resume/
   retry as needed; every job keeps its errors, warnings and event log.
4. **Import Center** (`/operations/import`) — domain data, backup restore
   (admin), server file batches — always validate/preview first.
5. **Search** — ingested content is searchable immediately after its file
   completes.
6. Dashboard — operations widget with active jobs and quick actions.

## Operator playbook

| Situation | Action |
|---|---|
| Ingestion too slow | check Jobs → throughput; increase `processing.max_workers` (bounded by CPU/DB pool) |
| Job stuck | Jobs → job detail shows current file/phase; cancel if needed (safe boundary) |
| App restarted mid-job | job marked FAILED with "interrupted" error → Retry (dedup prevents duplicates) |
| Re-ingest same data | safe by design: duplicates detected, nothing double-stored |
| Backup restore needed | Import Center → Backup (admin) → Validate → Restore |
| Many small jobs piling up | `JOBS_MAX_CONCURRENT` controls parallel jobs |

## Environment

See docs/job-system.md for the full list (`JOBS_*`, upload limits). All
configuration follows defaults < settings file < environment.

## Monitoring

* `GET /api/jobs/summary` — counts per status (used by the dashboard widget).
* Job events (DB) + correlation ids in server logs trace any file from
  discovery to database write.
* `verify_readiness.py` includes job-infrastructure checks (tables present).
  Run it after any deployment change; `READINESS: READY` is the gate.

## Status model and triage

Two stored columns answer two different questions, and they are not
interchangeable:

* `paths.file_status` — `Read` when the artifact yielded content, `Unread`
  otherwise. A deliberately skipped file (for example an image below the
  reader's minimum size), an unsupported type and a failed read are all
  `Unread`; *why* is in the second column.
* `paths.processing_status` — the stored outcome. The schema (migration 0007)
  permits `processed`, `partially_processed`, `failed`, `unsupported`,
  `skipped`, and the job layer adds the in-flight `discovered`, `queued`,
  `processing`, `retrying`. `status_detail` carries the reason
  (`too_small`, `ocr_required_engine_unavailable`, …), with `attempts` and
  `status_updated_at`.

The *run's* accounting uses a wider vocabulary than the column: `completed`,
`failed`, `skipped`, `unsupported`, `retryable`, `locked`, `cancelled` (see
the invariant section). In particular **`locked` has no column value**: a file
held open by another process is stored as `failed` with a `status_detail`
beginning `locked:` — the artifact is fine and the read is retryable once the
holder releases it, and the run counts it as `locked`, not as a failure. The
marker list is shared between the two layers, so the row and the accounting
cannot disagree.

```sql
-- what needs attention, without reading rows one by one
SELECT processing_status, COUNT(*) FROM paths GROUP BY processing_status;
SELECT file_name, status_detail, attempts FROM paths
 WHERE processing_status = 'failed' ORDER BY status_updated_at DESC;

-- held files, which are retryable rather than broken
SELECT file_name, status_detail FROM paths
 WHERE file_status = 'Unread' AND status_detail LIKE 'locked:%';

-- a run is only complete when every discovered object has a terminal state
SELECT processing_status, COUNT(*) FROM paths
 WHERE processing_status IN ('discovered', 'queued', 'processing') GROUP BY 1;
```

## Identity, provenance and where "detected as" lives

Every artifact also records *how it was identified*, as structured provenance
in `paths.extraction_provenance` (JSONB), under `detection`:

```json
{"detection": {"declared_name": "report.pdf", "declared_extension": ".pdf",
               "detected_extension": ".zip", "format_id": "zip",
               "format_family": "archive", "mime_type": "application/zip",
               "detection_method": "magic-bytes", "detection_confidence": "certain",
               "extension_mismatch": true,
               "features": {...}, "evidence": [...], "discrepancies": [...]}}
```

Long lists are truncated with an explicit `*_total` count rather than silently
dropped. This record is **metadata about the artifact, not its content**: it is
deliberately *not* part of the file's text, so it never appears as body text in
the content viewer or in search results (a mismatch is still findable, by
query, which keeps every hit explicable):

```sql
SELECT file_name FROM paths
 WHERE (extraction_provenance -> 'detection' ->> 'extension_mismatch') = 'true';
SELECT file_name FROM paths
 WHERE extraction_provenance -> 'detection' ->> 'format_family' = 'archive';
```

The same JSON is returned by the file-details API
(`GET /api/file/<id>/details`) and coerced/validated by
`Api/services/lineage_service.py`, so what an examiner sees matches what is
stored.

## Accounting invariants

The run reports one denominator (everything discovered, including archive
members, email attachments and embedded objects) and one bucket per outcome.
`GET /api/jobs/summary` and the persisted job statistics carry the same keys:

```
discovered = completed + failed + skipped + unsupported + retryable
           + locked + cancelled + in_progress + pending
```

Terminal buckets are reported by the job statistics and the live ingest
payload; the CLI summary prints them too (including `locked` and `cancelled`
when non-zero), so no object can be in a state the operator cannot see.

`containers_in_flight` / `container_work_outstanding` say whether a container
still has nested work to settle; a run is not complete while they are non-zero,
however the buckets read. Per-container attribution (`children_by_parent`) is
bounded for memory, and the exactly-counted remainder is in
`children_by_parent_overflow`, so map plus overflow always equals the nested
total.

## Archives that need an external decoder (RAR)

RAR is the one container this pipeline cannot decode in pure Python: `rarfile`
is a front end for `unrar`/`unar`/7-Zip/`bsdtar`, and the compressed streams are
proprietary. What `rarfile` *can* do without any tool is parse RAR4/RAR5
headers and read members stored uncompressed. The reader is built on that
distinction:

* Every member that can be read is extracted (and CRC-verified). A decoderless
  machine therefore still reads the stored part of an archive, instead of
  failing the whole file as it did when the first compressed member raised
  `RarCannotExec`.
* A member whose stream needs a decoder is recorded, not dropped: it appears in
  the archive's `status_detail` (for example
  `341 of 405 archive members could not be read (decoder required); 64 read`),
  in the archive's own content (its manifest, which lists the members that
  could not be read), and in `extraction_provenance`.
* The container is still reported as a partial success
  (`processing_status = 'partially_processed'`) — neither "processed" (which
  would claim the whole archive was read) nor "failed" (which would discard
  what was read).
* `ArchiveEncrypted` (needs a password) and `ArchiveSafetyError` (corrupt, or
  rejected by policy) stay distinct from the missing-decoder case, so the three
  different fixes are never confused.

To read the compressed members, install a decoder. The reader looks for one on
`PATH` and in the standard Windows install locations of WinRAR (`UnRAR.exe`),
7-Zip (`7z.exe`) and the bundled `bsdtar`; a candidate has to *demonstrate*
RAR support (GNU tar answers `--version` too and cannot read RAR, so presence
alone is not accepted).

    # what the machine currently has
    python -c "from core.archive_safety import rar_decoder_status; print(rar_decoder_status())"

```sql
-- archives blocked by a missing decoder, and how much of each was read
SELECT p.file_name, p.processing_status, p.status_detail
  FROM paths p
 WHERE p.extraction_provenance -> 'diagnostics' ->> 'decoder_missing' = 'true';

-- how much of a container's character count was inline code rather than body
SELECT p.file_name,
       p.extraction_provenance -> 'diagnostics' ->> 'visible_text_chars' AS visible,
       p.extraction_provenance -> 'diagnostics' ->> 'script_chars'        AS script,
       p.extraction_provenance -> 'diagnostics' ->> 'style_chars'         AS style
  FROM paths p
 WHERE p.extraction_provenance -> 'diagnostics' ->> 'script_chars' IS NOT NULL;
```

Re-running the ingest after installing a decoder reads the remaining members;
the members read the first time are already stored as children of the archive.
