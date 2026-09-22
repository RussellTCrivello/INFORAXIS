# The shared component library

**What this document is.** The contract for the interface components INFORAXIS
shares between pages, and the honest count of where pages still do the work
themselves. It is generated from the repository — the component list comes from
the declarations at the top of the files in `templates/components/`, and the
usage figures come from scanning the templates. Nothing here is typed by hand.

**Why it exists.** Several pages began by solving the same problems separately:
a table of records, a filter bar, a search box, a way to move through a long
list, an empty state, a loading state, an error, a confirmation, a toast, a
record header, a toolbar of actions, a status badge. The differences between
those solutions were not decisions — they were accidents of who wrote which
page first. The registry work made the *navigation* single-sourced; this makes
the *components* single-sourced, on the same principle: define it once, and
make it visible when something new appears beside it.

**What it is not.** This is not a redesign, and not a new visual language.
Every component renders the class names the stylesheets already define, so a
page that adopts one looks the same as before. A component that needs a class
no stylesheet defines fails the guardrail test instead of quietly inventing a
style.

## The rules

1. **A component declares itself.** Each file opens with a `{# component: … #}`
   block naming its purpose, the states it implements and the classes it
   renders. A file without one is reported as undeclared.
2. **States are explicit.** The vocabulary is fixed (spec §63). A component
   implements the states that apply to it; a state nobody implements is listed
   as *not yet*, with the component that will own it — never quietly absent.
3. **Presentation only.** A component renders what it is given. It does not
   query, does not authorize, and does not decide which state is true; the page
   decides that from real data. This is the same boundary the registry follows:
   one place defines, everyone else reads.
4. **The reader is told the truth.** An error says what failed and what to do
   next; it never carries a stack trace, a path, a query or an internal name
   (spec §38, §76). A number that was not measured says so (spec §8).
5. **Moving is visible.** A component is adopted one page at a time; the count
   of templates still writing the markup by hand is the measure of progress.

### One search box, and the page still owns the search

Thirteen pages built their own search box: a label, an input, a clear button,
an icon, and each one slightly different - some with an accessible name, some
without, some clearing on a button that could submit the form it sat in. The
component is now the only place that markup exists, and the page passes what
the component cannot know: the id its JavaScript already binds to, the
translated label and placeholder, the value to show back after a reload, and
the handler its own clear action calls.

What the page does *not* pass is what searching means. The component renders
the box; the page owns the query, the endpoint and the results. Keyboard
behaviour is the one thing that is neither - Escape clearing the box is the
same everywhere - so it lives in `static/js/modules/core/search-input.js`,
which clicks the page's own clear control rather than reimplementing it, so
the page's handler runs exactly once.

Adoption is counted by macro, not by file: a page that places its search box
through the filter bar has adopted the search box and has *not* adopted the
filter bar. Counting file references made both numbers wrong at once.

### Two paginations, deliberately

There are two components here and they are not a mistake. A numbered list knows
how many records there are and can be asked for page 7; a cursor-paged list
knows its next and previous cursor and nothing else, because asking a
billion-row table for an offset is not a thing it can answer. `pagination` and
`pagination_cursor` share their visual conventions — the same classes, the same
placed controls — and share none of their data semantics.

That separation was violated twice: `sides_list.html` and `sources_list.html`
are cursor-paged, and both rendered the numbered pager and then patched it with
script that converted a clicked page number into an estimated cursor. The
estimate was labelled "rough approximation" in the code and was not labelled at
all on screen. Both now render the cursor component: links that carry a real
cursor, forward and backward only, an estimated total that says it is estimated,
and no jump-to-page box, because a cursor cannot jump.

### The states every component has an answer for

| State | What it looks like to the reader |
| --- | --- |
| loading | Something is happening, and the page says what it is waiting for |
| empty | Nothing is here yet, and how to start is on screen |
| normal | The ordinary case, working as intended |
| filtered | Records exist, but not under the filters applied |
| selected | A choice has been made, and the actions that need one appear |
| editing | A value is being changed and is not saved yet |
| saving | A change is on its way to the server |
| success | The last action worked |
| warning | Something needs attention but is not broken |
| error | Something failed, with a next step |
| unauthorized | The server refused this for this account |
| unavailable | It needs something this installation does not have |
| archived | Kept and readable, out of the working set |

