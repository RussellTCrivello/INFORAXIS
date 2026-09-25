# The INFORAXIS interface registry

**What this document is.** The architectural contract describing the product
itself: what interfaces INFORAXIS offers, what domain each belongs to, who
should see it, what it needs, where it lives and whether it is switched on.
It replaces `INTERFACE_METADATA` — an untyped dictionary inside the settings
adapter that described pages which did not exist, missed most of the pages that
did, and could disagree with both the application and the stored settings.

**Where the truth lives.** `core/interfaces/registry.py`. This document is
generated from it (see *Keeping this document honest* at the end); if the two
disagree, the registry is right and the document is stale.

---

## 1. The model

```python
Interface(
    interface_id="batch_analysis",          # stable key; persisted settings use it
    name="Batch Analysis",                # what the operator is shown
    description="Process many objects…",    # what it is for
    domain=Domain.ANALYZE,                  # exactly one domain
    route="analysis_batch",                 # a Flask endpoint, not a URL
    aliases=("analysis_batch_legacy",),     # other endpoints this interface owns
    icon="bi-lightning-charge",
    default_enabled=True,                   # the ONLY definition of the default
    required_role=None,                     # visibility, never authorisation
    dependencies=("file_library",),         # what must be available to use it
    settings=("processing.max_workers",),   # references, never copies
    feature_flag=None,                      # gate for unreleased work
    help_topic="analyze/batch",             # None means deliberately none yet
    keyboard_shortcut="g b",
    kind=InterfaceKind.PAGE,                # PAGE | SECTION | INTERNAL | FEATURE
    status=InterfaceStatus.ACTIVE,          # ACTIVE | EXPERIMENTAL | DEPRECATED | RETIRED
)
```

Five kinds of question the model answers, and the answer to each:

| Question | Answer comes from |
| --- | --- |
| Does this exist? | `status` (`RETIRED` means no) |
| Is it switched on? | stored settings, defaulted from `default_enabled`, gated by dependencies and `feature_flag` |
| Who sees it? | `required_role` for visibility; `core/security` for access |
| Where does it live? | `route` + `aliases`, verified against the live URL map |
| What does it need? | `dependencies`, `settings` |

---

## 2. Why the registry, and not the old adapter dictionary

The old arrangement had the product model in three places: a metadata
dictionary, a stored settings dictionary, and a hand-written endpoint map — plus
a hand-written navigation template that named interface ids directly. The
consequences were visible in the product:

* `analytics` pointed at an endpoint that does not exist (checked against the
  URL map): a switch that gated nothing.
* `page_tips` was listed as an interface although it has no page; it is a
  cross-cutting feature and is declared as one (`FEATURES`).
* `file_browser` and `file_library` both claimed `files.files_list`: two
  switches for one page, one of them meaningless.
* Most page endpoints had no entry at all — the inventory in
  `core/interfaces/inventory.py` measures exactly how many now — so the greater
  part of the application could not appear in navigation, permissions, help or
  shortcuts.
* `reset_interfaces_to_defaults()` enabled *everything* in the settings file
  while the getter returned `False` for ids it did not know: the settings file
  was authoritative over the product model, and the two defaults disagreed.
* `is_interface_enabled_by_endpoint()` ended with `return True` for any
  endpoint missing from its hand-written map, which made a page somebody forgot
  to register indistinguishable from one that was registered.

Each of those is now a rule with a test:

| Defect | Rule | Where it is enforced |
| --- | --- | --- |
| Dead interface (`analytics`) | Every declared route must exist | `validate_registry` + `test_the_registry_validates_against_the_live_application` |
| Interface with no page (`page_tips`) | Pages have routes; features are `FEATURES` | model + `test_page_tips_is_a_feature_not_an_interface` |
| Two interfaces, one page | One endpoint has one owner; sharing means declaring an alias | `test_two_interfaces_may_not_own_one_endpoint`, `test_no_two_interfaces_own_the_same_endpoint` |
| Unmanaged pages | Every user-facing page is owned, or the build fails | `test_every_user_facing_page_has_exactly_one_owner` |
| Two different defaults | `default_enabled` is the only default | `test_reset_uses_registry_defaults_not_enable_everything` |
| "Unknown, therefore enabled" | Unknown means unregistered, and unregistered is not served | `test_an_unowned_endpoint_is_refused`, `test_an_unknown_interface_cannot_be_switched_on` |
| Navigation naming ids by hand | The sidebar renders from the registry | `test_no_source_file_gates_on_a_renamed_id`, `test_the_navigation_names_no_interface_id_at_all` |

