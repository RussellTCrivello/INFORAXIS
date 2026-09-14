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
