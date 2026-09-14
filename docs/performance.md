# Performance

## Architecture invariants

* **HTTP never does the heavy work.** Requests create jobs and return in
  milliseconds; worker threads run the engine (same as the old CLI did in
  its own process — no subprocess hop).
* Uploads are streamed to disk in chunks; werkzeug spools large parts to
  temporary files, so browser memory stays flat regardless of file size.
* Progress persistence is throttled (~1 s) and event writes are sampled for
  large jobs, keeping per-file DB overhead constant.

## Measured (benchmark_operations.py, disposable DB, 120 files)

| Metric | Baseline (direct service, what the CLI did) | Frontend job workflow |
|---|---|---|
| Total time | 26.83 s | 26.95 s |
| Throughput | 4.47 files/sec | 4.45 files/sec |
| Job create latency | — | 8.4 ms |
| Job startup latency | — | 59.8 ms |
| Slowdown | — | **+0.5 %** |

The ingestion rate is dominated by the engine's per-file database commit
cost, which is identical for both paths. Tolerance gate: 35 % (`--tolerance`).

Run it yourself:

```bash
python scripts/benchmark_operations.py --files 200
```

## Notes

* Worker concurrency is preserved (engine thread pool + storage semaphore
  bounded by the DB pool). Job-level parallelism is capped by
  `JOBS_MAX_CONCURRENT` to protect the database.
* Archive extraction and OCR throughput are engine characteristics,
  unchanged by the frontend integration (same code path).
