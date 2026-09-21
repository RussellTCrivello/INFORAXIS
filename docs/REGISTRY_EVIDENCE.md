# Registry evidence

This is the evidence required before the design-system and shell work begins:
the registry has to be demonstrably complete before anything is built on top of
it. The directive lists what must be shown —

```
Registry inventory
Endpoint coverage result
Interface count
Unmanaged endpoint count = 0
Internal endpoint exception count
Alias count
Dependency validation result
Registry test result
Legacy settings migration result
Rendered navigation result
```

— and every figure below is generated, because a hand-written figure is how the
productization map came to describe the same application as having 57, 40 and
41 endpoints in three different places.

**Sources.** Sections 1–6 come from the registry itself
(`python3 -m core.interfaces.evidence`); sections 7–10 come from the
application's own URL map (`build_inventory(app)`), so they are re-derived in
the integration suite rather than copied. The registry reference with one row
per interface is `docs/INTERFACE_REGISTRY.md`; the information model behind the
domains is `docs/DOMAIN_MODEL.md`.

---

## Part A — the declared product

<!-- BEGIN GENERATED REGISTRY EVIDENCE -->
### 1. Registry inventory

- Interfaces declared: **25**
- Cross-cutting features (not interfaces): **1**
- Endpoints owned (canonical routes + aliases): **63**
- With a keyboard shortcut: **11**
- With a help topic: **23**
- Declared domains in use: **10**

| Domain | Interfaces |
| --- | --- |
| WORK | 1 |
| DISCOVER | 9 |
| INGEST | 2 |
| ANALYZE | 3 |
| CLASSIFY | 2 |
| REPORT | 2 |
| OPERATE | 2 |
| ADMINISTRATION | 1 |
| SETTINGS | 2 |
| INTERNAL | 1 |

### 2. Aliases

Declared aliases: **39**, across **11** interfaces. An alias is an endpoint the interface owns but does not navigate to; aliases never become navigation entries.

| Interface | Aliases |
| --- | --- |
| `categories` | `category_add`, `category_words` |
| `concurrency_monitor` | `concurrency.get_async_tasks`, `concurrency.get_metrics`, `concurrency.get_pools`, `concurrency.get_processes`, `concurrency.get_threads` |
| `file_library` | `files.bulk_delete_files`, `files.delete_file`, `files.file_chart_data`, `files.file_content_lazy`, `files.file_content_page`, `files.file_detail`, `files.file_full_content`, `files.file_search_all_pages` |
| `input_ingestion` | `files.api_cancel_task`, `files.get_active_tasks`, `files.pause_task`, `files.resume_task`, `files.upload_page`, `files.upload_progress` |
| `jobs` | `operations_job_detail_page` |
| `keywords` | `keyword_detail`, `keywords_add` |
| `search` | `saved_searches_page`, `search_advanced`, `search_advanced_api`, `search_enhanced_page` |
| `settings` | `settings_api.settings_page` |
| `sides` | `side_add`, `side_categories_keywords`, `side_detail`, `side_edit` |
| `sources` | `source_add`, `source_categories_keywords`, `source_detail`, `source_edit` |
| `words` | `word_detail`, `words_add` |

### 3. Dependency validation

- Validation result: **no issues**
- Interfaces declaring a dependency: **8**
- Interfaces other interfaces depend on: **3**

| Interface | Requires | Required by |
| --- | --- | --- |
| `file_library` | — | `analyst_categorization`, `archives`, `batch_analysis`, `charts_dashboard`, `classification`, `comprehensive_dashboard`, `path_analysis` |
| `words` | — | `classification` |
| `analyst_categorization` | `file_library` | — |
| `archives` | `file_library` | — |
| `path_analysis` | `file_library` | — |
| `batch_analysis` | `file_library` | — |
| `classification` | `file_library`, `words` | — |
| `comprehensive_dashboard` | `file_library` | — |
| `charts_dashboard` | `file_library` | — |
| `settings` | — | `interface_manager` |
| `interface_manager` | `settings` | — |

### 4. Registry integrity

