# Post-Remediation Independent Acceptance Audit

**Repository:** `RussellTCrivello/file_analysis`
**Branch:** `arena/01a08e89-file-analysis`
**Baseline (pre-remediation) commit:** `e2766d7ebe76a747f8d9e17451cb15ae98bfedb1`
**Audit date:** 2026-09-10
**Method:** source-code-first. Every claim below is traced to a file, line and call path. Runtime probes are used only to *confirm* a source-level conclusion already reached by reading code; they are never the basis for acceptance.

---

## 1. Executive Summary

The remediation under review is **substantially correct but was not complete**, and **shipped one defect of its own**.

Fifteen defects were remediated in the diff. Fourteen verify correctly against source. One — SEC-03, the settings authorization fix — was **over-broad** and broke two features that render on every page for every non-admin user. I found and fixed that regression.

The more serious finding is what the remediation **exposed rather than caused**. The headline fix (ING-01, ingestion `UnboundLocalError`) removed only the *first* of **four** consecutive blockers in the same function. Because ingestion had never once succeeded, three further defects behind it had never executed:

* `monitor_interval=2.0` — not a parameter of `IntegratedFileReader.__init__` → `TypeError`
* `reader.initialize()` — no such method → `AttributeError`
* `reader.shutdown()` — no such method → `AttributeError` (swallowed, logged)

And critically, the task manager's `_task_lock` is a plain `threading.Lock` that is **acquired recursively in six places**. The moment a task reached any terminal state — success, cancel **or** failure — the worker thread self-deadlocked holding the lock forever. That permanently wedged every `/upload/*` endpoint for the lifetime of the process: `create_task`, `get_task_progress`, `pause`, `resume`, `cancel`. Each new request leaked a thread blocked on the same lock. This was reproduced with a `py-spy` thread dump showing the worker blocked at `_add_task_log` (from `_update_task_error`) and two request threads blocked at `get_task_progress`.

This is the **same defect class as CONC-01** (the error-monitor deadlock the diff already fixed) in a **different file** — exactly what a pattern-wide audit exists to find. A second, independent concurrency defect was found in the same class of file: an **ABBA lock-order inversion** between `_task_lock` and `_pause_lock` (`cancel_task`/`pause_task`/`resume_task` take them one way; `wait_if_paused`, which runs inside every processing loop, takes them the other).

Net effect before this audit's corrections: **server-path ingestion had a 0% success rate, and one failed task was enough to permanently disable the entire upload subsystem for that process.**

After correction, 32 concurrent ingestion tasks (success and failure paths interleaved) completed with **zero errors, zero tracebacks and zero hangs**, and the subsystem stayed responsive throughout.

**Verdict: CONDITIONALLY ACCEPTED.** See §19.

---

## 2. Changed Files

17 files, **+548 / −159** (figures include the corrections made during this audit).

| File | ± | Area |
|---|---:|---|
| `Api/task_manager.py` | 214 | Ingestion task lifecycle, locking |
| `Api/services/search_service.py` | 73 | Search, LIKE escaping, N+1 |
| `Api/routes/dashboard.py` | 64 | Dashboard queries |
| `core/security/flask_ext.py` | 61 | Authorization policy engine |
| `database/__init__.py` | 60 | Query executor, bulk insert |
| `Api/blueprints/files.py` | 38 | Upload, path validation, bulk delete |
| `settings/settings_adapter.py` | 39 | Settings adapter, `/health` probe |
| `database/database/queries/word_path_queries.py` | 30 | `words_paths` insert |
| `Api/routes/keywords.py` | 28 | Keyword routes |
| `static/js/pages/keywords-list-page.js` | 20 | Keyword UI |
| `database/database/repository/words_paths_repo.py` | 18 | `words_paths` repo |
| `Api/routes/api.py` | 18 | Categories, export JSON encoding |
| `Api/routes/search.py` | 22 | Search, user attribution |
| `Hdg_Err_Ex_Log/error_monitoring.py` | 8 | Error monitor lock |
| `Api/routes/words.py` | 6 | Word routes |
| `static/js/pages/words-list-page.js` | 6 | Word UI |
| `templates/base.html` | 2 | Script load |

No file was created or deleted. No build artefacts, no generated data, no credentials are present in the diff.

---

## 3. Changed Functions

