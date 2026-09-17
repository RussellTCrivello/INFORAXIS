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
```

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

Earlier, larger mixed-format run (40 325-file corpus, 250 MB, 25 x 4 MB files,
300 byte-identical duplicates, 4 levels deep): 58 865 processed units in 768 s
(52.5 files/s; the rate is dominated by 4 MB text files producing ~500 000 words
each), RSS max 931 MB, fds max 19, threads max 20, 0 storage failures, and
4 571 duplicates detected by content hash. That run predates the byte ceiling on
the retained-result window: with the ceiling in place the same workload retains
at most 64 MiB of results (measured 67.1 MB across 257 entries instead of a
count-bound 10 000 entries).

## What these results do **not** establish

* **No 5 TB or multi-million-file run has been executed.** The largest measured
  corpus is 40 325 files / 321 MB. Any statement about 5 TB or millions of files
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
  DPU, so only the CPU path is exercised. The compute layer reports exactly
  that.
* **The absolute throughput is host-specific.** Six workers on two cores
  oversubscribe the machine; the numbers show *stability* across dataset sizes,
  which is what the degradation question asks, not a peak rate for production
  hardware.
* 42 tests fail in this environment, all in OCR-dependent paths that need an
  engine that is not installed (`docs/scalability/known_failures.txt`). The
  failing set is identical to the pre-existing baseline.
