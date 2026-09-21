"""The action surface audit: what a person can do, and where it is done today.

Read-only and generated, like the rest of ``core/experience``. It answers the
question the Action Registry has to answer before it can exist: *which actions
does this product actually offer, what does each apply to, and which of them
cannot be described honestly by the model we have?*

Three measurements, none of them typed by hand:

* **The declared contract** (``declarations.py``): what somebody has described,
  and what the contract tests already verify against the screen itself.
* **The surfaces the templates still carry** - shared toolbar, hand-written
  bars, record-row actions, browser ``confirm()`` dialogs, viewer controls,
  page-local button state. Every scan is stated once and used for both the
  count and the file list, so the number and the evidence cannot disagree.
* **The gaps**: the short, curated list of actions whose behaviour the current
  model cannot say. Each entry names the code that proves it, and the test
  checks that the anchor still exists - so the list cannot quietly turn into
  opinion, and a fixed gap disappears from it instead of lingering.

Nothing here performs an action or changes a screen. The audit is the agenda
for the Action Registry, and it says out loud which screens nobody has
described yet instead of implying every screen has been designed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from core.frontend import component_audit
from core.interfaces import REGISTRY
from core.interfaces.model import NAVIGABLE_KINDS

from . import declarations
from .model import ACTION_SCOPES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = PROJECT_ROOT / "templates"
PAGES = PROJECT_ROOT / "static/js/pages"

BEGIN = "<!-- BEGIN GENERATED: action surfaces -->"
END = "<!-- END GENERATED: action surfaces -->"

#: The screens whose experience is described, and the file that serves each.
#: The contract tests keep the same mapping on purpose: one is the audit's
#: evidence pointer, the other is what stops a declaration from drifting away
#: from the screen it claims to describe.
SCREEN_TEMPLATES: Dict[str, str] = {
    "file_library": "templates/file/files_list.html",
    "keywords": "templates/Keyword/keywords_list.html",
    "words": "templates/Word/Word_list.html",
    "sources": "templates/Sources/sources_list.html",
    "sides": "templates/Side/sides_list.html",
}

#: Repeated markup that means "there is an action here". Each entry is
#: (key, what it is, pattern, where to look).
SURFACES: Tuple[Tuple[str, str, str, Tuple[Path, ...]], ...] = (
    ("toolbar_component", "Shared action toolbar",
     r"action_toolbar\(", (TEMPLATES,)),
    ("hand_written_bar", "Hand-written action bar",
     r'class="[^"]*action-bar', (TEMPLATES,)),
    ("record_row_actions", "Record actions drawn by hand",
     r'btn-action-icon|onclick="editWord\(|onclick="deleteWord\(',
     (TEMPLATES,)),
    ("filter_submit", "Filter form submitted from a bar",
     r"submit=True", (TEMPLATES,)),
    ("viewer_controls", "Document viewer controls",
     r'id="btn(Copy|Download|Print|Wrap|FontInc|FontDec)"', (TEMPLATES,)),
    ("browser_confirm", "Browser confirm() dialog",
     r"confirm\(", (TEMPLATES, PAGES)),
    ("page_local_button_state", "Button state decided by the page",
     r"\.disabled = true", (PAGES,)),
)

#: Actions the current model cannot describe honestly, each anchored to code.
#: The point of the audit is not to be reassuring: an action that does not fit
#: is how the next abstraction gets designed, and it is cheaper to name it here
#: than to widen the toolbar for it.
GAPS: Tuple[Dict[str, object], ...] = (
    {
        "what": "edit_selected",
        "where": "keywords, words",
        "cannot_say": "The action needs a selection (scope=selection) but acts "
                      "on one member of it - the first record - asking first "
                      "when several are selected. Nothing in the model "
                      "distinguishes 'acts on all of the selection' from 'acts "
                      "on one of it'.",
        "evidence": ("static/js/pages/keywords-list-page.js",
                     "static/js/pages/words-list-page.js"),
    },
    {
        "what": "merge_duplicates",
        "where": "keywords",
        "cannot_say": "A page action whose confirmation carries runtime "
                      "numbers - how many duplicates, what will be merged. "
                      "`confirmation` is a translation key and nothing else, so "
                      "the dialog cannot be handed values.",
        "evidence": ("static/js/pages/keywords-list-page.js",),
    },
    {
        "what": "export_selected",
        "where": "sources, sides",
        "cannot_say": "Declared bulk with no endpoint: the control exists and "
                      "the operation does not. The model has no 'declared but "
                      "not implemented' state, so the audit has to report it - "
                      "and the pages still own a second refusal ('please select "
                      "sources to export') that the toolbar already decides.",
        "evidence": ("static/js/pages/sources-list-page.js",
                     "static/js/pages/sides-list-page.js"),
    },
    {
        "what": "select_all / select_none",
        "where": "keywords, words, sources, sides",
        "cannot_say": "Selection *controls*, declared as page actions because "
                      "that is the only vocabulary available. They produce the "
                      "scope the other actions consume; the model has one word "
                      "for both roles, so the pattern cannot be required of the "
                      "next screen.",
        "evidence": ("templates/Sources/sources_list.html",
                     "templates/Side/sides_list.html"),
    },
    {
        "what": "apply_filters",
        "where": "email_words",
        "cannot_say": "A page action that is really a filter surface's control "
                      "(it submits the filter form). Declaring it as an action "
                      "would give one control two owners - the filter "
                      "definition and the action definition.",
        "evidence": ("templates/email_words/email_words.html",),
    },
    {
        "what": "open / edit / delete (record actions)",
        "where": "file_library, words",
        "cannot_say": "Record scope, rendered inside the row today: the model "
                      "can describe them, but no component owns where they are "
                      "drawn. That is the Record Action Surface, which does not "
                      "exist yet.",
        "evidence": ("templates/Word/Word_list.html",
                     "templates/file/files_list.html"),
    },
    {
        "what": "upload, bulk analyze, bulk archive",
        "where": "file_library",
        "cannot_say": "Long-running work: these start persistent jobs, and the "
                      "model has no job semantics (RUNNING, progress, 'finished "
                      "later'). The disabled-until-selected rule is also "
                      "implemented by hand in this bar.",
        "evidence": ("templates/file/files_list.html",),
    },
    {
        "what": "export_data (email_words)",
        "where": "email_words",
        "cannot_say": "Loading is implemented by the page (button disabled, "
                      "label swapped) because the action model has no RUNNING "
                      "state; and the export acts on the filtered set, which is "
                      "neither page nor selection scope as currently worded.",
        "evidence": ("static/js/pages/email-words-page.js",),
    },
    {
        "what": "viewer controls",
        "where": "full_content",
        "cannot_say": "Copy, Download, Print, Wrap, Smaller/Larger, Dark: "
                      "document controls, not screen actions, and deliberately "
                      "not toolbar buttons. They need a viewer surface, and "
                      "the audit records them so nobody 'fixes' them into one.",
        "evidence": ("templates/file/full_content.html",),
    },
    {
        "what": "permission",
        "where": ", ".join(sorted(declarations.DECLARED_SCREENS)),
        "cannot_say": "No action names a permission, because there is no "
                      "permission vocabulary for actions - only for interfaces. "
                      "Until there is one, the registry cannot answer 'may this "
                      "person run this?' when deciding what to render.",
        "evidence": ("core/experience/declarations.py",),
    },
    {
        "what": "cancel_job, reprocess",
        "where": "operations, file_detail",
        "cannot_say": "Record-scope destructive actions confirmed with a "
                      "browser dialog and declared nowhere, because those "
                      "screens have no contract yet. They are why the audit is "
                      "produced before more migration, not after.",
        "evidence": ("templates/Operations/jobs.html",
                     "templates/file/file_detail.html"),
    },
)


def _read(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8", errors="ignore")


def _scan(pattern: str, roots: Sequence[Path], skip_components: bool) -> List[str]:
    """Files under ``roots`` matching ``pattern``, relative to the repository."""
    expression = re.compile(pattern)
    found = []
    for root in roots:
        for path in sorted(root.rglob("*.html" if root == TEMPLATES else "*.js")):
            if skip_components and component_audit.COMPONENTS in path.parents:
                continue
            if expression.search(path.read_text(encoding="utf-8", errors="ignore")):
                found.append(str(path.relative_to(PROJECT_ROOT)))
    return sorted(set(found))


def surfaces() -> Dict[str, List[str]]:
    """Every scanned surface, as the files that carry it."""
    return {
        key: _scan(pattern, roots,
                   skip_components=bool(roots) and roots[0] == TEMPLATES)
        for key, _what, pattern, roots in SURFACES}


def declared_actions() -> List[Dict[str, object]]:
    """The declared actions, with the component that renders each today."""
    rows: List[Dict[str, object]] = []
    for interface_id in declarations.DECLARED_SCREENS:
        component = _component_for(interface_id)
        for action in declarations.actions(interface_id):
            rows.append({
                "interface": interface_id,
                "action": action.action_id,
                "label": action.source,
                "scope": action.scope,
                "permission": action.permission,
                "destructive": action.destructive,
                "confirmation": action.confirmation,
                "requires_selection": action.requires_selection,
                "endpoint": action.endpoint,
                "component": component if action.scope != "record"
                             else "record row",
            })
    return rows


def _component_for(interface_id: str) -> str:
    template = SCREEN_TEMPLATES.get(interface_id)
    if template is None:
        return "not described"
    text = _read(template)
    if "action_toolbar(" in text:
        return "ActionToolbar"
    if re.search(r'class="[^"]*action-bar', text):
        return "hand-written bar"
    return "page"


def described_interfaces() -> Tuple[str, ...]:
    return tuple(sorted(set(declarations.DECLARED_SCREENS) & set(SCREEN_TEMPLATES)))


def undescribed_interfaces() -> Tuple[str, ...]:
    return tuple(sorted({i.interface_id for i in REGISTRY
                         if i.kind in NAVIGABLE_KINDS
                         and i.interface_id not in SCREEN_TEMPLATES}))


def library_toolbar() -> Dict[str, int]:
    """The component library's own count for the action bar family.

    The two reports measure the same bars from different directions - this
    audit by what the bar *is* (an action surface or a viewer surface), the
    library by what the markup *looks like*. The numbers are reconciled in the
    document and a test fails if they stop agreeing, which is the only way two
    measurements stay useful.
    """
    row = next(item for item in component_audit.adoption()
               if item["key"] == "action_toolbar")
    return {"standardized": row["standardized"], "hand_written": row["hand_written"]}


def counts() -> Dict[str, object]:
    """Everything the report claims, computed here and nowhere else."""
    rows = declared_actions()
    scanned = surfaces()
    by_scope = {scope: sum(1 for row in rows if row["scope"] == scope)
                for scope in ACTION_SCOPES}
    navigable = [i for i in REGISTRY if i.kind in NAVIGABLE_KINDS]
    return {
        "interfaces": len(REGISTRY),
        "navigable_interfaces": len(navigable),
        "described_interfaces": len(described_interfaces()),
        "undescribed_interfaces": len(undescribed_interfaces()),
        "declared_actions": len(rows),
        "by_scope": by_scope,
        "destructive": sum(1 for row in rows if row["destructive"]),
        "with_confirmation": sum(1 for row in rows if row["confirmation"]),
        "with_permission": sum(1 for row in rows if row["permission"]),
        "with_endpoint": sum(1 for row in rows if row["endpoint"]),
        "toolbar_component": len(scanned["toolbar_component"]),
        "hand_written_bars": len(scanned["hand_written_bar"]),
        "record_action_files": len(scanned["record_row_actions"]),
        "filter_submit_files": len(scanned["filter_submit"]),
        "viewer_control_files": len(scanned["viewer_controls"]),
        "confirm_files": len(scanned["browser_confirm"]),
        "page_local_state_files": len(scanned["page_local_button_state"]),
        "library_toolbar": library_toolbar(),
        "gaps": len(GAPS),
    }


def _files(count: int) -> str:
    return f"{count} template" if count == 1 else f"{count} templates"


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> List[str]:
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join("" if cell is None else str(cell)
                                       for cell in row) + " |")
    return lines


def reference_markdown() -> str:
    """The generated block. Every figure in it comes from ``counts()``."""
    values = counts()
    scanned = surfaces()
    lines: List[str] = []

    lines += ["### What was measured", "",
              "Three sources, none of them typed by hand:", "",
              "* the **declared contract** - the actions somebody has described, "
              "which the contract tests already verify against the screen;",
              "* the **surfaces the templates carry** - the shared toolbar, the "
              "bars still written by hand, record-row actions, browser "
              "confirmation dialogs, viewer controls and page-local button "
              "state, each with the files that prove it;",
              "* the **gaps** - actions whose behaviour the current model cannot "
              "say, each anchored to code.", "",
              "This is a measurement of the product as it is, not a target.", ""]

    lines += _table(
        ("Measure", "Value"),
        (("Registered interfaces", values["interfaces"]),
         ("Navigable screens", values["navigable_interfaces"]),
         ("Screens with a described experience", values["described_interfaces"]),
         ("Screens nobody has described yet", values["undescribed_interfaces"]),
         ("Declared actions", values["declared_actions"]),
         ("- page / record / selection / bulk",
          "{} / {} / {} / {}".format(values["by_scope"]["page"],
                                     values["by_scope"]["record"],
                                     values["by_scope"]["selection"],
                                     values["by_scope"]["bulk"])),
         ("- destructive", values["destructive"]),
         ("- naming a confirmation", values["with_confirmation"]),
         ("- naming a permission", values["with_permission"]),
         ("- naming the endpoint that performs them", values["with_endpoint"]),
         ("Templates rendering the shared ActionToolbar", values["toolbar_component"]),
         ("Hand-written action bars", values["hand_written_bars"]),
         ("Templates with record actions in the row", values["record_action_files"]),
         ("Templates with a filter submit inside a bar", values["filter_submit_files"]),
         ("Templates with document viewer controls", values["viewer_control_files"]),
         ("Files still calling the browser confirm()", values["confirm_files"]),
         ("Files deciding button state by hand", values["page_local_state_files"]),
         ("Actions that do not fit the current abstractions", values["gaps"])))
    lines.append("")

    lines += ["### Declared actions", "",
              "Permission and endpoint are empty because nothing claims them "
              "yet: the permission vocabulary for actions does not exist, and "
              "no declared action names the route that performs it. Those two "
              "columns are the reason the Action Registry comes next.", ""]
    lines += _table(
        ("Interface", "Action", "Scope", "Permission", "Destructive",
         "Confirmation", "Component"),
        [(row["interface"], row["action"], row["scope"],
          row["permission"] or "-", "yes" if row["destructive"] else "-",
          row["confirmation"] or "-", row["component"])
         for row in declared_actions()])
    lines.append("")

    lines += ["### Surfaces the model does not own yet", "",
              "Each row is a scan from `SURFACES`, so the count and the files "
              "come from one statement.", ""]
    lines += _table(
        ("Surface", "Files", "Where"),
        [(_what, len(scanned[key]), ", ".join(f"`{f}`" for f in scanned[key]) or "-")
         for key, _what, _pattern, _roots in SURFACES])
    lines.append("")
    library = values["library_toolbar"]
    lines += [
        "The component library counts {} standardised and {} hand-written "
        "action bars. Those are the same bars seen from two directions: the {} "
        "templates rendering the shared toolbar are listed above, and the "
        "hand-written ones split into the file list's action bar and the "
        "full-content viewer's bar - which this audit counts as a viewer "
        "control, because that is what it is, not as an action bar to "
        "migrate.".format(library["standardized"], library["hand_written"],
                          values["toolbar_component"]),
        "",
        "The scripts are scanned as well as the templates, which is why the "
        "browser `confirm()` and page-local button state rows are larger here "
        "than in the component library: a dialog written in a page's "
        "JavaScript is still a dialog nobody owns.",
        ""]

    lines += ["### Candidate surfaces for the next layer", "",
              "Derived from the table above, not from taste:", "",
              "* **Record action surface** - the {} declared record-scope "
              "actions, plus the {} that draw record actions themselves "
              "(in a row or on a record page).".format(
                  values["by_scope"]["record"],
                  _files(values["record_action_files"])),
              "* **Specialized composites** - a viewer surface ({}) for the "
              "document controls, and a filter surface ({}) for the bar that "
              "submits a filter form.".format(
                  _files(values["viewer_control_files"]),
                  _files(values["filter_submit_files"])),
              "* **Long-running work** - the file library's upload, analyze and "
              "archive buttons announce work that finishes later; the action "
              "model has no job semantics for them yet.",
              ""]

    lines += ["### Actions that do not fit the current abstractions", "",
              "This is the agenda for the Action Registry: each row is something "
              "the model cannot say today, and the code that proves it.", ""]
    lines += _table(("Action", "Where", "What the model cannot say", "Evidence"),
                    [(gap["what"], gap["where"], gap["cannot_say"],
                      ", ".join(f"`{f}`" for f in gap["evidence"]))
                     for gap in GAPS])
    return "\n".join(lines) + "\n"


def write_document(path: str) -> None:
    with open(path, "r", encoding="utf-8") as handle:
        document = handle.read()
    if BEGIN not in document or END not in document:
        raise SystemExit(
            "the document is missing the generated block markers "
            f"({BEGIN} / {END})")
    head, rest = document.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"{head}{BEGIN}\n{reference_markdown()}{END}{tail}")


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        print("usage: python3 -m core.experience.action_audit "
              "docs/ACTION_SURFACE_AUDIT.md")
        return 2
    write_document(argv[1])
    return 0


if __name__ == "__main__":  # pragma: no cover - a command, not a library
    import sys

    raise SystemExit(main(sys.argv))
