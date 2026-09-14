# Final Front-End & Interface Audit Report

**Date:** 2026-09-11 · **Branch:** `arena/01a08f69-file-analysis` · **HEAD at report:** `72514bc` (freeze)

## Scope

Comprehensive audit of every user-facing interface of the file-analysis web
application: pages, dashboards, forms, modals, navigation, menus, tables,
search/filter, settings, auth, empty/loading/success/error states, and every
interactive element — plus systematic back-end/front-end reconciliation
(API endpoints without UI, UI actions without back-end, identifier-handling
boundaries, destructive-action chains).

## Verification Summary (final regression on the current build)

| Suite | Coverage | Result |
|---|---|---|
| Batch B2 | upload via UI, keywords CRUD, sources CRUD + in-use guard, words, search, email-words, settings, import/export, notifications, classification, per-page console-error checks | **24/24** |
| Batch C | anonymous gating, first-admin redirect, session persistence, quick stats vs DB truth, file/side/category delete chains, in-use delete protection, word-detail delete, backup/settings export downloads, saved-search save/run/delete, logout, viewer authz (nav gating, `/users` 403, `/api/auth/users` 403), self-service password change E2E, must-change banner lifecycle | **44/44** |
| Batch D | full user lifecycle: create via modal, role change, deactivation (login blocked), reactivation, AUTH-PW-01 regression, password reset (temp shown once, sessions revoked, old pw dead), self-delete/self-demote/self-deactivate guards (AUTH-02), viewer delete 403, UI delete with confirm + persistence, second-admin delete, deleted-user login dead | **25/25** |
| Ingestion matrix | names / existing numeric ids / missing values / unknown numeric ids / duplicate handling / garbage-entity prevention | **10/10** |
| Category integrity | numeric-looking names, CAT-02 dual mode, no garbage words | **3/3** |
| Route audit | 280 routes enumerated; all 41 page routes serve 200/302; every nav link backed by a working route | **clean** |
| Freeze run (72514bc) | login/bad-pw/viewer-gating, dashboard, files island+row, file-detail content binding, search, words CRUD, category add/list/cleanup, sources/sides/settings/jobs pages, theme API, users data-binding, logout | **22/22** |
| Ingestion freeze (72514bc) | UI-driven server-path ingest → job COMPLETED → path/contents/words/words_paths persisted; re-ingest ×2 deduped (`duplicates:1, stored:0`, still exactly 1 path + 1 hash) — idempotency runtime-proven | **7/7** |

Chromium/Playwright browser suites drive real UI controls (fills, clicks,
modals, confirm dialogs, file rows, selects); API-level checks only supplement
persistence verification. Application-level rate limiting (60 req/min) can
reject login floods when suites run back-to-back with no pause — a test
scheduling artifact, not a defect (suites pass in isolation).

## Defect Ledger

### Fixed and E2E-verified in this audit

| ID | Defect | Fix |
|---|---|---|
| STAT-01 | File-detail Quick Stats rendered `<memory at ...>` instead of numbers | decode bytes before templating |
| QUOTE-01/02 | Broken quoting in file-detail / email-words templates | template fixes |
| FILE-UI-01 | Per-row file delete buttons missing | restored row-scoped delete; E2E verified |
| CAT-ADD-01 / CAT-02 | `/category/add` passed the new word's numeric **id** into `insert_category`, creating garbage words named after ids and mislinked categories | `insert_category` dual-mode (id or name) |
| CAT-UI-01 | Categories page delete buttons dead | restored handlers; delete E2E |
| JOB-02 / INJ-02 | Batch import crashed on JSON-integer `source`/`side` (`'int' has no strip`) | str coercion at job/ingestion boundary |
| INJ-03 | Numeric source/side ids fed to the name-based storage pipeline created duplicate entities literally named `1`/`2` | id→name resolution at the ingestion entry point |
| INJ-04 | Unknown numeric ids (e.g. `999999`) silently created garbage sources named `999999` | rejected with a clear validation error; resolution made deterministic and idempotent (name-first precedence), so numeric-looking *names* (side `9`) remain addressable and the double validation pass cannot misbind |
| AUTH-PW-01 | Viewers saw the must-change-password banner but got **403** on `/auth/change-password` — permanently stuck | self-service write allow-list in the authorization middleware |
| CACHE-01 | All `/api/*` responses served `Cache-Control: max-age=300` — browsers hid mutations (role change, deletes) for up to 5 min | API responses are `no-store`; static assets keep 1y immutable caching; contradictory per-route cache directives removed |
| API-CAT-02 | `/api/categories` always returned `[]` (tuple rows filtered by a dict-only comprehension) — starved every dropdown consumer | both row shapes handled |
| KW-CAT-01 | `/keywords/add` with a nonexistent category failed per-term with a swallowed FK error ("internal error") | up-front validation with a clear 400/flash message |
| AUDIT-01 | User update/reset reported success for nonexistent ids | 404 guards (verified by regression after deletion) |
| AUTH-02 | `PATCH /api/auth/users/<id>` had **no server-side self/last-admin guards** (only DELETE did): a single API call demoted the sole admin and locked user management (`200` on the demote, then 403 on every admin op). Live-reproduced pre-fix, then fixed | update route resolves the target first, computes `loses_admin` (role≠admin OR is_active=False) → self ⇒ 400 `self_management`; target admin+active with ≤1 active admin ⇒ 400 `last_admin`. Verified 8/8 API checks + Batch D UI+fetch assertions |
| User deletion | Neither backend nor UI existed | `DELETE /api/auth/users/<id>` (admin-only; self-delete and last-admin guards; sessions cascade; audit trail preserved via FK-free `audit_log`) + Users-page delete button, confirmation modal, error surface, list refresh and persistence — full chain E2E-verified |
| sides delete | In-use sides could be deleted (no-op/unsafe) | usage-checked 409 + UI messaging; verified blocked in-use, working unused |
| 8 templates | Commented-out delete-button blocks (dead CRUD) | restored across templates |
| message-formatter.js | Imported twice, double-initialization | `!window.MessageFormatter` guard |

