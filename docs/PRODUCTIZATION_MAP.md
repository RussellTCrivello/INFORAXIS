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
| Navigation and visibility | **Registry-driven navigation** (commit for steps 1–2): one entry per interface supplies the sidebar, the switch, the role gate and the endpoint gate; the sidebar template renders from it | `core/interfaces/`, `templates/components/sidebar_nav.html`, `settings/settings_adapter.py`, `Api/routes/common.py` |
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

**Historical baseline** (measured from the running application before the
registry existed, and kept only to size the work — it is a snapshot, not a
maintained figure): 57 GET page endpoints excluding `/api` and static, of which
one page was unreadable while another was duplicated, served by 29 route
modules. The single-window list/detail/search/operations surfaces named in the
specification were therefore mostly *presentations of existing capability*
rather than new capability.

Live counts are no longer written down anywhere by hand. They are generated
from the application's URL map by `core/interfaces/inventory.py` and published
at `GET /api/interfaces/coverage` (how much of the application is accounted
for) and `GET /api/interfaces` (what the registry declares).

---

## 2. The cross-cutting gaps

Four gaps explain most of the distance between the current application and
the specified product. Each one is a piece of architecture, not a page.

### G1 — No single interface registry — **resolved** (steps 1–2)

The interface set was a metadata dictionary of 21 entries merged at read time
with per-interface `enabled` flags. It is now a declared model,
`core.interfaces.Interface`, in one registry that drives the sidebar, the
settings switches, the role gate and the endpoint gate. `INTERFACE_METADATA` is
**deleted** — the legacy names survive only as migration entries in
`LEGACY_INTERFACE_IDS`, so an operator's stored choice still reaches the
interface that replaced it.

The defects the old arrangement produced, and what now prevents each one:

| Defect (at the time) | Now |
| --- | --- |
| `analytics` named an endpoint that does not exist in the URL map | `analytics` is folded onto `comprehensive_dashboard`; `validate_registry` fails the build on any route the application does not serve |
| `page_tips` had no page at all | declared as a `Feature` in `FEATURES`, not an interface |
| `file_browser` and `file_library` both claimed `files.files_list` | merged; two interfaces on one endpoint now fails the suite unless one declares the endpoint as an alias |
| `file_analysis` displayed as "INFORAXIS" (the product name, not the workspace) | renamed `archives`, "File Management and Analysis" |
| Most page endpoints had no registry entry (19 named, the rest unmanaged) | every user-facing page endpoint has exactly one owner; the coverage test fails on an unowned page |
| `reset_interfaces_to_defaults()` enabled everything while the getter returned `False` for unknown ids | `Interface.default_enabled` is the only definition of the default; reset applies it |
| `is_interface_enabled_by_endpoint()` returned `True` for any endpoint missing from its map | unknown endpoint means not registered, and an unregistered page is refused rather than served |

The field set, the service API, the lifecycle states and the documentation
contract are recorded in **`docs/INTERFACE_REGISTRY.md`** (generated from the
registry); the information model behind it is in **`docs/DOMAIN_MODEL.md`**.


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

## 3. The interface registry (build-order steps 1–2) — **delivered**

The registry is now the single declaration of what the product offers. One
entry per interface:

```python
Interface(
    interface_id="batch_analysis",          # stable key (persisted flags use it)
    name="Batch Analysis",                # what the operator sees
    description="Process many files...",
    domain=Domain.ANALYZE,                  # exactly one domain, from a closed enum
    route="analysis_batch",                 # endpoint, not a URL string
    aliases=(),                             # other endpoints this interface owns
    icon="bi-lightning-charge",
    default_enabled=True,
    required_role=None,                     # visibility only; enforcement stays in core/security
    dependencies=("file_library",),         # what must be enabled for this to work
    settings=("processing.max_workers",),   # settings this interface consumes
    feature_flag=None,
    help_topic="analysis/batch",
    keyboard_shortcut="g b",
    kind=InterfaceKind.PAGE,                # PAGE | SECTION | INTERNAL | FEATURE
    status=InterfaceStatus.ACTIVE,          # ACTIVE | EXPERIMENTAL | DEPRECATED | RETIRED
)
```

The full model, the boundary it must not cross (it holds no business logic, no
authorisation logic, no setting values and no second router) and the generated
reference table are in **`docs/INTERFACE_REGISTRY.md`**.

Rules the registry introduces, each with the test that enforces it:

* **One source.** `settings/settings_adapter.py` consumes the registry instead
  of carrying metadata; the settings page, navigation, permissions, help,
  shortcuts and visibility all read the same objects
  (`tests/integration/test_interface_coverage.py`).
