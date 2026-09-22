# The Screen Inspector: Evidence

**What this document is.** The measured evidence for the Screen Inspector: how
much of the answer *"what is this element?"* the product can already derive,
where the answer comes from, and the questions the product cannot answer
honestly yet. Every count below is generated from the product itself — the
registry, the declarations, the binding scan and the component library — and a
test fails if this document and the code disagree.

**What the Inspector is.** A read-only diagnostic. It answers, for the element
under the pointer, which interface owns it, which component renders it, which
action it presents, what that action declares (scope, permission name,
confirmation, operation reference), where the action's binding lives, which
translation key labels it, what it currently is (available, disabled, hidden,
running, success, failed — with the vocabulary's own reason), and what the
product does *not* know. It is switched on in Settings → Advanced, it is absent
from every page when it is off, and it never changes anything: no action is
executed, no permission is decided, no record is touched, no setting is written.

**What it is not.** It is not a configuration editor and it is not a second
registry. It reads what already exists — the Interface Registry, the
declarations, the Action Registry, the binding scan, the component library, the
presentation layer — and it fails visibly rather than guessing. Nothing in it
can create an interface, an action, a permission or a translation, and the
evidence below exists so that a reader does not have to take any of that on
trust.

## How an answer is derived

| Question | Answer comes from | Never from |
| --- | --- | --- |
| Which interface is this? | `core/interfaces` — the registry entry for the endpoint the request was served by | the URL, the path, the page title |
| Which component renders it? | the class list plus `component_audit`, where a class counts only if a component declares it as its own | the words on the button, a familiar-looking class name |
| Which action is it? | `data-inspector-action` → `core/experience/action_registry.py` | the label, the icon, the English text |
| What does the action apply to? | the registry's `scope` | the number of rows on screen |
| May this account run it? | the permission *name* the action declares, and the authorization the server gave for this request, shown apart | a boolean, a role, a disabled attribute |
| Where is it bound? | the binding scan over the components, the pages and the Python that prepares the surface | a promise that a screen *should* bind it |
| What is it right now? | the action state model both the toolbar and the record surface already use | a second vocabulary |
| Which translation labels it? | the key the registry declares | a search of the translation catalog for the text on screen |
| What does it do? | the registry's opaque `execution` reference, or "Not built" | a Flask URL, a route, a file path |

Two rules make the rest of this document readable. **Permission metadata is not
authorization**: the panel shows the name an action declares and the decision
the server returned for that request, in different rows, and the Inspector is
architecturally unable to merge them — `core/experience/inspector.py` imports no
session, no role and no policy, and a test asserts it stays that way.
**Unknown stays unknown**: the vocabulary has separate words for "Not declared",
"Not applicable", "Unavailable" and "Unknown", and a field the product has not
declared reads as one of those rather than being filled with a plausible value.

## How to regenerate

```
python3 -m core.experience.audit docs/SCREEN_INSPECTOR_EVIDENCE.md
```

The counts, the per-action table, the interface table, the field coverage and
the list of questions the Inspector cannot answer yet are all written by that
command. `python3 -m core.experience.audit --json` prints the same numbers as
JSON.

## How this evidence was produced

The Inspector is covered from three directions, and each one can fail on its
own:

* `tests/unit/test_screen_inspector.py` — the model: every refusal above, one
  test each, including the endpoint's guard and the panel's rows.
* `tests/js/screen_inspector_smoke.mjs` — the runtime against the shipped
  module: an idempotent `init()`, a click that inspects a Delete button without
  ever reaching it, Escape leaving targeting before the mode, and no answer
  about one element ever left on screen while another is described.
* `tests/unit/test_experience_contract.py` and
  `tests/unit/test_interface_docs.py` — the registries the Inspector reads,
  which must stay the single source it joins.

## Reading the numbers honestly

Three of the counts below are uncomfortable on purpose, and none of them is a
defect in the Inspector — each is a fact about the product's metadata that the
Inspector exists to make visible:

* **Presented actions nothing binds.** A screen's declaration says the action is
  offered there; nothing in the product names the action id, because those
  screens still render the frozen toolbar's hand-written buttons and page
  functions. The Inspector reports what it finds, so the number falls as screens
  are rendered from the registry, and it is not allowed to fall any other way.
* **Interfaces declaring no keyboard shortcut** (and two with no help topic).
  The registry is the only place a shortcut or a help topic can come from. The
  Inspector does not invent either, so a missing one appears here and in the
  panel as "Not declared".
* **Fields with no declared value.** `execution` is absent for the actions that
  are declared and not built. That is the honest answer, and it is why
  `files.reprocess` reads *hidden — not built* rather than *unavailable —
  denied*.

<!-- BEGIN GENERATED: experience audit -->
## What the product can say about an element

Measured from the interface registry, the action registry, the binding
scan and the component library. Nothing on this page was typed by hand:
`python3 -m core.experience.audit` writes it, and the test compares the
document with what it writes.

| Measurement | Count |
| --- | --- |
| Interfaces | 25 |
| Navigable interfaces | 23 |
| Interfaces with a described screen | 5 |
| Interfaces declaring no help topic | 2 |
| Interfaces declaring no keyboard shortcut | 14 |
| Registered actions | 34 |
| Actions bound to a control | 6 |
| Presented actions nothing binds | 28 |
| Actions declared and not built | 1 |
| Actions named in markup and never registered | 0 |
| Actions no described screen presents | 1 |
| Declared components | 20 |
| Components an element cannot resolve to | 0 |
| Classes rendered in the product | 280 |
| Classes the project owns | 81 |
| Classes that are third-party | 199 |
| Classes belonging to nobody | 0 |
| Bindings the scan found | 8 |

### How far each action's binding reaches

| Status | Actions |
| --- | --- |
| bound to a control | 5 |
| declared, not built | 1 |
| presented, nothing binds it | 28 |

`bound to a control` means the product names the action where a control
comes from - a shared component, a page script, or the Python that
prepares the surface. Everything else is an action a reader can meet that
the architecture cannot yet account for, and each one is listed below
with the evidence.

### The actions the product cannot account for

| Action | Status | Where | Shared surface it uses |
| --- | --- | --- | --- |
| `files.reprocess` | declared, not built | Api/blueprints/files.py:122 | the shared record action surface |
| `files.analyze_selected` | presented, nothing binds it | file_library | the shared record action surface |
| `files.delete_selected` | presented, nothing binds it | file_library | the shared record action surface |
| `files.export_selected` | presented, nothing binds it | file_library | the shared record action surface |
| `files.open_record` | presented, nothing binds it | file_library | the shared record action surface |
| `files.select_all` | presented, nothing binds it | file_library | the shared record action surface |
| `files.select_none` | presented, nothing binds it | file_library | the shared record action surface |
| `files.upload` | presented, nothing binds it | file_library | the shared record action surface |
| `keywords.delete_selected` | presented, nothing binds it | keywords | the shared action toolbar |
| `keywords.edit_selected` | presented, nothing binds it | keywords | the shared action toolbar |
| `keywords.merge_duplicates` | presented, nothing binds it | keywords | the shared action toolbar |
| `keywords.select_all` | presented, nothing binds it | keywords | the shared action toolbar |
| `keywords.select_none` | presented, nothing binds it | keywords | the shared action toolbar |
| `keywords.update` | presented, nothing binds it | keywords | the shared action toolbar |
| `sides.edit_selected` | presented, nothing binds it | sides | the shared action toolbar |
| `sides.export_selected` | presented, nothing binds it | sides | the shared action toolbar |
| `sides.select_all` | presented, nothing binds it | sides | the shared action toolbar |
| `sides.select_none` | presented, nothing binds it | sides | the shared action toolbar |
| `sources.edit_selected` | presented, nothing binds it | sources | the shared action toolbar |
| `sources.export_selected` | presented, nothing binds it | sources | the shared action toolbar |
| `sources.select_all` | presented, nothing binds it | sources | the shared action toolbar |
| `sources.select_none` | presented, nothing binds it | sources | the shared action toolbar |
| `words.delete` | presented, nothing binds it | words | the shared action toolbar |
| `words.delete_selected` | presented, nothing binds it | words | the shared action toolbar |
| `words.edit` | presented, nothing binds it | words | the shared action toolbar |
| `words.edit_selected` | presented, nothing binds it | words | the shared action toolbar |
| `words.open` | presented, nothing binds it | words | the shared action toolbar |
| `words.select_all` | presented, nothing binds it | words | the shared action toolbar |
| `words.select_none` | presented, nothing binds it | words | the shared action toolbar |

### Interfaces the Inspector describes

| Interface | Domain | Route | Help topic | Shortcut | Actions |
| --- | --- | --- | --- | --- | --- |
| `dashboard` | WORK | `index` | work/dashboard | g w | 0 |
| `file_library` | DISCOVER | `files.files_list` | discover/file-library | g f | 12 |
| `search` | DISCOVER | `search_page` | discover/search | g s | 0 |
| `sources` | DISCOVER | `sources_list` | discover/sources | Not declared | 4 |
| `sides` | DISCOVER | `sides_list` | discover/sides | Not declared | 4 |
| `keywords` | DISCOVER | `keywords_list` | discover/keywords | Not declared | 6 |
| `words` | DISCOVER | `words_list` | discover/words | Not declared | 7 |
| `categories` | DISCOVER | `categories_list` | discover/categories | Not declared | 0 |
| `email_words` | DISCOVER | `email_words` | discover/email-words | Not declared | 0 |
| `analyst_categorization` | CLASSIFY | `analyst_categorization_page` | classify/analyst-categories | Not declared | 0 |
| `notifications` | DISCOVER | `notifications_page` | discover/notifications | g n | 0 |
| `input_ingestion` | INGEST | `operations_input_page` | ingest/input | g i | 0 |
| `import_center` | INGEST | `operations_import_page` | ingest/import-center | Not declared | 0 |
| `archives` | ANALYZE | `archives_page` | analyze/archives | g a | 0 |
| `path_analysis` | ANALYZE | `path_analysis_page` | analyze/path-analysis | g p | 0 |
| `batch_analysis` | ANALYZE | `analysis_batch` | analyze/batch | g b | 0 |
| `classification` | CLASSIFY | `file_classification_page` | classify/classification | Not declared | 0 |
| `comprehensive_dashboard` | REPORT | `comprehensive_dashboard` | report/detailed-dashboard | Not declared | 0 |
| `charts_dashboard` | REPORT | `charts_dashboard` | report/charts | Not declared | 0 |
| `jobs` | OPERATE | `operations_jobs_page` | operate/jobs | g j | 0 |
| `import_export_console` | OPERATE | `import_export_page` | Not declared | Not declared | 0 |
| `users` | ADMINISTRATION | `users_page` | administration/users | g u | 0 |
| `settings` | SETTINGS | `settings_page_direct` | settings/overview | g , | 0 |
| `interface_manager` | SETTINGS | `None` | settings/interfaces | Not declared | 0 |
| `concurrency_monitor` | INTERNAL | `concurrency.dashboard` | Not declared | Not declared | 0 |

### Fields, and how many actions declare them

| Field | Declared | Of |
| --- | --- | --- |
| action | 34 | 34 |
| binding | 6 | 34 |
| component | 20 | 20 |
| execution | 29 | 34 |
| help | 23 | 25 |
| interface | 25 | 25 |
| permission | 34 | 34 |
| scope | 34 | 34 |
| state | 34 | 34 |
| translation | 34 | 34 |

A field nobody declares is not a defect in the Inspector: it is why the
panel says *Not declared*, and the number is here so filling the metadata
in is visible progress rather than a matter of opinion.

### The questions the Inspector cannot answer yet

**Actions with no operation: `execution` is empty and no job exists** — The registry can say 'declared, not built' and the surface honours it - the button is hidden, nothing is drawn, and no route is bound - but four actions (`files.reprocess`, `sources.export_selected`, `sources.edit_selected`, and the bulk export and edit of the same family) have no operation to name, so the Inspector can only report the absence. Building one means giving it a persistent job and a path policy first, which the action vocabulary has no room for.

Evidence: `core/experience/action_registry.py`, `Api/blueprints/files.py`, `pipeline/storage_pipeline.py`

**An action's help topic and shortcut** — Every interface declares a help topic and five of six navigable screens declare no keyboard shortcut, and an action declares neither. The Inspector therefore shows the screen's help and nothing for the action's own, rather than borrowing one: a help topic is a promise that a page answers that question, and the action vocabulary has no field for it.

Evidence: `core/interfaces/registry.py`, `core/experience/inspector.py`

**What a control is bound to, when it is wired by a page function** — The frozen toolbar renders buttons that call a page function by name (`data-sequence-action`), not from the registry, so for most actions the only honest answer is 'hand-written button, not registry-bound'. The Inspector cannot trace a click to its operation for those screens until each screen renders its toolbar from the registry, which the freeze defers on purpose.

Evidence: `templates/components/action_toolbar.html`, `static/js/pages/keywords-list-page.js`, `static/js/pages/sources-list-page.js`

**Whether the reader is permitted to run the action** — The Inspector reports the permission *name* the action declares and the authorization decision the server gave for that request, and keeps them apart on purpose: a name is not a decision, and a browser must never be shown one as a boolean. There is no server-side 'may this account run this action' answer to show yet, because authorization today is decided where the operation runs - so the field reads 'Not determined' rather than a guess.

Evidence: `core/experience/inspector.py`, `core/security/flask_ext.py`
<!-- END GENERATED: experience audit -->

## What the Inspector will never report

* A permission as a decision, a role, or a boolean.
* An authorization answer the server did not give.
* An action inferred from the text of a button, or a component inferred from the
  words on it.
* A translation key found by searching the catalog for the text on screen.
* A filesystem path, a database connection, a credential, a session or CSRF
  secret, a raw trace, or an exception object. Observed text that looks like a
  path is dropped before it is carried anywhere.
* A route where an operation reference belongs. `execution` is opaque and is
  validated as such by the Action Registry; a URL in that field is rejected
  before the Inspector can see it.
* A second answer to a question the registry already answers: no route map, no
  component inventory, no permission list, no catalog of its own.