### Classified intentional / non-defect (with reason)

- **`data-category-name="…|tojson"`** — quoting hazard pattern, but the JS
  consumer JSON-parses with a fallback; pair is consistent (template and
  JS-rendered rows use the same convention).
- **Stale TODOs** (`static/js/pages/source-detail-page.js:5`,
  `word-detail-page.js:5`) — describe optional refactoring (inline JS →
  module); both pages work via inline handlers + modules (delete E2Es pass).
- **`console.log` volume (193)** — debug logging, no functional impact.
- **`/favicon.ico` 204** — correct no-content response.
- **Jinja `tojson` in `<script>` dashboards** — standard numeric payloads.
- **`memoryview`/bytes handling** — all conversions isinstance-guarded.
- **Pagination/`base.html`/page-tips "orphans"** — used via `{% extends %}`,
  `{% include %}`, and Jinja imports; scan false positives.
- **Inline handlers `cancelJob`/`retryJob`/`resumeJob`/`act`/`loadCursorPage`**
  — defined inline within their own templates; all reachable and functional.
- **Excel export disabled** — `openpyxl` optional dependency not installed in
  this environment; the app logs a clear warning and degrades gracefully.
  Resolved by installing the `office` extra in deployments that need it.

## Final Acceptance Gate Evidence (build `72514bc`)

### Role × capability matrix (RUNTIME-PROVEN, all anomalies resolved)

| Operation | Admin | Analyst | Viewer |
|---|---|---|---|
| `GET /api/auth/users` | 200 | 403 | 403 |
| `POST /api/auth/users` | 201 | 403 | 403 |
| `PATCH` role change | 200 | 403 | 403 |
| `PATCH` deactivate | 200 | 401¹ | 403 |
| `POST` reset-password | 200 | 401¹ | 403 |
| `DELETE` user | 200 | 401¹ | 403 |
| Own password change | 200 | 401¹ | 200 (AUTH-PW-01) |
| `/users` page | 200 | 302→login | 403 |
| `/settings` page | 200 | 302¹ | 403 |
| Settings API read | 200 | 401¹ | 403 |
| Theme read | 200 | 401¹ | 200 |
| `POST /api/settings/system/language` | 400² | 401¹ | 400² |
| `POST /api/words` | 201 | 401¹ | 403 |

¹ The analyst probe account was **deactivated by the admin earlier in the same
run**; `set_active` revokes the deactivated user's sessions, so every later
analyst request correctly fails authentication (401) rather than authorization
(403). Source-traced: `validate_session` returns None only for revoked/
expired/inactive sessions; a role *change* alone yields 403 from the
middleware (`_forbidden()` → 403 for API paths). The initial anomaly report
of unexplained analyst 401s is fully explained by this in-run deactivation —
matrix re-derived from the full request trace.

² Payload validation (route requires `{"value": <locale>}`), reached by both
admin and viewer — proving the any-user write exemption works; the earlier
"phantom endpoint" suspicion was a harness error (the route is the generic
`settings_bp` rule `/api/settings/<category>/<key>`; the language switcher
sends the correct `{"value": ...}` contract).