<!-- BEGIN GENERATED COMPONENT AUDIT -->

### Components

Read from the `{# component: … #}` declaration at the top of each file in `templates/components/`. A file without one has no declared purpose or states, and is listed as such.

| Component | File | States | Macros | Purpose |
| --- | --- | --- | --- | --- |
| `action_toolbar` | `templates/components/action_toolbar.html` | `selected`, `loading` | `action_toolbar`, `action_group`, `action_button`, `bulk_action_button`, `selection_summary` | The bar of actions on a list: the groups, the buttons, and the one state the server can know for certain - nothing is selected yet. |
| `analyst_classify` | `templates/components/analyst_classify.html` | `normal`, `editing`, `saving`, `success`, `error`, `unauthorized` | `analyst_classify` | The analyst-category control for the record being read, usable from wherever that record is displayed. |
| `breadcrumbs` | `templates/components/breadcrumbs.html` | `normal` | `breadcrumbs` | Where the reader is, rendered from the interface registry: a page says what it is about, the registry supplies the words and icons. |
| `confirm_dialog` | `templates/components/confirm_dialog.html` | `normal`, `saving`, `error`, `unauthorized` | `confirm_dialog` | One way to ask "are you sure?" before something irreversible. The component renders the question; it never performs the operation and never knows what the operation is. The page decides - and it says which action it is asking about, by id, so the dialog and the action registry agree on what is happening. |
| `file_nav` | `templates/components/file_nav.html` | `normal`, `empty` | `file_nav` | Previous/next through the records the reader is working through, and where this one sits in that set. |
| `filter_bar` | `templates/components/filter_bar.html` | `normal`, `filtered`, `empty` | `filter_section`, `filter_grid`, `filter_bar`, `filter_group`, `search_group`, `hidden_filter` | The controls above a list that decide which records it shows: a search box and the filters that narrow it, in the arrangement fifteen pages currently rebuild by hand. |
| `operations_widget` | `templates/components/operations_widget.html` | `normal`, `loading`, `empty`, `error` | — | What the ingestion and processing system is doing right now: active jobs, throughput, and the shortcuts into Operations. |
| `page_data` | `templates/components/analyst_classify_page_data.html` | `normal` | `analyst_classify_page_data` | The translated strings and the write permission the analyst classification module needs, so nothing is hard-coded in JavaScript and a language switch reaches it. |
| `page_tips` | `templates/components/page_tips.html` | `normal`, `empty` | `page_tips` | The explanatory tips at the top of a page: what this page is for, what the elements on it do, how to add data here. |
| `pagination` | `templates/components/unified_pagination.html` | `normal`, `filtered` | `unified_pagination` | Moving through a long list: where you are, how much there is, and how to get to a page you know the number of. |
| `pagination_cursor` | `templates/components/cursor_pagination.html` | `normal`, `filtered` | `cursor_pagination` | Moving through a list that has no page numbers - only "next" and "back" - and saying honestly what is known about how much is left. |
| `record_actions` | `templates/components/record_actions.html` | `normal`, `loading`, `success`, `error`, `unauthorized` | `record_action_button`, `record_action_surface` | The actions a single record offers. The buttons come from the Action Definition layer - id, label, icon, scope, destructiveness, confirmation key - joined with the screen's own bindings by core/experience/presentation.py, so a page cannot invent an action and two pages cannot render one action two ways. |
| `record_header` | `templates/components/record_header.html` | `normal`, `empty`, `loading`, `unavailable`, `archived` | `record_header` | The top of a record: what this record is, what state it is in, and the one action that matters most. The same header for a file, a source, a side, a category, an analysis or a report - it knows nothing about what kind of record it is describing. |
| `screen_inspector` | `templates/components/screen_inspector.html` | `normal`, `loading`, `empty`, `error`, `unavailable` | `inspector_field`, `screen_inspector` | The panel that answers what an element on this screen is: which interface owns it, which component renders it, which action it presents, what scope and permission metadata that action declares, where it is bound, and what it currently is. A diagnostic tool for a developer or an operator, not a configuration editor. |
| `search_input` | `templates/components/search_input.html` | `normal`, `loading`, `filtered`, `unavailable` | `search_input` | The one search box: label, icon, placeholder, value, clear action, a place for the loading state, and the ARIA that makes it a search box rather than an empty text field. |
| `sidebar_nav` | `templates/components/sidebar_nav.html` | `normal`, `empty` | — | The product navigation, grouped by domain, rendered from the navigation model the application prepares. |
| `states` | `templates/components/states.html` | `loading`, `empty`, `filtered`, `success`, `warning`, `error`, `unauthorized`, `unavailable`, `archived` | `state_panel`, `empty_state`, `filtered_state`, `loading_state`, `success_state`, `warning_state`, `error_state`, `unauthorized_state`, `unavailable_state`, `archived_state` | The states a region can be in, in one place, so a page never invents its own wording for "nothing here yet" or its own markup for "this failed". |
| `status_badge` | `templates/components/status_badge.html` | `success`, `warning`, `error`, `unavailable`, `archived` | `status_badge`, `_chip`, `status_badge_with_icon` | One way to show a status word, so the same state is not green on one page and grey on the next. An application status is looked up in the vocabulary - `core/frontend/status_vocabulary.py` - which maps it to one of a few presentation states; the component only turns that state into classes. |
| `table` | `templates/components/table.html` | `normal`, `empty`, `filtered`, `selected`, `loading`, `error` | `data_table`, `table_empty_row`, `table_loading_row`, `table_error_row`, `select_all_checkbox`, `sort_header` | The frame a list of records is read in, and the rows that stand in for a list that is empty, still loading or failed. Ten tables in this application were written with ten different class combinations; this is the one they become. |
| `toast` | `templates/components/toast.html` | `success`, `warning`, `error`, `loading`, `unavailable` | `toast_region` | One place where the application tells the reader that something happened. Every action ends visibly - success, information, warning, failure - and every message passes through here, so no page invents its own notification and no failure goes silent. |

