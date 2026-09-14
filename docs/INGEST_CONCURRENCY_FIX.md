# Parallel ingestion: transaction & concurrency integrity fix

Incident: during parallel document storage a subset of each batch failed with
`relation "tmp_words" does not exist`, `no COPY in progress`, `current
transaction is aborted`, `Hash ID N does not exist (transaction may have been
rolled back)` and foreign-key violations (`fk_contents_raw_path`,
`words_paths_word_id_fkey`, `contents_path_id_fkey`, …), ending in
`❌ STORAGE FAILED: '<file>' was NOT stored in database` while the rest of the
batch succeeded.

This document records the root causes, the design of the fix and the evidence
that the behaviour is now correct.

## 1. Root cause A — a transaction was bound by mutating a shared object

`StoragePipeline` holds **one** `ContentDBService`, and
`IntegratedFileReader._process_with_threads` starts one managed thread per file,
so several documents are stored through the same service instance at once.
`ContentDBService.transaction()` implemented its transaction by replacing the
service's repositories with connection-bound clones
(`setattr(self, repo_name, repo.transactional_clone)`) and restoring them on
exit. With two threads inside `process_full_document`:

* thread B's clones overwrote thread A's;
* thread A's next statement therefore ran on **thread B's connection**;
* `tmp_words` is a per-*session* temporary table with a fixed name, so it was
  created on one connection and read on another (`relation "tmp_words" does not
  exist`), and two threads drove `COPY` on one session (`no COPY in progress`,
  `server sent data ("D" message) without prior row description ("T" message)`);
* the damaged transaction was aborted, and `Hash ID`/FK errors followed.

Reproduction (before the fix): 4 threads × 6 documents through one
`ContentDBService` printed the production error chain and **never terminated**
(a deadlock between the attribute swapping and the pooled connections).

## 2. Root cause B — silent rollbacks and swallowed errors

* `BaseRepository.get_cursor()` detected an aborted transaction and issued a
  `conn.rollback()` itself. Inside a transaction that silently discarded the
  hash/path rows the caller had already created, while the caller kept using
  their ids → `Hash ID N does not exist` and
  `violates foreign key constraint` on the next write.
* `ContentsRepository.store_symbol_pairs()` caught every insert error and
  `print`-ed it, returning `[]` as if the content had been stored.
  `KeywordsRepository.insert_keywords()`, `SourcesRepository.insert_info_sources()`
  and `ContentDBService.process_keywords_for_path()` did the same.
* The document pipeline contained 1,700 lines of `except` blocks that inspected
  exception *text* for `'transaction is aborted'` and often just logged.

## 3. The fix

### 3.1 Thread/task-local transaction binding (`TransactionScope`)

`database/database/repository/transaction_scope.py` holds the transaction
connection in a `contextvars.ContextVar`. Repositories resolve their connection
per call:

```python
@property
def _connection(self):
    if self._explicit_connection is not None:      # legacy standalone binding
        return self._explicit_connection
    if self._scope is not None:
        return self._scope.current                 # this thread's transaction
    return None                                    # pooled, auto-commit path
```

* `ContentDBService._init_repositories()` creates one scope and passes it to all
  repositories; nothing on the shared service is mutated any more.
* `transaction()` binds a pooled connection to **the calling thread/task**,
  commits once, rolls back once, and releases the connection.
* A nested `transaction()` becomes a `SAVEPOINT`, so a nested failure cannot
  discard the surrounding unit of work.

### 3.2 Cursor/error contract

* `get_cursor()` never commits and never rolls back inside a transaction; a
  statement that aborts the transaction raises `TransactionAbortedError`
  (subclass of `QueryError`), and every later statement reports the abort
  immediately instead of running on a rolled-back connection.
* Errors are no longer swallowed: `store_symbol_pairs`, `insert_keywords`,
  `insert_info_sources`, `process_keywords_for_path` propagate.
* `process_full_document` is a linear, readable flow (duplicate check → hash →
  path → content → optional steps → word index → title). Optional work
  (display text, keyword index, title) runs inside
  `with self.savepoint():`, so a failure is contained, logged, and reported in
  `result['warnings']`.

### 3.3 Words no longer go through a temporary table

