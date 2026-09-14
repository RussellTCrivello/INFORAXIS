# Analyst-Driven Manual Categorization with Scoped Search Control

This document describes the **analyst categorization** feature: a manual,
human-driven categorization layer that lets an analyst tag files surfaced by
their own searches, and lets subsequent searches be scoped around what has or
has not already been categorized.

> **Hard architectural rule (FR-1.4 / NFR-1):** analyst categories and the
> system-generated ("smart") classification taxonomy are **two entirely
> separate systems**. They use separate tables, separate API namespaces,
> separate UI controls, and separate export fields. They are never merged,
> cross-referenced as equivalent, or displayed as a single unified category
> set. Nothing in this feature reads or writes the smart taxonomy, and
> nothing in the smart taxonomy reads or writes these tables.

## Data model (migration `0009_analyst_categorization`)

**Upgrading an existing installation:** the analyst tables are created by
migration `0009`. On an install that predates this feature, simply restart
the application after pulling the code — pending migrations are applied
automatically at startup (see [DATABASE.md](DATABASE.md#upgrades-existing-
installations)). No manual database step is needed.

| Table | Purpose |
|---|---|
| `analyst_categories` | Analyst-defined category labels (name unique, optional description/color, creator) |
| `analyst_file_categories` | Assignments of those labels to files (`path_id` × `category_id` unique). Stores who assigned, when, and the **originating search query** that surfaced the file |
| `analyst_categorization_log` | Audit trail: analyst identity, timestamp, action (`assign`/`remove`/`category_created`), category, source query, affected file ids (JSONB) |

Separation guarantees baked into the schema:

* No shared "category" table with a type flag — the analyst tables have no
  FK, join path or column in common with `categorys` / `words_categorys` /
  `keywords`.
* A file may hold a smart category **and** analyst categories at the same
  time; neither can overwrite the other (NFR-2).
* `idx_afc_path_id` serves the `EXISTS`/`NOT EXISTS` scope probes, so scoped
  searches perform like unscoped ones as the categorized set grows (NFR-4).

## Search scope control (FR-2.x)

Every search surface (basic `/search`, Advanced Search `/search/advanced`,
Enhanced Search `/search/enhanced`, and the `/api/search` API) accepts a
`scope` parameter:

| Value | Behavior |
|---|---|
| `uncategorized` *(default)* | Only files **without** any analyst category |
| `categorized` | Only files **with** an analyst category |
| `all` | Entire dataset, regardless of analyst categorization |

* The scope filters **exclusively** on analyst categorization status. Smart
  categorization status is never consulted (FR-2.4) — a smart-classified file
  is still "uncategorized" until an analyst categorizes it.
* The last-selected scope is remembered in the user's session (FR-2.3,
  session-only persistence).
* The Advanced Search interface exposes the selector as a first-class radio
  group (FR-3.2), plus a separate **Analyst Categories** filter control next
  to (never merged with) the **Smart Categories** filter.

## Workflow

1. **Search** — run a keyword/multi-keyword search (Advanced Search is the
   primary surface; the scope defaults to *Uncategorized Files Only*).
2. **Select** — check individual results, or use the select-all checkbox
   (FR-1.2).
3. **Categorize** — pick an existing analyst category or type a new one; it
   is created at the point of assignment (FR-1.3). The current search query
   is recorded with every assignment.
4. **Continue** — the next default search automatically skips the files you
   just categorized.

Every action (assign, remove, category creation) is audit-logged (FR-1.5).

## Analyst Categorization View (`/analyst/categorization`) — FR-4

A dedicated interface, visually distinct (violet banner/cards) from the
smart-classification pages. It supports:

* Filtering by analyst category, by analyst, by assignment date range, and
  by originating search query (traceability back to FR-1.5).
* Per-assignment removal (reversible, NFR-3) and category management.
* A live audit log panel and CSV export with dedicated
  `analyst_category` / `assigned_by` / `originating_search_query` columns.

## API

| Endpoint | Method | Notes |
|---|---|---|
| `/api/analyst/categories` | GET | Analyst-defined categories only (never smart categories) |
| `/api/analyst/categories` | POST | Create (analyst/admin) |
| `/api/analyst/categories/<id>` | PATCH/DELETE | Edit/delete (analyst/admin) |
| `/api/analyst/assign` | POST | `{path_ids, category_id \| category_name+create_category, source_query}` (analyst/admin) |
| `/api/analyst/remove` | POST | `{path_ids, category_ids?}` — omit `category_ids` to clear all (analyst/admin) |
| `/api/analyst/assignments` | GET | Filtered/paginated listing (category, analyst, dates, query, file text) |
| `/api/analyst/analysts` | GET | Distinct analysts with assignments |
| `/api/analyst/stats` | GET | Summary counters |
| `/api/analyst/log` | GET | Audit trail |
| `/api/analyst/export` | GET | CSV export honoring the view filters |

Search integration: `/api/search` accepts `scope` and `analyst_category_id`
(multi-value), echoes the applied scope in `filters.analyst_scope`, and
returns `analyst_categories` on each result as a field separate from any
smart-category data. Search-result CSV export emits `smart_categories` and
`analyst_categories` as adjacent, independent columns.

## Permissions (NFR-5)

The global role policy applies automatically:

* **Reads** (view page, listings, export): any authenticated user.
* **Writes** (assign, remove, category create/edit/delete): `analyst` or
  `admin` only, enforced server-side (403 otherwise).

## Out of scope (by specification)

* This feature does not modify, retrain or influence the smart classification
  engine.
* Analyst and smart categories are never merged into a unified taxonomy.
* The default *Uncategorized Files Only* scope refers only to analyst
  categorization status.

## Implementation map

* Migration: `database/migrations/m0009_analyst_categorization.py`
* Service: `Api/services/analyst_categories.py`
* Routes/API: `Api/routes/analyst_categories.py`
* Scope filter in search: `Api/services/search_service.py`,
  `Api/utils/utils.py` (`search_files_by_word`, `get_optimized_search_results`)
* Search routes: `Api/routes/search.py`
* UI: `templates/Analyst/analyst_categorization.html`,
  `templates/Search/search_advanced.html`, `templates/Search/search.html`,
  `templates/Search/search_enhanced.html`, `templates/file/file_detail.html`
* Page scripts/styles: `static/js/pages/analyst-categorization-page.js`,
  `static/js/pages/search-advanced-page.js`, `static/css/analyst-categorization.css`
* Tests: `tests/integration/test_analyst_categorization.py`
