# Whole-repository review, September 2026

Scope: every change between the first commit (`109cf7c`) and the tip of
`arena/01a0af97-inforaxis`, with emphasis on the updates after the merge to
`main` (`485d6ee`), where the content-based-identification, forensic-extraction,
exact-accounting, compute-control and scalability work landed.

This document records **what was found, why it happened, what changed, and how
each change was verified**. It deliberately separates *verified* results from
*unverified* conditions (section 7) so nothing here reads as a stronger claim
than the evidence supports.

---

## 1. How the review was performed

| Method | What it covered |
| --- | --- |
| History review | `git log -S`/`git log -p` per symbol across `109cf7c → 97bb14b`, comparing the historical implementation of each area against the current one |
| Cross-snapshot diffs | `git diff 485d6ee..HEAD` per module (90 files, +24 011/−2 031 lines), each hunk read for behaviour change, not just for syntax |
| Static analysis | `pyflakes` on every module the updates touched (baseline vs tip sets compared, so only *new* findings were triaged); AST scans for duplicate definitions and for `logger` shadowing; a dependency audit that parses every third-party import in the tree against `requirements.txt` |
| Executable evidence | unit + integration suites per area, run against a real PostgreSQL (pgserver) and a real database bootstrap; `verify_readiness.py` run end-to-end on a fresh install; deliberate mutation of fixed code to prove each new regression test fails without the fix |
| Contract checking | the documented behaviour in `docs/` and in the tests was treated as the specification; where code and tests disagreed, the disagreement itself was recorded as a finding |

---

## 2. What the history showed

