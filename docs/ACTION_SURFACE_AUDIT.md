# The Action Surface Audit

**What this document is.** The measured inventory of everything a person can do
in INFORAXIS and where that control lives today: the shared action toolbar, the
bars still written by hand, the buttons drawn inside a record's row, browser
`confirm()` dialogs, filter submits, viewer controls, and the button state each
page decides for itself.

**Why it exists.** The action toolbar is frozen. Before another screen is
migrated onto it, the product needs an honest answer to a smaller and less
comfortable question: how many actions are there, what does each apply to, and
which of them cannot be described by the model that exists? Migrating screens
faster than the model grows is how a toolbar ends up with a `mode` option for
one page's button — which is exactly what the freeze forbids.

**What it is not.** It is not the Action Registry, and it does not change a
screen. It measures: the declared contract, the templates as they are, and the
actions whose behaviour the current abstractions cannot state. Every count and
every file list below is generated from the product itself — a test fails if
this document and the code disagree — and the "cannot say" column is anchored
to the code that proves it, so the moment a gap is closed it leaves the list
instead of lingering as folklore.

Regenerate with:

```
python3 -m core.experience.action_audit docs/ACTION_SURFACE_AUDIT.md
```

<!-- BEGIN GENERATED: action surfaces -->
### What was measured

Three sources, none of them typed by hand:

* the **declared contract** - the actions somebody has described, which the contract tests already verify against the screen;
* the **surfaces the templates carry** - the shared toolbar, the bars still written by hand, record-row actions, browser confirmation dialogs, viewer controls and page-local button state, each with the files that prove it;
* the **gaps** - actions whose behaviour the current model cannot say, each anchored to code.

This is a measurement of the product as it is, not a target.

| Measure | Value |
| --- | --- |
| Registered interfaces | 25 |
| Navigable screens | 23 |
| Screens with a described experience | 5 |
| Screens nobody has described yet | 18 |
| Declared actions | 24 |
| - page / record / selection / bulk | 11 / 5 / 2 / 6 |
| - destructive | 5 |
| - naming a confirmation | 5 |
| - naming a permission | 0 |
| - naming the endpoint that performs them | 0 |
| Templates rendering the shared ActionToolbar | 5 |
| Hand-written action bars | 1 |
| Templates with record actions in the row | 3 |
| Templates with a filter submit inside a bar | 1 |
| Templates with document viewer controls | 1 |
| Files still calling the browser confirm() | 20 |
| Files deciding button state by hand | 7 |
| Actions that do not fit the current abstractions | 11 |

### Declared actions

Permission and endpoint are empty because nothing claims them yet: the permission vocabulary for actions does not exist, and no declared action names the route that performs it. Those two columns are the reason the Action Registry comes next.

| Interface | Action | Scope | Permission | Destructive | Confirmation | Component |
| --- | --- | --- | --- | --- | --- | --- |
| file_library | upload | page | - | - | - | hand-written bar |
| file_library | read | record | - | - | - | record row |
| file_library | delete | record | - | yes | action.files.delete.confirm | record row |
| keywords | update | page | - | - | - | ActionToolbar |
| keywords | select_all | page | - | - | - | ActionToolbar |
| keywords | select_none | page | - | - | - | ActionToolbar |
| keywords | edit_selected | selection | - | - | - | ActionToolbar |
| keywords | bulk_delete | bulk | - | yes | action.keywords.bulk_delete.confirm | ActionToolbar |
| keywords | merge_duplicates | page | - | yes | action.keywords.merge_duplicates.confirm | ActionToolbar |
| sources | select_all | page | - | - | - | ActionToolbar |
| sources | select_none | page | - | - | - | ActionToolbar |
| sources | export_selected | bulk | - | - | - | ActionToolbar |
| sources | edit_selected | bulk | - | - | - | ActionToolbar |
| sides | select_all | page | - | - | - | ActionToolbar |
| sides | select_none | page | - | - | - | ActionToolbar |
| sides | export_selected | bulk | - | - | - | ActionToolbar |
| sides | edit_selected | bulk | - | - | - | ActionToolbar |
| words | select_all | page | - | - | - | ActionToolbar |
| words | select_none | page | - | - | - | ActionToolbar |
| words | edit_selected | selection | - | - | - | ActionToolbar |
| words | bulk_delete | bulk | - | yes | action.words.bulk_delete.confirm | ActionToolbar |
| words | open | record | - | - | - | record row |
| words | edit | record | - | - | - | record row |
| words | delete | record | - | yes | action.words.delete.confirm | record row |

### Surfaces the model does not own yet

Each row is a scan from `SURFACES`, so the count and the files come from one statement.

