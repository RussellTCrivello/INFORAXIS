# Browsing between files (Previous / Next)

## What it is for

Reviewing a folder of documents means opening one file after another. Until
now the File Detail page and the Reader (full content) page could each show
only one file, so moving on meant going back to the library list, finding the
place again, and opening the following row.

Both pages now carry a Previous / Next control:

```
[ < Previous ]   File 12 of 3 481   [ Next > ]
```

* the buttons name the file they lead to (hover tooltip) and can be driven
  from the keyboard: `Alt+Left` / `Alt+Right`;
* the counter says where the file sits in the view that is being browsed;
* at the boundary of that view the button is shown disabled, so "there is no
  next file" is visibly different from "there is no control".

## What "next file" means

A neighbour is only defined relative to a set, and this feature deliberately
uses **the set the library list was showing**, not "all files" and not "the
files currently rendered in the browser":

* open a file from `/files?source=7&search=passport` and Previous/Next walk
  that filtered list, in that order, across page boundaries;
* open a file from a bookmark, a link or a search result and no filter is
  invented: the whole library is browsed, newest first;
* the order is the list's order, defined once in
  `Api/services/file_navigation.py` (`ORDER_BY`) and used by both the list
  query and the navigation queries, including a tie-break on `p.id` so two
  files ingested in the same second cannot swap places between two requests.

The last two paragraphs are the whole reason the filters travel in the URL.

### The `nav_` namespace

The browsing context is carried as `nav_<field>` query parameters:
`nav_search`, `nav_source`, `nav_side`, `nav_status`, `nav_file_type`,
`nav_date_from`, `nav_date_to`, `nav_size_min`, `nav_size_max`.

The prefix is not decoration. On the library list `search` filters **file
names**; on the detail page `search`/`q` mean **find this text inside the
document** and drive the search box and highlighter. Sharing one name would
silently change what the in-document search does as soon as a filter was
carried over. Prefixed parameters cannot collide with page state, and page
state (`q`, `search`, `case_sensitive`, `whole_word`, `per_page`) travels
alongside them so a search term or a page size is not lost when stepping to
the next file.

The list validates filters (`Api/services/file_navigation.build_library_filters`)
and the navigation context reuses the *same* validation. A filter the list
would ignore (an unparseable date, an unknown status, a reversed range) is
never silently applied by the navigation controls either, and the values that
go back into links are the normalised ones.

## How it is implemented

| Piece | Where |
|---|---|
| Context validation, ordering, neighbours, links | `Api/services/file_navigation.py` |
| Filter validation shared with the list | `build_library_filters()` in the same module |
| List route (filters, counters, links) | `Api/blueprints/files.py::files_list` |
| Detail / Reader routes | `Api/blueprints/files.py::file_detail`, `file_full_content` |
| Control markup | `templates/components/file_nav.html` |
| Styles | `static/css/file-nav.css` |
| Keyboard shortcuts | `static/js/file-nav.js` |

Neighbours are found with a keyset (seek) query - one row either side of the
current file, `ORDER BY ... LIMIT 1` - never by loading the list and searching
in Python, because the library is expected to hold millions of files and this
runs on every page view. The position counter is a single aggregate over the
filtered set (the same `COUNT` the list page already performs).

Two details worth knowing before changing this code:

* the Previous direction is selected with the order **reversed**
  (`PREVIOUS_ORDER_BY`): the neighbour before a file is the *closest* row in
  that direction, which is the last row of the set in the list's order. Order
  the before-set by the list order and the Previous button jumps to the top of
  the list;
* the position aggregate binds the keyset parameters **before** the filter
  parameters, because the predicate sits in the `SELECT` list of that
  statement; positional parameters are bound in the order they appear in the
  statement text.

Both surfaces share one control and link to each other with the view intact
("View Full Content" and "← Details" keep the context), so switching between
the two views of a file does not reset where the operator is.

## Relationship to the older modal control

The file library's quick-look modal has its own Previous/Next
(`static/js/modules/file-operations/file-navigation.js`, styles `.file-nav-btn`
/ `.file-nav-counter` in `static/css/fmas.css`). It walks the rows already
rendered in the browser and wraps around at the ends. It is unrelated to this
control - different surface, different set definition - and was left as it is;
the new classes are deliberately distinct.

## Verified

`tests/unit/test_file_navigation.py` (context validation, `nav_` isolation,
keyset predicates, the reversed Previous order, link parameters) and
`tests/integration/test_file_navigation_pages.py` (real routes on a real
database: stepping visits exactly the list order including the tie-break,
boundaries render disabled, the position counter, a filtered view stays
filtered, a file outside the view still renders, the reader shares the
control) - 42 tests.

## Not covered (deliberate)

* **Search results keep their own order.** A file opened from the global
  search results page browses the whole library, not the ranked result list:
  reproducing the ranking for neighbouring rows is a search-system change, not
  a navigation one. The search page therefore does not pass a context.
* **The undated-file branch** of the keyset predicate cannot be reached with
  the current schema (`paths.date_creation` is `NOT NULL`, m0001). It is
  pinned by unit tests only.
* Translation catalogues (`translations/messages.pot` and the per-language
  files) were not regenerated; the new strings fall back to English, as any
  newly added string does until the extraction script is next run.