`validate_registry()` reports no issues: identifiers unique, domains from the closed set, roles known, routes declared consistently, no dependency is unknown or circular, and no two interfaces share a keyboard shortcut.

### 5. Lifecycle and migration

- Interfaces by status: **ACTIVE 24, DEPRECATED 1**
- Interfaces by kind: **INTERNAL 1, PAGE 23, SECTION 1**

Renames and merges the registry understands (a stored value under an old key reaches the interface that replaced it; the code may not name the old key):

| Legacy key | Reaches |
| --- | --- |
| `advanced_search` | `search` |
| `analytics` | `comprehensive_dashboard` |
| `file_analysis` | `archives` |
| `file_browser` | `file_library` |
| `file_upload` (retired: no interface of its own) | `input_ingestion` |
| `upload_files` | `input_ingestion` |

### 6. Feature declarations

| Feature | Default | Description |
| --- | --- | --- |
| `page_tips` | on | Explanatory tips at the top of each page, describing the elements on it, how to use them and how to add data. |
<!-- END GENERATED REGISTRY EVIDENCE -->

---

## Part B — the application it describes

<!-- BEGIN GENERATED APPLICATION EVIDENCE -->
### 7. Endpoint coverage

- Endpoints in the application's URL map (static excluded): **299**
- User-facing page endpoints: **49**
- Owned by an interface: **63**
- **Unmanaged user-facing endpoints**: **0**
- Interfaces with a navigable route: **24**

Unmanaged user-facing endpoints: **0** — every page the application serves is owned by exactly one interface.

### 8. Endpoint classification

| Classification | Endpoints |
| --- | --- |
| ACTION | 7 |
| API_ENDPOINT | 225 |
| INTERNAL_PAGE | 1 |
| REDIRECT | 1 |
| SYSTEM_ENDPOINT | 16 |
| TEST_ENDPOINT | 1 |
| USER_INTERFACE | 48 |

By blueprint:

| Blueprint | Endpoints |
| --- | --- |
| (app) | 133 |
| analytics | 22 |
| archives_api | 10 |
| auth | 12 |
| concurrency | 6 |
| content_analysis | 6 |
| cursor_api | 3 |
| error_dashboard | 4 |
| files | 20 |
| health | 1 |
| import_export | 6 |
| operations_api | 29 |
| paths | 3 |
| performance | 7 |
| preview | 1 |
| settings_api | 27 |
| setup | 5 |
| translations | 4 |

### 9. Declared exceptions

The coverage rule tolerates exactly these, by name — a new page cannot be added to an exception list by accident, because each list is declared in `core/interfaces/inventory.py` and reproduced here.

**SYSTEM_ENDPOINTS** (17): `auth.change_password`, `auth.first_admin_create`, `auth.first_admin_page`, `auth.login`, `auth.login_page`, `auth.logout`, `auth.me`, `favicon`, `get_csrf_token`, `health.health`, `set_language`, `setup.check_setup_status`, `setup.run_installation`, `setup.setup_page`, `setup.system_check`, `setup.test_database`, `static`

**INTERNAL_PAGE_ENDPOINTS** (1): `concurrency.dashboard`

**REDIRECT_ENDPOINTS** (1): `files.upload_page`

**TEST_ENDPOINT_PREFIXES** (1): `/_test/`

Endpoints the interface switch does not gate (API, system and infrastructure; authentication and authorization are unchanged): **242**

### 10. Rendered navigation

`GET /` as an administrator returned 200; the sidebar renders **9 domains** and **23 entries**, all of them from the registry:

- Work
- Discover
- Classify
- Ingest
- Analyze
- Report
- Operate
- Administration
- Settings

Entries, in render order: `index`, `files.files_list`, `search_page`, `sources_list`, `sides_list`, `keywords_list`, `words_list`, `categories_list`, `email_words`, `notifications_page`, `analyst_categorization_page`, `file_classification_page`, `operations_input_page`, `operations_import_page`, `archives_page`, `path_analysis_page`, `analysis_batch`, `comprehensive_dashboard`, `charts_dashboard`, `operations_jobs_page`, `import_export_page`, `users_page`, `settings_page_direct`