### States (§63)

Every state in the vocabulary is answered by at least one component; a state nobody implements does not exist in the product, however often it is referred to.

| State | Meaning | Implemented by |
| --- | --- | --- |
| `loading` | Work is in progress; the reader is told what is being waited for. | `action_toolbar`, `operations_widget`, `record_actions`, `record_header`, `screen_inspector`, `search_input`, `states`, `table`, `toast` |
| `empty` | Nothing exists here yet, and the reader is told how to start. | `file_nav`, `filter_bar`, `operations_widget`, `page_tips`, `record_header`, `screen_inspector`, `sidebar_nav`, `states`, `table` |
| `normal` | The ordinary case: content is present and usable. | `analyst_classify`, `page_data`, `breadcrumbs`, `confirm_dialog`, `pagination_cursor`, `file_nav`, `filter_bar`, `operations_widget`, `page_tips`, `record_actions`, `record_header`, `screen_inspector`, `search_input`, `sidebar_nav`, `table`, `pagination` |
| `filtered` | Something exists, but not under the filters applied. | `pagination_cursor`, `filter_bar`, `search_input`, `states`, `table`, `pagination` |
| `selected` | A row or record is chosen; actions that need a choice appear. | `action_toolbar`, `table` |
| `editing` | A value is being changed, and the change is not saved yet. | `analyst_classify` |
| `saving` | A change is on its way to the server. | `analyst_classify`, `confirm_dialog` |
| `success` | The last action worked. | `analyst_classify`, `record_actions`, `states`, `status_badge`, `toast` |
| `warning` | Something needs attention but is not broken. | `states`, `status_badge`, `toast` |
| `error` | Something failed, with a next step rather than a stack trace. | `analyst_classify`, `confirm_dialog`, `operations_widget`, `record_actions`, `screen_inspector`, `states`, `status_badge`, `table`, `toast` |
| `unauthorized` | The server refused this for this account. | `analyst_classify`, `confirm_dialog`, `record_actions`, `states` |
| `unavailable` | It needs something this installation does not have. | `record_header`, `screen_inspector`, `search_input`, `states`, `status_badge`, `toast` |
| `archived` | Kept and readable, but out of the working set. | `record_header`, `states`, `status_badge` |

### Markup pages still write by hand

Counted by scanning `templates/**`. These are the places a shared component has not reached yet - the number goes down as components are adopted, and it is the measure of this phase rather than an impression of it.