---

## 3. The boundary the registry must not cross

Three systems stay authoritative for three different things. The registry
refers to them; it never restates them.

| Concern | Authority | What the registry may say |
| --- | --- | --- |
| May this request execute? | `core/security` (roles, sessions, blueprint policy) | `required_role` — *visibility only*. Nothing in the registry grants access, and `InterfaceState` has no authorisation method. |
| What is this setting's value? | the settings engine (`AllSettings`) | `settings=("processing.max_workers",)` — a reference, validated against the model. |
| Does this URL exist? | Flask's URL map | `route="analysis_batch"` — an endpoint name, verified by the coverage test. |

A registry that decided authorisation would be a second security model; one
that stored values would be a second settings engine; one that matched URLs
would be a second router. It is a description, and this boundary is the reason
the tests can check it: a description that lies is detectable, a description
that adjudicates is not.

---

## 4. Lifecycle

```
ACTIVE ──────► EXPERIMENTAL (needs a feature_flag; off until the flag is on)
   │
   ├─────────► DEPRECATED (works, superseded; still listed and switchable)
   │
   └─────────► RETIRED (no longer part of the product)
```

`exists` and `enabled` are different questions, and the retirement path keeps
them apart:

* A retired id lives in `RETIRED_INTERFACE_IDS`. Its stored value is never
  deleted — the settings file belongs to the operator — but it cannot switch
  anything on, and `resolve_interface_id` only lets it through when it was
  *merged* into a successor (`file_upload` → `input_ingestion`).
* Retired and renamed ids are reported: `InterfaceState.state_report()` lists
  `retired_stored`, `unknown_stored` and `migrated_from`, so an administrator
  can see what their file contains and what it was understood to mean.

Renames and merges going forward:

```python
LEGACY_INTERFACE_IDS = {
    "file_analysis": "archives",             # renamed: it displayed the product name
    "upload_files":  "input_ingestion",      # renamed: it describes an upload page
    "file_upload":   "input_ingestion",      # retired: a duplicate with no route
    "file_browser":  "file_library",         # merged: same page
    "advanced_search": "search",             # merged: a mode of one interface
    "analytics":     "comprehensive_dashboard",  # its endpoint never existed
}
```

An old key in a settings file keeps the operator's choice; a *code* reference
to an old key is a defect the test suite reports (§ above), because that is how
the navigation entry vanished the first time this rename happened.

---

## 5. The registry reference

<!-- BEGIN GENERATED REGISTRY TABLE -->
- Interfaces: **26** (features declared separately: **1**)
- Endpoints owned: **67**
- With a keyboard shortcut: **12**; with a help topic: **24**
- By domain: ADMINISTRATION 1, ANALYZE 3, CLASSIFY 2, DISCOVER 9, INGEST 2, INTERNAL 1, OPERATE 2, REPORT 2, SETTINGS 3, WORK 1
- By status: ACTIVE 25, DEPRECATED 1
- By kind: INTERNAL 1, PAGE 24, SECTION 1


### WORK (1)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dashboard` | Dashboard | WORK | `index` | — | any | on | — | work/dashboard | g w | ACTIVE |

### DISCOVER (9)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `file_library` | File Library | DISCOVER | `files.files_list` | `files.file_detail`, `files.file_content_lazy`, `files.file_content_page`, `files.file_full_content`, `files.file_search_all_pages`, `files.file_chart_data`, `files.file_types_page`, `files.delete_file`, `files.bulk_delete_files`, `files.bulk_export_files` | any | on | — | discover/file-library | g f | ACTIVE |
| `search` | Search | DISCOVER | `search_page` | `search_advanced`, `search_enhanced_page`, `saved_searches_page`, `search_advanced_api` | any | on | — | discover/search | g s | ACTIVE |
| `sources` | Sources | DISCOVER | `sources_list` | `source_add`, `source_detail`, `source_edit`, `source_categories_keywords` | any | on | — | discover/sources | — | ACTIVE |
| `sides` | Sides | DISCOVER | `sides_list` | `side_add`, `side_detail`, `side_edit`, `side_categories_keywords` | any | on | — | discover/sides | — | ACTIVE |
| `keywords` | Keywords | DISCOVER | `keywords_list` | `keyword_detail`, `keywords_add` | any | on | — | discover/keywords | — | ACTIVE |
| `words` | Words | DISCOVER | `words_list` | `word_detail`, `words_add` | any | on | — | discover/words | — | ACTIVE |
| `categories` | Categories | DISCOVER | `categories_list` | `category_words`, `category_add` | any | on | — | discover/categories | — | ACTIVE |
| `email_words` | Email Words | DISCOVER | `email_words` | — | any | on | — | discover/email-words | — | ACTIVE |
| `notifications` | Notifications | DISCOVER | `notifications_page` | — | any | on | — | discover/notifications | g n | ACTIVE |

