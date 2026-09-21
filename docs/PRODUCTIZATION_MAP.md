# INFORAXIS productization — conformance map and build plan

This document is the bridge between the productization specification (sections
1–77) and the code that already exists in this repository. It answers three
questions for every part of the specification:

1. **What already exists**, and where — so the platform is *unified*, not
   rebuilt.
2. **What is missing**, expressed as a gap against a named file, table or
   engine rather than as an aspiration.
3. **How it will be verified**, in the same terms the repository already uses
   (a test, a rendered page, a recorded row).

Nothing here proposes a rewrite. The processing engine, readers, job system,
hashing, dedup, checkpointing, import validation, backup safety, security
controls, search engine, settings engine and monitoring stay as they are; the
work is to give them one shell, one registry and one vocabulary.

---

## 1. What the repository already provides

| Specification area | Existing foundation | Where |
| --- | --- | --- |
| Application shell | Jinja base layout with sidebar, top bar hooks, breadcrumbs, theme tokens | `templates/base.html`, `static/js/modules/ui/sidebar.js`, `static/js/modules/navigation/` |
| Navigation and visibility | Interface switches already gate every nav entry and, for mapped endpoints, the page itself | `settings/settings_adapter.py` (`INTERFACE_METADATA`, `is_interface_enabled_by_endpoint`), `Api/routes/common.py` |
| Settings engine | Full settings model with persistence, backups, validation, reset, import/export | `settings/settings_models.py`, `settings/settings_manager.py`, `settings/settings_adapter.py`, `settings/routes.py` |
| Authentication / authorization | Session + DB-backed sessions, roles `admin`/`analyst`/`viewer`, server-side blueprint and endpoint gates, audit log | `core/security/`, `database/migrations/m0003_auth_tables.py` (`audit_log`), `Api/routes/auth.py` |
| Error model | Sanitized client messages + correlation ids (`ERR-YYYYMMDD-NNNN`) | `core/errors.py`; settings now routed through it (commit `49797fc`) |
| Jobs / operations | Persistent job and job-event architecture with statistics and terminal states | `services/jobs/`, `database/migrations/m0006_job_infrastructure.py` |
| Ingest / processing | Readers, container handling, hashing, dedup, checkpointing, per-file status and errors | `pipeline/`, `services/ingesting/`, `readers/`, `Api/routes/operations_pages.py` |
| Search | Query engine, history, saved searches, enhanced and advanced pages | `Api/routes/search.py`, `Api/services/search_history.py`, `Api/utils/` |
| Analysis surfaces | Batch, path, classification, relations, timeline-ish archive views, charts | `Api/routes/analysis.py`, `Api/routes/analytics.py`, `Api/blueprints/files.py`, `Api/routes/archives.py` |
| File browser / detail | List, detail, content, full content, original file, lineage, relations, export | `Api/blueprints/files.py`, `Api/services/original_file.py`, `templates/` |
| Measurement discipline | `Measurement` type (measured / estimated / unavailable) | `core/measurements.py`, `Api/services/analysis_stats.py`, commit `cc54732` |
| Monitoring / diagnostics | Health, performance, error dashboard, concurrency dashboard | `Api/routes/{health,performance,error_dashboard,concurrency}.py`, `core/monitoring/` |
| Internationalisation | Four UI languages with RTL handling | `settings/languages.py` (en, ar, he, fa), `translations/` |
| Data model | Sources → sides → hashs → paths → contents/contents_raw, plus keywords, categories and analyst assignments | `database/migrations/m0001…m0010` |

Measured from the running application: **57 page endpoints** (GET, excluding
`/api` and static) served by **29 route modules**. The single-window list/detail/search/operations surfaces named in
the specification are therefore mostly *presentations of existing capability*
rather than new capability.

---

## 2. The cross-cutting gaps

Four gaps explain most of the distance between the current application and
the specified product. Each one is a piece of architecture, not a page.

### G1 — No single interface registry

Today the interface set is a metadata dictionary of 21 entries
(`INTERFACE_METADATA`, `settings/settings_adapter.py:35`) merged at read time
with per-interface `enabled` flags. The specification's requirement — one
registry driving navigation, permissions, settings, help, shortcuts and
visibility — needs a real model, and the current one has defects that the map
makes visible:

* `analytics` names an endpoint that does not exist in the URL map;
* `page_tips` has no page at all;
* `file_browser` and `file_library` both point at `files.files_list`;
* `file_analysis` displays as "INFORAXIS", which names the product, not the
  workspace;