Marked active on this page: `index`
<!-- END GENERATED APPLICATION EVIDENCE -->

---

## Part C — registry test result

The suites that hold the registry to the rules, and what each one proves. The
counts are deliberately absent: they are reported by the run itself
(`pytest --junitxml`), and a count written into a document is the kind of
figure that goes stale silently.

| Suite | What it establishes |
| --- | --- |
| `tests/unit/test_interface_registry.py` | Identifier, domain, role and route integrity; dependency cycles; shortcut collisions; alias resolution; one definition of the default; retired and renamed ids; and the guardrail that keeps a renamed id out of source files |
| `tests/unit/test_interface_docs.py` | The reference document cannot drift from the registry, and no document carries a live endpoint count of its own |
| `tests/integration/test_interface_coverage.py` | Every user-facing page has exactly one owner; the request gate serves what an interface owns and refuses what nothing owns; disabling a needed interface is refused with the dependents named; an inconsistent stored state is reported; reset applies registry defaults; a settings file written by an earlier version still works; this report matches the application |
| `tests/security/test_interface_visibility.py` | `required_role` narrows visibility and never widens access; a viewer sees no administration entry *and* is refused the page; a check that cannot run refuses the request instead of falling open |
| `tests/e2e/` | The rendered product: one ingestion interface, one shortcut, one switch, in every language |

Run:

```bash
python3 -m pytest tests/unit/test_interface_registry.py tests/unit/test_interface_docs.py \
                 tests/integration/test_interface_coverage.py \
                 tests/security/test_interface_visibility.py tests/e2e --junitxml=registry.xml
```

---

## Part D — acceptance scenarios

The ten scenarios the directive names, and where each is proved:

| # | Scenario | Where |
| --- | --- | --- |
| 1 | A page added without a registry entry fails the suite | `test_every_user_facing_page_has_exactly_one_owner` |
| 2 | A bad domain, role or route fails validation | `validate_registry()` + `test_the_registry_validates_against_the_live_application` |
| 3 | Disabling a needed dependency is refused, with the dependents named | `test_a_dependency_cannot_be_disabled_while_needed`; live: `POST /api/settings/interfaces/file_library` → 409 naming seven dependents |
| 4 | An unknown endpoint is not "enabled" by default | `test_an_endpoint_nothing_owns_is_not_served`, `test_an_unknown_interface_cannot_be_switched_on` |
| 5 | Deleting the old metadata dictionary does not break the application | `INTERFACE_METADATA` is deleted; the suite is green without it |
| 6 | A viewer sees no administration interface, and is refused the page | `test_a_viewer_does_not_see_administration_interfaces` + `test_visibility_never_widens_permissions` |
| 7 | `default_enabled=False` stays off after a reset | `test_reset_uses_registry_defaults_not_enable_everything` |
| 8 | Two interfaces may not own one endpoint unless the sharing is declared | `test_two_interfaces_may_not_own_one_endpoint`, `test_no_two_interfaces_own_the_same_endpoint` |
| 9 | A retired id in old settings keeps its choice and stays harmless | `test_legacy_ids_reach_their_replacement`, `test_a_legacy_only_file_still_produces_a_working_interface_set` |
| 10 | Every entry answers the ten questions | `/api/interfaces` + `test_every_entry_answers_the_reader_questions` |

---

## Part E — what remains legacy

The registry is authoritative, and the code that used to be a second definition
of the product is gone — `INTERFACE_METADATA` no longer exists, and
`is_interface_enabled_by_endpoint` has no "unknown therefore enabled" fallback.
Two compatibility surfaces are deliberate and stay:

* `LEGACY_INTERFACE_IDS` — read-only knowledge of old keys, so an existing
  settings file keeps the operator's choices. Nothing else may name them.
* `settings/settings_adapter.py` — a translation layer from the old call style
  to the registry. It holds no interface metadata of its own; if it starts to,
  the migration has regressed.