### INGEST (2)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `input_ingestion` | Input / Ingestion | INGEST | `operations_input_page` | `files.upload_page`, `files.get_active_tasks`, `files.upload_progress`, `files.api_cancel_task`, `files.pause_task`, `files.resume_task` | any | on | — | ingest/input | g i | ACTIVE |
| `import_center` | Import Center | INGEST | `operations_import_page` | — | any | on | — | ingest/import-center | — | ACTIVE |

### ANALYZE (3)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `archives` | File Management and Analysis | ANALYZE | `archives_page` | — | any | on | `file_library` | analyze/archives | g a | ACTIVE |
| `path_analysis` | Path Analysis | ANALYZE | `path_analysis_page` | — | any | on | `file_library` | analyze/path-analysis | g p | ACTIVE |
| `batch_analysis` | Batch Analysis | ANALYZE | `analysis_batch` | `analysis_batch_process` | any | on | `file_library` | analyze/batch | g b | ACTIVE |

### CLASSIFY (2)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `analyst_categorization` | Analyst Categories | CLASSIFY | `analyst_categorization_page` | — | any | on | `file_library` | classify/analyst-categories | — | ACTIVE |
| `classification` | Classification | CLASSIFY | `file_classification_page` | — | any | on | `file_library`, `words` | classify/classification | — | ACTIVE |

### REPORT (2)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `comprehensive_dashboard` | Comprehensive Dashboard | REPORT | `comprehensive_dashboard` | — | any | on | `file_library` | report/detailed-dashboard | — | ACTIVE |
| `charts_dashboard` | Charts Dashboard | REPORT | `charts_dashboard` | — | any | on | `file_library` | report/charts | — | ACTIVE |

### OPERATE (2)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `jobs` | Jobs | OPERATE | `operations_jobs_page` | `operations_job_detail_page` | any | on | — | operate/jobs | g j | ACTIVE |
| `import_export_console` | Import/Export | OPERATE | `import_export_page` | — | admin | on | — | — | — | DEPRECATED |

### ADMINISTRATION (1)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `users` | User Management | ADMINISTRATION | `users_page` | — | admin | on | — | administration/users | g u | ACTIVE |

### SETTINGS (3)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `settings` | Settings | SETTINGS | `settings_page_direct` | `settings_api.settings_page` | admin | on | — | settings/overview | g , | ACTIVE |
| `interface_manager` | Interface Manager | SETTINGS | — | — | admin | on | `settings` | settings/interfaces | — | ACTIVE |
| `translation_manager` | Translation Management | SETTINGS | `translations.translation_management_page` | — | admin | on | — | settings/translations | g t | ACTIVE |

### INTERNAL (1)

| ID | Name | Domain | Route | Aliases | Role | Default | Depends on | Help | Shortcut | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `concurrency_monitor` | Concurrency Monitor | INTERNAL | `concurrency.dashboard` | `concurrency.get_metrics`, `concurrency.get_threads`, `concurrency.get_processes`, `concurrency.get_pools`, `concurrency.get_async_tasks` | admin | on | — | — | — | ACTIVE |

### Features (not interfaces)

| ID | Name | Description | Default |
| --- | --- | --- | --- |
| `page_tips` | Page Tips & Documentation | Explanatory tips at the top of each page, describing the elements on it, how to use them and how to add data. | on |
<!-- END GENERATED REGISTRY TABLE -->


---

## 8. The contract is frozen

