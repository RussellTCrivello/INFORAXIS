# Authenticated Application — Frontend & Interface Integrity Audit

**Branch:** `arena/01a08e89-file-analysis`
**Base commit:** `e2766d7ebe76a747f8d9e17451cb15ae98bfedb1`
**Audit commits:** `c35e253`, `ae42cec`, `569c83a`
**Method:** source-first (file → function → caller → execution path → observed behavior); runtime verification used to *confirm* source-derived conclusions, never to replace them.

---

## 0. PHASE 0 — OPS-07 RESOLVED BEFORE ANY FRONTEND WORK

### OPS-07 (CRITICAL) — startup silently replaced a validated database configuration

**Source proof.** `core/initialization.py::initialize_database_config` seeded `database.*` one key at a time via `set_setting()`. `SETTING_DEFINITIONS` (settings/settings_models.py:529) contains **no** `database.*` keys, so `SettingsManager.set(..., validate=True)` looked up a definition, found none, and validated nothing. `set_setting()` then called `manager.save()`. `ensure_system_initialized()` runs this on **every** startup, not just the first, so an operator `config.json` silently overwrote the configuration an administrator had saved through the validated endpoint.

**Runtime proof (before fix).** With `config.json` = `{"database": {"host": "nonexistent-startup-host.invalid", "port": 5432}}`, a startup sequence rewrote `data/settings.json` from `127.0.0.1:5433` to `nonexistent-startup-host.invalid:5432` and exported it to `DB_HOST`/`DB_PORT` — persistent *and* active.

**Fix.** The mutation boundary was moved into `SettingsManager`:

* `SettingsManager.set()` / `update_many()` now **refuse** any `database.*` key unless `apply_database_config()` has deliberately opened the boundary (`_database_mutation_depth`).
* New `SettingsManager.apply_database_config(proposed, *, require_test=True, persist=True, activate=True)` is the single supported mutator: validate → probe → commit atomically (with in-memory **and** environment rollback on failure) → sync `DB_*` → persist → drop cached connections.
* `core/initialization.py` now builds one candidate and calls it; a rejection is **not** persisted and the process keeps the configuration it loaded from `settings.json`.
* `settings/routes.py::update_database_settings` delegates its commit to the same mutator instead of `setattr`-ing the live `DatabaseConfig` with a private copy of the rollback logic (this removed the third composition site).

### OPS-07 verification matrix (all 10 required cases)

| # | Case | Result |
| - | ---- | ------ |
| 1 | Valid startup configuration | Accepted / preserved |
| 2 | Invalid startup configuration | **Rejected**, existing kept, logged as `rejected and has NOT been applied` |
| 3 | Partial startup configuration (host only) | Merged; `port` fell back to current (5433), **not** to the `5432` default |
| 4 | Omitted database configuration | No-op |
| 5 | Malformed (string / port 99999 / empty host / list) | **Rejected** in all four variants |
| 6a | Environment override (valid) | Applied only after a successful probe |
| 6b | Environment override (invalid) | See classification below |
| 7 | Existing valid configuration, no `config.json` | Preserved; 22 interfaces intact |
| 8 | Clean installation (no `settings.json`) | Seeded from `config.json`; 22 interfaces restored |
| 9 | Restart ×3 | Idempotent |
| 10 | Recovery (invalid config removed) | Returns to the valid configuration |

**Case 6b classification — by design, not a defect.** When `DB_HOST` is itself invalid, `DatabaseConfig.apply_env_overrides()` (settings/settings_models.py:249) makes the environment authoritative over the file *at load time*, before any mutation code runs. `candidate_differs()` then compares the candidate against a `current` that already absorbed the environment, finds no difference, and skips the probe. Three facts establish this is not the OPS-07 failure mode:

1. The value comes from the **environment**, not from `config.json` — startup replaces nothing.
2. It is **pre-existing**: the old code also read `settings.database` after `apply_env_overrides()` and saved the same value.
3. It is **not silent**: with `DB_HOST=env-bogus.invalid`, `/health` returns `{"status":"degraded","checks":{"database":"error: OperationalError"}}` and startup logs `ERROR ... could not translate host name "env-bogus.invalid"`.

