# Operations API

Base rules for every endpoint: session authentication (default-deny
middleware), CSRF on state changes, JSON envelopes
`{"success": bool, ...}` and structured errors:

```json
{"success": false,
 "error": {"code": "VALIDATION_FAILED",
           "message": "Path not allowed: passwd",
           "details": {},
           "request_id": "db11506b543b"}}
```

## Input / Ingestion

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/input/options-info` | user | capability facts (roots configured?) |
| GET | `/api/input/sources` | user | list sources (`?q=` search) |
| POST | `/api/input/sources` | analyst+ | create source (validated; 20/min) |
| GET | `/api/input/sides` | user | list sides |
| POST | `/api/input/sides` | analyst+ | create side |
| POST | `/api/input/uploads` | analyst+ | stream upload → staged paths (30/min, size limit) |
| POST | `/api/input/jobs` | analyst+ | create ingestion job; `dry_run` answers inline (10/min) |
| GET | `/api/input/jobs` | user | ingestion jobs |

Job payload: `path` XOR `file_paths`, `source`, `side` (mandatory),
`recursive`, `dry_run`, `processing: {max_workers, checkpoint, enable_monitoring}`.

## Import Center

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/import/validate` | analyst+ | type-specific validation, no writes |
| POST | `/api/import/preview` | analyst+ | dry-run import job |
| POST | `/api/import/jobs` | analyst+ (`backup_import`: **admin**) | start import job |
| GET | `/api/import/jobs` | user | import jobs |

Types: `domain_import`, `backup_import`, `batch_import`.

## Jobs

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/jobs` | user | filters: `type`, `status`, `user`, `limit`, `offset` |
| GET | `/api/jobs/{id}` | user | full record incl. statistics |
| GET | `/api/jobs/{id}/events` | user | `?after_id=` incremental polling |
| GET | `/api/jobs/{id}/errors` | user | errors + warnings |
| GET | `/api/jobs/{id}/results` | user | result summary + stats |
| POST | `/api/jobs/{id}/cancel` | analyst+ | cooperative |
| POST | `/api/jobs/{id}/pause` | analyst+ | safe boundary |
| POST | `/api/jobs/{id}/resume` | analyst+ | successor job |
| POST | `/api/jobs/{id}/retry` | analyst+ | successor job (dedup-safe) |
| DELETE | `/api/jobs/{id}` | **admin** | terminal jobs only |
| GET | `/api/jobs/stream` | user | SSE events (single-process; poll otherwise) |
| GET | `/api/jobs/summary` | user | counts per status + active |

Status codes: 202 job accepted · 400 validation · 401 unauthenticated ·
403 unauthorized · 404 unknown job · 409 invalid state transition ·
413 upload too large · 429 rate limited.