From this point the registry is a lock, not a description:

| To add… | You must |
| --- | --- |
| a page | register an interface with a route, a domain, a description and the endpoints it owns; the coverage test fails until you do |
| a navigation entry | declare the interface — the sidebar renders the registry and nothing else |
| a keyboard shortcut | declare `keyboard_shortcut` (two interfaces may not share one) |
| a help topic | declare `help_topic`, or set it to `None` deliberately |
| a visibility rule | declare `required_role` — and remember it hides, it does not authorise |
| a dependency | declare it; disabling a dependency of a live interface is refused, and an inconsistent stored state is reported |

The guardrails that enforce this, and where they live:

| Guardrail | Test |
| --- | --- |
| A page nobody registered fails the build | `tests/integration/test_interface_coverage.py` |
| The registry is internally consistent | `tests/unit/test_interface_registry.py` |
| The documentation cannot drift from the registry | `tests/unit/test_interface_docs.py` |
| No template names a product id or keeps a label map | `tests/unit/test_registry_purity.py` |
| A lifecycle status means one thing everywhere | `tests/unit/test_interface_lifecycle.py` |
| Visibility never becomes authorisation | `tests/security/test_interface_visibility.py` |

### What each lifecycle status means

| Status | Navigable | Switchable | Marked | Meaning |
| --- | --- | --- | --- | --- |
| ACTIVE | yes | yes | — | — (no status remark; the interface's own description is enough) |
| EXPERIMENTAL | only while its feature flag is on | yes | "Experimental" | Not finished; hidden until the flag is enabled. |
| DEPRECATED | yes | yes | "Deprecated" | Still works and is still supported, but scheduled to be replaced. |
| RETIRED | no | no | "Retired" | No longer part of the product; a stored setting for it is kept and ignored. |

### The four questions stay four questions

`exists` (the product declares it), `enabled` (this installation has it on),
`visible` (this operator may see it), `accessible` (its own conditions are met).
They are never collapsed: an interface can exist and be enabled while a viewer
may not see it. None of them is authorisation — `core/security` decides whether
a request executes, and the API payloads say so in an `authorization` field.

---

## 6. The service API

Callers use these instead of inspecting dictionaries.

**The registry itself** (`core.interfaces`) — what exists:

```python
get_interface(interface_id)            # the Interface, or None
get_all_interfaces()                   # every declared interface
get_interfaces_by_domain()             # grouped, for navigation and settings
get_interface_for_endpoint(endpoint)   # the owner of a Flask endpoint, or None
is_registered(interface_id)            # is this id part of the product?
get_dependencies(id) / get_dependents(id)
default_enabled(id) / defaults()       # the single definition of the default
resolve_interface_id(value)            # fold a legacy id onto its successor
summary()                              # generated counts (never typed by hand)
```

**Stored state applied** (`settings.interface_state.InterfaceState`) — what this
installation has switched on:

```python
is_enabled(interface_id)               # usable now (own switch + dependencies + flag)
own_enabled(interface_id)              # just this interface's switch
is_visible(interface_id, user)         # navigation: enabled, role, dependencies
get_visible_interfaces(user) / get_visible_by_domain(user)
can_disable(id) / can_enable(id)       # (allowed, explanation) for the settings screen
missing_dependencies(id) / enabled_dependents(id)
endpoint_enabled(endpoint, path)       # the request gate's question
state_report() / interfaces_with_state(user)   # what an administrator is shown
```

**The application's own facts** (`core.interfaces.inventory`):

```python
build_inventory(app)                   # every endpoint, classified, from the URL map
registry_coverage(records)             # how much of the application is accounted for
unowned_user_interfaces(records)       # the guardrail's answer (must be empty)
```

Administratively, the same information is served at `/api/interfaces`,
`/api/interfaces/coverage` and `/api/interfaces/inventory`; switching is
`/api/settings/interfaces/<id>` (which refuses configurations that cannot work
and explains why).

---

## 7. Keeping this document honest

The block between the markers above is generated:

```bash
python3 -m core.interfaces.docgen docs/INTERFACE_REGISTRY.md
```

`tests/unit/test_interface_docs.py` compares the two, so a registry change that
is not reflected here fails the suite. Nothing in this document is counted by
hand — including the endpoint figures, which come from the application's URL
map through `build_inventory`.
