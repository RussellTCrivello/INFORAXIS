# Security Documentation

This document describes the security architecture actually implemented in this
codebase. Every control listed here has an automated regression test in
`tests/security/`.

## Authentication (SEC-01)

* Real session-based authentication: `POST /auth/login`, `POST /auth/logout`.
* Passwords hashed with Werkzeug **scrypt** (memory-hard, salted). Plaintext
  passwords never touch the database or logs.
* Sessions are **server-side records** (`sessions` table keyed by
  `SHA-256(token)`), so they are revocable and expire server-side
  (12 h max, 6 h sliding idle extension).
* Account lockout: 5 consecutive failures lock the account for 15 minutes.
* Uniform `401 Invalid username or password` for unknown users and bad
  passwords (no account enumeration; timing is equalized).
* Secure cookies: `HttpOnly`, `SameSite=Lax`, `Secure` in production.
* First-run bootstrap: when zero users exist, an initial administrator is
  created (`APP_ADMIN_USERNAME` / `APP_ADMIN_PASSWORD`, or a random password
  written to `APP_DATA_DIR/runtime/initial_admin_password.txt` with `0600`
  permissions). The `/auth/first-admin` web flow is available only while zero
  users exist.
* Password reset strategy: administrators generate a one-time random password
  (`POST /api/auth/users/<id>/reset-password`); all of the target's sessions
  are revoked; the account is flagged `must_change_password`.

## Authorization (SEC-02)

Roles: `admin`, `analyst`, `viewer`.

Server-side enforcement happens in two layers:

1. **Middleware** (`core/security/flask_ext.py`): every request is
   authenticated (default-deny; public endpoints are an explicit allow-list).
   Mutating methods (POST/PUT/PATCH/DELETE) require analyst or admin; mutating
   methods on admin blueprints (`settings`, `setup`, `concurrency`,
   `error_dashboard`, `translations`) require admin; read access to settings
   requires admin.
2. **Decorators** (`@login_required`, `@roles_required`, `@admin_required`,
   `@write_access_required`) tighten specific endpoints. Decorators can
   tighten but never loosen the middleware policy.

Protected operations include file deletion, bulk operations, import, export,
database configuration, settings, source/side management, keyword/category
management, backup/restore, and all administrative endpoints.

## SQL injection (SEC-03)

* All values are parameterized. There is **no** f-string/`%`/concatenated SQL
  constructed from client input.
* Dynamic identifiers (ORDER BY columns, table names) pass through
  `core/sql_safety.validate_identifier` with an explicit client-value →
  approved-column mapping; anything outside the allowlist returns **HTTP 400**.
* Backup import composes identifiers via `psycopg2.sql.Identifier` after
  allowlist validation.

## Backup import (SEC-04)

* Table allowlist (`ImportService.ALLOWED_TABLES`), strict identifier
  validation, live information_schema column validation, JSON/type/row-count
  validation, per-value size limits, transactional restore (DELETE + INSERT in
  one transaction; rollback on any failure), admin-only authorization, audit
  logging.
* Failed validation aborts the entire restore - the database is never left
  partially restored.

## Archive extraction (SEC-05)

`core/archive_safety.py` is the single extraction path for ZIP/TAR/GZ/BZ2/RAR/7z:

* Rejects absolute paths, `..` traversal, drive-qualified paths, UNC paths,
  NUL bytes; re-verifies every destination resolves beneath the extraction
  root after normalization.
* Refuses symlinks and hard links.
* Limits: depth ≤ 8, ≤ 10,000 files, ≤ 2 GiB total, ≤ 512 MiB per file,
  compression ratio ≤ 500, wall-clock timeout, per-file size checks.
* No `extractall` anywhere.

## Filesystem access (SEC-06)

* Server-path ingestion validates every path against `INGESTION_ROOTS`
  (semicolon-separated). With no roots configured, server-path ingestion is
  **disabled entirely** (fails closed); clients must upload files instead.