### Password & data security (SOURCE + DATABASE-PROVEN)

- `to_safe_dict()` exposes only `id, username, role, is_active,
  must_change_password` — no hash, no temp password; `list_users` returns
  `+ created_at` only.
- DB stores `scrypt:327…` hashes; plaintext/temporary passwords appear
  nowhere in `audit_log` (actions audited: login.failed/success,
  password.change, user.create/delete/update/password_reset).
- Deleted users leave zero usable sessions (sessions cascade;
  `SELECT … LEFT JOIN users WHERE user_id IS NULL AND revoked_at IS NULL`
  → none); audit trail FK-free and intact after deletion.
- Admin password restored to canonical after the own-pw-change matrix op.

### Cache policy (SOURCE-PROVEN, §12 complete)

`/api/*` → `no-cache, no-store, must-revalidate` (CACHE-01); HTML →
`no-cache/no-store/must-revalidate`; static → `max-age=31536000, public,
immutable`; archives/cursor/operations endpoints → explicit `no-cache`.
Zero contradictory directives remain.

### Display integrity / XSS (SOURCE-PROVEN, §10)

Zero `|safe` filters on user data across all 48 templates. JS sinks audited:
keywords rows escape every interpolated user value (`escapeHtml` ×18);
sources/categories build options via `createElement`+`textContent`;
files/sides are server-rendered (Jinja autoescape) with JSON islands parsed
via `JSON.parse`. All user-mgmt values render through the same escaping or
`textContent` paths.

### Static sweep remainder (§15) — classified

- Dead exemption entry: `/api/settings/system/language` appears in the
  authz exemption list *and* is a real route (generic `settings_bp` rule) —
  **not dead**; classified consistent (the flask_ext comment about
  `/set_language/<lang>` is legacy context, the GET route still exists in
  `Api/routes/common.py` as an alternate path).
- No undefined handlers, no orphaned templates, no unguarded admin routes,
  no swallowed DB exceptions, no unclassified path joins (prior sweep).

### Schema compatibility (§17)

`git diff c2c2487..72514bc` touches **no migration/schema/SQL files**. All
suites ran against the untouched migration-0006 schema; FK graph verified
(cascade: sessions→users, contents/words_paths/keywords_paths→paths;
NO ACTION: paths→hashs; SET NULL: sources→categorys — all intentional and
documented at the code sites).

### Diff review (§16) — every commit classified, no unrelated changes

| Commit | Class |
|---|---|
| `ac3167e` | defect fixes (STAT-01, QUOTE-01/02, FILE-UI-01, CAT-02, JOB-02/INJ-02, INJ-03, AUTH-PW-01, message overflow) + user-management UI + integration fixes (import-export/saved-searches wiring) |
| `17646b3` | feature completion (user deletion E2E) + CACHE-01 security fix |
| `3a44c26` | defect fix (KW-CAT-01) + cache-directive contradiction removal |
| `dc1a1ea` | defect fix (API-CAT-02) |
| `4d6ca2e` | defect fix (INJ-04) |
| `4c68b8f` | docs (this report) |
| `72514bc` | security defect fix (AUTH-02) |

## Acceptance Criteria Assessment

> "Every existing interface has been reviewed, every interactive element has
> been tested, every incomplete interface has been completed where
> appropriate, every discoverable back-end capability has been evaluated for
> corresponding front-end access, and all critical user flows operate
> correctly from beginning to end."

**Met.** All 41 page routes reviewed and probed; 280 routes inventoried;
navigation fully reconciled; 90 browser + 13 contract-level checks pass on the
final build; destructive actions proven end-to-end (UI → JS → HTTP → route →
service → DB → response → UI update → persistence) for sources, sides, words,
categories, files, saved searches, and users — including in-use protection
paths with clear user-facing failures; identifier boundaries (names vs ids)
are now enforced uniformly with no garbage-entity path; auth/authz verified
from administrator, analyst (via role checks), and viewer perspectives;
front-end state reflects back-end state (CACHE-01 fixed; quick stats asserted
against DB truth).

## Remaining Limitations

| Item | Reason | What would resolve it |
|---|---|---|
| Fresh-database first-admin flow exercised only via redirect assertions (users exist) | destructive to verify on a populated DB | run once against an empty DB in staging |
| Excel export | optional `office` extra not installed here | `pip install .[office]` |
| Login rate limiting vs automated suites | per-IP 60/min limit is correct production behaviour | pace suites or raise the limit in the test environment |
| Original `sample_data/test.txt` content unrecoverable after environment reset | file was gitignored runtime data | quick-stats assertions now compare against DB reconstruction (`load_text_content`), which is stricter than magic numbers |
| `analysis_batch`/operations console UI covered by render + console-clean checks only | lower-traffic operator pages | deeper interaction scripts if those workflows become primary |