| ID | Function / symbol | File | Change |
|---|---|---|---|
| ING-01 | `_process_task` (source/side lookup) | `Api/task_manager.py` | Look up source/side **by id** (`get_source_by_id`) instead of by name; raise `ValueError` if either is unknown |
| ING-02 | `_process_task` (reader ctor) | `Api/task_manager.py` | Removed invalid `monitor_interval=2.0` kwarg *(this audit)* |
| ING-03 | `_process_task` (reader init) | `Api/task_manager.py` | Removed `reader.initialize()` — method does not exist *(this audit)* |
| ING-04 | `_process_task` (final stats, ×2) | `Api/task_manager.py` | Single-file tasks now count real results instead of the reader's batch-only counters *(this audit)* |
| ING-05 | `_process_task` (cleanup) | `Api/task_manager.py` | `reader.shutdown()` → `reader.__exit__(None,None,None)` *(this audit)* |
| CONC-01 | `ErrorMonitor.__init__` | `Hdg_Err_Ex_Log/error_monitoring.py` | `_lock`: `Lock` → `RLock` |
| CONC-02 | `FileProcessingTaskManager.__init__` | `Api/task_manager.py` | `_task_lock`: `Lock` → `RLock`; documented mandatory lock order *(this audit)* |
| CONC-03 | `pause_task`, `resume_task`, `cancel_task` | `Api/task_manager.py` | Reordered to `_pause_lock` → `_task_lock`; logging moved outside critical sections *(this audit)* |
| SEC-03 | `_enforce_role_policy` | `core/security/flask_ext.py` | Match `settings_api` blueprint, not `settings.`; added `AUTH_SETTINGS_ANY_USER_{READ,WRITE}_PATHS` exemptions *(exemption this audit)* |
| SEC-04 | `SearchService._find_matching_lines` | `Api/services/search_service.py` | HTML-escape the line before injecting `<mark>` |
| SEC-05 / API-05 | `_escape_like` (new), `_build_pattern`, `simple_search` | `Api/services/search_service.py` | Escape `%`/`_` wildcards; drop the redundant quote-doubling on a bound parameter |
| SEC-06 | `process_path` | `Api/blueprints/files.py` | Added `validate_ingestion_path` containment check against `INGESTION_ROOTS` |
| DB-01 | `insert_words_paths` | `database/database/queries/word_path_queries.py`, `…/words_paths_repo.py` | `ON CONFLICT` → `WHERE NOT EXISTS` |
| DB-02 | `bulk insert` | `database/__init__.py` | Removed `print(query)` of the full INSERT |
| DB-05 | `delete_file`, `bulk_delete` | `Api/blueprints/files.py` | Extract count from the 1-tuple before comparing to `0` |
| API-02 | `list_categories` | `Api/routes/api.py` | Replaced call to non-existent `categorys_repo.list_categories()` |
| API-03 | export JSON encoding | `Api/routes/api.py` | `Decimal`/`date` default for `json.dumps` |
| API-04 | `_current_user_id` (new) | `Api/routes/search.py` | Read `session['auth_user_id']`, not the never-set `session['user_id']` |
| PERF-01 | `SearchService` | `Api/services/search_service.py` | `MAX_LINE_MATCHES_PER_FILE = 10` bounds the per-result file scan |
| OPS-01 | `SettingsAdapter.version` | `settings/settings_adapter.py` | Implement the attribute `/health` probes |

---

## 4. Critical Fix Verification

### 4.1 ING-01 — ingestion `UnboundLocalError` — **VERIFIED, but insufficient on its own**

**Original broken path.** `Api/task_manager.py` received `source_id`/`side_id` (integers) from the request but called `get_source_by_name(source_id)` / `get_side_by_name(side_id)` — a *name* lookup fed an *id*. The lookup never matched, so `source_name`/`side_name` were never bound, and the reader constructor raised `UnboundLocalError: cannot access local variable 'source_name'`. Every server-path ingestion task ended in `Failed to initialize IntegratedFileReader`.

**Remediation.** Switched to `get_source_by_id` / `get_side_by_id`, with an explicit `ValueError` when either id is unknown.

**Verification.** The ids are now resolved correctly — confirmed indirectly by the fact that a task now reaches the reader constructor and stores a file (`Storage confirmed: 'evidence.txt' → Database (Path ID: 61)`).

**But this fixed only blocker 1 of 4.** With ING-01 alone, ingestion still failed 100% of the time — first with `TypeError: … unexpected keyword argument 'monitor_interval'`, then with `AttributeError: 'IntegratedFileReader' object has no attribute 'initialize'`. Those are ING-02 and ING-03 below.