| Surface | Files | Where |
| --- | --- | --- |
| Shared action toolbar | 5 | `templates/Keyword/keywords_list.html`, `templates/Side/sides_list.html`, `templates/Sources/sources_list.html`, `templates/Word/Word_list.html`, `templates/email_words/email_words.html` |
| Hand-written action bar | 1 | `templates/file/files_list.html` |
| Record actions drawn by hand | 3 | `templates/Word/Word_detail.html`, `templates/Word/Word_list.html`, `templates/file/files_list.html` |
| Filter form submitted from a bar | 1 | `templates/email_words/email_words.html` |
| Document viewer controls | 1 | `templates/file/full_content.html` |
| Browser confirm() dialog | 20 | `static/js/pages/analysis-batch-page.js`, `static/js/pages/analyst-categorization-page.js`, `static/js/pages/base-page.js`, `static/js/pages/categories-list-page.js`, `static/js/pages/category-words-page.js`, `static/js/pages/keyword-detail-page.js`, `static/js/pages/keywords-list-page.js`, `static/js/pages/notifications-page.js`, `static/js/pages/saved-searches-page.js`, `static/js/pages/search-advanced-page.js`, `static/js/pages/search-enhanced-page.js`, `static/js/pages/side-detail-page.js`, `static/js/pages/sides-list-page.js`, `static/js/pages/source-detail-page.js`, `static/js/pages/sources-list-page.js`, `static/js/pages/users-page.js`, `static/js/pages/word-detail-page.js`, `static/js/pages/words-list-page.js`, `templates/Operations/jobs.html`, `templates/file/file_detail.html` |
| Button state decided by the page | 7 | `static/js/pages/analysis-batch-page.js`, `static/js/pages/categories-list-page.js`, `static/js/pages/email-words-page.js`, `static/js/pages/ingestion-studio-page.js`, `static/js/pages/keywords-list-page.js`, `static/js/pages/notifications-page.js`, `static/js/pages/users-page.js` |

The component library counts 5 standardised and 2 hand-written action bars. Those are the same bars seen from two directions: the 5 templates rendering the shared toolbar are listed above, and the hand-written ones split into the file list's action bar and the full-content viewer's bar - which this audit counts as a viewer control, because that is what it is, not as an action bar to migrate.

The scripts are scanned as well as the templates, which is why the browser `confirm()` and page-local button state rows are larger here than in the component library: a dialog written in a page's JavaScript is still a dialog nobody owns.

### Candidate surfaces for the next layer

Derived from the table above, not from taste:

* **Record action surface** - the 5 declared record-scope actions, plus the 3 templates that draw record actions themselves (in a row or on a record page).
* **Specialized composites** - a viewer surface (1 template) for the document controls, and a filter surface (1 template) for the bar that submits a filter form.
* **Long-running work** - the file library's upload, analyze and archive buttons announce work that finishes later; the action model has no job semantics for them yet.

### Actions that do not fit the current abstractions

This is the agenda for the Action Registry: each row is something the model cannot say today, and the code that proves it.

| Action | Where | What the model cannot say | Evidence |
| --- | --- | --- | --- |
| edit_selected | keywords, words | The action needs a selection (scope=selection) but acts on one member of it - the first record - asking first when several are selected. Nothing in the model distinguishes 'acts on all of the selection' from 'acts on one of it'. | `static/js/pages/keywords-list-page.js`, `static/js/pages/words-list-page.js` |
| merge_duplicates | keywords | A page action whose confirmation carries runtime numbers - how many duplicates, what will be merged. `confirmation` is a translation key and nothing else, so the dialog cannot be handed values. | `static/js/pages/keywords-list-page.js` |
| export_selected | sources, sides | Declared bulk with no endpoint: the control exists and the operation does not. The model has no 'declared but not implemented' state, so the audit has to report it - and the pages still own a second refusal ('please select sources to export') that the toolbar already decides. | `static/js/pages/sources-list-page.js`, `static/js/pages/sides-list-page.js` |
| select_all / select_none | keywords, words, sources, sides | Selection *controls*, declared as page actions because that is the only vocabulary available. They produce the scope the other actions consume; the model has one word for both roles, so the pattern cannot be required of the next screen. | `templates/Sources/sources_list.html`, `templates/Side/sides_list.html` |
| apply_filters | email_words | A page action that is really a filter surface's control (it submits the filter form). Declaring it as an action would give one control two owners - the filter definition and the action definition. | `templates/email_words/email_words.html` |
| open / edit / delete (record actions) | file_library, words | Record scope, rendered inside the row today: the model can describe them, but no component owns where they are drawn. That is the Record Action Surface, which does not exist yet. | `templates/Word/Word_list.html`, `templates/file/files_list.html` |
| upload, bulk analyze, bulk archive | file_library | Long-running work: these start persistent jobs, and the model has no job semantics (RUNNING, progress, 'finished later'). The disabled-until-selected rule is also implemented by hand in this bar. | `templates/file/files_list.html` |
| export_data (email_words) | email_words | Loading is implemented by the page (button disabled, label swapped) because the action model has no RUNNING state; and the export acts on the filtered set, which is neither page nor selection scope as currently worded. | `static/js/pages/email-words-page.js` |
| viewer controls | full_content | Copy, Download, Print, Wrap, Smaller/Larger, Dark: document controls, not screen actions, and deliberately not toolbar buttons. They need a viewer surface, and the audit records them so nobody 'fixes' them into one. | `templates/file/full_content.html` |
| permission | file_library, keywords, sides, sources, words | No action names a permission, because there is no permission vocabulary for actions - only for interfaces. Until there is one, the registry cannot answer 'may this person run this?' when deciding what to render. | `core/experience/declarations.py` |
| cancel_job, reprocess | operations, file_detail | Record-scope destructive actions confirmed with a browser dialog and declared nowhere, because those screens have no contract yet. They are why the audit is produced before more migration, not after. | `templates/Operations/jobs.html`, `templates/file/file_detail.html` |
<!-- END GENERATED: action surfaces -->