| Commit | Claim | What the review found |
| --- | --- | --- |
| `109cf7c`, `7cc3421` | initial project | Several contracts documented only in tests (image size floor, `too_small` skip reason) were never implemented in any commit's source. See R-2. |
| `f1e0357`, `485d6ee` | "Fix parallel ingestion: thread-safe transactions, honest accounting" | The accounting model was still keyed on the top-level tree; nested container work was invisible. |
| `688a779` | "Scalability hardening + gateway compute-control layer" | Streaming discovery, journal checkpointing, cached source/side resolution and the compute-control layer; its only router change was honest duplicate reporting. The CPU-as-overload rule it is often blamed for predates it (R-5). |
| `d94eb76`, `95d945a` | scalability harness + evidence | Evidence files and their limits are recorded, but the measured runs target 100 K–1 M objects, not the 5 TB / multi-million case. |
| `9cad168` | "Content-based format identification, forensic extraction, exact accounting and explicit compute control" | Introduced the identity record; it was also folded into the *content* channel (R-1), referenced an undeclared `oletools` dependency (C-1), and added dead imports/code (D-1). On the credit side it replaced the original CPU-as-overload throttle and the sequential sub-tree fallback with a memory-based policy (R-5). |
| `3b66299` | "Fix StoragePipeline class truncation" | Followed a `return` that had made the rest of the class dead. A 319-line disabled block and a duplicated fail-safe stayed in the storage pipeline until this review removed them (D-8), and the CLI crash paths it touched were still broken (R-3). |
| `c7fde4b` | "Stop re-recognising every image, serialise word inserts, fix Windows test DB probing" | Correct fixes; the word-ordering change is sound (`sorted(set(values))` makes lock acquisition monotone). |
| `fe23947` | "Open spreadsheets by content, quiet nested sub-runs" | Two conflicting openpyxl rules appeared (D-3) and the workbook was given a stream it did not own (R-4). |
| `6e1af06` | user-selectable compute mode | Policy is now implemented and tested; the CLI paths that *refused* a mode crashed (R-3). |
| `f73c3a8 … 97bb14b` | corrective work (this review's fixes) | Each item in section 3, with the guards in section 6. |

---

## 3. Regressions and failures found

Severity is about user-visible consequence, not code size. "Detected by" says
what would have caught it earlier, i.e. why the existing safeguards did not.

### R-1 (critical) A file that yielded no content was stored as `Read`

* **Symptom**: a 20×20 icon the image reader deliberately skipped was stored
  with `file_status='Read'` and ~200 characters of "content" that were nothing
  but identity labels ("Original name: icon.png", …). The Unread contract in
  `tests/integration/test_status_persisted.py` failed, search results were
  polluted with ~10 boilerplate labels per artefact, and the labels were shown
  to the examiner as file content.
* **Root cause**: the identity record (added by `9cad168`) was appended to the
  artifact's flattened content text by `_detection_search_text`, and
  `file_status`/`content_words` are derived from that text. Metadata *about* a
  file was therefore counted as evidence that the file could be read.
* **Introduced by**: `9cad168`. **Fixed by**: `f73c3a8`, hardened in
  `test_content_vs_identity.py` (content channel holds only extracted content;
  identity lives in `paths.extraction_provenance -> 'detection'`, queryable).
* **Why the safeguards missed it**: unit tests exercised the readers and the
  storage pipeline separately; only the end-to-end status test mixed them, and
  it was already failing for a second reason (R-2), which masked this one.
* **Verification**: `tests/integration/test_status_persisted.py` 11/11;
  `tests/unit/test_content_vs_identity.py` green; a diagnostic run showed the
  skipped icon's reader result carries `extracted: False`, no text, and is
  stored `Unread / skipped / too_small` (the probe was removed afterwards).

### R-2 (critical) Images below the documented size floor were OCR'd

* **Symptom**: `skip_reason == "too_small"` was asserted by four suites and
  never produced: tiny images were pushed through OCR, failed, and were
  recorded as `partially_processed` instead of `skipped`.
* **Root cause**: the contract existed only in tests. `git grep` at `109cf7c`,
  `7cc3421`, `f1e0357` and `485d6ee` finds `too_small`/`min_ocr_dimension` in
  no source file - the reader never implemented it, so the tests had been
  failing (or skipped) for the entire history in this repository.
* **Fixed by**: `f73c3a8` (`MIN_OCR_DIMENSION = 50` with an explicit
  `extraction_info` skip record).
* **Verification**: `test_oversmall_image_is_skipped_not_failed` and the
  Unread-state contract in `test_status_persisted.py` pass; the skip is
  reported, not silent (`skip_reason`, `reason`, `min_ocr_dimension`).

### R-3 (high) Every legacy `.ppt` / `.pot` / `.pps` read raised `UnboundLocalError`

* **Symptom**: legacy presentations failed with an error mentioning `logger`,
  not PowerPoint.
* **Root cause**: `read_ppt_file` began with `if logger is None: logger =
  logging.getLogger(__name__)`. Binding a name anywhere in a function makes it
  local for the whole body, so the `if` raised before any work happened.
* **Introduced by**: present in the initial commit `7cc3421` - it never worked.
  **Fixed by**: `8f82a87`. **Guarded by**: `tests/unit/test_ppt_legacy_read.py`
  (behavioural) and `tests/unit/test_logger_shadowing.py` (repo-wide AST scan
  for use-before-bind, with self-tests; the whole repository is clean under it).
* **Mutation check**: restoring the two lines in a scratch copy makes 6 tests
  fail, including three parametrised `.ppt`/`.pot`/`.pps` cases.

### R-4 (high) Spreadsheets opened by content raised `seek of closed file`

* **Symptom**: `.xlsx`/`.xlsm` handed to the reader as a stream failed to load.
* **Root cause**: `fe23947` opened the file with `with open(...)`, handed the
  handle to openpyxl and let the `with` block close it, while openpyxl reads
  the stream lazily.
* **Fixed by**: `8f82a87` - one rule in `core/file_utils.load_spreadsheet_workbook`,
  the workbook keeps the stream alive (`_inforaxis_source_stream`, wrapped
  `close()`), and the handle is closed on load failure.
* **Verification**: `tests/unit/test_spreadsheet_by_content.py` 6/6 (2 failed
  before the fix), plus the preview path closes its workbook
  (`Api/services/file_preview.py`).

### R-5 (high) A healthy, saturated run was throttled as "overloaded"

* **Symptom**: on a 2-core host the worker pool was cut from 8 to 2 within
  seconds of starting and stayed there; a 19 566-attachment PST then ran
  strictly serially.
* **Root cause**: the monitor treated `CPU > 85 %` as overload, and the worker
  budget was `min(max_workers, 4)`. An I/O-bound pipeline saturating its cores
  is the *intended* state; each monitoring cycle removed a worker (8 → 2 on a
  2-core host within seconds), the cap made a configured 8/16-worker host run
  at 4, and each reader sub-tree fell back to sequential processing under the
  "overload" flag.
* **Introduced by**: the original implementation (`7cc3421`) - the CPU rule,
  the cap and the sequential fallback are all in the first commit.
  **Fixed by**: `9cad168` (memory is the only throttle signal, ceiling from
  cores *and* memory, degraded workers instead of sequential sub-trees).
  **Completed here**: the monitor restored workers against a single-instance
  ceiling even with a second instance live, and the policy had no tests.
* **Also fixed here**: `is_system_overloaded()`'s docstring still advertised
  the removed CPU rule. Policy now lives in `_evaluate_pressure()`;
  `tests/unit/test_resource_coordinator_policy.py` (15 tests) pins it,
  including "CPU saturation alone changes nothing", "no hard cap of 4",
  "restore bounded by the live instance count" and "capacity never reaches
  zero".

### R-6 (high) Crash-path regressions in the CLI and the deadline watchdog

* **Symptom**: `cli_main()` raised `NameError` on every invocation (the
  compute-policy block read `output_json` one line before assigning it) and the
  folder summary raised `NameError` on an undefined `stats`; the per-file
  deadline watchdog silently did nothing.
* **Root cause**: refactors removed or renamed the values the reporting code
  read; `_file_window` computed a constant 300 s and the resulting `TypeError`
  was swallowed by a bare `except`, so timeouts were never applied.
* **Fixed by**: `f2a266b`, plus this review's removal of the last two
  unconsumed `results =` assignments in `apps/cli/main.py` (dead, not a crash).
* **Verification**: `tests/integration/test_cli_compute_refusal.py` and
  `tests/integration/test_cli_parity.py` green; `pyflakes` clean on the file.

### R-7 (medium) Symlinks and special files disappeared from the accounting

* **Symptom**: discovery dropped anything that was neither a regular file nor a
  directory, so those inputs were neither processed nor counted.
* **Root cause**: the discovery walk returned only FILE/DIR records.
* **Fixed by**: `81dbb10` - SYMLINK records are produced and reported through
  `inventory['not_ingested']`, with the deliberate `(not followed)` decision
  documented; `tests/unit/test_discovery_contract.py` 11/11.

### R-8 (medium) Shared connection pool leaked when `Database` failed to initialise

* **Fixed by**: `93fca77` (release-on-failure), `tests/unit/test_connection_pool_sharing.py` 11/11.

### R-9 (medium) A fresh install reported NOT READY

* **Symptom**: `verify_readiness.py` failed its login check on a correct new
  deployment.
* **Root cause**: the check asserted HTTP 200 for `/auth/login`, but before an
  administrator exists the app redirects to `/setup` (302 → 200).
* **Fixed by**: `5095934`; the check now follows the first-run redirect and
  reports the state as evidence. Guarded by
  `tests/integration/test_readiness_login_check.py` (2 tests).
* **Verification**: full run against a real PostgreSQL + fresh `APP_DATA_DIR`:
  `Total: 29 checks, 0 failed (0 critical)` / `READINESS: READY`.

---

## 4. Obsolete, duplicated and conflicting code removed

| Item | Where | Why it was dead / duplicated |
| --- | --- | --- |
| D-1 dead imports/bindings (the real dead weight among 55 new pyflakes findings) | `pipeline/integrated_reader.py`, `read_archive/email/pdf/remaining.py`, `thread_manager.py`, `settings/config.py`, `verify_readiness.py`, `database.py`, `file_reader_service.py`, `path_utils.py`, `contents_repo.py`, `read_img_fast.py`, `apps/cli/main.py` | Triage of the 55 findings the updates introduced; optional-library availability probes were kept and labelled (`# noqa: F401` + comment), not deleted |
| D-2 duplicate identifier resolver | `services/ingesting/service.py` | A docstring-only `_resolve_identifier` was silently overwritten by the real INJ-04 implementation; its stale docstring contradicted the live precedence rules |
| D-3 two openpyxl-by-content rules | `core/file_utils.py` + `reader_file/readers/read_office.py` | Two implementations of one rule; consolidated in `8f82a87` |
| D-4 dead chunk-size estimate | `database/database/repository/contents_repo.py` | `chunk_end` was superseded by the `best_chunk_end` binary search and never read |
| D-5 shadowed `global _LIBS_CACHE` | `reader_file/readers/read_img_fast.py` | Declared for a name the function only reads |
| D-6 duplicate `os` import | `core/path_utils.py` | The module-level import was shadowed everywhere by the function-local one that is actually used |
| D-7 unconsumed return values | `apps/cli/main.py` | Both folder entry points print their own summary; the aggregated `results` was never read |
| D-8 disabled legacy storage block + duplicate fail-safe | `pipeline/storage_pipeline.py` | A 319-line triple-quoted copy of the old `_store_file_sync` (with `_store_content_pipeline`) sat unreachable next to the live implementation; removed in `81dbb10`, with `tests/unit/test_storage_dead_paths.py` asserting no such literal and the new fail-safe contract |

Also reviewed and left alone (deliberate, documented behaviour):
`verify_readiness.py`'s repeated `def _():` names (the decorator registry
key is the check name), `OUTCOME_UNSUPPORTED` in `progress_ledger.py` (still
returned by `classify_result`), and the local `logger = logging.getLogger(...)`
assignments inside `except` blocks elsewhere (redundant, but they bind before
use, and the new AST guard proves it).