**Evidence that ING-02/03/05 are pre-existing, not introduced by this remediation** — they are all present in the baseline commit:

```
$ git show e2766d7e:Api/task_manager.py | grep -nE "monitor_interval|reader\.initialize|reader\.shutdown|_task_lock = "
76:        self._task_lock = threading.Lock()
375:                    monitor_interval=2.0,
381:                reader.initialize()
531:                            reader.shutdown()
```

### 4.2 CONC-01 — error-monitor self-deadlock — **VERIFIED**

`ErrorMonitor._lock` is now `RLock`. Verified by source: `get_metrics()` acquires the lock and calls `_get_recent_errors()`, which acquires it again — genuine recursion. Acquisition sites 226 / 310 / 362 / 372 / 400 / 405 all checked; **no DB call, logging call or external-service call is made while the lock is held**. The sibling `_monitor_lock` (line 420) is a plain `Lock` but only guards singleton creation and is never nested — correct as-is.

Runtime corroboration: 40 concurrent requests across `/api/errors/{metrics,recent,patterns,stats}` completed in 0.75 s (max 0.374 s).

### 4.3 DB-01 — `words_paths` upsert — **VERIFIED, and the schema observation is correct**

Source: `words_paths` is created by `m0001_initial_schema` with **no primary key, no `id` column, and no unique index** — only the non-unique `idx_words_paths_path_word`. The original `ON CONFLICT (path_id, word_id) … RETURNING id` was therefore *always* invalid SQL. The `WHERE NOT EXISTS` rewrite is the correct fix **given the constraint that no schema change may be applied**.

I independently dumped every unique/primary index from the live PostgreSQL instance and cross-checked **every** `ON CONFLICT` target in the repository. All others are backed by a real constraint:

| Table | Target | Backing constraint |
|---|---|---|
| `hashs` | `(hash, source_id, side_id)` | `hashs_hash_source_id_side_id_key` |
| `keywords_paths` | `(path_id, keyword_id)` | `unique_keywords_paths_path_keyword` |
| `words_categorys` | `(word_id, category_id)` | `unique_word_category` |
| `categorys` | `(word_id)` | `categorys_word_id_key` |
| `words` | `(word)` | `words_word_key` |
| `punctuation` | `(punctuation_text)` | `punctuation_punctuation_text_key` |
| `sides` / `sources` / `users` | `(name)` / `(name)` / `(username)` | unique |

**`words_paths` is the sole outlier** — confirming the original finding rather than assuming it.

**Recommendation (reported, NOT applied):** a `CREATE UNIQUE INDEX ON words_paths(path_id, word_id)` would restore true upsert semantics and make the insert race-free at the database level instead of relying on `WHERE NOT EXISTS`. This is a schema change and is deliberately withheld per the database safety gate.

---

## 5. Security Verification

### SEC-04 — search highlighter XSS — **VERIFIED**

Source trace: `_find_matching_lines` produced `highlighted_line` by splicing `<mark>` into raw file content. That field is rendered with `innerHTML` by `static/js/modules/search/advanced-search.js` (`match.highlighted_line || escapeHtml(match.line_text)`), while the sibling `line_text` **is** escaped. Any file containing HTML metacharacters therefore injected markup into the DOM. The fix escapes the line before injecting the tag. The asymmetry between the two fields in the JS is what made this non-obvious and is now handled server-side, which is the correct layer.

### SEC-05 / API-05 — LIKE escaping — **VERIFIED**

Two distinct bugs in one expression:
1. `f'%{term}%'` passed as a bound parameter — `%` and `_` in user input acted as wildcards. A search for `%%` returned the entire corpus. Now escaped.
2. `simple_search` did `term.replace("'", "''")` on a value that is *already* a bound parameter — a literal `O'Brien` could never match. Removed.

Both fixes are correct: bound parameters need no quote escaping, but wildcard escaping must be done explicitly because it is interpreted *inside* the SQL value, not by the driver.

### SEC-06 — server-path ingestion containment — **VERIFIED**

*Source-side:* `validate_ingestion_path` is fail-closed — with no roots configured, **every** path is rejected.

*Runtime:* 11 malicious paths tested with roots unset — all `403`: `/etc/passwd`, `../../../etc/passwd`, URL-encoded traversal, `C:\Windows\win.ini`, `\\server\share\file.txt`, null-byte injection, `/proc/self/environ`, non-existent path, a directory, `.flask_secret_key`, `.env`.

