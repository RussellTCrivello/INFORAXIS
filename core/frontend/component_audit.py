"""The shared component library, and where pages still do the work by hand.

Two questions, both answered from the repository rather than from memory:

* what components exist, what states each one implements, and what classes it
  renders - read out of the component files themselves; and
* how many templates still hand-roll that markup - counted, not estimated.

The second number is the point. "Introduce shared components" is not
verifiable on its own; "eleven templates still write their own empty state,
it was fourteen" is. Nothing here is maintained by hand: the component list
comes from the `{# component: ... #}` declarations at the top of each file in
``templates/components``, and the usage counts come from scanning the
templates.

Usage::

    python3 -m core.frontend.component_audit                    # report
    python3 -m core.frontend.component_audit docs/COMPONENT_LIBRARY.md
"""

from __future__ import annotations

import pathlib
import re
import sys
from functools import lru_cache
from typing import Dict, Iterable, List, NamedTuple

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TEMPLATES = PROJECT_ROOT / "templates"
COMPONENTS = TEMPLATES / "components"
STYLESHEETS = PROJECT_ROOT / "static/css"

BEGIN = "<!-- BEGIN GENERATED COMPONENT AUDIT -->"
END = "<!-- END GENERATED COMPONENT AUDIT -->"

#: Stylesheets INFORAXIS owns. Anything defined here is the product's own
#: vocabulary, whatever file it lands in.
PROJECT_STYLESHEETS = ("static/css",)

#: Stylesheets somebody else owns, bundled with the application. A class found
#: here is a dependency, not a decision: it is expected to be defined outside
#: this repository and it is not a violation to use it.
THIRD_PARTY_STYLESHEETS = (
    "static/css/bootstrap.min.css",
    "static/icons/bootstrap-icons.css",
)

#: The three answers a rendered class can have.
OWNED = "OWNED"
THIRD_PARTY = "THIRD_PARTY"
UNKNOWN = "UNKNOWN"

#: The states a component has to have an answer for (spec §63). A component
#: implements the states that apply to it; every state must be implemented by
#: *something*, or the state does not exist in the product.
STATES: Dict[str, str] = {
    "loading": "Work is in progress; the reader is told what is being waited for.",
    "empty": "Nothing exists here yet, and the reader is told how to start.",
    "normal": "The ordinary case: content is present and usable.",
    "filtered": "Something exists, but not under the filters applied.",
    "selected": "A row or record is chosen; actions that need a choice appear.",
    "editing": "A value is being changed, and the change is not saved yet.",
    "saving": "A change is on its way to the server.",
    "success": "The last action worked.",
    "warning": "Something needs attention but is not broken.",
    "error": "Something failed, with a next step rather than a stack trace.",
    "unauthorized": "The server refused this for this account.",
    "unavailable": "It needs something this installation does not have.",
    "archived": "Kept and readable, but out of the working set.",
}

#: The declaration a component file opens with. Parsed, so a component cannot
#: exist without saying what it is for and which states it answers.
DECLARATION = re.compile(
    r"\{#\s*component:\s*(?P<name>[\w-]+)(?P<body>.*?)#\}", re.DOTALL)
FIELD = re.compile(r"^\s*(?P<key>\w+):\s*(?P<value>.*?)(?=\n\s*\w+:|\Z)",
                   re.DOTALL | re.MULTILINE)


#: States in the vocabulary that no component implements *yet*, and the
#: component that will implement each. This is a deliberate absence list, not
#: a wish: the audit reports them as missing, a test fails when one appears or
#: disappears without the list being updated, and nothing pretends otherwise.
PLANNED_STATES: Dict[str, str] = {}


class Pattern(NamedTuple):
    """A piece of markup that pages currently write for themselves."""

    key: str
    description: str
    regex: str
    component: str


