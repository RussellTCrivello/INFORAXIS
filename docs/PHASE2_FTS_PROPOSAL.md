# PHASE2 — FTS / Search-Index Audit and Proposal (ITEM-11.3, ITEM-11.4)

**Status: PROPOSAL ONLY. No schema, index, or production-data change has been made.
Explicit approval is required before anything in §6 is applied.**

Baseline at the time of writing: `79b55e0`. All measurements were taken on
**throwaway** `pgserver` databases under `tempfile.mkdtemp()`; the production
database was never opened by any measurement in this document.

---

## 1. What the audit found

### 1.1 The default search path documents a capability it does not implement

`Api/services/search_service.py`

| Line | Function | What the code actually does |
|---|---|---|
| L118 | `full_text_search` docstring | *"Perform full-text search using PostgreSQL tsvector/tsquery."* |
| L167, L176 | `full_text_search` body | `p.file_name ILIKE %s` and `w.word ILIKE %s` with **leading wildcards** (`%term%`, built at L163). No `tsvector` anywhere in the function. |
| L189–193 | `full_text_search` | builds a `tsquery_terms` string and then **never uses it** — the variable is assigned and discarded. |
| L561, L570 | `simple_search` | pure leading-wildcard `ILIKE`. |
| L727/733, L749/754, L777/782 | `advanced_search` phrase branch | pure leading-wildcard `ILIKE`. |
| L820–828, L847–856 | `advanced_search` main branch | `to_tsvector('english', w.word) @@ to_tsquery(...)` **`OR w.word ILIKE %s`**. |
| `Api/routes/api.py` L770, L779 | word search | `w.word ILIKE %s`. |

Dispatch (`Api/routes/search.py` L322): `use_advanced` defaults to `'true'`, so
**`advanced_search` is the default production path**, i.e. the `tsvector OR ILIKE`
shape.

The docstring is therefore false for `full_text_search`, and misleading for
`advanced_search`: the `tsvector` branch is present but neutralised by the `OR`
with a leading-wildcard `ILIKE` on the same column.

### 1.2 Why the index was removed, and whether that was justified

`database/migrations/m0004_remove_pg_trgm.py` dropped `idx_words_word_gin` and
the `pg_trgm` extension, stating:

> *"no runtime query path uses trigram similarity; the extension and its GIN
> index … provided no runtime benefit while adding an operational dependency
> that is unavailable on minimal PostgreSQL installs."*

Both halves of that need separating:

* **The portability half is correct and independently re-verified.** This
  environment's PostgreSQL ships only `plpgsql` and `vector`:
  `.venv/.../pgserver/pginstall/share/postgresql/extension/` contains 32 files,
  and `CREATE EXTENSION pg_trgm` fails with
  `FeatureNotSupported: extension "pg_trgm" is not available`.
  `find / -name "pg_trgm*"` returns nothing. **`pg_trgm` cannot be restored
  here**, so `idx_words_word_gin` cannot be recreated as it was.

* **The "no runtime benefit" half was wrong.** A `pg_trgm` GIN index does not
  only serve `similarity()`; it is the standard way to accelerate
  `LIKE`/`ILIKE '%pattern%'`. Leading-wildcard `ILIKE` is *exactly* what the
  application's content search issues (`search_service.py` L176, L570, L733,
  L754, L782, L828, L856; `api.py` L770, L779). So m0004 removed the one index
  class that could serve the hot path, on a rationale that overlooked what that
  index class does.

The consequence is measurable: `ILIKE '%…%'` on `words.word` is unindexable by
the surviving B-tree (`idx_words_word`, m0001 L29) and falls back to a sequential
scan of `words` on every search.

### 1.3 The defect is the query shape, not merely the missing index

This is the finding that changes the recommendation. Measured at
**2,000,000 words / 6,000,000 `words_paths` links**, running `advanced_search`'s
actual predicate shape:

| Query shape | Median | Plan |
|---|---|---|
| `tsvector @@ tsquery OR w.word ILIKE '%x%'` — **before** any new index | **1423.7 ms** | `Seq Scan on words`, GIN absent |
| same query — **after** adding a `to_tsvector` expression GIN | **1315.8 ms** | `Seq Scan on words`, **GIN not used** |
| same index, `OR ILIKE` branch **removed** | **3.6 ms** | `Index Scan`, GIN used |

The index alone bought **1.08×**. Removing the `OR … ILIKE` branch bought
**367×**. PostgreSQL cannot use a GIN index for a disjunction whose other arm is
an unindexable leading-wildcard match, so **no index addition can help while that
`OR` remains.**

---

## 2. Measurements