* The security boundary is the explicit root allowlist. On Windows,
  drive-qualified (`C:\data`) and UNC (`\\server\share`) candidates are
  accepted when they resolve under a configured root; containment matching is
  case-insensitive and separator-tolerant. On POSIX, Windows-shaped absolute
  paths are rejected (they cannot refer to real POSIX locations).
* Relative candidates resolve against the configured roots, never the server
  process working directory.

## Secrets (SEC-07)

* No credentials in source. Database credentials come from `DB_*`
  environment variables or the settings store (which is git-ignored).
* `FLASK_SECRET_KEY` from the environment; development fallback writes a
  generated key to the data root (not the repo).
* `.env` is git-ignored; `.env.example` documents the required variables.
* **Action required for existing deployments**: the credential that was
  committed historically (`postgres` superuser password) must be rotated in
  PostgreSQL: `ALTER USER postgres WITH PASSWORD '<new-password>';` — and the
  old password must be revoked from any role/grant that used it.

## Error handling (SEC-08)

* `core/errors.py`: raw exception text never reaches clients. Clients receive
  a generic message plus a correlation id (`ERR-YYYYMMDD-NNNN`); the server
  log carries the full traceback, user, route, method and subsystem.
* Never exposed: SQL, filesystem paths, credentials, connection strings,
  stack traces, internal class names, database details.

## CSRF & browser security (SEC-09)

* `flask-wtf` CSRF protection covers **every** state-changing request,
  including setup (the previous setup CSRF exemption was removed).
* Headers on every response: CSP (`default-src 'self'`, `frame-ancestors
  'none'`, `object-src 'none'`), `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, COOP. HSTS is sent in production.
* Session cookies: `HttpOnly`, `SameSite=Lax`, `Secure` (production).

## Debug mode (SEC-10)

* `run_web.py` reads `FLASK_DEBUG`/`FLASK_ENV`. Startup **refuses** to run
  with debug enabled while `FLASK_ENV=production`. Debug is never hardcoded.

## Rate limiting (API-01)

* Flask-Limiter: default 60 requests/minute and 600/hour per client IP.
  Login has a strict 10/minute limit. Storage backend configurable via
  `RATELIMIT_STORAGE_URI` (use Redis in multi-process deployments).

## Operations API (unified jobs)

* All job creation/control endpoints require analyst or admin (middleware);
  `backup_import` jobs and job deletion require admin - enforced in the API
  layer, not by hiding buttons.
* Server paths for ingestion are validated against `INGESTION_ROOTS`
  (fail-closed when unset). Staged uploads under the application-managed
  `APP_DATA_DIR/uploads` are a configured application input location.
* Uploads: streamed, size-limited (`OPERATIONS_MAX_UPLOAD_MB`), filenames
  never trusted, archive/path safety applies to staged files identically.
* Strict per-route rate limits: job creation 10/min, uploads 30/min,
  validation 20/min, control ops 30/min.
* Job IDs are capability-free identifiers: knowing one grants nothing
  without a valid session and role.

## Route classification (Phase 7)

| Class | Endpoints | Control |
|---|---|---|
| public | `GET /auth/login`, `GET /auth/me`, `GET /auth/first-admin`, setup pages (gated), static, health | allow-listed in `PUBLIC_ENDPOINTS` |
| authenticated | all dashboards, search, preview, listings | default-deny middleware |
| authorized (write) | POST/PUT/PATCH/DELETE application data | analyst/admin middleware |
| admin | settings, setup, concurrency, error dashboards, translations, user management, backup restore | admin middleware + decorators |
| disabled | none | — |

## Known limitations

* CSP currently allows `script-src 'unsafe-inline'` because legacy templates
  embed JavaScript. Removing this requires extracting inline scripts from ~40
  templates (tracked as follow-up work).
* Rate limiting uses in-memory storage by default (per-process). Use
  `RATELIMIT_STORAGE_URI=redis://...` in multi-process production.