---

## 5. Dependencies, configuration and consistency corrections

* **C-1 `oletools` was never declared** although `core/forensics/vba.py` needs
  it for MS-OVBA macro source (code added in `9cad168`, requirement added in
  `f2a266b`). The dependency audit now reports no undeclared third-party
  import: `extract-msg`, `rarfile`, `py7zr`, `striprtf`, `flask-*`, `sentry-sdk`
  and the rest are all present.
* **C-2 terminal states were not reported everywhere.** `locked` and
  `cancelled` were added to the ledger but never reached the job statistics,
  the live ingest payload, the web task detail or the CLI summary, so objects
  in those states looked unaccounted for. All four now report them, together
  with the bounded-attribution overflow and the in-flight container work, so
  `map + overflow` stays exact wherever attribution is shown.
* **C-3 bounded attribution counter**: folding a container's entry into the
  overflow bucket did not decrement the "containers with nested work" counter.
* **C-5 `locked` had no stored representation.** The ledger counts a held file
  as `locked` (retryable, not a defect), but the column vocabulary from
  migration 0007 has no such value, so the stored row said `failed` with prose
  the operator had to interpret. A locked read now carries a `locked:` prefix
  in `status_detail`, produced from the *same* marker list `classify_result`
  uses, and `tests/unit/test_status_resolver.py` asserts the row and the
  accounting can never disagree. `docs/operations.md` now documents both
  vocabularies, the triage queries, the identity/`extraction_provenance`
  location (metadata, deliberately not content) and the accounting invariant.
