"""Declared experience: the screens somebody has actually described.

Everything in this file is *verified against the product* by
``tests/unit/test_experience_contract.py``: a declared column, filter, action
or state must name a string that really appears in that interface's template,
or the test fails. That is the difference between a contract and a wish - a
declaration that has drifted from the screen is a defect, not documentation.

Screens that are not listed here get a contract derived from the registry with
``declared = False``: identity, navigation, lifecycle and help are known, and
the audit says the experience has not been described yet instead of inventing
columns and actions nobody has built.

The keys are semantic and stable (``screen.files.column.name.label``), never the
English sentence, so the wording can change without changing the key and two
identical English words can hold two different translations.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .model import (
    ActionDefinition,
    ColumnDefinition,
    FieldDefinition,
    FilterDefinition,
    HelpDefinition,
    LayoutDefinition,
    ShortcutDefinition,
    StateDefinition,
)

#: Screens whose experience has been described. Everything else is derived.
DECLARED_SCREENS: Dict[str, Dict[str, Any]] = {

    # ---------------------------------------------------------------- files
    "file_library": {
        "title": "File Library",
        "columns": (
            ("name", "File Name", "screen.files.column.name.label",
             {"sortable": True, "filterable": True}),
            ("type", "Type", "screen.files.column.type.label",
             {"filterable": True}),
            ("size", "Size", "screen.files.column.size.label",
             {"render": "bytes", "align": "end", "sortable": True}),
            ("source", "Source", "screen.files.column.source.label",
             {"filterable": True}),
            ("side", "Side", "screen.files.column.side.label",
             {"filterable": True}),
            ("status", "Status", "screen.files.column.status.label",
             {"render": "status", "filterable": True}),
            ("date", "Date", "screen.files.column.date.label",
             {"render": "date", "sortable": True}),
        ),
        "filters": (
            ("file_type", "Type", "screen.files.filter.file_type.label",
             {"control": "select"}),
            ("status", "Status", "screen.files.filter.status.label",
             {"control": "select"}),
            ("source", "Source", "screen.files.filter.source.label",
             {"control": "select"}),
            ("side", "Side", "screen.files.filter.side.label",
             {"control": "select"}),
        ),
        "actions": (
            ("upload", "Upload Files", "action.files.upload.label",
             {"scope": "page"}),
            ("read", "Read", "action.files.read.label",
             {"scope": "record"}),
            ("delete", "Delete", "action.files.delete.label",
             {"scope": "record", "destructive": True,
              "confirmation": "action.files.delete.confirm"}),
        ),
        "states": (
            ("empty", "No files found.", "state.files.empty.title"),
        ),
        "help": ("files", "File Library",
                 "help.files.title", "help.files.summary"),
    },

    # ------------------------------------------------------------- keywords
    "keywords": {
        "title": "Keyword Intelligence",
        "columns": (
            ("keyword", "Keyword", "screen.keywords.column.keyword.label",
             {"sortable": True, "filterable": True}),
            ("usage", "Usage", "screen.keywords.column.usage.label",
             {"render": "number", "align": "end", "sortable": True}),
            ("status", "Status", "screen.keywords.column.status.label",
             {"render": "status", "filterable": True}),
            ("category", "Category", "screen.keywords.column.category.label",
             {"filterable": True}),
        ),
        "filters": (
            ("status", "Status", "screen.keywords.filter.status.label",
             {"control": "select"}),
            ("sort", "Sort By", "screen.keywords.filter.sort.label",
             {"control": "select"}),
        ),
        "actions": (
            ("update", "Update Keywords", "action.keywords.update.label",
             {"scope": "page"}),
            ("bulk_delete", "Delete Selected",
             "action.keywords.bulk_delete.label",
             {"scope": "bulk", "requires_selection": True, "destructive": True,
              "confirmation": "action.keywords.bulk_delete.confirm"}),
        ),
        "states": (
            ("empty", "No keywords found.", "state.keywords.empty.title"),
        ),
        "help": ("keywords", "Keyword Intelligence",
                 "help.keywords.title", "help.keywords.summary"),
    },

    # -------------------------------------------------------------- sources
    # The reference pair for the action toolbar. These are the actions the bar
    # offers, described and not performed: `select_all`/`select_none` act on the
    # page, the other two act on the selection and therefore may not be usable
    # until a scope exists. No permission is claimed here - INFORAXIS decides
    # authorisation server-side from the account's role, and a permission
    # vocabulary that does not exist yet would be an invention. The execution
    # reference (handler, endpoint) is the page's, not the definition's.
    "sources": {
        "title": "Sources",
        "actions": (
            ("select_all", "Select All", "action.sources.select_all.label",
             {"scope": "page"}),
            ("select_none", "Select None", "action.sources.select_none.label",
             {"scope": "page"}),
            ("export_selected", "Export Selected",
             "action.sources.export_selected.label",
             {"scope": "bulk", "requires_selection": True}),
            ("edit_selected", "Edit Selected", "action.sources.edit_selected.label",
             {"scope": "bulk", "requires_selection": True}),
        ),
        "states": (
            ("empty", "No sources yet.", "state.sources.empty.title"),
        ),
        "help": ("sources", "Sources", "help.sources.title", "help.sources.summary"),
    },

    # ---------------------------------------------------------------- sides
    "sides": {
        "title": "Sides",
        "actions": (
            ("select_all", "Select All", "action.sides.select_all.label",
             {"scope": "page"}),
            ("select_none", "Select None", "action.sides.select_none.label",
             {"scope": "page"}),
            ("export_selected", "Export Selected",
             "action.sides.export_selected.label",
             {"scope": "bulk", "requires_selection": True}),
            ("edit_selected", "Edit Selected", "action.sides.edit_selected.label",
             {"scope": "bulk", "requires_selection": True}),
        ),
        "states": (
            ("empty", "No sides yet.", "state.sides.empty.title"),
        ),
        "help": ("sides", "Sides", "help.sides.title", "help.sides.summary"),
    },

    # ---------------------------------------------------------------- words
    "words": {
        "title": "Word Index",
        "columns": (
            ("word", "Word", "screen.words.column.word.label",
             {"sortable": True, "filterable": True}),
            ("usage", "Usage Count", "screen.words.column.usage.label",
             {"render": "number", "align": "end", "sortable": True}),
            ("status", "Status", "screen.words.column.status.label",
             {"render": "status"}),
        ),
        "actions": (
            ("bulk_edit", "Edit Selected", "action.words.bulk_edit.label",
             {"scope": "bulk", "requires_selection": True}),
            ("bulk_delete", "Delete Selected",
             "action.words.bulk_delete.label",
             {"scope": "bulk", "requires_selection": True, "destructive": True,
              "confirmation": "action.words.bulk_delete.confirm"}),
        ),
        "states": (
            ("empty", "No words found.", "state.words.empty.title"),
        ),
    },
}


def columns(interface_id: str) -> Tuple[ColumnDefinition, ...]:
    entries = DECLARED_SCREENS.get(interface_id, {}).get("columns", ())
    return tuple(
        ColumnDefinition(column_id=column_id, label_key=key, source=source,
                         **options)
        for column_id, source, key, options in entries
    )


def filters(interface_id: str) -> Tuple[FilterDefinition, ...]:
    entries = DECLARED_SCREENS.get(interface_id, {}).get("filters", ())
    return tuple(
        FilterDefinition(filter_id=filter_id, label_key=key, source=source,
                         **options)
        for filter_id, source, key, options in entries
    )


def actions(interface_id: str) -> Tuple[ActionDefinition, ...]:
    entries = DECLARED_SCREENS.get(interface_id, {}).get("actions", ())
    return tuple(
        ActionDefinition(action_id=action_id, label_key=key, source=source,
                         **options)
        for action_id, source, key, options in entries
    )


def states(interface_id: str, prefix: str) -> Tuple[StateDefinition, ...]:
    entries = DECLARED_SCREENS.get(interface_id, {}).get("states", ())
    return tuple(
        StateDefinition(state=state, title_key=key, source=source,
                        message_key=f"{key.rsplit('.', 1)[0]}.message")
        for state, source, key in entries
    )


def help_definition(interface_id: str) -> HelpDefinition | None:
    entry = DECLARED_SCREENS.get(interface_id, {}).get("help")
    if not entry:
        return None
    topic, source, title_key, summary_key = entry
    return HelpDefinition(topic=topic, title_key=title_key, source=source,
                          summary_key=summary_key)


def title(interface_id: str) -> str | None:
    return DECLARED_SCREENS.get(interface_id, {}).get("title")


def fields(interface_id: str) -> Tuple[FieldDefinition, ...]:
    entries = DECLARED_SCREENS.get(interface_id, {}).get("fields", ())
    return tuple(
        FieldDefinition(field_id=field_id, label_key=key, source=source,
                        **options)
        for field_id, source, key, options in entries
    )


def shortcuts(interface_id: str) -> Tuple[ShortcutDefinition, ...]:
    entries = DECLARED_SCREENS.get(interface_id, {}).get("shortcuts", ())
    return tuple(
        ShortcutDefinition(shortcut=shortcut, action_key=key)
        for shortcut, key in entries
    )


def layout(interface_id: str) -> LayoutDefinition:
    return LayoutDefinition()


__all__ = [
    "DECLARED_SCREENS",
    "actions",
    "columns",
    "fields",
    "filters",
    "help_definition",
    "layout",
    "shortcuts",
    "states",
    "title",
]
