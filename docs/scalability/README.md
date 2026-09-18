# Scalability verification — how to reproduce, what is measured, what is not

This directory contains the measurement harness for the ingestion pipeline's
scalability claims, plus the recorded evidence and its limits.

Run everything from the repository root, with the project's virtualenv active.

```bash
# 1. representative corpus (count, size mix, nesting, formats, large-file tail)
python tools/scalability/gen_corpus.py /tmp/corpus --files 25000 \
    --dirs-per-level 5 --depth 4 --avg-bytes 4096 \
    --formats text,json,csv,binary,zip --large-count 25 --large-bytes 4194304

# 2. end-to-end soak: real pipeline + resource sampling + DB cross-check
python tools/scalability/soak_ingest.py /tmp/corpus --out /tmp/out --workers 6 \
    --max-conn 25 --pool 8 --label local

# 3. crash/restart: kill a run, then resume against the same database
python tools/scalability/soak_ingest.py /tmp/corpus --out /tmp/out_a --label run \
    --pgdata /tmp/pgdata --checkpoint-file /tmp/cp.json --kill-after 30
python tools/scalability/soak_ingest.py /tmp/corpus --out /tmp/out_b --label run \
    --pgdata /tmp/pgdata --checkpoint-file /tmp/cp.json

# 4. throughput vs. dataset size (fresh database per size, like-for-like)
python tools/scalability/measure_throughput_scaling.py --sizes 1000,10000,25000

# 5. compute-mode equivalence: same corpus, one database per mode, compare
#    every stored object's evidence fingerprint (<workdir>/compute_mode_validation.json)
python tools/scalability/validate_compute_modes.py --workdir /tmp/modes --files 500
```

`soak_ingest.py` **refuses to run against a database that already holds rows**
(or a `--pgdata` directory with a live server): a previous run's rows would make
the new run report its files as "duplicates" of work it never did.  A deliberate
crash/resume run passes `--allow-existing-db`.  Each summary records the server
identity and the row count at t0 (`db.identity`), so evidence can be traced to
the database it came from.

`soak_ingest.py` writes `summary.json` (all scalar metrics), `samples.json`
(the raw 1 Hz resource time series) and `records.json` (every log record the
pipeline emitted, with level and logger) into the `--out` directory.

## What the harness measures