* **C-4 compute-mode policy** (`6e1af06`): precedence CLI flag → `COMPUTE_MODE`
  env → `processing.compute_mode` → default, refusal with the exact remedy for
  a GPU-only run on a CPU-only host, no silent substitution; guarded by
  `tests/unit/test_compute_mode_policy.py` and
  `tests/integration/test_cli_compute_refusal.py`.

---

## 6. Guards added so these classes cannot return

| Guard | Locks out |
| --- | --- |
| `tests/unit/test_logger_shadowing.py` (3 tests) | use-before-bind `logger` shadowing, repo-wide, with self-tests proving the scan can fail and does not over-report |
| `tests/unit/test_ppt_legacy_read.py` (5 tests) | `.ppt`/`.pot`/`.pps` regression, "missing file still reports File not found", router hand-off |
| `tests/unit/test_resource_coordinator_policy.py` (15 tests) | worker-ceiling policy: no hard cap of 4, memory bound, per-instance split, stale-instance filter, CPU saturation ≠ overload, memory pressure reduction, never zero, restore ≤ live-instance ceiling, monitor loop not re-implementing thresholds |
| `tests/unit/test_content_vs_identity.py` | identity metadata reaching the content channel |
| `tests/unit/test_storage_dead_paths.py` (24 tests) | dead-code and fail-safe contracts in the storage pipeline (no >5 000-char literal, no `db_hub.path_operations` sites, loud fall-through fail-safe) |
| `tests/unit/test_spreadsheet_by_content.py` (6 tests) | spreadsheet-by-content loading and the stream it owns |
| `tests/unit/test_connection_pool_sharing.py` (11 tests) | pool registry and release-on-failure |
| `tests/unit/test_discovery_contract.py` (11 tests) | symlinks and not-ingested accounting |
| `tests/integration/test_readiness_login_check.py` | first-run readiness semantics |
| `tests/integration/test_status_persisted.py` (11 tests) | `Read`/`Unread` + `processing_status` end-to-end |

---

## 7. Validation status: verified vs unverified

**Verified in this environment (real PostgreSQL, real files, real bootstrap)**

* `verify_readiness.py`: 29 checks, 0 failed, `READINESS: READY` on a fresh
  `APP_DATA_DIR`; without PostgreSQL it correctly reports 8 critical
  `connection refused` failures (environmental, not a defect).