#: Markup that a shared component exists (or should exist) for. The regular
#: expressions are deliberately narrow: they match the *repeating* markup, not
#: every mention of a word.
PATTERNS: List[Pattern] = [
    Pattern("empty_state", "Hand-written empty state", r'class="empty-state"', "states"),
    Pattern("loading", "Hand-written loading indicator",
            r'(spinner-border|skeleton-loader)', "states"),
    Pattern("error", "Hand-written inline error", r'(alert-danger|error-state)', "states"),
    Pattern("table", "Hand-written table", r"<table\b", "table"),
    Pattern("pagination", "Hand-written pagination",
            r'class="[^"]*(pagination|page-navigation-bar)', "pagination"),
    Pattern("search", "Hand-written search input",
            r'(type="search"|role="search"|search-input|search-input-group)', "search_bar"),
    Pattern("filter", "Hand-written filter control",
            r'(filter-bar|filter-group|filters-panel|filter-control)', "filter_bar"),
    Pattern("confirm", "Browser confirm() dialog", r"\bconfirm\(", "confirm_dialog"),
    Pattern("badge", "Hand-written status badge", r'class="badge bg-[a-z]+', "status_badge"),
    Pattern("toolbar", "Hand-written action bar",
            r'class="action-bar|action-toolbar|btn-toolbar', "action_toolbar"),
]


class Component(NamedTuple):
    name: str
    path: str
    purpose: str
    states: List[str]
    classes: List[str]
    notes: str
    macros: List[str]


def _parse_field(body: str, key: str) -> str:
    match = re.search(rf"^\s*{key}:\s*(?P<value>.*?)(?=\n\s*\w+:|\Z)",
                      body, re.DOTALL | re.MULTILINE)
    if not match:
        return ""
    lines = [line.strip() for line in match.group("value").strip().splitlines()]
    return " ".join(line for line in lines if line)


