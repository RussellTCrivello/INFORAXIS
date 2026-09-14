# DatabaseHub operation call sites — individual investigation

Task 8/9: investigate each `db_hub.<x>_operations` call site individually and
determine delete / rewire / retain. No bulk change was made.

The question posed was whether these represent **silently swallowed core
functionality** rather than harmless dead code. That was the right question to
ask, because a previous turn of mine asserted there were "20 call sites, each
inside a broad `except`", which implied live functionality was failing
silently. **That assertion was wrong.** A raw `grep` counted occurrences inside
comments and inside a disabled string literal as if they were code. The
investigation below separates them.

## How each site was classified

A site is only reachable if it is (a) parsed as code, and (b) inside a method
that a live caller invokes. Both were checked mechanically with `ast`, not by
reading:

* string literals were mapped by `ast.Constant` nodes spanning multiple lines;
* enclosing functions by `ast.FunctionDef` line ranges;
* callers by searching the module for the method name and excluding any
  reference that falls inside a string literal or a comment.

## Results

### `path_operations` — 4 sites, all inert

| Line | Call | Classification |
|---|---|---|
| 1117 | `store_metadata(...)` | inside string literal |
| 1187 | `get_path_by_id(...)` | inside string literal |
| 1192 | `store_metadata(...)` | inside string literal |
| 1245 | `update_file_status(path_id, 'Read')` | inside string literal |

A single triple-quoted string spans **lines 999–1314** (20,095 characters). It
opens after a `return None` and a `logger.critical(...)` block whose own text
says:

```
# OLD CODE BELOW IS DISABLED - DO NOT UNCOMMENT
# The code below uses db_hub.path_operations, db_hub.word_operations, etc. which don't exist
# All storage should use ContentDBService.process_full_document() instead
```

So these are not executable and the file already documents that. **Retain as
is** — removing 300 lines of commented history is a separate, cosmetic decision.

### `word_operations` (7), `punctuation_operations` (2), `content_operations` (1)

All ten live-syntax sites are inside `_store_content_pipeline` (L2402+).

That method's **only** caller is line 1237:

```
L1237: success = self._store_content_pipeline(text, path_id)   -> STRING (inside 999-1314)
L2402: def _store_content_pipeline(...)                        -> LIVE definition
```

So the method is defined but unreachable. Every DB call in it would raise
`AttributeError`, and it never runs.

**Recommendation: delete `_store_content_pipeline`.** It is not silently
swallowing anything — it cannot execute. Deleting it removes the only remaining
live references to attributes that do not exist.

### `title_operations` — 0 sites

Removed in DEAD-01 (`a7511ee`).

### `hash_operations` — 0 sites

Only two comments (L1010, L2743), both noting that the live path uses
`self.db_service.hashs_repo` instead. Correct as is.

## What the live path actually persists (runtime evidence)

Ingesting one real text PDF through `IntegratedFileReader.process_folder`
against a real PostgreSQL database:

```
paths            = 1        words_paths      = 27
hashs            = 1        contents         = 1
words            = 28       titles_content   = 1
words_paths.word_count > 0        : 27 of 27
words_paths.position_indexer set  : 27 of 27
punctuation      = 0        keywords         = 0
```

Words, per-path word counts, positional indexes, content, titles, hashes and
paths are all written by `ContentDBService.process_full_document`. The dead
method duplicated work the live path already does.

## The one genuine gap this uncovered

`punctuation` and `keywords` are permanently empty. The code that would fill
`punctuation` is `ContentsDBService.create_content_from_symbols()` (L756–831),
which extracts words **and** punctuation marks and resolves punctuation IDs via
`punctuation_repo.resolve_punctuation_ids_batch`.

Searching the whole repository, that method has **zero callers**:

```
L756: def create_content_from_symbols(      <- definition only
```

So formatting/position metadata is designed, implemented, and never wired in.
This is a real capability gap — unlike the `_operations` sites, it is not
harmless. It is recorded here and left open because wiring it is a
content-model change, not a dead-code cleanup, and it belongs with the document
structure work (2C) rather than with this investigation.

## Summary

| Attribute | Live sites | Disposition |
|---|---|---|
| `path_operations` | 0 (4 in a string) | Retain; already documented as disabled |
| `word_operations` | 7, unreachable | Delete the enclosing method |
| `punctuation_operations` | 2, unreachable | Delete the enclosing method |
| `content_operations` | 1, unreachable | Delete the enclosing method |
| `title_operations` | 0 | Already deleted |
| `hash_operations` | 0 | Comments only; live path is correct |

None of the `_operations` sites represent swallowed core functionality. The one
genuine gap found is the never-called `create_content_from_symbols`.