With `INGESTION_ROOTS=/tmp/audit/ingest_root` set, verified:

| Path | Result |
|---|---|
| `/tmp/audit/ingest_root/evidence.txt` (in root) | `202` → completed |
| `evidence.txt` (relative to root) | `202` → completed |
| `/etc/passwd` (outside) | `403` |
| `/tmp/audit/ingest_root/../../etc/passwd` (traversal) | `403` |
| `/tmp/audit/ingest_root/link_to_passwd` (symlink inside root → `/etc/passwd`) | `403` |

The **symlink case is the one that matters** and it is handled: containment is resolved against the real path, so a symlink planted inside an approved root cannot be used to escape it.

### Secrets

No secret values appear anywhere in the diff. `DB-02` removed a `print(query)` that dumped full INSERT statements to stdout.

---

## 6. Authorization Verification

### SEC-03 — settings gating — **the remediation was over-broad; I introduced and then fixed a regression**

**What the original fix got right.** The test was `full_endpoint.startswith("settings.")`, but the blueprint is registered as `settings_api` and the settings page is the app-level `settings_page_direct` route. The check matched **nothing**. Any authenticated user — including `viewer` — could read `/settings` and `/api/settings/database` (which exposes database host, port, user and password in plaintext), and any `analyst` could POST to `/api/settings/*`. That is a genuine and serious privilege-escalation defect, correctly identified.

**What it got wrong.** The fix gated the entire `settings_api` blueprint to admin. But two endpoints in that blueprint are consumed by **every page, by every role**:

* `static/js/modules/ui/theme-manager.js:313` — `GET /api/settings/theme`, loaded unconditionally by `templates/base.html:188`
* `static/js/modules/core/language-switcher.js:91` — `POST /api/settings/system/language`, from the sidebar switcher available to all users

Under the original fix both returned `403` for analyst and viewer — theming and language switching broken for everyone but admin. Confirmed by direct request.

**The security justification for exempting the language write is that the exemption adds nothing.** `Api/routes/common.py:47` exposes `GET /set_language/<lang>`, which performs the *same global mutation* for *any* authenticated user. I verified this: an analyst issuing `GET /set_language/ar` received `200`, and an admin subsequently read `system.language == ar`. Gating the API equivalent while leaving the app route open was security theatre with a real availability cost.

**Corrected design.** Two explicit, minimal, auditable allowlists in `core/security/flask_ext.py`:

```python
AUTH_SETTINGS_ANY_USER_READ_PATHS  = {"/api/settings/theme"}
AUTH_SETTINGS_ANY_USER_WRITE_PATHS = {"/api/settings/system/language"}
```

exempted inside `_enforce_role_policy` in the GET and write branches respectively. Everything else in the blueprint stays admin-only.

### Verified 3-role matrix (live instance)

| Endpoint | admin | analyst | viewer |
|---|---|---|---|
| `/settings` and all sub-pages | 200 | 403 | 403 |
| `/api/settings/` (index) | 200 | 403 | 403 |
| `/api/settings/database` | 200 | 403 | 403 |
| `/api/settings/system` | 200 | 403 | 403 |
| `/api/settings/theme` | 200 | **200** | **200** |
| `/api/settings/{storage,export,backups,interfaces,page,1/1}` | 200 | 403 | 403 |
| `POST /api/settings/app_name` | 200 | 403 | 403 |
| `POST /api/settings/custom_css` | 200 | 403 | 403 |
| `POST /api/settings/interfaces` | 200 | 403 | 403 |
| `POST /api/settings/logo/remove` | 200 | 403 | 403 |
| `POST /api/settings/reload` | 200 | 403 | 403 |
| `POST /api/settings/system/language` | 200 | **200** | 403 |
| `POST /api/settings/{batch,reset}` | 400 * | 403 | 403 |
| `GET /set_language/en` | 302 | 302 | 302 |

\* `400` is request-body validation, not an authorization failure.

Non-admins are denied on **every** settings read and every settings mutation except the two allowlisted paths. The privilege escalation is closed.

### API-04 — search-history user attribution — **VERIFIED**

The auth middleware stores the user id under `session['auth_user_id']` (`_SESSION_USER_KEY` in `core/security/flask_ext.py`). The code read `session['user_id']`, which is never set — so history and saved searches were recorded with `user_id = NULL`, attributable to no one and uncleanable. Fixed with a `_current_user_id()` helper reading the correct key.

