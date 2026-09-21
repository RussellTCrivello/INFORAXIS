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
| `analyst_classify` | `templates/components/analyst_classify.html` | `normal`, `editing`, `saving`, `success`, `error`, `unauthorized` | `analyst_classify` | The analyst-category control for the record being read, usable from wherever that record is displayed. |
| `breadcrumbs` | `templates/components/breadcrumbs.html` | `normal` | `breadcrumbs` | Where the reader is, rendered from the interface registry: a page says what it is about, the registry supplies the words and icons. |
| `file_nav` | `templates/components/file_nav.html` | `normal`, `empty` | `file_nav` | Previous/next through the records the reader is working through, and where this one sits in that set. |
| `operations_widget` | `templates/components/operations_widget.html` | `normal`, `loading`, `empty`, `error` | — | What the ingestion and processing system is doing right now: active jobs, throughput, and the shortcuts into Operations. |
| `page_data` | `templates/components/analyst_classify_page_data.html` | `normal` | `analyst_classify_page_data` | The translated strings and the write permission the analyst classification module needs, so nothing is hard-coded in JavaScript and a language switch reaches it. |
| `page_tips` | `templates/components/page_tips.html` | `normal`, `empty` | `page_tips` | The explanatory tips at the top of a page: what this page is for, what the elements on it do, how to add data here. |
| `pagination` | `templates/components/unified_pagination.html` | `normal`, `filtered` | — | Moving through a long list: where you are, how much there is, and how to get to a page you know the number of. |
| `pagination_cursor` | `templates/components/cursor_pagination.html` | `normal`, `filtered` | — | The same job for cursor-paged lists, where "page 7" does not exist and only forward/backward is meaningful. |
| `sidebar_nav` | `templates/components/sidebar_nav.html` | `normal`, `empty` | — | The product navigation, grouped by domain, rendered from the navigation model the application prepares. |
| `states` | `templates/components/states.html` | `loading`, `empty`, `filtered`, `success`, `warning`, `error`, `unauthorized`, `unavailable`, `archived` | `state_panel`, `empty_state`, `filtered_state`, `loading_state`, `success_state`, `warning_state`, `error_state`, `unauthorized_state`, `unavailable_state`, `archived_state` | The states a region can be in, in one place, so a page never invents its own wording for "nothing here yet" or its own markup for "this failed". |
| `status_badge` | `templates/components/status_badge.html` | `success`, `warning`, `error`, `unavailable`, `archived` | `status_badge`, `status_badge_with_icon` | One way to show a status word, so the same state is not green on one page and grey on the next. |
| `table` | `templates/components/table.html` | `normal`, `empty`, `filtered`, `selected`, `loading`, `error` | `data_table`, `table_empty_row`, `table_loading_row`, `table_error_row`, `select_all_checkbox`, `sort_header` | The frame a list of records is read in, and the rows that stand in for a list that is empty, still loading or failed. Ten tables in this application were written with ten different class combinations; this is the one they become. |

### States (§63)

Every state in the vocabulary is answered by at least one component; a state nobody implements does not exist in the product, however often it is referred to.

| State | Meaning | Implemented by |
| --- | --- | --- |
| `loading` | Work is in progress; the reader is told what is being waited for. | `operations_widget`, `states`, `table` |
| `empty` | Nothing exists here yet, and the reader is told how to start. | `file_nav`, `operations_widget`, `page_tips`, `sidebar_nav`, `states`, `table` |
| `normal` | The ordinary case: content is present and usable. | `analyst_classify`, `page_data`, `breadcrumbs`, `pagination_cursor`, `file_nav`, `operations_widget`, `page_tips`, `sidebar_nav`, `table`, `pagination` |
| `filtered` | Something exists, but not under the filters applied. | `pagination_cursor`, `states`, `table`, `pagination` |
| `selected` | A row or record is chosen; actions that need a choice appear. | `table` |
| `editing` | A value is being changed, and the change is not saved yet. | `analyst_classify` |
| `saving` | A change is on its way to the server. | `analyst_classify` |
| `success` | The last action worked. | `analyst_classify`, `states`, `status_badge` |
| `warning` | Something needs attention but is not broken. | `states`, `status_badge` |
| `error` | Something failed, with a next step rather than a stack trace. | `analyst_classify`, `operations_widget`, `states`, `status_badge`, `table` |
| `unauthorized` | The server refused this for this account. | `analyst_classify`, `states` |
| `unavailable` | It needs something this installation does not have. | `states`, `status_badge` |
| `archived` | Kept and readable, but out of the working set. | `states`, `status_badge` |

### Markup pages still write by hand

Counted by scanning `templates/**`. These are the places a shared component has not reached yet - the number goes down as components are adopted, and it is the measure of this phase rather than an impression of it.

| Markup | Component that replaces it | Templates |
| --- | --- | --- |
| Hand-written empty state | `states` | 4 |
| Hand-written loading indicator | `states` | 8 |
| Hand-written inline error | `states` | 7 |
| Hand-written table | `table` | 13 |
| Hand-written pagination | `pagination` | 6 |
| Hand-written search input | — | 14 |
| Hand-written filter control | — | 15 |
| Browser confirm() dialog | — | 2 |
| Hand-written status badge | `status_badge` | 22 |
| Hand-written action toolbar | — | 1 |

### Classes rendered by components

These class names are rendered by a component but no stylesheet defines them:

* `templates/components/analyst_classify.html`: `bi-person-fill`, `bi-person-tags`, `bi-tag`, `bi-tag-fill`
* `templates/components/breadcrumbs.html`: `bi-house-door`
* `templates/components/cursor_pagination.html`: `bi-info-circle`, `cursor-pagination-container`
* `templates/components/file_nav.html`: `file-nav__text`
* `templates/components/operations_widget.html`: `bi-box-arrow-in-down`, `bi-clock-history`, `bi-list-check`, `bi-plus-lg`, `bi-search`
* `templates/components/page_tips.html`: `bi-chevron-up`, `bi-lightbulb-fill`
* `templates/components/sidebar_nav.html`: `sidebar-nav-badge`
* `templates/components/table.html`: `bi-arrow-down-up`
* `templates/components/unified_pagination.html`: `bi-info-circle`

<!-- END GENERATED COMPONENT AUDIT -->

## Where this goes next

The table is built — the frame, the standing rows for a list that is empty,
filtered or failed, the selection affordance and the sort header. What is still
written by hand, and named by the audit above rather than implied: the filter
bar, the search bar, the record header, the action toolbar, the confirmation
dialog and the toast. Each will declare itself the same way, and the counts on
this page are what will show the duplication falling.