**Deliberate exemption.** On the *first* startup (`.system_initialized` absent) the connectivity probe is skipped, because there is no existing configuration to preserve; `POST /api/setup/install` runs `core.installer.test_database_connection` before installing (Api/routes/setup.py:123). Once a configuration exists, every later startup probes.

### Generic settings authorization — question closed

`core/security/flask_ext.py::_enforce_role_policy` makes blueprint `settings_api` admin-only for all mutating methods, except paths in `AUTH_SETTINGS_ANY_USER_WRITE_PATHS` (`/api/settings/system/language` only). Reads are admin-only except `/api/settings/theme`. Analyst/viewer receiving 403 on `/api/settings/<category>/<key>` is therefore the **intended** contract, not over-protection — this was the open question from the previous gate.

---

## 1. SOURCE ARCHITECTURE VERIFIED

* **Configuration mutation boundary** is now enforced in one place (`SettingsManager`), not in each caller. Verified: `manager.set("database.host", "sneaky-bypass-host")` → refused; `manager.save()` immediately after → disk unchanged; `update_many({"database.port": 1, ...})` → refused; `apply_database_config()` → works, and rejects a bad target.
* **Password security** (core/security/passwords.py): Werkzeug `scrypt`, salted; `verify_password` is constant-time and returns `False` on malformed hashes. Verified in the database: stored value begins `scrypt:32768:8:1$…`; the plaintext was absent from the row and from every API response.
* **Session/authorization stack**: session-token based (`_SESSION_TOKEN_KEY`), validated against a hash, with sliding expiry; `validate_session` rejects revoked, expired and inactive users (service.py:404).
* **Error handling**: `/api/file/999999/details` → `404 {"error":"File not found"}` — JSON, no stack trace.
* **Security headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP present.

---

## 2. USER MANAGEMENT

### Verdict: **BACKEND EXISTS / UI MISSING**

There is no User Management interface. Grepping the entire frontend for `api/auth/users` returns **zero** hits; no template, no page JS, no sidebar entry exists. The complete backend is:

| Route | Method | Enforcement |
| ----- | ------ | ----------- |
| `/api/auth/users` | GET | inline `current_user().is_admin` → 403 |
| `/api/auth/users` | POST | inline admin check |
| `/api/auth/users/<id>` | PATCH | inline admin check |
| `/api/auth/users/<id>/reset-password` | POST | inline admin check |

Per Phase 23 this is classified **MISSING / FUTURE FUNCTIONALITY** — not invented.

### End-to-end verification of the backend (all PASS)

* **List:** admin 200 with `id, username, role, is_active, must_change_password, created_at`; no password field of any kind. Analyst 403, viewer 403.
* **Create:** valid → 201. Rejected correctly: duplicate → `duplicate_username`; `short` → `weak_password` (policy: `PASSWORD_MIN_LENGTH`, default 12); `superadmin` → `invalid_role`; blank username → `invalid_username`; missing CSRF → 400.
* **Roles:** analyst and viewer are refused create, role-change, deactivate and password-reset (403).
* **Persistence:** row written; `password_hash` starts with `scrypt`; plaintext absent from the database.
* **Lifecycle:** created user authenticates (200) and is correctly *not* admin (403 on `/api/auth/users`). Admin changes role analyst→viewer (persisted). Deactivate → `/auth/me` reports `authenticated: false`, the admin API returns 401, login fails. Reactivate → login succeeds again.

### Deletion vs deactivation

**There is no delete endpoint.** Deactivation is the intended model and it is correctly implemented: `set_active(False)` sets `is_active` **and** revokes every live session in the same transaction (service.py:256). Test accounts were left deactivated, since deactivation is the only supported removal.

---

## 3. INTERFACE INVENTORY