Corpus A: 200,000 words / 20,000 paths / 1,200,000 links.
Corpus B: 2,000,000 words / 100,000 paths / 8,000,000 links.
Corpus C: 2,000,000 words / 100,000 paths / 6,000,000 links.
Median of 3–5 runs, `EXPLAIN (ANALYZE, BUFFERS)`.

### 2.1 Corpus A

Rows 1 and 4 are from the same run; row 2 is from a separate run of the same
corpus, so the ILIKE baseline in that run was 67.34 ms. The run-to-run spread on
this query is ~1 ms, well inside the differences reported.

| Query | Median |
|---|---|
| `ILIKE '%financial14%'`, no trigram index (today) | 67.34 ms |
| inline `to_tsvector(w.word)`, unindexed (today's `advanced_search`) | 126.78 ms |
| `ILIKE` + pg_trgm GIN | *not measurable — extension unavailable* |
| `tsquery` + expression GIN | 52.84 ms (1.3×) |

The second row is worth its own line: today's default path computes
`to_tsvector()` per row with no index, and is **slower** than the plain `ILIKE`
it is OR-ed with (126.78 ms vs 67.34 ms). The `tsvector` arm currently costs
performance and buys nothing, because the `OR ILIKE` arm forces the same
sequential scan anyway.

### 2.2 Corpus B

| Query | Median | Plan |
|---|---|---|
| `ILIKE '%financial14%'` (common term) | 619.7 ms | Seq Scan on words |
| `ILIKE '%token1234567%'` (rare term, 4 matches) | 500.0 ms | Seq Scan on words |
| `tsquery 'financial14:*'` + expression GIN | 358.9 ms | Seq Scan (planner) |
| `tsquery 'token1234567'` + expression GIN | **3.6 ms (138×)** | Index Scan |

Note the pathology in row 2: a **rarer** term is no cheaper, because the cost is
scanning all 2,000,000 words to discover 4 matches.

### 2.3 Corpus C — the query actually shipped

See §1.3. Index-only change: **1.08×**. Index + query change: **367×**.

### 2.4 Candidates rejected by measurement

| Candidate | Measured | Cost | Verdict |
|---|---|---|---|
| `pg_trgm` GIN on `words(word)` | not measurable | — | **unavailable** in this build |
| `to_tsvector('english', word)` expression GIN | 138× exact, 1.7× prefix, **1.08×** as shipped | 138 MB at 2M words vs 95 MB heap | viable **only with** a query change |
| `words_paths (word_id) INCLUDE (path_id)` | 1.14× prefix, 1.07× exact | 129 MB | **rejected** — not worth the space |
| query restructure only (filter `words` once, join outward) | 1.2× at corpus A | none | marginal on its own |

---

## 3. Semantic compatibility — the blocking issue

`pg_trgm` is what preserves the current behaviour. Without it, **no index in
this PostgreSQL build can serve infix substring matching**. Measured divergence
on corpus A:

| Predicate | Words matched |
|---|---|
| `word ILIKE '%nancial1%'` (today's behaviour) | **15,873** |
| `to_tsvector('english', word) @@ to_tsquery('english','nancial1:*')` | **0** |

So a naive switch from `ILIKE '%x%'` to `tsquery 'x:*'` is a **silent recall
regression**: any search term that matches inside a word rather than at its start
would return nothing. This is the single most important compatibility
implication and is why this is a proposal rather than a change.

---

## 4. Root cause summary

1. The docstring/implementation mismatch (§1.1) hid the fact that the hot path
   is unindexable leading-wildcard `ILIKE`.
2. m0004 removed the only index class that could serve it, on a rationale that
   was right about portability and wrong about benefit (§1.2).
3. `advanced_search` ORs an indexable predicate with an unindexable one, so the
   indexable half is dead weight (§1.3).
4. `pg_trgm` — the natural fix for substring semantics — is not installable here.

Therefore: **an index-only change is not sufficient, and a query-only change is
not free.** Any real fix is the pair, and it must decide what to do about infix
search.

---

## 5. Options

### Option 1 — Index only (NOT recommended)
Add the §6.1 index, change nothing else. Measured benefit **1.08×**. Cost 138 MB
and ongoing write overhead. This is recorded so the "just add the index back"
reflex is explicitly rejected by measurement.

### Option 2 — Query change only, no schema change (lowest risk)
Split the predicate: use `tsvector`/`tsquery` for whole-word and prefix terms,
and retain `ILIKE '%…%'` **only** as a bounded secondary branch. No migration.
Benefit up to 367× on the indexed arm; infix recall preserved by the fallback.

### Option 3 — Additive migration + query change (recommended, needs approval)
§6.1 index **plus** the §6.2 query change, with the fallback of Option 2
retained. Highest measured benefit; the only change that makes the default path
indexed *and* keeps current recall.

**Recommendation: Option 3.** It is purely additive (new index, no column type
change, no data rewrite), reversible with one `DROP INDEX`, and it is the only
option whose measured benefit is more than noise.

---

## 6. Proposed change (Option 3) — for approval

### 6.1 Migration `m0008_words_tsvector_index.py`

Purely additive: one `CREATE INDEX CONCURRENTLY`. No `ALTER TABLE`, no column
change, no data rewrite, no `DROP` of any existing object, no touch to existing
rows.

```python
"""Add a built-in full-text GIN index on words.word.

Additive only. Creates no table, alters no column, rewrites no row, and drops
nothing. Uses PostgreSQL's built-in tsvector/tsquery because pg_trgm is not
available on the target PostgreSQL build (verified: only plpgsql and vector are
installed), so the trigram index removed by m0004 cannot be restored.

CONCURRENTLY so the index build does not hold an ACCESS EXCLUSIVE lock on
`words` and ingestion can continue. Note that CONCURRENTLY cannot run inside a
transaction block - see the runner note below.
"""

version = "0008"
name = "words_tsvector_index"

INDEX_NAME = "idx_words_word_tsv"
INDEX_DDL = (
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_words_word_tsv "
    "ON words USING gin (to_tsvector('english', word))"
)


def upgrade(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_indexes WHERE indexname = %s", (INDEX_NAME,)
        )
        if cur.fetchone():
            return
        # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
        conn.autocommit = True
        try:
            cur.execute(INDEX_DDL)
        finally:
            conn.autocommit = False
```

**Runner implication that must be decided before approval is acted on:**
`database/migration_runner.py` runs *one transaction per migration* and records
the result in `schema_migrations`. `CREATE INDEX CONCURRENTLY` cannot execute
inside a transaction block. Two acceptable resolutions, both needing a decision:

* **(a)** drop `CONCURRENTLY` and accept a brief `SHARE` lock on `words`
  (blocks writes, not reads). Measured build time at 2M words: **6 s**. Simple,
  transactional, fully compatible with the existing runner.
* **(b)** teach `migration_runner` about a `REQUIRES_AUTOCOMMIT = True`
  migration flag, and make such migrations explicitly non-transactional with a
  documented partial-failure recovery (`DROP INDEX CONCURRENTLY` then retry).

I recommend **(a)**: 6 s at 2M words is not worth a runner change, and it keeps
the one-transaction-per-migration guarantee that makes rollback simple.

Expected index size: **138 MB at 2M words** against a 95 MB `words` heap.

### 6.2 Affected queries

All in `Api/services/search_service.py` unless stated. The change is to stop
OR-ing an unindexable predicate with an indexable one.

| Site | Current | Proposed |
|---|---|---|
| L820–828 (`advanced_search`, single term) | `to_tsvector(...) @@ to_tsquery(%s) OR w.word ILIKE %s` | `to_tsvector(...) @@ to_tsquery(%s)`, with an `ILIKE` fallback arm executed **only if** the indexed arm returns fewer than `FTS_FALLBACK_MIN_RESULTS` rows |
| L847–856 (`advanced_search`, multi-term) | `to_tsvector(...) @@ to_tsquery(%s) OR w.word ILIKE ANY(ARRAY[%s])` | same two-phase treatment, per term |
| L167, L176 (`full_text_search`) | leading-wildcard `ILIKE` only, docstring claims tsvector | either adopt the same two-phase shape, or **correct the docstring** to describe what it does. The false docstring must not survive either way. |
| L561, L570 (`simple_search`) | leading-wildcard `ILIKE` | leave behaviour; it is the documented simple path |
| `Api/routes/api.py` L770, L779 | `w.word ILIKE %s` | leave; this is the category-management word picker, not content search |

Two-phase fallback keeps infix recall (§3) while making the common case indexed.
`FTS_FALLBACK_MIN_RESULTS` should be a module constant, default proposed `10`,
and must be measured (§8) rather than assumed.

### 6.3 Expected benefit (measured, not projected)

| Case | Today | Option 3 | Source |
|---|---|---|---|
| rare/exact term, 2M words | 500.0 ms | **3.6 ms** | §2.2 (138×) |
| shipped `advanced_search` shape, 2M words | 1423.7 ms | **~3.6 ms** on the indexed arm | §1.3 (367×) |
| common prefix term, 2M words | 619.7 ms | 358.9 ms | §2.2 (1.7×) |
| infix term | 500 ms | unchanged (fallback arm) | §3 |
| 200k words (small corpus) | 68 ms | ~53 ms | §2.1 (1.3×) |

Benefit grows with corpus size and is largest for selective terms. On a small
corpus it is marginal — which is the honest expectation, and the reason this
should be approved as a scaling fix rather than sold as a general speedup.

---

## 7. Compatibility and rollback

### Compatibility
* **Additive**: no table, column, constraint, or existing index is altered.
* **No data rewrite**: an expression index is built from existing values; no row
  is updated, so no `UPDATED`/`xmin` churn and no interaction with the dedup
  uniqueness constraint `(content_hash, source_id, side_id)`.
* **Write cost**: every `INSERT` into `words` must also update a 138 MB GIN
  index. This is the real ongoing cost and is measured in §8 before rollout.
* **Portability**: uses only built-in PostgreSQL text-search support (>= 9.6), so
  it does not reintroduce the dependency m0004 removed.
* **Replication/restore**: `pg_dump`/restore and the backup-restore path
  (`Api/services/import_service.py`) are unaffected — indexes are rebuilt, and
  `order_paths_by_lineage` restore ordering is untouched.
* **Search semantics**: unchanged *if* the §6.2 fallback is implemented. Changed
  (infix recall lost) if it is not. This is the approval-critical point.

### Rollback
Single statement, no data involved:

```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_words_word_tsv;
```

Implemented as a `downgrade(conn)` in the same migration file. The runner never
calls `downgrade()` automatically (existing behaviour, preserved), so rollback is
an explicit operator action. Reverting the §6.2 query change is an ordinary
revert of one commit; the index may be left in place harmlessly because nothing
reads it once the query change is reverted.

---

## 8. Verification plan (to be executed after approval)

1. **Pre-flight, throwaway DB only.** Build a 2M-word corpus, record
   `EXPLAIN (ANALYZE, BUFFERS)` for every query in §6.2 before the index.
2. **Migration idempotence.** Run m0008 twice; second run must be a no-op and
   `schema_migrations` must contain exactly one `0008` row.
3. **Plan assertion.** After the index, `EXPLAIN` each §6.2 query and assert
   `idx_words_word_tsv` appears in the plan for the indexed arm. A regression
   test asserting *plan shape*, not just latency, so the index cannot silently
   stop being used (this is precisely how §1.3 was missed).
4. **Semantic equivalence.** For a fixed query set covering whole-word, prefix,
   infix, numeric, mixed-case and multi-term queries, assert the result **set**
   is identical before and after. This is the test that catches §3.
5. **Write-cost measurement.** Time 100k `words` inserts with and without the
   index; report the delta. If the delta is material, report it rather than
   shipping it.
6. **Rollback drill.** `DROP INDEX CONCURRENTLY`, re-run steps 3–4, confirm the
   queries revert to their prior plans and identical results.
7. **Full regression suite** plus the existing
   `tests/integration/test_search_after_ingest.py`,
   `test_ocr_searchable.py`, `test_archive_nesting.py`,
   `test_email_lineage.py`, `test_universal_recursion.py` — all of which assert
   searchable content and therefore exercise the changed queries end to end.
8. **Deliberate falsification.** Drop the index and confirm the new plan-shape
   test fails; remove the fallback arm and confirm the semantic-equivalence test
   fails.

---

## 9. Explicitly NOT proposed

* Restoring `pg_trgm` / `idx_words_word_gin` — **impossible** in this build
  (verified, §1.2).
* A `words_paths (word_id) INCLUDE (path_id)` covering index — **rejected** at
  1.14×/1.07× for 129 MB (§2.4).
* Any `tsvector` **generated column** on `words` — unnecessary; an expression
  index serves the same queries without a column change, and a column change
  would be a far larger compatibility event for no measured gain.
* Any change to `contents.position_indexer` / symbol-pair storage. That is the
  separate ITEM-11.2 finding (see `tests/unit/test_storage_dead_paths.py::
  TestPunctuationGap`), not an FTS change.

---

## 10. Decision requested

1. Approve / reject **Option 3** (§6.1 additive index + §6.2 two-phase query
   change).
2. If approved, choose runner strategy **(a)** plain `CREATE INDEX` (6 s lock at
   2M words) or **(b)** an autocommit-capable migration flag.
3. Confirm that retaining the `ILIKE` fallback arm — and therefore preserving
   infix substring recall — is required. If infix search may be dropped, the
   change becomes simpler and faster, but §3's recall regression becomes real
   user-visible behaviour.

Nothing in §6 will be applied until all three are answered.