---

## 7. Filesystem Security Verification

Covered in §5 (SEC-06). Summary: fail-closed when unconfigured; absolute-path, relative, traversal, UNC, Windows, null-byte, `/proc`, directory and secret-file probes all rejected; symlink escape rejected when roots are configured; legitimate in-root files accepted and ingested.

---

## 8. Database Verification

### DB-01 — `words_paths` — **VERIFIED** (see §4.3)

### DB-05 — bulk-delete hash orphans — **VERIFIED**

Both delete paths (`delete_file` and `bulk_delete` in `Api/blueprints/files.py`) did:

```python
hash_usage = execute_query("SELECT COUNT(*) FROM paths WHERE hash_id = %s", (hash_id,), fetch="one")
if hash_usage and hash_usage == 0:      # (0,) == 0  ->  always False
```

`execute_query(fetch="one")` returns a **row tuple** `(0,)`. Comparing a tuple to an int is always `False`, so the branch **never fired** and every deletion left an orphaned `hashs` row. Because ingestion dedupes on hash, an orphaned hash made the deleted file **permanently non-reingestable** — the real user-visible harm. Both sites now extract `hash_usage[0]`.

### Database safety gate — **PASSED**

The diff contains **no** `DROP`, `TRUNCATE`, `ALTER TABLE`, `CREATE TABLE`, `CREATE INDEX` or schema-replacing statement. A `DELETE FROM hashs …` appears in the diff grep, but it is a **context line** (verified: `git diff -U3 | grep -E "^[+-].*DELETE FROM hashs"` returns nothing) — it is pre-existing targeted row deletion, not a destructive statement, and is now correctly guarded by a reference count.

No production data was modified.

### SQL injection

All user input reaches the database through bound parameters. The one SQL-construction risk found (SEC-05 wildcard injection) is a semantic, not an injection, defect and is fixed.

---

## 9. Concurrency Verification

This is where the remediation was most incomplete. **Three** pre-existing concurrency defects exist in `Api/task_manager.py`; the diff addressed none of them.

### CONC-02 — `_task_lock` self-deadlock — **CRITICAL, FIXED THIS AUDIT**

`_task_lock` was a plain `threading.Lock` (`Api/task_manager.py:76` at baseline). It is acquired **recursively in six places** — `_update_task_error`, `pause_task`, `resume_task`, and three terminal branches of `_process_task` all call `_add_task_log`, which acquires the same lock while it is already held.

Consequence: the first task to reach *any* terminal state — success, cancel or failure — self-deadlocked while **holding the lock**. The lock is never released, so every subsequent `/upload/*` request blocks forever and leaks a worker thread. One failed ingestion permanently disables the upload subsystem for that process.

**Proof (py-spy dump of the wedged instance):**

```
Thread 25865 "task_beaaf9c7_Process: evidence.txt"
    _add_task_log (task_manager.py:653)
    _update_task_error (task_manager.py:649)     <-- already holding _task_lock
    _process_task (task_manager.py:405)
Thread 25868 / 25943 "process_request_thread"
    get_task_progress (task_manager.py:149)      <-- blocked on the same lock
    upload_progress (blueprints/files.py:308)
```

Note the worker thread shows **0% CPU** — this is a blocked lock, not a busy loop, which is why it is invisible to CPU monitoring.

**Fix:** `_task_lock` → `threading.RLock()`, with the recursion documented at the definition site. This matches the pattern already applied to `error_monitoring.py`.

### CONC-03 — ABBA lock-order inversion — **CRITICAL, FIXED THIS AUDIT**

`RLock` alone is insufficient, because two *different* locks are involved:

* `cancel_task` / `pause_task` / `resume_task` acquired **`_task_lock` → `_pause_lock`**
* `wait_if_paused` — which runs inside **every** processing loop — acquired **`_pause_lock` → `_task_lock`**

Thread A holding `_task_lock` and wanting `_pause_lock`, against thread B holding `_pause_lock` and wanting `_task_lock`, is a textbook deadlock that no re-entrancy fixes.