* 40 of the 57 page endpoints have no registry entry — they name 19 endpoints
  in total — so most of the application is reachable but unmanaged: it cannot
  appear in navigation, permissions, help or shortcuts because there is
  nothing to reference;
* `reset_interfaces_to_defaults()` enables every interface, while
  `InterfaceVisibility.get_interface_enabled()` returns **False** for an
  unknown id: two defaults that disagree.

### G2 — The shell is assembled per page

Navigation is a hand-written list of `<li>` items in `templates/base.html`
with section labels ("General", …) that do not correspond to the task-oriented
domains (WORK / DISCOVER / ANALYZE / OPERATE / REPORT / ADMINISTRATION /
SETTINGS). Lists, tables, filters, empty states and error states are
re-implemented per template, so a component cannot be changed once.

### G3 — No automation layer and no command palette

The specification's automation rules and command palette have no counterpart
in the repository (`services/` has jobs and ingest, not rules; `static/js/`
has no palette module). These are the two genuinely new subsystems; both
should be thin layers over the job system and the registry rather than new
engines.

### G4 — Metric and error discipline (closed for the two named defects)

The specification calls out two concrete defects. Both were resolved before
this map was written, and both are now enforced by tests rather than by
review:

* **§8 — fabricated metrics.** `Api/routes/analysis.py` returned
  `avg_processing_time = 2.3` and `success_rate = 98.5` when it could not
  compute real values, and the template carried a three-run "History" panel
  that never happened. Every figure on the page is now a `Measurement`
  (`core/measurements.py`): measured from `paths` rows, estimated from jobs
  that actually finished and labelled "Estimated" with its derivation, or
  explicitly unavailable. Verified live: with an empty job history the page
  reads *"Insufficient data: no completed job has recorded timings"*; with one
  recorded job it reads *"Estimated 8 s — elapsed time ÷ files processed,
  across 1 completed job"*; the history panel lists the recorded job.
  (`cc54732`, `tests/unit/test_measurements.py`,
  `tests/unit/test_analysis_stats.py`)
* **§38 — settings error leak.** `settings/routes.py` returned `str(e)` from
  its generic handler on the surface that owns database configuration. All 27
  endpoints now answer through `core/errors.py` with a correlation id, a
  blueprint-level handler covers future endpoints, and
  `DatabaseConfigRejected` keeps its operator-facing 422 in one explicit
  branch. `sanitize_message` now removes a connection string whole. Verified
  by `tests/security/test_settings_error_hygiene.py` (16 tests), including a
  revert-check that fails on the old handler.

The rule that follows from §8 is general and applies to every later step: **a
figure is shown only with its basis, and where there is no basis it says so.**

---

## 3. The interface registry (build-order steps 1–2)

The registry becomes the single declaration of what the product offers. One
entry per interface, with the fields the specification lists:

```python
Interface(
    interface_id="batch_analysis",          # stable key (persisted flags use it)
    name="Batch Processing",                # what the operator sees
    description="Process many files...",
    category="ANALYZE",                     # the domain it belongs to
    route="analysis_batch",                 # endpoint, not a URL string
    icon="bi-lightning-charge",
    default_enabled=True,
    required_role="analyst",                # visibility only; enforcement stays in core/security
    dependencies=("file_library",),         # what must be enabled for this to work
    settings=("processing.max_workers",),   # settings this interface consumes
    feature_flag=None,
    help_topic="analysis/batch",
    keyboard_shortcut="g b",
)
```

Rules the registry introduces:

* **One source.** `settings/settings_adapter.py` consumes the registry instead
  of carrying metadata; the settings page, navigation, permissions, help,
  shortcuts and visibility all read the same objects.
* **Unknown means absent, not enabled.** `get_interface_enabled` keeps
  returning False for ids outside the registry, and the registry is the list
  that decides what exists — the two defaults stop disagreeing.
* **Dependencies are enforced and explained** (§46): enabling an interface
  whose dependency is off is refused with a message naming the dependency and
  offering to enable it, not silently allowed.
* **Permissions decide visibility, authorization decides access.** The
  registry's `required_role` hides navigation; `core/security` remains the
  enforcement point (§7, §57).
* **Every page is either registered or explicitly internal** (setup, health,
  error surfacing). The endpoint inventory from the running application is the
  checklist; a test asserts that each GET page endpoint is in one of the two
  sets, so a new page cannot be added invisibly.

---

## 4. Build order (§71) mapped to this repository