| Markup | Component that replaces it | Templates |
| --- | --- | --- |
| Hand-written empty state | `states` | 4 templates |
| Hand-written loading indicator | `states` | 8 templates |
| Hand-written inline error | `states` | 7 templates |
| Hand-written table | `table` | 13 templates |
| Hand-written pagination markup | `pagination` | 0 templates |
| Pagination mount (filled by the shared renderer) | `pagination` | 4 templates |
| Hand-written search input | `search_input` | 6 templates |
| Hand-written filter control | `filter_bar` | 14 templates |
| Browser confirm() dialog | `confirm_dialog` | 0 templates |
| Hand-written status badge | `status_badge` | 0 badges, in 0 templates |
| Hand-written badge chip (count, id, method) | — | 68 badges |
| Hand-written action bar | `action_toolbar` | 2 templates |

### Adoption

How much of the repeated markup has moved onto its component. Standardized counts the templates that read through the component; hand-written counts what is still done by hand; the rate is the completion criterion for this phase, not an impression of it.

| Markup | Standardized | Hand-written | Adoption |
| --- | --- | --- | --- |
| Hand-written empty state | 2 | 4 | 33% |
| Hand-written table | 1 | 13 | 7% |
| Hand-written pagination markup | 10 | 0 | 100% |
| Hand-written search input | 8 | 6 | 57% |
| Hand-written filter control | 1 | 14 | 7% |
| Browser confirm() dialog | 2 | 0 | 100% |
| Hand-written status badge | 7 | 0 | 100% |
| Hand-written action bar | 5 | 2 | 71% |

**Declared exceptions.** Not everything that looks similar is the same thing, and overloaded components stop being usable. An exception is a decision with an owner:

| Area | Reason | Owner |
| --- | --- | --- |
| analysis relationship matrix | A matrix of relationships between records is not a list of records: its rows and columns are both entities, and its cells are computed pairs. Forcing it into the table component would give the component a second meaning. | analysis workspace |

### CSS ownership of the classes components render

Every class a component renders has exactly one owner. **OWNED** means an INFORAXIS stylesheet defines it, or the component declares it in its own `classes:` header. **THIRD_PARTY** means a bundled dependency defines it - Bootstrap and Bootstrap Icons are expected dependencies, and using them is not a finding. **UNKNOWN** means nobody does, and an unknown class is how a component invents a style: it fails the guardrail test rather than being reported and forgotten.

| Ownership | Classes |
| --- | --- |
| OWNED (INFORAXIS) | 81 |
| THIRD_PARTY (Bootstrap, Bootstrap Icons) | 199 |
| UNKNOWN | 0 |

Third-party stylesheets bundled with the application: `static/css/bootstrap.min.css`, `static/icons/bootstrap-icons.css`.

Owned by declaration rather than by a stylesheet - the component states these are its own hooks, and no rule styles them (which is a decision, not an accident):

* `cursor-pagination-container` (cursor_pagination.html)
* `file-nav__text` (file_nav.html)
* `search-input-spinner` (search_input.html)
* `sidebar-nav-badge` (sidebar_nav.html)

<!-- END GENERATED COMPONENT AUDIT -->

## How this is measured

Two numbers, both generated, because "introduce shared components" is not
verifiable on its own:

* **hand-written** — the templates still building this markup themselves, and
  for badges, the badges still built by hand;
* **adoption** — the templates reading through the component, and the rate
  between the two, which is the completion criterion for this phase.

Two things the audit is careful about, because a metric that counts the wrong
thing is worse than no metric:

* a status badge is counted by **what it shows**. A badge showing `Active` is a
  status badge; a badge showing `#41` or `GET` is a count or a method. The
  earlier count said "22 status badges" when most of them were numbers;
* a component's CSS ownership is classified as **OWNED**, **THIRD_PARTY** or
  **UNKNOWN**. Bootstrap and Bootstrap Icons are expected dependencies, so
  using them is not a finding; only UNKNOWN fails the guardrail.

**Declared exceptions** are part of the contract, not a loophole. Where
something looks like a repeated pattern but is a different thing, it is written
down with a reason and an owner, so the alternative — a second component grown
quietly, or the generic one overloaded until nobody can use it — does not
happen.

## Where this goes next

The table is built — the frame, the standing rows for a list that is empty,
filtered or failed, the selection affordance and the sort header. What is still
written by hand, and named by the audit above rather than implied: the filter
bar, the search bar, the record header, the action toolbar, the confirmation
dialog and the toast. Each will declare itself the same way, and the counts on
this page are what will show the duplication falling.
