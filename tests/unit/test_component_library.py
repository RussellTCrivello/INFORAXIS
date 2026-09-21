"""Unit: the shared components keep their contract.

The library is only worth having if the components stay predictable:

* every component says what it is for and which states it answers;
* the state vocabulary is complete - a state nobody implements is named as
  *not yet*, with the component that will own it, rather than implied;
* a component renders the stylesheets' own vocabulary and invents no styles;
* a component renders what it is given - no queries, no authorization, no
  deciding which state is true;
* an error state written for a reader never carries a stack trace, a path or
  a query (spec §38/§76);
* the document and the components cannot drift apart.

These are the rules from `docs/COMPONENT_LIBRARY.md`, as tests.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from core.frontend.component_audit import (
    COMPONENTS,
    PLANNED_STATES,
    PROJECT_ROOT,
    STATES,
    audit_block,
    components,
    state_coverage,
    undeclared_files,
    unknown_classes,
)

LIBRARY_DOC = PROJECT_ROOT / "docs/COMPONENT_LIBRARY.md"

#: Class names a component renders that no stylesheet defines, on purpose:
#: structural hooks used by scripts, and the Bootstrap Icons vocabulary the
#: bundled icon font supplies. The list is a ratchet - a new unstyleable class
#: has to be added here, which means somebody decided it was meant to be there.
UNSTYLED_HOOKS = {
    "sidebar-nav-badge",
    "file-nav__text",
    "cursor-pagination-container",
}

#: Things a component must never do: read the database, take a decision the
#: server should take, or reach past its inputs.
FORBIDDEN = (
    ".query(", "db.session", "session[", "current_app", "requests.",
    "sqlalchemy", "get_interface(", "interface_registry(", "is_interface_enabled(",
    "has_permission", "check_permission",
)


def _component_texts():
    for path in sorted(COMPONENTS.glob("*.html")):
        yield path.name, path.read_text(errors="ignore")


def _renderable(text: str) -> str:
    """The component's markup, without its own prose.

    A component is allowed to describe a call it must not make - that is how
    the rule is written down in the file. Only what actually renders counts.
    """
    text = re.sub(r"\{#.*?#\}", " ", text, flags=re.DOTALL)
    return re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)


class TestEveryComponentDeclaresItself:
    def test_no_component_file_is_undeclared(self):
        assert undeclared_files() == [], (
            "a file in templates/components/ has no `{# component: … #}` "
            "declaration, so its purpose and states are unknown")

    def test_declared_states_are_from_the_vocabulary(self):
        for name, component in components().items():
            for state in component.states:
                assert state in STATES, f"{name} declares an unknown state: {state}"

    def test_every_component_says_what_it_is_for(self):
        for name, component in components().items():
            assert component.purpose, f"{name} does not say what it is for"


class TestTheStateVocabularyIsComplete:
    def test_the_vocabulary_is_the_thirteen_states(self):
        assert len(STATES) == 13, "the §63 vocabulary is thirteen states"

    def test_a_state_is_either_implemented_or_named_as_not_yet(self):
        covered = {state for state, owners in state_coverage().items() if owners}
        missing = set(STATES) - covered
        assert missing == set(PLANNED_STATES), (
            "the states no component implements must be exactly the ones this "
            "project has declared it still owes; if one has just been built, "
            "remove it from PLANNED_STATES; if one has gone missing, that is "
            "the regression. missing=" + repr(sorted(missing)))

    def test_each_planned_state_is_a_real_state(self):
        for state in PLANNED_STATES:
            assert state in STATES, state

    def test_the_document_calls_them_not_yet_rather_than_implying_coverage(self):
        text = LIBRARY_DOC.read_text()
        for state in PLANNED_STATES:
            assert f"`{state}`" in text
        assert "not yet" in text


class TestComponentsArePresentationOnly:
    def test_no_component_reads_the_database_or_decides_access(self):
        offenders = []
        for name, text in _component_texts():
            for needle in FORBIDDEN:
                if needle in _renderable(text):
                    offenders.append(f"{name}: {needle}")
        assert offenders == [], (
            "components render what they are given; these reach past their "
            "inputs:\n  " + "\n  ".join(offenders))

    def test_no_component_names_a_product_interface(self):
        from core.interfaces import REGISTRY

        offenders = []
        for name, text in _component_texts():
            for interface in REGISTRY:
                if f"'{interface.interface_id}'" in text:
                    offenders.append(f"{name}: {interface.interface_id}")
        assert offenders == [], offenders

    def test_the_error_state_never_renders_an_internal(self):
        text = (COMPONENTS / "states.html").read_text()
        for leak in ("str(e)", "str(exc)", "traceback", ".query", "sql",
                     "__class__", "repr("):
            assert leak not in text, (
                "the error state is written for a reader; it must not be able "
                f"to render internals ({leak})")

    def test_a_failure_is_announced_and_a_wait_is_polite(self):
        text = (COMPONENTS / "states.html").read_text()
        assert "role='alert'" in text or 'role="alert"' in text
        assert "role='status'" in text or 'role="status"' in text
        # error and unauthorized are `alert`; empty and loading are `status`.
        assert re.search(r"state_panel\('error'.*role='alert'", text, re.DOTALL)
        assert re.search(r"state_panel\('unauthorized'.*role='alert'", text, re.DOTALL)
        assert re.search(r"state_panel\('loading'.*role='status'", text, re.DOTALL)


class TestClassesStayInTheDesignSystem:
    def test_no_component_invents_a_style(self):
        problems = unknown_classes()
        cleaned = {
            path: [name for name in names
                   if not name.startswith("bi") and name not in UNSTYLED_HOOKS]
            for path, names in problems.items()
        }
        cleaned = {path: names for path, names in cleaned.items() if names}
        assert cleaned == {}, (
            "these classes are rendered by a component but no stylesheet "
            "defines them:\n  " + repr(cleaned))

    def test_the_unstyled_hooks_are_still_real(self):
        """A hook that has been renamed or removed must leave this list."""
        rendered = set()
        for _, text in _component_texts():
            rendered.update(re.findall(r'class="([^"]*)"', text))
        rendered = " ".join(rendered)
        for hook in UNSTYLED_HOOKS:
            assert hook in rendered, (
                f"{hook} is in the ratchet list but no longer rendered")


class TestTheDocumentCannotDrift:
    def test_the_generated_section_matches_the_components(self):
        text = LIBRARY_DOC.read_text()
        assert "<!-- BEGIN GENERATED COMPONENT AUDIT -->" in text
        start = text.index("<!-- BEGIN GENERATED COMPONENT AUDIT -->")
        end = text.index("<!-- END GENERATED COMPONENT AUDIT -->")
        generated = text[start:end].split("\n", 1)[1].strip()
        assert generated == audit_block().strip(), (
            "docs/COMPONENT_LIBRARY.md is out of date with the components; "
            "regenerate with `python3 -m core.frontend.component_audit "
            "docs/COMPONENT_LIBRARY.md`")

    def test_the_document_states_the_rules(self):
        text = LIBRARY_DOC.read_text()
        assert "Presentation only" in text
        assert "not a redesign" in text


class TestAdoption:
    """The library is used, and the hand-written count is the measure."""

    def test_the_migrated_pages_use_the_component(self):
        migrated = [
            "templates/Keyword/keywords_list.html",
            "templates/Word/Word_list.html",
            "templates/file/files_list.html",
        ]
        for relative in migrated:
            text = (PROJECT_ROOT / relative).read_text()
            assert "components/states.html" in text, (
                f"{relative} still writes its own empty state")
            assert 'class="empty-state"' not in text, relative

    def test_the_audit_counts_the_hand_written_markup(self):
        """The measure of this phase is a number, not an impression."""
        from core.frontend.component_audit import counts, users

        assert counts()["pattern_empty_state"] == len(users(
            next(p for p in __import__(
                "core.frontend.component_audit", fromlist=["PATTERNS"]
            ).PATTERNS if p.key == "empty_state")))
        assert counts()["pattern_empty_state"] < 7, (
            "adoption has not started; the baseline was seven templates")
        assert counts()["pattern_empty_state"] == 4, (
            "three of the seven empty states moved onto the component; this "
            "number is the measure of the phase, so it is pinned rather than "
            "admired")