| Question | Where it comes from |
| --- | --- |
| Files discovered / processed / stored / failed / skipped / unsupported / pending | `summary.json → ledger` (the pipeline's `ProgressLedger`, the single source of truth) |
| Duplicate *processing* (same file stored twice) | `db.duplicate_path_rows` — `paths` grouped by `file_path` |
| Duplicate *content* (same hash stored twice) | `db.duplicate_hash_groups` — `hashs` grouped by `hash` |
| Referential integrity | `db.paths_without_hash_row`, `db.contents_without_path_row` |
| Throughput and its trend | `elapsed_s`, `files_per_second`, `ms_per_file`, `rate_*_fps` per decile |
| Memory, fds, threads, CPU, DB backends | sampled at 1 Hz: `rss_*`, `fd_*`, `threads_*`, `cpu_percent_*`, `db_clients_max` |
| Retries, error rate, failure classes | `log_counts` plus `records.json` (full log capture) |
| Database and index growth | `db.db_size_bytes`, `db.index_size_bytes`, per-table row counts |

## Measured results on this machine

Host: 2 logical cores, ~3.9 GB RAM, 21 GB disk, `ulimit -n 1024`, Python 3.11;
PostgreSQL 16 local; no OCR engine installed. Workers 6, DB pool 8, max
connections 25.

Throughput across sizes (`measure_throughput_scaling.py`, three independent runs,
fresh database each):

| corpus files | processed units (incl. nested) | elapsed | files/s | ms/file | RSS max | fds | DB size | index size | dup paths | pending |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 000 | 1 600 | 11.0 s | 90.6 | 11.04 | 71 MB | 8 | 29.5 MB | 11.1 MB | 0 | 0 |
| 10 000 | 16 000 | 107.6 s | 93.0 | 10.76 | 212 MB | 9 | 203 MB | 96.1 MB | 0 | 0 |
| 25 000 | 40 000 | 276.9 s | 90.3 | 11.08 | 351 MB | 9 | 490 MB | 238.8 MB | 0 | 0 |

Per-file cost is flat (10.8–11.1 ms) across a 25x increase in dataset size: no
progressive degradation in this range. Both databases contain exactly the
processed units (`paths_rows` 1 600 / 16 000 / 40 000) with **zero** duplicate
path rows and **zero** duplicate hash groups, and `pending = 0` at `percent = 100`.

Crash/restart (6 000-file corpus, hard `os._exit` mid-run, then resume against
the same database and checkpoint):

| run | outcome |
| --- | --- |
| A (killed at 30 s) | journal held 2 602 identifiers; `paths` rows left by the crash were committed by the pipeline's own transactions |
| B (resume) | 2 611 files skipped as already processed (journal + compaction), 5 948 discovered units completed, `pending = 0`, `percent = 100`, **0 duplicate path rows, 0 duplicate hash groups, 0 errors** |

100 000-file soak (mixed types, 5 levels deep, 20 x 4 MB files; 100 020 files /
436 MB on disk with 20 000 zip containers producing 60 000 nested members =
160 020 processed units; fresh database, workers 6, pool 8):

| metric | measured |
| --- | --- |
| processed units | 160 020 = 120 567 completed + 19 589 failed + 19 864 unsupported, `pending = 0`, `percent = 100` |
| elapsed / rate | 1 630 s / 61.3 units per second (98.1 units/s while the corpus was in cache) |
| RSS | start 310 MB, max 550 MB, end 390 MB over 160 020 units |
| fds / threads max | 13 / 19 (no fd growth) |
| database | 160 020 `paths`, 160 020 `hashs`, 100 587 `contents`, 3 324 056 `words`, 1.94 GB + 0.90 GB indexes |
| duplicates | **0** duplicate path rows, **0** duplicate hash groups |
| referential integrity | 0 paths without a hash row, 0 contents without a path row |
| storage failures / retries | 0 / 70 |

Both failure buckets are *correct classifications*, not lost work, and both are
instrumented rather than suppressed:

* 19 864 `unsupported` are files whose content the detector could not identify
  (`.bin`). They are hashed, sized, typed and recorded with the reason; nothing
  is guessed about their content.
* 19 589 `failed` were `JSONDecodeError: Extra data` — see the coverage fix
  below, which now reads those files.

### Coverage fix: JSON document sequences

`read_json_file` used `json.load`, which accepts exactly one document. A mixed
corpus containing JSON Lines / NDJSON / concatenated documents therefore failed
every such file: 19 589 of 20 000 `.json` files (19.6 % of a corpus) produced no
content and a `failed` row, despite the bytes being perfectly readable.

The reader now falls back to a streaming *document-sequence* reader: the file is
read once, every document is counted exactly, and retention is bounded
(`JSON_DOCUMENTS_MAX_RETAINED` = 10 000 documents / 8 MiB of source text) with an
explicit `truncated` flag. The fallback only accepts a file whose documents
parse completely and whose tail is whitespace — a valid first document followed
by arbitrary text still fails with the original error, so no partial read is
ever presented as content. Verified end-to-end through the router: 12 of 14
files stored (8/8 JSON Lines + 2/2 single documents + 2/2 arrays), the two
deliberately malformed files still failing with the original error, and a
200 000-document NDJSON file reporting `document_count = 200 000` with exactly
10 000 retained.

### Compute-mode validation: device selection changes performance only

`validate_compute_modes.py` runs the same corpus under `cpu`, `auto`, `gpu`,
`cpu+gpu` and `bypass` (gateway disabled), each against its own fresh database,
then compares the evidence fingerprint of every stored object: file hash, type,
status, extracted text and its length, the indexed word multiset digest, title
row counts and per-table row counts.

Result on this host: **identical** — 752/752 objects with `missing = 0`,
`extra = 0`, `differing = 0` for all four modes against the reference, with every
run reaching `pending = 0`. `mode = gpu` on a machine without a GPU therefore
produces exactly the reference evidence through graceful CPU fallback (the
fallback is recorded in the gateway's own stats).

Two fields are deliberately *not* compared, because they are keyed by
database-assigned word ids whose allocation order depends on concurrent inserts:
`contents.content_data` (compressed word-position index) and `titles_content.title_data`.
Comparing them reports a difference between any two runs, including two runs of
the same mode; the id-free word multiset digest and the raw extracted text are
the evidence contract that must hold, and both are compared.

Earlier, larger mixed-format run (40 325-file corpus, 250 MB, 25 x 4 MB files,
300 byte-identical duplicates, 4 levels deep): 58 865 processed units in 768 s
(52.5 files/s; the rate is dominated by 4 MB text files producing ~500 000 words
each), RSS max 931 MB, fds max 19, threads max 20, 0 storage failures, and
4 571 duplicates detected by content hash. That run predates the byte ceiling on
the retained-result window: with the ceiling in place the same workload retains
at most 64 MiB of results (measured 67.1 MB across 257 entries instead of a
count-bound 10 000 entries).

## Large-container remediation (PST / many-attachment report)

The recorded CLI session - a 2.1 GB PST with 19 566 attachments - exposed a
connected chain of defects. Each is fixed at its cause, with a regression test
in `tests/integration/test_large_container_accounting.py` and
`tests/integration/test_container_timeout_progress.py`.

### 1. Nested work was invisible to the report ("why doesn't it count nested files?")

The CLI printed `Total Files: 2` for a run that processed 19 566 attachments.
It used `len(results)`, and `results` is the *bounded* per-file result window
(deliberately capped so a million-file corpus cannot pin its extracted text in
memory) - it holds only what is still retained, and only the top-level files.

Every report now reads the ledger, which is the run's authoritative accounting:
`files_discovered`, `files_nested`, `containers_opened`, `files_completed`,
`files_failed`, `files_skipped`, `files_unsupported`, `files_retryable` and
`files_pending`. The run summary distinguishes top-level files from nested ones
and names the container count.

### 2. Work was written off while a container was still running ("why did it stop?")

`_reconcile_outstanding` ran at the end of the run and settled *every* unit with
no terminal state as `skipped`, with the log line

    19 013 discovered file(s) never reached a worker; recording as skipped

Those 19 013 files were the PST's remaining attachments - the nested reader was
still working through them. The run reported completion with 97 % of the
container's contents never processed, and because the terminal state was
`skipped`, nothing looked wrong.

Two changes at the cause:

* **Container work tracking** (`pipeline/progress_ledger.py`): a container's
  published units are tracked as outstanding until they settle. Nested readers
  are told which container they belong to (`container_path`, set by
  `FileRouterService`), and every settle decrements that container. A container
  with outstanding work is visible in the snapshot
  (`containers_in_flight`, `container_work_outstanding`). The map is bounded
  (4096 entries, least-recently-touched dropped), and a dropped entry reads as
  "not in flight" - what a stale container is.
* **The end-of-run sweep waits** for those containers before deciding anything
  (`_wait_for_live_containers`), bounded by *measured progress*: while any
  container's outstanding count is falling the run keeps waiting, and a
  container that stops moving for 120 s is escalated with an explicit warning
  rather than silently closed. Work that still never ran is recorded as
  **failed**, not skipped, and the run marks itself partial
  (`RUN INCOMPLETE: N discovered file(s) were not processed`). A user-requested
  cancel still skips the rest, which is what cancel means.

### 3. The timeout that killed the container

The old formula gave a 2.1 GB file 1 322 s (30 s/MB up to 1 GB, 3x base cap) -
less time than reading it takes - while recommending 125 555 s for the same
file, and at 5 TB it recommends years. It was replaced by a measured model
(`file_timeout_seconds`):

    budget = base_timeout + file_size / max(1 MiB/s, observed_rate / 4)

where `observed_rate` is this run's own throughput over completed files
(`_observed_bytes_per_second`, exact even when results are released). The budget
is capped by `processing.max_file_timeout_s` (default 24 h, configurable) so one
file cannot run forever, and a *live* worker whose container is still settling
children has its deadline extended on measured progress
(`_deadline_extended`) - which is what actually covers a 2 GB PST with 19 566
attachments. The operator-facing recommendation is derived from the same
measurement instead of a constant.

Measured on this host: 2.1 GB → 3 350 s (was 1 322 s), 5 TB → the 24 h ceiling
(was years), small files → the base timeout.

### 4. Resource protection was throttling healthy runs

The monitor treated **CPU > 85 %** as overload. A saturated, I/O-bound pipeline
is *supposed* to sit near 100 %, so the pool shrank from 8 workers to 2 within
seconds of starting, and the reader's overload check then pushed every extracted
sub-tree through "sequential processing to prevent freezing".

* `core/resource_coordinator.py`: memory pressure (85 %, emergency 92 %) is now
  the only throttle signal - it is the condition that actually kills workers.
  CPU saturation is reported, not throttled. The worker ceiling is derived from
  cores *and* memory (`_worker_ceiling`: cores − 2, doubled for I/O-bound work,
  capped by RAM/worker), with a per-instance ceiling of 16 instead of 4, so a
  large host can use the concurrency its settings ask for. Recovery is restored
  in steps rather than one worker per cycle.
* `reader_file/services/file_router_service.py`: resource pressure now reduces
  the *number* of workers for an extracted sub-tree (floor of 2); it never
  switches to one-at-a-time. Parallel pool sizing scales with the work
  (`len(files)//10 + 1`, capped at 8, clamped by the coordinator) instead of
  topping out at 4.
* `IntegratedFileReader.__exit__` waits for a running worker while it makes
  progress instead of abandoning it after 30 s - that abandonment released the
  database handle under a worker that was still storing a large file.

### 5. Degraded storage looked like success

The PST was reported as

    [STORAGE] ⚠️  'ssss.pst' stored with degraded data: raw_text step failed: ... NUL (0x00) ...

while its row said `processed`. Two fixes:

* **NUL** (PostgreSQL TEXT cannot hold U+0000): `ContentsRepository.store_raw_content`
  replaces NUL with U+FFFD at that single choke point - position preserving,
  deterministic, and counted (`last_sanitisation`). Everything else is stored
  byte-for-byte. The display text for binary-container content is no longer lost.
* **A partial store says so in the database**: `_note_optional_failure` sets
  `paths.processing_status` to **`partially_processed`** with `status_detail`
  naming the failing step, inside a savepoint so a rejected status write can
  never take the document down with it (an injected raw-text failure did exactly
  that before the savepoint existed). The row stays searchable - the evidence
  *is* stored - but it can no longer be mistaken for a clean success.

  Note on the vocabulary: `partially_processed` is an existing value of
  **m0007**'s `paths_processing_status_check` constraint. An earlier revision of
  this document described a migration **m0011** adding a `partial` status; that
  migration was never needed and was removed, because writing a status outside
  the constraint aborted the whole store transaction - the one failure mode this
  fix exists to prevent. Pinned by
  `tests/integration/test_partial_status_recorded.py`, which asserts the allowed
  vocabulary against the live schema.

### Regression coverage added

| file | pins |
| --- | --- |
| `tests/integration/test_large_container_accounting.py` | timeout model (large, measured-rate, cap, configurable, never below base); container work tracking; sweep waits; unprocessed → failed not skipped; NUL sanitisation incl. a real PostgreSQL round trip |
| `tests/integration/test_container_timeout_progress.py` | a 300-member container with a 2 s file budget: all 301 units complete, nothing skipped, `containers_in_flight = 0`, attribution exact, statistics sourced from the ledger |
| `tests/integration/test_partial_status_recorded.py` | m0007 status vocabulary; degraded store → `partially_processed` + named step + still searchable; clean store unaffected |
| `tests/unit/test_json_document_sequences.py` | JSON Lines / NDJSON / concatenated documents read; malformed files still fail; bounded retention |

## What these results do **not** establish

* **No 5 TB or multi-million-file run has been executed.** The largest measured
  corpus is 100 020 files / 436 MB (160 020 processed units) plus a 40 325-file
  mixed-format run. Any statement about 5 TB or millions of files
  is an *extrapolation* from the per-file costs above, not a measurement, and is
  labelled as such wherever it appears. Linear extrapolation of the flat
  per-file cost gives roughly 1 400 files/s-of-corpus for 5 TB only if the
  per-file size and type mix match this corpus — it certainly does not for the
  large-file tail, where cost is dominated by content volume.
* **Memory is bounded by design, not by measurement at scale.** The mechanisms
  that bound it are measured (streaming discovery: 0.59 MB peak for 10 084
  entries vs 11.17 MB for the list form; result window: 64 MiB byte ceiling;
  checkpoint: flat 0.04 ms per save regardless of the processed set), but the
  absolute RSS of a million-file run on this host has not been observed.
* **Accelerator paths are not verified**: this host has no GPU, NPU, FPGA or
  DPU, so only the CPU path is exercised; `mode = gpu` is verified only as
  *graceful CPU fallback*, not as GPU execution. The compute layer reports
  exactly that. Compare `docs/scalability/compute_mode_validation.json`.
* **Compute-mode equivalence is measured, not proved for all workloads**: the
  validator compared 752 objects from a 503-file mixed corpus under five modes.
  Larger mode-validation runs (≥ 100 000 files) have not been executed yet.
* **The absolute throughput is host-specific.** Six workers on two cores
  oversubscribe the machine; the numbers show *stability* across dataset sizes,
  which is what the degradation question asks, not a peak rate for production
  hardware.
* 42 tests fail in this environment, all in OCR-dependent paths that need an
  engine that is not installed (`docs/scalability/known_failures.txt`). The
  failing set is identical to the pre-existing baseline.
