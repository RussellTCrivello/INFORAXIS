# The INFORAXIS Experience Contract

**What this document is.** The third layer of the product's description. The
interface registry says *what the product offers*. The component library says
*how a repeated piece of interface is drawn*. The Experience Contract says *how
one screen behaves and presents itself*: its navigation entry, the actions it
offers, the columns and filters it shows, the states it can be in, its help, its
shortcuts, how it is laid out, and the translation keys every one of those
strings is edited by.

It is generated from the contracts themselves — every count below comes out of
the code, and a test fails if the document and the product disagree.

**Why it exists.** The registry gave the application one answer to "what is
this?", and the component library gave it one answer to "what does a table look
like?". What remained scattered was everything in between: which columns the
file list shows, whether a delete action asks for confirmation, what a screen
says when it is empty, what a button is called in Arabic, and which of those
things an administrator is allowed to change. Today those answers live in
templates, hand-written badges, inline `confirm()` calls and hard-coded English
strings, one page at a time.

**What it is not.** It is not a page builder and not a second settings engine. A
contract describes; it does not execute. There is no SQL in it, no import, no
expression to evaluate, no authorisation decision — `core/experience/validation.py`
refuses those, and the tests run that check over every contract on every build.
Authorisation stays in `core/security`, values stay in the settings engine, URLs
stay in Flask's URL map, and business logic stays in the service layer, exactly
as the registry rules already require.

## The rules

1. **Keys, not sentences.** Every human-readable string in a contract is a
   semantic translation key (`screen.files.column.name.label`) with its English
   source recorded beside it. A screen cannot grow a string no translator can
   find, and rewording does not change an identifier.
2. **A declaration is verified or it is not a declaration.** The screens
   described in `core/experience/declarations.py` name strings that really
   appear in that interface's template; the test reads both and fails when they
   drift apart.
3. **Nothing is invented.** Where nothing is declared, the contract answers from
   the registry — the shell needs a title and a navigation entry for every
   screen — and marks the screen `derived`. The gap is reported as work to do,
   never smoothed over with plausible-looking defaults.
4. **Measurements, not scores.** Translation coverage is counted from the
   catalogs the build ships. There is no "quality score": what is reported is
   how many strings are translated, how many fall back to English, and which
   ones are missing.
5. **The immutable half is labelled.** A contract shows the route and endpoints
   the implementation uses and states `editable_from_frontend: false` beside
   them. A configuration screen may never pretend it can edit where the code
   lives.

## The objects

```text
Interface                     (the registry: what exists)
    └── ScreenConfiguration   (how this deployment presents it)
            ├── NavigationDefinition     domain, label key, order, visibility
            ├── ActionDefinition[]       label key, scope, permission, danger,
            │                            confirmation, shortcut, loading
            ├── FieldDefinition[]        label key, type, required, editable
            ├── ColumnDefinition[]       label key, width, sort, filter, render
            ├── FilterDefinition[]       label key, control, default
            ├── StateDefinition[]        the §63 state, title and message keys
            ├── HelpDefinition           topic, title key, related topics
            ├── TranslationDefinition[]  key, source, context, placeholders
            ├── ShortcutDefinition[]     keys → action key
            └── LayoutDefinition         navigator, workspace, inspector
```

Two of those carry rules that are worth stating plainly, because they are the
rules that keep the product safe to configure:

* **A destructive action must declare a confirmation.** An action that destroys
  data and cannot ask "are you sure?" is how a product loses data by accident,
  so the definition cannot even be constructed without one.
* **A bulk action must declare that it requires a selection.** An action that
  applies to many records and does not name its scope cannot show the reader
  what it is about to do.

## Translation, measured

The product ships two catalogs and the frontend runtime reads both: the Babel
catalogs under `translations/<locale>` for server-rendered text, and the
JavaScript UI packs under `static/js/i18n/locales` for strings that exist only in
client code. Coverage counts the union — a figure drawn from one of them would
be a number the reader can see to be wrong.

Catalogs still key by English source string, which is convenient and not the
long-term model. The contract therefore looks a string up **by semantic key
first and by its source string second**, and reports which lookup succeeded:
`by key` is the part of the migration that has actually happened. Nothing is
claimed about strings that have not been moved.

## Where this goes next

* the **Experience Studio**, which edits these contracts in the frontend, with
  draft → review → publish, versioning and rollback;
* the **Translation Studio**, which manages catalogs as data — statuses,
  placeholders, terminology, import and export — on top of the same coverage
  measurements;
* the **shell**, rebuilt to consume the registry plus this contract rather than
  another collection of page-specific decisions;
* the **Inspector**, which reads a contract to know what to show about the thing
  the reader selected.

<!-- BEGIN GENERATED EXPERIENCE CONTRACT -->
### What this build declares

- Contracts: **25** (described: **3**, derived from the registry only: **22**)
- Definitions: **7** actions, **14** columns, **6** filters, **0** fields, **3** states
- Translation keys the screens need: **157**
- With help: **23**; with a shortcut: **11**; with a navigation entry: **25**

### Every screen