`CREATE TEMP TABLE tmp_words` + `COPY` + `INSERT … SELECT FROM tmp_words` is
replaced by paged `INSERT INTO words (word) VALUES %s ON CONFLICT (word) DO
NOTHING` (`WordsRepository.bulk_upsert_words`). It needs no session state, is
atomic and is safe to run concurrently. The oversized-token guard
(`core/word_limits.MAX_WORD_BYTES`) is unchanged.

### 3.4 Deduplication returns the right identifiers

`HashsRepository.check_duplicate()` returns a **path** id but callers used it as
a hash id (`get_path_id_by_hash_id(<path id>)`), producing an unrelated or
missing document on re-ingest. New `get_duplicate_document()` returns
`(hash_id, path_id)` from one row, and `get_hash_id_by_value()` serves the
"hash exists but no path yet" case.

### 3.5 Accounting and reporting

* Jobs report storage counters: the manager merges the engine's closing
  statistics into the persisted job stats, so `/api/jobs/<id>` now exposes
  `duplicates`, `files_stored` and byte totals (the Jobs page previously showed
  `duplicates: null`).
* A store attempt that resolved to an existing document is recorded as
  *duplicate* (`StoragePipeline.get_store_outcome`) and accounted as skipped
  instead of succeeded — a re-run reports "0 new files, N duplicates" rather
  than "N succeeded".
* `ContentsRepository` and `WordsPathsRepository` log warnings instead of
  printing; `Hdg_Err_Ex_Log.is_retryable_error` no longer classifies the removed
  `tmp_words`/COPY symptoms as retryable.

### 3.6 Performance defects fixed while tracing the failure

* `select_content_ids_by_words()` loaded the **entire** words table into a dict
  on every document (O(all words) per file); it now resolves only the document's
  own words (`WHERE word = ANY(%s)`), batched. `select_words_by_ids()` is the
  counterpart for id inputs and fixes `get_keywords_as_words()` (which passed ids
  to a words-based lookup and always returned empty).
* `load_text_content()`/`_load_word_join_content()` no longer load the whole
  words table to render one file.
* `ResourceCoordinator.should_yield()`/`get_yield_duration()` called
  `psutil.cpu_percent(interval=0.1)`, which **sleeps in the calling thread**;
  the ingest loops hit it every 1000 items, so a single 50,000-word document
  spent ~10 s in `time.sleep` *inside the storage transaction*. Sampling is now
  non-blocking (`interval=None`) and cached for 500 ms:
  **50k-word document ingest 10.5 s → 0.62 s (17×), identical on the untouched
  baseline for comparison.**
* `bulk_insert_words_paths()` sends bounded batches (5,000 rows) instead of one
  statement with tens of thousands of parameters.
* Keyword matching indexes positions by the pattern's first id instead of
  rescanning the document once per keyword.

## 4. Verification

| Evidence | Result |
| --- | --- |
| `tests/integration/test_concurrent_document_ingest.py` (new) | green: 6 concurrent documents per thread through one shared service, all stored with content/raw text/word index/title; failed documents leave no rows; a failed optional step keeps the document; re-ingest reports the existing document; aborted transactions are reported, not silently rolled back |
| Same file on the untouched baseline | fails with `no COPY in progress` / `current transaction is aborted` / `Hash ID 1 does not exist` — the production signature |
| `tests/integration/test_oversized_word_ingest.py` | green (unchanged behaviour) |
| `tests/unit/test_keyword_matching.py` (new) | green, fuzzed against the naive reference implementation |
| 4 threads × 6 documents, shared service | before: error chain + hang (>300 s). after: `OK=24 FAILED=0`, all 24 documents with index/content/raw/title, 0.17 s |
| Full suite (unit + integration + security + e2e), branch vs baseline | 0 regressions; 5 previously failing tests now pass (`test_frontend_workflow` dedup job, `test_dedup_second_run_safe`, `test_job_runs_to_completion_with_events`, `test_pause_and_resume`, `test_crash_recovery_then_retry_no_duplicate_work`) |

The remaining suite failures are identical on the untouched baseline: they need
an OCR engine (Tesseract binary / ONNX model) that is not installed in the test
sandbox.

## 5. Operational notes

* No schema change and no migration: the fix is entirely in the application
  layer and stays compatible with existing databases (migrations stay at 0010).
* `BaseRepository.create_temp_copy_to_words()` is kept as a thin compatibility
  shim for external callers; it inserts the CSV payload directly into `words`.
* Pool sizing guidance is unchanged; a transaction still owns exactly one
  connection for its whole duration.