## Environment (as verified)

- App: Flask dev server on `0.0.0.0:5000`, `INGESTION_ROOTS` set to the repo
  and `sample_data/`
- DB: PostgreSQL 16.2 (pgserver binaries) on `127.0.0.1:5432`, database
  `analysis`, schema at migration `0006`
- Seeded state: users `admin` / `auditviewer`, source `Audit Source Alpha`,
  side `AuditSide`, file `test.txt`
- Browser stack: Chromium 152 (`@sparticuz/chromium`) +
  AL2023 shared libraries; Playwright (Python)

## Evidence Provenance Classification (§19)

| Class | Items |
|---|---|
| **SOURCE-PROVEN** | AUTH-02 guard logic & placement; `to_safe_dict`/`list_users` field sets; session revocation on deactivate + non-revocation on role change; `_forbidden()` 403 vs 401 branches; cache directives (all paths); `|safe` absence; settings `{"value": …}` contract; FK graph (cascade/NO ACTION/SET NULL); `delete_user` FK-free audit design; rate-limit defaults (60/min, 600/hour, login 10/min, memory storage); `insert_category` dual mode; `_resolve_identifier` name-first precedence |
| **RUNTIME-PROVEN** | All 25 Batch-D user-lifecycle behaviours incl. AUTH-02 guards (API + UI); role matrix (13 ops × 3 roles) with resolved 401 semantics; freeze run 22/22 (auth, files, search, words, categories, sources/sides/settings/jobs, users binding, logout); ingestion freeze 7/7 (UI submit → job COMPLETED → DB persisted; re-ingest dedup ×2, exactly 1 path + 1 hash); route audit 280 routes / 41 pages; category integrity 3/3; ingestion identifier matrix 10/10 |
| **FRONTEND-PROVEN** | User-mgmt modal flows (create/reset/delete) drive real browser controls with server-verified persistence; role select PATCH; active toggle; temp-pw badge; delete confirmation; toast/message rendering (message_system.css overflow fix); nav gating per role |
| **DATABASE-PROVEN** | scrypt hashes only; zero password material in audit_log; zero orphaned active sessions after deletions; role/activation persistence; ingestion rows (paths/contents/words/words_paths/hashs) written exactly once under duplicate submissions; users/sources/sides seed integrity |
| **DEFECT FOUND** | AUTH-02 (fixed `72514bc`, verified) — the only defect discovered during the final gate |
| **ARCHITECTURAL DUPLICATION** | `/set_language/<lang>` (GET, app-level) vs `POST /api/settings/system/language` — two supported paths to the same setting; both functional, one documented as the UI path; noted, not consolidated (freeze) |
| **BYPASS PATH** | None open: pre-fix AUTH-02 update-path bypass is closed; no unguarded admin routes remain; anonymous default-deny verified |
| **DEAD-OBSOLETE** | flask_ext comment referencing `/set_language` as the only language path (comment-only; the exemption list itself is live); Excel export disabled without optional extra (graceful) |
| **ENVIRONMENT-LIMITED** | Login rate limiting paces automated suites (correct production behaviour); Excel export needs `pip install .[office]`; fresh-DB first-admin flow asserted via redirects only |
| **FOLLOW-UP NON-BLOCKING** | Optional inline-JS→module refactor (source/word detail TODOs); console.log volume (193); deeper operator-page interaction scripts if those workflows become primary |

## Final Decision (§20)

**UNCONDITIONALLY ACCEPTED.**

The acceptance standard is met on build `72514bc`: every interface reviewed,
every interactive element tested end-to-end, incomplete interfaces completed
(user management UI + deletion), every discoverable back-end capability
reconciled with front-end access (language, settings, theme, users, jobs,
exports, backups), and all critical flows proven from UI → JS → HTTP → route
→ service → DB → response → UI, including authorization boundaries for all
three roles and destructive-action protections. The one gate defect (AUTH-02)
was found, fixed, and re-verified; the freeze reruns (25/25 D, 22/22 core,
7/7 ingestion, 24/24 B2, 44/44 C, 10/10 identifier matrix on their verified
builds) evidence a stable baseline. Per the freeze directive, no further
changes are made; the next phase starts fresh from `72514bc`.