def _split(value: str) -> List[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def components() -> Dict[str, Component]:
    """Every component file, with what it declares about itself."""
    found: Dict[str, Component] = {}
    for path in sorted(COMPONENTS.glob("*.html")):
        match = DECLARATION.search(path.read_text(errors="ignore"))
        if not match:
            # Files that predate the declaration; reported as undeclared so
            # the gap is visible instead of implied.
            found[path.stem] = Component(path.stem, str(path.relative_to(PROJECT_ROOT)),
                                         "", [], [], "no declaration", [])
            continue
        body = match.group("body")
        macros = re.findall(r"{%\s*macro\s+(\w+)\s*\(", path.read_text(errors="ignore"))
        found[match.group("name")] = Component(
            name=match.group("name"),
            path=str(path.relative_to(PROJECT_ROOT)),
            purpose=_parse_field(body, "purpose"),
            states=_split(_parse_field(body, "states")),
            classes=_split(_parse_field(body, "classes")),
            notes=_parse_field(body, "notes"),
            macros=macros,
        )
    return found


def users(pattern: Pattern) -> List[str]:
    """Templates that still hand-roll this markup."""
    expression = re.compile(pattern.regex)
    hits = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        if COMPONENTS in path.parents:
            continue
        if expression.search(path.read_text(errors="ignore")):
            hits.append(str(path.relative_to(PROJECT_ROOT)))
    return hits


def state_coverage(library: Dict[str, Component] | None = None) -> Dict[str, List[str]]:
    """Which component answers for each state in the vocabulary."""
    library = library if library is not None else components()
    coverage: Dict[str, List[str]] = {state: [] for state in STATES}
    for component in library.values():
        for state in component.states:
            coverage.setdefault(state, []).append(component.name)
    return coverage


def counts() -> Dict[str, int]:
    library = components()
    return {
        "components": len(library),
        "declared": sum(1 for c in library.values() if c.states),
        "undeclared": sum(1 for c in library.values() if not c.states),
        "states": len(STATES),
        "states_covered": sum(1 for v in state_coverage(library).values() if v),
        "states_not_yet": len(PLANNED_STATES),
        **{f"pattern_{p.key}": len(users(p)) for p in PATTERNS},
    }


class RenderedClass(NamedTuple):
    """A class a component renders, and who owns it."""

    name: str
    ownership: str
    source: str


def _classes_in_files(library: Dict[str, Component] | None = None) -> Dict[str, List[str]]:
    """The class names each component file actually renders.

    Jinja expressions are removed first: `class="badge {{ tone }}"` renders a
    class the component does not name, and the identifiers inside the
    expression are not class names at all.
    """
    rendered: Dict[str, List[str]] = {}
    for path in sorted(COMPONENTS.glob("*.html")):
        text = re.sub(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", " ",
                      path.read_text(errors="ignore"), flags=re.DOTALL)
        names: set = set()
        for value in re.findall(r"""class=["']([^"']*)["']""", text):
            for token in re.split(r"\s+", value):
                token = token.strip("{}%'\"~ .")
                if token and re.fullmatch(r"[a-zA-Z][\w-]*", token):
                    names.add(token)
        rendered[str(path.relative_to(PROJECT_ROOT))] = sorted(names)
    return rendered


def stylesheet_classes(relative: str) -> set:
    """The class names one stylesheet defines."""
    path = PROJECT_ROOT / relative
    if path.is_dir():
        names: set = set()
        for child in path.glob("*.css"):
            names |= stylesheet_classes(str(child.relative_to(PROJECT_ROOT)))
        return names
    return set(re.findall(r"\.(-?[a-zA-Z_][\w-]*)", path.read_text(errors="ignore")))


@lru_cache(maxsize=None)
def owned_classes() -> frozenset:
    """Every class INFORAXIS's own stylesheets define."""
    names: set = set()
    for relative in PROJECT_STYLESHEETS:
        names |= stylesheet_classes(relative)
    # The third-party bundles also ship classes the project uses incidentally;
    # those are still third-party, so they are removed from the owned set.
    return frozenset(names - third_party_classes())


@lru_cache(maxsize=None)
def third_party_classes() -> frozenset:
    """Every class the bundled third-party stylesheets define."""
    names: set = set()
    for relative in THIRD_PARTY_STYLESHEETS:
        names |= stylesheet_classes(relative)
    return frozenset(names)


def classify_class(name: str, declared: set | None = None) -> RenderedClass:
    """Owned, third-party, or unknown - and what says so.

    A class is OWNED when a stylesheet INFORAXIS ships defines it, or when the
    component that renders it declares it in its own `classes:` header: a
    component saying "this class is mine" is a decision, and it is visible in
    the component's declaration rather than inferred. THIRD_PARTY is an
    expected dependency (Bootstrap, Bootstrap Icons). Anything else is
    UNKNOWN, and an unknown class is how a component invents a style nobody
    defined - which is what the guardrail exists to catch.
    """
    declared = declared or set()
    if name.endswith(("-", "_")):
        # A fragment built from a variable: `file-nav--{{ variant }}`.
        prefix = name
        return RenderedClass(
            name,
            OWNED if any(c.startswith(prefix) for c in owned_classes())
            or declared and any(c.startswith(prefix) for c in declared)
            else UNKNOWN,
            "project stylesheet (built from a variable)")
    if name in owned_classes():
        return RenderedClass(name, OWNED, "project stylesheet")
    if name in third_party_classes():
        return RenderedClass(name, THIRD_PARTY,
                             "Bootstrap" if name.startswith(("bi", "col", "row"))
                             else "third-party bundle")
    if name in declared:
        return RenderedClass(name, OWNED, "component declaration")
    return RenderedClass(name, UNKNOWN, "nothing defines it")


def class_ownership() -> Dict[str, List[RenderedClass]]:
    """Every class every component renders, classified."""
    library = components()
    declared_by_file = {component.path: set(component.classes)
                        for component in library.values()}
    report: Dict[str, List[RenderedClass]] = {}
    for relative, names in _classes_in_files(library).items():
        declared = declared_by_file.get(relative, set())
        report[relative] = [classify_class(name, declared) for name in names]
    return report


def unknown_classes() -> Dict[str, List[str]]:
    """Rendered classes with no owner: the violations."""
    problems: Dict[str, List[str]] = {}
    for relative, entries in class_ownership().items():
        missing = [entry.name for entry in entries if entry.ownership == UNKNOWN]
        if missing:
            problems[relative] = missing
    return problems


def undeclared_files() -> List[str]:
    return [c.path for c in components().values() if not c.states]


def audit_block() -> str:
    """The generated part of the component library document."""
    library = components()
    coverage = state_coverage(library)
    parts: List[str] = []

    parts.append("### Components\n")
    parts.append("Read from the `{# component: … #}` declaration at the top of "
                 "each file in `templates/components/`. A file without one has "
                 "no declared purpose or states, and is listed as such.\n")
    parts.append("| Component | File | States | Macros | Purpose |")
    parts.append("| --- | --- | --- | --- | --- |")
    for name, component in sorted(library.items()):
        states = ", ".join(f"`{s}`" for s in component.states) or "— none declared —"
        macros = ", ".join(f"`{m}`" for m in component.macros) or "—"
        parts.append(f"| `{name}` | `{component.path}` | {states} | {macros} | "
                     f"{component.purpose or '—'} |")
    parts.append("")

    parts.append("### States (§63)\n")
    parts.append("Every state in the vocabulary is answered by at least one "
                 "component; a state nobody implements does not exist in the "
                 "product, however often it is referred to.\n")
    parts.append("| State | Meaning | Implemented by |")
    parts.append("| --- | --- | --- |")
    for state, meaning in STATES.items():
        owners = ", ".join(f"`{c}`" for c in coverage.get(state, []))
        if not owners:
            planned = PLANNED_STATES.get(state)
            owners = (f"**not yet** — planned for `{planned}`" if planned
                      else "**nobody**")
        parts.append(f"| `{state}` | {meaning} | {owners} |")
    parts.append("")

    parts.append("### Markup pages still write by hand\n")
    parts.append("Counted by scanning `templates/**`. These are the places a "
                 "shared component has not reached yet - the number goes down "
                 "as components are adopted, and it is the measure of this "
                 "phase rather than an impression of it.\n")
    parts.append("| Markup | Component that replaces it | Templates |")
    parts.append("| --- | --- | --- |")
    for pattern in PATTERNS:
        hits = users(pattern)
        owner = f"`{pattern.component}`" if pattern.component in library else "—"
        parts.append(f"| {pattern.description} | {owner} | {len(hits)} |")
    parts.append("")

    # ---- CSS ownership -------------------------------------------------
    ownership = class_ownership()
    totals = {OWNED: 0, THIRD_PARTY: 0, UNKNOWN: 0}
    declared_hooks: List[str] = []
    for relative, entries in sorted(ownership.items()):
        for entry in entries:
            totals[entry.ownership] += 1
            if entry.ownership == OWNED and entry.source == "component declaration":
                declared_hooks.append(f"`{entry.name}` ({relative.split('/')[-1]})")

    parts.append("### CSS ownership of the classes components render\n")
    parts.append("Every class a component renders has exactly one owner. "
                 "**OWNED** means an INFORAXIS stylesheet defines it, or the "
                 "component declares it in its own `classes:` header. "
                 "**THIRD_PARTY** means a bundled dependency defines it - "
                 "Bootstrap and Bootstrap Icons are expected dependencies, and "
                 "using them is not a finding. **UNKNOWN** means nobody does, "
                 "and an unknown class is how a component invents a style: it "
                 "fails the guardrail test rather than being reported and "
                 "forgotten.\n")
    parts.append("| Ownership | Classes |")
    parts.append("| --- | --- |")
    parts.append(f"| OWNED (INFORAXIS) | {totals[OWNED]} |")
    parts.append(f"| THIRD_PARTY (Bootstrap, Bootstrap Icons) | {totals[THIRD_PARTY]} |")
    parts.append(f"| UNKNOWN | {totals[UNKNOWN]} |")
    parts.append("")
    parts.append("Third-party stylesheets bundled with the application: " +
                 ", ".join(f"`{path}`" for path in THIRD_PARTY_STYLESHEETS) + ".")
    parts.append("")
    if declared_hooks:
        parts.append("Owned by declaration rather than by a stylesheet - the "
                     "component states these are its own hooks, and no rule "
                     "styles them (which is a decision, not an accident):\n")
        parts.append("* " + "\n* ".join(declared_hooks))
    else:
        parts.append("No component currently declares a class that no "
                     "stylesheet styles.")
    parts.append("")
    if totals[UNKNOWN]:
        parts.append("**Unknown classes (this fails the guardrail):**\n")
        for relative, names in sorted(unknown_classes().items()):
            parts.append(f"* `{relative}`: " + ", ".join(f"`{n}`" for n in names))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def splice(text: str, block: str) -> str:
    """Replace the generated section, leaving the hand-written part alone."""
    if BEGIN not in text or END not in text:
        raise SystemExit(f"the document has no generated section ({BEGIN} … {END})")
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{BEGIN}\n\n{block}\n{END}{tail}"


def main(argv: Iterable[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    block = audit_block()
    if not argv:
        print(block)
        return 0
    path = pathlib.Path(argv[0])
    path.write_text(splice(path.read_text(), block))
    print(f"regenerated the component audit in {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