**Fix:** established a single mandatory order — **`_pause_lock` (outer) → `_task_lock` (inner)`** — chosen because `wait_if_paused` is the hot path and harder to restructure. `pause_task`, `resume_task` and `cancel_task` were reordered accordingly, and their `_add_task_log` calls were moved **outside** both critical sections, which both shortens the critical sections and removes the recursion entirely for those methods.

### Verification of both

Direct in-process test against the real class:

```
_task_lock: RLock | _pause_lock: lock
recursive _update_task_error returned: True | thread alive (True==DEADLOCK): False
status: TaskStatus.FAILED | logs: 2
pause/resume/cancel returned: True | alive (True==DEADLOCK): False
ABBA race 4s: alive (True==DEADLOCK): [False, False]
```

System-level: 30 submissions (success and failure interleaved) plus 6 threads hammering progress/pause/resume/cancel — 66 poller iterations, all tasks `202`, and the final `/upload/active-tasks` returned in **0.004 s**. Before the fix that call hung indefinitely.

### Repository-wide lock pattern audit

I enumerated all 44 lock definitions in the codebase. The two `RLock` conversions are the only changes made. `error_monitoring.py::_monitor_lock`, `settings_manager.py::_manager_lock`, `task_manager.py::_thread_lock`, `services/jobs/manager.py::_*` and the rest were inspected and are **not** recursively acquired. I did **not** convert them: an `RLock` where none is needed hides design errors and costs performance, and the instruction was to fix only what evidence justifies.

---

## 10. Frontend Verification

* **Theme manager** — `static/js/modules/ui/theme-manager.js:313` calls `GET /api/settings/theme` on every page load via `templates/base.html:188`. Works for all roles after the SEC-03 correction.
* **Language switcher** — `static/js/modules/core/language-switcher.js:91` POSTs `/api/settings/system/language` with `X-CSRFToken` and 2 retries. Works for admin/analyst after the correction; viewer is denied, matching the matrix.
* **Search rendering** — the `highlighted_line` / `line_text` asymmetry documented in §5 is the SEC-04 sink; the fix is server-side, and the JS fallback `match.highlighted_line || escapeHtml(match.line_text)` remains correct.
* No frontend architecture, routing or state management was rebuilt or replaced. Changes are 20 and 6 lines in two page modules.

---

## 11. API Contract Verification

* **API-02** — `list_categories` called `categorys_repo.list_categories()`, which does not exist; both callers (`/api/categories/all-words`, `get_categorys_word_id()`) returned 500. The repository exposes `search_categories` and `get_categories_with_stats`, but **neither returns `word_id`**, which callers require — so the fix correctly reuses `list_all_join` and returns dicts. This is the right call: a fix that had reused an existing repo method would have silently dropped a field callers depend on.
* **API-03** — `json.dumps` cannot encode `Decimal` (psycopg2 returns `NUMERIC` as `Decimal`), so source export 500'd. Fixed with a `default=` handler covering `Decimal`, `date` and `datetime`.
* **OPS-01** — `/health` probes `settings.version` on the adapter; the adapter only forwarded `.settings`, so `/health` returned `{"status":"degraded","checks":{"settings":"error: AttributeError"}}` on **every boot**. That is precisely the signal a container orchestrator uses to restart or drain an instance. The adapter now resolves the version from the `version` module with a guarded fallback.
* **PERF-01** — in-content line matching loaded and scanned the entire file for **every** result (N+1). Response time grew linearly with `per_page` (measured 0.17 s at `per_page=5` vs 0.71 s at `per_page=50` on 59 files). Now bounded to `MAX_LINE_MATCHES_PER_FILE = 10`, which matches the UI, which renders three matches and then "+N more".

---

## 12. Regression Findings

| ID | Regression | Introduced by | Status |
|---|---|---|---|
| REG-01 | `GET /api/settings/theme` and `POST /api/settings/system/language` returned 403 for analyst and viewer, breaking theming and language switching on every page | SEC-03 settings fix (remediation under audit) | **Fixed** — narrow path allowlists; re-verified by 3-role matrix |

No other regression was found. All other remediations were checked against their callers and downstream consumers and are behaviour-preserving.

---

## 13. Newly Discovered Related Defects

All are **pre-existing** (present at baseline `e2766d7e`, proven by `git show`), and all were found by pattern search for the *same classes* as the reported defects rather than by re-testing the reported ones.

| ID | Severity | Defect | Status |
|---|---|---|---|
| CONC-02 | **Critical** | `_task_lock` plain `Lock` acquired recursively in 6 places → self-deadlock on first terminal task; permanently wedges all `/upload/*` endpoints and leaks a thread per request | Fixed |
| CONC-03 | **Critical** | ABBA lock-order inversion `_task_lock` ↔ `_pause_lock` between `cancel/pause/resume_task` and `wait_if_paused` | Fixed |
| ING-02 | **Critical** | `IntegratedFileReader(..., monitor_interval=2.0, ...)` — parameter does not exist; every task died with `TypeError` | Fixed |
| ING-03 | **Critical** | `reader.initialize()` — method does not exist; every task died with `AttributeError`. `__init__` already calls `_init_storage()` | Fixed |
| ING-04 | Medium | Single-file ingestion reported "Successfully processed **0** file(s)" despite the file being stored. `IntegratedFileReader` maintains `_processing_stats['completed'|'total']` only in the folder/batch paths (lines 950/1022/1043), never in `process_single_file` | Fixed |
| ING-05 | Low | `reader.shutdown()` — method does not exist; logged a spurious cleanup warning on every task | Fixed |
| OPS-02 | High | `POST /api/settings/database` persists credentials to `data/settings.json` **with no connectivity validation**. Observed during this audit: a test POST with a bogus host bricked the instance — every subsequent login returned 500 (`psycopg2.OperationalError: could not translate host name`), requiring manual repair of `settings.json`. Combined with the original SEC-03 defect (any viewer could reach it), this was a one-request denial of service | **Reported, not fixed** — adding validation is a design change beyond audit scope |
| DB-06 | Medium | Neither `delete_file` nor `bulk_delete` runs in a transaction. Six sequential autocommitted `DELETE`s mean an interruption leaves a partially deleted file (e.g. `words_paths` rows gone, `paths` row intact) | **Reported, not fixed** — would change database abstraction behaviour |

---

## 14. Architectural Duplication

The root cause of nearly every ingestion defect is that **two parallel ingestion implementations exist and have drifted apart**:

1. `Api/task_manager.py::_process_task` — the web/server-path ingestion path. It hand-constructs `IntegratedFileReader`, calls `initialize()` and `shutdown()` (neither exists), passes a parameter that was removed, and maintains its own progress bookkeeping against statistics the reader only populates for batch runs.
2. `services/ingesting/service.py` — builds kwargs via `_default_reader_factory` and uses the context-manager protocol (`with IntegratedFileReader(**kwargs)`). **This path is correct.**

I verified every `IntegratedFileReader` call site in the repository: `Api/routes/analysis.py:136`, `apps/cli/main.py:163,265`, `verify_readiness.py:326`, `reader_file/services/file_router_service.py:430`, `services/ingesting/service.py:406` and all four in `tests/e2e/test_full_workflow.py` **all use valid parameters**. `Api/task_manager.py` was the **sole** outlier — it is the only place using `monitor_interval`, `initialize()` or `shutdown()`.

**Recommendation (not applied):** retire the duplicate in `task_manager.py` and route web ingestion through `services/ingesting/service.py`. That is a refactor, not an audit fix, and is deliberately out of scope here.

---

## 15. Dead Code

Nothing was deleted during this audit, per the instruction not to remove code solely because it appears unused without tracing reachability.

Two observations worth recording:
* `IntegratedFileReader.get_storage_statistics()` exists and is called by `reader_file/services/file_router_service.py:430` and `apps/cli/main.py` — reachable, not dead.
* The `AUTH_ADMIN_READ_BLUEPRINTS` / `AUTH_ADMIN_READ_ENDPOINTS` configuration sets in `core/security/flask_ext.py` were inspected and are live inputs to `_enforce_role_policy`; the new `AUTH_SETTINGS_ANY_USER_*` sets follow the same pattern rather than adding a parallel mechanism.

---

## 16. Remaining Risks

1. **OPS-02 (High)** — unvalidated credential persistence on `POST /api/settings/database`. One malformed request takes the instance down and requires filesystem repair. Should validate connectivity before persisting, and ideally write atomically with a backup.
2. **DB-06 (Medium)** — non-transactional multi-statement deletes.
3. **DB-01 residual (Medium)** — `words_paths` has no unique index. The `WHERE NOT EXISTS` insert is correct but is a check-then-act race in principle; a unique index is the durable fix. Withheld per the safety gate.
4. **Architectural duplication (Medium)** — §14. The `task_manager` ingestion path has no test coverage and drifted into four separate breakages; it will drift again.
5. **`/set_language/<lang>` (Low)** — an app-level **GET** that mutates global state, for any authenticated user, with no CSRF token. It is outside the settings blueprint and predates this diff. It is the reason the language-API exemption is security-neutral, but it is itself an unsafe-by-method mutation.
6. **Development server (Informational)** — the app runs under the Werkzeug development server, which prints a warning that it is unsuitable for production.

---

## 17. Test Results

Runtime probes were used to **confirm** source-level conclusions, not to establish them.

| Probe | Result |
|---|---|
| Path security, roots unset (11 malicious paths) | 11/11 `403` — fail-closed |
| Path security, roots set (5 cases) | 2 legitimate `202` → completed; `/etc/passwd`, traversal, symlink-inside-root → `403` |
| 32 concurrent ingestion tasks (success + failure interleaved), 6 concurrent poller threads | All `202`; 66 poller iterations; **0** errors, **0** tracebacks, **0** hangs |
| Post-stress `/upload/active-tasks` | `0.004 s` (pre-fix: hung indefinitely) |
| In-process recursion test (`_update_task_error`, `pause`, `resume`, `cancel`) | All returned; no thread alive |
| 4 s ABBA race (`cancel_task` vs `wait_if_paused`) | No deadlock |
| 40 concurrent error-monitor requests | 0.75 s total, max 0.374 s |
| 12-way concurrent `words_paths` insert race | No duplicate; count remained 1 |
| 3-role authorization matrix | All 32 cells match §6 |

Note on test evidence: the repository's own pytest suite has a pre-existing failure unrelated to this diff, and several endpoints are rate-limited (flask-limiter, `10/min` on `auth.login`), which produces `429`/`401` under load. Those artefacts were distinguished from genuine failures and are not counted as defects here.

---

## 18. Git Diff Assessment

* **Scope:** 17 files, +548 / −159. Proportionate to 15 defect classes plus 6 corrections. No unrelated refactoring, no reformatting, no dependency changes.
* **Attribution:** the 6 newly discovered defects (CONC-02, CONC-03, ING-02/03/04/05) are all **pre-existing at baseline** — proven by `git show e2766d7e:Api/task_manager.py`. Only REG-01 was introduced by the remediation, and it is fixed.
* **Comment quality:** each change carries an `AUDIT (ID):` comment explaining the original defect, the failure mode, and the reasoning. This is genuinely useful for future maintenance and is unusual in a good way.
* **Database safety gate:** **PASSED** — no `DROP`/`TRUNCATE`/`ALTER`/`CREATE TABLE`/destructive `DELETE`/schema replacement anywhere in the diff.
* **Suggestion:** commit as ≥3 logical commits — (a) the 15 original fixes, (b) the REG-01 authorization correction, (c) the CONC-02/03 + ING-02..05 corrections — rather than one squash, so the distinct root causes remain reviewable.

---

## 19. Final Acceptance Decision

# CONDITIONALLY ACCEPTED

**Basis.** This decision rests on source-code evidence and execution-path tracing, not on tests passing, HTTP 200s, page renders, or the app starting.

**Why not ACCEPTED.** In its submitted form the remediation:
* contained a self-inflicted authorization regression (REG-01) that broke theming and language switching for every non-admin on every page;
* left server-path ingestion at a 0% success rate, having removed only the first of four consecutive blockers;
* left a pre-existing self-deadlock (CONC-02) that permanently disabled the entire upload subsystem after a single failed task, plus a lock-order inversion (CONC-03) of the same class.

**Why not NOT ACCEPTED.** Every one of those has now been traced to source, corrected with a minimal and targeted change, and re-verified — by direct in-process lock testing, by 32 concurrent tasks with zero errors, and by a 32-cell role matrix. The 14 correctly-remediated defects are sound, including the two security findings (SEC-03 privilege escalation, SEC-04 stored XSS) and the subtle database finding (DB-01), which I independently confirmed against the live schema rather than taking on trust.

**The single condition.** ACCEPTED becomes unconditional once **OPS-02** is addressed: `POST /api/settings/database` must validate connectivity before persisting credentials. This audit demonstrated that a single malformed request to that endpoint renders the application unbootable for all users, recoverable only by hand-editing `data/settings.json` on the server. It is reachable only by admins now that SEC-03 is fixed, but it remains a one-request, no-special-privilege denial of service with no in-app recovery path.

**Also required before production, though not blocking acceptance:** a unique index on `words_paths(path_id, word_id)` (DB-01 residual, §16.3), and transactional wrapping of the multi-statement deletes (DB-06, §16.2).

---

*No credentials, secrets or connection strings are reproduced in this report. Runtime values used during the audit (database connection parameters, test account passwords) were confined to the audit environment and are deliberately excluded.*