| # | Step | Existing foundation | Work added |
| --- | --- | --- | --- |
| 1 | Domain boundaries and the information model | `m0001…m0010` schema; Source → Side → Files | `docs/` model reference + registry of entities; no schema churn |
| 2 | Interface registry | `INTERFACE_METADATA`, `InterfaceVisibility` | registry module, adapter rewiring, endpoint-coverage test |
| 3 | Design system and components | `static/css/design-system.css`, `templates/components/` | tokens + shared macros for table, filter bar, empty/error/loading states |
| 4 | Application shell | `templates/base.html`, sidebar JS | domain-based navigation, top bar, status bar, breadcrumbs |
| 5 | Permission-aware navigation | `is_interface_enabled_by_endpoint`, roles | registry-driven rendering; server gates unchanged |
| 6 | Unified list / detail patterns | files list, archives, jobs, users pages | one table + filter + paging contract used by all of them |
| 7 | Unified search | `Api/routes/search.py`, saved searches, history | single search surface; advanced builder over the same service |
| 8 | Operations center | `operations_pages.py`, `services/jobs/`, `job_events` | ingest wizard (validate → preview → confirm → monitor) over existing pipeline |
| 9 | Analysis workspaces | `analysis.py`, `analytics.py`, `files.py` charts | shared workspace chrome; measurement-based figures throughout |
| 10 | Reporting | existing queries and charts | report definitions, saved reports, export |
| 11 | Administration center | users/roles, `audit_log`, error dashboard, health, performance, storage/backups | one administration surface over existing endpoints |
| 12 | Settings UX | `AllSettings`, `settings/routes.py` | reorganisation around the registry; no engine change |
| 13 | Interface manager | `/api/settings/interfaces` | dependency enforcement, help links, shortcut display |
| 14 | Automation layer | job system, job events | **new**: rule definitions evaluated against job events, executed through the job system |
| 15 | Diagnostics | monitoring, error dashboard, concurrency | consolidated view; correlation-id lookup |
| 16 | Accessibility | templates, CSS, JS | focus order, labels, keyboard paths, contrast |
| 17 | Security pass | auth, CSRF, rate limits, error pipeline | endpoint-by-endpoint authorization review (§57 matrix) |
| 18 | Performance | indexes (`m0002`), query cache, pagination | measured before/after, reported as measurements |
| 19 | Recovery | backups, job recovery, validation | recovery UI; visible degraded/read-only states |
| 20 | End-to-end verification | existing suites | acceptance run per §72 with evidence recorded |

Each step lands with tests and a rendered-page check, in the order above —
the shell depends on the registry, and every later surface depends on the
shell.

---

## 5. Verification contract

Every step is accepted on evidence, not on intent:

* **Functional** — the page or endpoint does what the section says, checked
  against the running application.
* **Integrated** — it uses the existing service/engine (jobs, settings,
  security, search); no parallel implementation (§70, §73).
* **Secure** — authorization checked server-side; no exception text, SQL,
  path or credential in any response; settings errors carry correlation ids.
* **Observable** — long operations report progress from the job system and
  every figure states its basis (measured / estimated / unavailable).
* **Recoverable** — failures surface with a correlation id and a next action;
  imports remain validate → preview → confirm.
* **Accessible and consistent** — shared components, shared states, keyboard
  reachable.
* **Measurable** — the numbers shown are reproducible from the database.

Current evidence for the two resolved defects:

```
tests/unit           1193 tests, 25 failures — all in the OCR suites that
                     require tesseract (pre-existing, environment)
tests/security       32 tests, 0 failures (16 of them new, for §38)
live page            /analysis/batch: 0 occurrences of 98.5 / 2.3s / "Batch #5"
live API             /api/settings/*, /api/settings/interfaces: 200 success
revert-checks        restoring the old handler fails the new tests; restoring
                     the old analysis route fails the source-pinning test
```

---

## 6. Immediate next actions

1. **Registry (step 1–2).** Introduce the registry module with the field set
   above; seed it from `INTERFACE_METADATA` plus the 41 unregistered page
   endpoints (19 named today, 40 unmanaged); fix the four defects listed under G1; rewire the settings
   adapter and the navigation to read it; add the coverage test.
2. **Shell (step 3–4).** Re-label and regroup the sidebar into the task
   domains, driven by the registry, and extract the table/filter/state macros
   so later surfaces reuse them.
3. **Automation and command palette (steps 14 and 4).** Both are new; both are
   thin layers over the job system and the registry, and they come after the
   shell because they read from it.