* **Unknown means absent, not enabled.** Ids outside the registry stay `False`,
  and the registry decides what exists — the two defaults no longer disagree
  (`test_an_unknown_interface_cannot_be_switched_on`).
* **Dependencies are enforced and explained** (§46): disabling an interface a
  live interface needs is refused with a message naming the dependents, and a
  stored state whose dependency is off is *reported* as inconsistent rather
  than silently rewritten (`test_a_dependency_cannot_be_disabled_while_needed`,
  `state_report()["missing_dependencies"]`).
* **Permissions decide visibility, authorization decides access.** The
  registry's `required_role` hides navigation and nothing else; `core/security`
  remains the enforcement point (§7, §57), verified by
  `tests/security/test_interface_visibility.py`, which asserts a viewer sees no
  administration entry *and* is refused the page directly.
* **Every page is registered, internal, or fails the build.** The endpoint
  inventory from the running application is the checklist
  (`core/interfaces/inventory.py`); a test asserts that every user-facing page
  endpoint has exactly one owner, so a new page cannot be added invisibly.
  The test suite's own scaffolding routes are classified `TEST_ENDPOINT` and
  excluded explicitly — an omission has to be a decision, not an oversight.
* **Renames keep their meaning.** A stored value for a renamed id is folded
  onto its successor; a *source file* naming a renamed id fails the suite,
  which is how the sidebar lost an entry the first time this rename happened.

---

## 4. Build order (§71) mapped to this repository

| # | Step | Existing foundation | Work added |
| --- | --- | --- | --- |
| 1 | Domain boundaries and the information model | `m0001…m0010` schema; Source → Side → Files | **done** — `docs/DOMAIN_MODEL.md` (information model + the twelve task domains declared in `core/interfaces/domains.py`); no schema churn |
| 2 | Interface registry | `INTERFACE_METADATA` (**deleted**), `InterfaceVisibility` | **done** — `core/interfaces/` (model, registry, validation, inventory, docgen), adapter rewired, `INTERFACE_METADATA` removed; coverage/duplicate/dependency/shortcut/migration tests; `docs/INTERFACE_REGISTRY.md` generated |
| 3 | Design system and components | `static/css/design-system.css`, `templates/components/` | tokens + shared macros for table, filter bar, empty/error/loading states |
| 4 | Application shell | `templates/base.html`, sidebar JS | **navigation delivered** — `templates/components/sidebar_nav.html` renders the registry by domain; top bar, status bar and breadcrumbs still to come |
| 5 | Permission-aware navigation | `endpoint_enabled`, `is_visible(user)` | **behind the same template** — the registry supplies visibility and the request gate; server gates unchanged |
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

Current evidence:

```
tests/unit           1193+ tests; the only failures are the 25 OCR tests that
                     require tesseract (pre-existing, environment)
tests/security       32 tests, 0 failures (16 for §38, 12 for interface
                     visibility)
tests/integration    27 interface-coverage tests, 0 failures (every user-facing
                     page owned; duplicate ownership, dependency cycles,
                     shortcut collisions and legacy migration all checked)
tests/e2e            50 tests, 0 failures
live page            /analysis/batch: 0 occurrences of 98.5 / 2.3s / "Batch #5"
live page            sidebar renders 9 domains / 23 entries from the registry
live API             /api/interfaces, /api/interfaces/coverage, /api/settings/*
                     : 200 success; counts generated, never typed
revert-checks        restoring the old settings handler fails the new tests;
                     restoring the old analysis route fails the source-pinning
                     test; naming a renamed interface id in a template fails the
                     navigation guardrail
```

---

## 6. Next actions

1. **Shared components (step 3).** Table, filter bar, search bar, pagination,
   empty / loading / error states, confirmation dialog, toast, record header,
   action toolbar and status badge — extracted from the templates that
   re-implement them today, with the state set of §63 declared per component.
   The design tokens already exist (`static/css/design-system.css`).
2. **Shell completion (step 4).** The sidebar now reads the registry; the top
   bar, status bar and breadcrumbs follow, over the same data.
3. **Remaining gaps.** G2 (per-page shell assembly), G3 (automation, command
   palette) and the rest of the build order are unchanged. The registry work
   deliberately stopped short of the command palette: the shortcut data is
   declared and validated now, the palette itself is not built (§1, §55).

Out-of-scope for the registry work, recorded so nobody reopens it: no visual
redesign, no new pages, no command palette, no automation layer. The navigation
markup keeps the same classes, icons and `data-endpoint` attributes it had, so
the stylesheet and the sidebar scripts continue to work unchanged.