* Status contract: `tests/integration/test_status_persisted.py` 11/11.
* Accounting/progress: `test_progress_ledger.py`, `test_progress_pipeline_chain.py`,
  `test_nested_progress_accounting.py`, `test_large_container_accounting.py`,
  `test_container_timeout_progress.py`, `test_partial_status_recorded.py` all green.
* Readers/routing/identity: `test_reader_routing.py`, `test_format_detection.py`,
  `test_provenance_builder.py`, `test_content_vs_identity.py`,
  `test_archive_safety.py`, `test_forensic_extraction.py` (5/5 macro tests with
  `oletools` installed) green.
* CLI: `test_cli_compute_refusal.py`, `test_cli_parity.py` green.
* Resource policy: 15/15 green; mutation of the fixed shapes fails the new guards.
* `compileall` over all packages: clean.

**Not verified here (state so explicitly)**

* OCR-dependent suites (`test_ocr_engines.py`, `test_ocr_matrix.py`,
  `test_pdf_text_layer.py`, `test_embedded_images.py`) fail in the sandbox
  because no Tesseract binary is installed; `cv2` cannot import there
  (`libGL.so.1`). These are environment limits, and they fail identically on
  the `main` baseline snapshot - no claim is made about OCR quality here.
* No GPU is present, so GPU/accelerator paths are **implemented and unit-tested
  for policy, not verified on hardware**. `GPU-ONLY` refuses rather than
  substituting CPU (`C-4`).
* Scale: the recorded evidence covers 100 K–1 M-object runs
  (`docs/scalability/`). The 5 TB / multi-million-file condition is
  **extrapolated**, not measured; the bounded structures that make it plausible
  (journal checkpoints, bounded attribution maps, streaming discovery) are
  covered by tests but not by a 5 TB run.
* Windows-specific behaviour (paths, sharing violations, UnRAR/bsdtar absence)
  is covered by unit tests but not executed here.

---

## 7b. Residual static-analysis debt (deliberately not mass-edited)

`pyflakes` over the whole tree (excluding `tests/`) still reports 274
findings - 23 f-strings without placeholders, unused typing/stdlib imports and
unused local variables - concentrated in code this review did not otherwise
change:

| Area | Findings |
| --- | --- |
| `Api/routes` | 69 |
| `Hdg_Err_Ex_Log` | 28 |
| `Api/blueprints`, `Api/utils`, `Api/services` | 64 |
| `reader_file/readers` | 20 |
| `apps/importing/utils`, `settings`, `concurrency`, `database`, `apps/web`, rest | 93 |

The findings the *updates* introduced were all triaged and cleared in
`5941cfe` (this review's dead-code pass), so nothing here is a defect that
recent work added. The legacy remainder is left alone on purpose: mass-editing
unused imports and f-strings across 20+ legacy modules is churn that would
touch far more code than it improves, and every edit carries a chance of
changing behaviour in code with no test coverage. It is recorded here as known
debt, with its exact size, rather than silently fixed or silently ignored:

```bash
python -m pyflakes $(git ls-files '*.py' | grep -v '^tests/')
```

Two of those findings are *not* debt and must stay:

* optional-library availability probes (`import fitz`, `CheckpointManager`,
  `rarfile`, `py7zr`, `striprtf`, `openpyxl`, …) where the `ImportError` is the
  check - each is now labelled with a comment saying so;
* `Hdg_Err_Ex_Log` re-export imports used by callers of those modules.

---

## 8. Reproducing the checks

```bash
# one-time: a virtualenv with requirements minus the libpff build
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# the guards this review added
.venv/bin/python -m pytest tests/unit/test_logger_shadowing.py \
    tests/unit/test_ppt_legacy_read.py \
    tests/unit/test_resource_coordinator_policy.py -q

# the contracts that were failing before the fixes
.venv/bin/python -m pytest tests/integration/test_status_persisted.py \
    tests/unit/test_storage_dead_paths.py tests/unit/test_content_vs_identity.py \
    tests/unit/test_spreadsheet_by_content.py -q

# end-to-end readiness on a fresh install (needs a reachable PostgreSQL)
DB_HOST=... DB_PORT=... DB_USER=... DB_PASSWORD=... DB_NAME=... \
    APP_DATA_DIR=$(mktemp -d) python verify_readiness.py
```

Static cross-checks used during the review (no extra dependencies beyond
`pyflakes`): `python -m pyflakes <modules>`, plus the AST scans that are now
permanent tests in `tests/unit/test_logger_shadowing.py`.