24 authenticated page routes; **all return 200 for admin, with no redirect loops.**

| Interface | Route | Template | JS | Status |
| --------- | ----- | -------- | -- | ------ |
| Dashboard | `/` | Analysis/dashboard.html | pages/dashboard-page.js | VERIFIED |
| Charts dashboard | `/dashboard/charts` | Analysis/charts_dashboard.html | pages/charts-dashboard-page.js | VERIFIED |
| Comprehensive dashboard | `/dashboard/comprehensive` | Analysis/comprehensive_dashboard.html | pages/comprehensive-dashboard-page.js | VERIFIED |
| Path analysis | `/analytics/path-analysis` | Analysis/path_analysis.html | pages/path-analysis-page.js | VERIFIED |
| Archives | `/archives` | file/File_Management_Analysis_System.html | pages/archives-page.js | VERIFIED |
| Files | `/files` | file/files_list.html | pages/files-list-page.js | VERIFIED |
| File detail | `/file/<id>` | file/file_detail.html | pages/file-detail-page.js | VERIFIED |
| Full content | `/file/<id>/full-content` | file/full_content.html | pages/full-content-page.js | VERIFIED |
| Upload | `/upload` | file/upload.html | pages/upload-page.js | VERIFIED (302 — see §4) |
| Search | `/search` | Search/search.html | pages/search-page.js | VERIFIED |
| Advanced search | `/search/advanced` | Search/search_advanced.html | pages/search-advanced-page.js | VERIFIED |
| Enhanced search | `/search/enhanced` | Search/search_enhanced.html | pages/search-enhanced-page.js | VERIFIED |
| **Saved searches** | — *(no route)* | Search/saved_searches.html | pages/saved-searches-page.js | **DEAD / ORPHANED** |
| Keywords / detail | `/keywords`, `/keywords/<id>` | Keyword/*.html | pages/keywords-list-page.js | VERIFIED |
| Words / detail | `/words`, `/words/<id>` | Word/*.html | pages/words-list-page.js | VERIFIED |
| Categories | `/categories` | Category/categories_list.html | pages/categories-list-page.js | VERIFIED |
| Sources | `/sources`, `/sources/<id>` | Sources/*.html | pages/sources-list-page.js | VERIFIED |
| Sides | `/sides`, `/sides/<id>` | Side/*.html | pages/sides-list-page.js | VERIFIED |
| Email words | `/email-words` | email_words/email_words.html | pages/email-words-page.js | VERIFIED |
| Notifications | `/notifications` | Notifications/notifications.html | pages/notifications-page.js | VERIFIED |
| Import/export | `/import-export` | ImportExport/import_export.html | pages/import-export-page.js | VERIFIED |
| Operations | `/operations/import`, `/input`, `/jobs` | Operations/*.html | — | VERIFIED |
| Settings | `/settings` | Settings/settings.html | settings/settings-ui.js | VERIFIED |
| Concurrency | `/concurrency/` | concurrency/dashboard.html | pages/concurrency-dashboard-page.js | VERIFIED (admin-only, §6) |
| **File classification** | — *(no route)* | Analysis/file_classification.html | pages/file-classification-page.js | **DEAD / ORPHANED** |

**Orphaned (Phase 19).** `Analysis/file_classification.html` and `Search/saved_searches.html` are rendered by **no** route and included by **no** other template, yet each loads its own page JS. Two complete interfaces exist with no way to reach them. `base.html` and `components/*.html` are correctly orphaned (parent/includes).

---

## 4. NAVIGATION INTEGRITY

All 17 `url_for()` targets in `templates/base.html` resolve to registered endpoints — no dead links, no duplicate routes, no self-redirects.

`/upload` returns **302 → `/`**. This is correct, not broken: the `upload_files` interface is disabled in the default configuration, so `Api/routes/common.py` redirects, and the sidebar link is wrapped in `{% if is_interface_enabled('upload_files') %}` so it is not offered. The `/` self-redirect defect from the previous gate remains fixed.

---

## 5. FRONTEND / BACKEND CONTRACTS

* **Mismatch found:** `static/js/modules/core/language-switcher.js:91` POSTs to `/api/settings/system/language`, which the server (correctly) treats as the one settings write available to any authenticated user. Before the AUTH-01 fix the server returned 403 for viewers — see §6.
* **CSRF** is enforced by `CSRFProtect` with no exemptions: a create-user POST with no token returns `400 {"error":"CSRF token is missing or invalid"}` and no row is written.
* **Error contract** is consistent JSON (`{"error": ..., "success": false}`), including for missing resources.
* No evidence was found of JS calling removed endpoints; `/api/files` (404 in probing) is simply not a route the frontend uses.

---

## 6. ROLE / AUTHORIZATION MATRIX

| Interface / action | Admin | Analyst | Viewer |
| ------------------ | :---: | :-----: | :----: |
| `/settings` | 200 | 403 | 403 |
| `/concurrency/` | 200 | 403 | 403 |
| `/files`, `/search`, `/keywords`, `/words`, `/categories`, `/sources`, `/sides`, `/notifications`, `/import-export`, `/operations/jobs` | 200 | 200 | 200 |
| `/upload` | 302 | 302 | 302 |
| `GET /api/auth/users` | 200 | 403 | 403 |
| `GET /api/settings/database` | 200 | 403 | 403 |
| `GET /api/settings/theme` | 200 | 200 | 200 |
| `POST /api/settings/system/language` | 200 | 200 | 200 |
| `POST /upload/process-path` (`/etc/passwd`) | 403 | 403 | 403 |
| `GET /api/dashboard/stats`, `/api/keywords` | 200 | 200 | 200 |

*The `/upload/process-path` 403 is path containment, not authorization — valid ingestion paths succeed for all three roles.*

---

## 7. SECURITY FINDINGS

### Fixed in this audit

| ID | Severity | Finding |
| -- | -------- | ------- |
| **OPS-07** | CRITICAL | Startup overwrote a validated DB configuration with an unvalidated `config.json` target (§0). |
| **AUTHZ-01** | MEDIUM | `/concurrency/` and `/api/errors/*` exposed internal runtime state to **every** authenticated role. The blueprints were admin-only for writes and have no navigation entry, but reads were ungated, so a viewer could reach them by direct URL. Added to `AUTH_ADMIN_READ_BLUEPRINTS`. |
| **AUTH-01** | MEDIUM | Under-permission. `AUTH_SETTINGS_ANY_USER_WRITE_PATHS` exempted `/api/settings/system/language` from the admin check, but execution then fell through to the analyst-or-admin check, so viewers got 403 from the sidebar language switcher while `GET /set_language/<lang>` performed the same mutation for everyone. |
| **AUDIT-01** | MEDIUM | `PATCH /api/auth/users/<id>` and `POST .../reset-password` updated by id and never checked the row count, so a missing user returned `200 {"success": true, "user": null}` — success reported for a change never applied, and a temporary password minted for a non-existent account. Both now return `404 user_not_found`. |

### Verified safe (no defect)

* **Reflected XSS (search).** `<img src=x onerror=alert(1)>` appears only as `&lt;img src=x onerror=alert(1)&gt;` — inside an escaped attribute value and escaped element text. Neither occurrence is inside a `<script>` block.
* **Stored XSS (file content).** `content-formatter.js::formatTextContent` (line 2006) emits `${escapeHtml(content)}` into `<pre>`; tables (579/591), paragraphs (880) and file paths (1165) all escape. `escapeHtml` (modules/core/utils.js:11) is a complete DOM-based escape (`textContent` → `innerHTML`).
* **CSRF** enforced on every mutation tested.
* **Passwords** never returned by any API, never logged, stored as salted scrypt.
* **Deactivation** revokes live sessions in the same transaction.

### Defense-in-depth note (LOW, not changed)

CSP is present but `script-src 'self' 'unsafe-inline'`, which weakens XSS mitigation. This is pre-existing and structural — the templates rely on inline script blocks — so changing it is a redesign, not a fix.

---

## 8. FUNCTIONAL FINDINGS

| ID | Severity | Finding |
| -- | -------- | ------- |
| **FUNC-01** | MEDIUM | **User Management has no interface.** Four admin-authorized endpoints exist with zero UI (§2). Administrators cannot manage users without calling the API directly. Classified MISSING / FUTURE FUNCTIONALITY. |
| **FUNC-02** | LOW | Two complete interfaces (`file_classification.html`, `saved_searches.html`) plus their page JS are unreachable — no route renders them. |
| **FUNC-03** | LOW | `/api/search?q=XSSPROBE` echoed `"query": ""` and returned no results; the parameter name the UI uses was not confirmed against ingestion. Search-over-ingested-content needs its own contract review. |

---

## 9–11. DATABASE, PERFORMANCE, ACCESSIBILITY

Survey-level only — these phases were **not** audited interface-by-interface and are reported as indicators, not proven defects.

* **Database.** User-management SQL is fully parameterized and single-query per operation (no N+1). `set_active` performs both the status change and session revocation in one transaction. No partial writes were observed.
* **Performance.** 59 `SELECT … FROM` statements in routes/services/repositories do not carry an inline `LIMIT`; some are bounded by cursor pagination instead, so this is a flag for per-query review rather than a proven defect.
* **Accessibility.** 325 `<label>` elements and 183 `aria-*` attributes across 15 templates. **No `role="dialog"` was found on any modal**, which is a concrete ARIA gap worth a dedicated pass.
* **Responsive.** 141 fixed-width declarations (>100 px) in CSS — a survey indicator only.

---

## 12. DEAD / ORPHANED

* `templates/Analysis/file_classification.html` + `static/js/pages/file-classification-page.js` — no route.
* `templates/Search/saved_searches.html` + `static/js/pages/saved-searches-page.js` — no route.
* `templates/{403,404,500}.html`, `base.html`, `components/*` — legitimately referenced via handlers/extends/includes.
* No duplicate API wrapper was found: `static/js/modules/api/api-client.js` is the single `apiRequest`/`apiGet` implementation.

---

## 13. DEFECTS FOUND

| Severity | Count | IDs |
| -------- | :---: | --- |
| CRITICAL | 1 | OPS-07 |
| HIGH | 0 | — |
| MEDIUM | 3 | AUTHZ-01, AUTH-01, AUDIT-01 |
| LOW | 3 | FUNC-01, FUNC-02, FUNC-03 |

---

## 14. FIXES MADE

1. `settings/settings_manager.py` — `database.*` refused in `set()`/`update_many()` unless `apply_database_config()` opened the boundary; new `apply_database_config()` with atomic commit and memory+environment rollback; `_activate_database_config()` extracted.
2. `core/initialization.py` — startup routes through `apply_database_config()`; rejection is logged and nothing is persisted; non-dict `database` blocks are rejected.
3. `settings/routes.py` — `POST /api/settings/database` delegates its commit to the shared mutator (removed the third composition site).
4. `core/security/flask_ext.py` — AUTH-01 fall-through fixed; AUTHZ-01 admin-read blueprints extended.
5. `Api/routes/auth.py` — AUDIT-01 existence checks returning `404 user_not_found`.

---

## 15. UNRESOLVED

* **FUNC-01** — User Management UI does not exist. Requires a product decision (build the interface) rather than an audit fix.
* **FUNC-02** — two orphaned interfaces; decide whether to add routes or delete the files.
* **FUNC-03** — search parameter contract not confirmed.
* Phases 12, 13, 15, 16, 17, 18 were surveyed, not audited per interface; the indicators above (unbounded queries, missing `role="dialog"`, fixed-width CSS) need dedicated passes.
* 552 `innerHTML` sites exist in first-party JS. The highest-risk paths (search reflection, file content) were traced and are safe; a full sink-by-sink audit was not completed.