| Interface | Domain | Declared | Title key | Columns | Filters | Actions | States | Help |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dashboard` | WORK | derived | `screen.dashboard.title` | — | — | — | — | yes |
| `file_library` | DISCOVER | yes | `screen.file_library.title` | 7 | 4 | 3 | 1 | yes |
| `search` | DISCOVER | derived | `screen.search.title` | — | — | — | — | yes |
| `sources` | DISCOVER | derived | `screen.sources.title` | — | — | — | — | yes |
| `sides` | DISCOVER | derived | `screen.sides.title` | — | — | — | — | yes |
| `keywords` | DISCOVER | yes | `screen.keywords.title` | 4 | 2 | 2 | 1 | yes |
| `words` | DISCOVER | yes | `screen.words.title` | 3 | — | 2 | 1 | yes |
| `categories` | DISCOVER | derived | `screen.categories.title` | — | — | — | — | yes |
| `email_words` | DISCOVER | derived | `screen.email_words.title` | — | — | — | — | yes |
| `analyst_categorization` | CLASSIFY | derived | `screen.analyst_categorization.title` | — | — | — | — | yes |
| `notifications` | DISCOVER | derived | `screen.notifications.title` | — | — | — | — | yes |
| `input_ingestion` | INGEST | derived | `screen.input_ingestion.title` | — | — | — | — | yes |
| `import_center` | INGEST | derived | `screen.import_center.title` | — | — | — | — | yes |
| `archives` | ANALYZE | derived | `screen.archives.title` | — | — | — | — | yes |
| `path_analysis` | ANALYZE | derived | `screen.path_analysis.title` | — | — | — | — | yes |
| `batch_analysis` | ANALYZE | derived | `screen.batch_analysis.title` | — | — | — | — | yes |
| `classification` | CLASSIFY | derived | `screen.classification.title` | — | — | — | — | yes |
| `comprehensive_dashboard` | REPORT | derived | `screen.comprehensive_dashboard.title` | — | — | — | — | yes |
| `charts_dashboard` | REPORT | derived | `screen.charts_dashboard.title` | — | — | — | — | yes |
| `jobs` | OPERATE | derived | `screen.jobs.title` | — | — | — | — | yes |
| `import_export_console` | OPERATE | derived | `screen.import_export_console.title` | — | — | — | — | — |
| `users` | ADMINISTRATION | derived | `screen.users.title` | — | — | — | — | yes |
| `settings` | SETTINGS | derived | `screen.settings.title` | — | — | — | — | yes |
| `interface_manager` | SETTINGS | derived | `screen.interface_manager.title` | — | — | — | — | yes |
| `concurrency_monitor` | INTERNAL | derived | `screen.concurrency_monitor.title` | — | — | — | — | — |

### Translation coverage, measured

Counted from the catalogs the build ships - the Babel catalogs under `translations/` and the JavaScript UI packs under `static/js/i18n/locales` - against the strings in the message template. `translated` excludes strings that are identical to the source, which are counted as `fallback`.

| Language | Catalog entries | Source strings | Translated | Fallback | Missing | Coverage | Of which translated |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ar` | 2872 | 2505 | 2498 | 7 | 0 | 100.0% | 99.7% |
| `fa` | 2872 | 2505 | 2500 | 5 | 0 | 100.0% | 99.8% |
| `he` | 2872 | 2505 | 2494 | 11 | 0 | 100.0% | 99.6% |
| `hr` | 2620 | 2505 | 2422 | 21 | 62 | 97.5% | 96.7% |

### Coverage per screen

The strings a screen's contract asks for, and how many of them a language actually translates. Looked up by semantic key first and by the English source string second, because the catalogs still key by source string today; `by key` is the part of the migration that has happened.

| Interface | Keys | ar | fa | he | hr |
| --- | --- | --- | --- | --- | --- |
| `dashboard` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `file_library` | 22 | 90.9% (0 by key) | 90.9% (0 by key) | 90.9% (0 by key) | 81.8% (0 by key) |
| `search` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `sources` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `sides` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `keywords` | 16 | 68.8% (0 by key) | 68.8% (0 by key) | 68.8% (0 by key) | 56.2% (0 by key) |
| `words` | 13 | 76.9% (0 by key) | 69.2% (0 by key) | 69.2% (0 by key) | 61.5% (0 by key) |
| `categories` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `email_words` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `analyst_categorization` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `notifications` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `input_ingestion` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `import_center` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `archives` | 5 | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) |
| `path_analysis` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `batch_analysis` | 5 | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) |
| `classification` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `comprehensive_dashboard` | 5 | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) |
| `charts_dashboard` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `jobs` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `import_export_console` | 3 | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) |
| `users` | 5 | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) |
| `settings` | 5 | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) | 80.0% (0 by key) |
| `interface_manager` | 5 | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) |
| `concurrency_monitor` | 3 | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) | 0.0% (0 by key) |

### Screens nobody has described yet

These have a contract derived from the registry, so they work: they have an identity, a navigation entry, a lifecycle and a help topic. What they do not have is a description of what they offer - columns, filters, actions, states - because nobody has decided it. The list is the remaining work, not a defect.

`dashboard`, `search`, `sources`, `sides`, `categories`, `email_words`, `analyst_categorization`, `notifications`, `input_ingestion`, `import_center`, `archives`, `path_analysis`, `batch_analysis`, `classification`, `comprehensive_dashboard`, `charts_dashboard`, `jobs`, `import_export_console`, `users`, `settings`

### Contract validation

Every contract passes the declarative checks: no SQL, no imports, no calls, no authorisation decisions, destructive actions carry a confirmation, bulk actions require a selection, and no key holds two different source strings.

_Generated from 25 contracts, 2505 source strings and 5 catalogs._
<!-- END GENERATED EXPERIENCE CONTRACT -->
