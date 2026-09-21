"""What the Experience Contract refuses to be.

A configuration layer that can hold anything eventually holds logic, and then
the product has a second, invisible implementation of its own behaviour. These
checks are the boundary: they run over every definition the application builds,
and the tests fail the build when a contract crosses it.

The forbidden list is deliberately about *mechanism*, not vocabulary. A screen
may be called "SQL console" and it is still fine; a contract that carries
``SELECT``, an import, a shell command or a call is not - it is describing work
that belongs in a service, and no amount of validation makes it safe to run
from a configuration file.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from .model import (
    ExperienceContract,
    check_placeholders,
    placeholders,
)

#: Mechanisms a declarative layer must never carry. Each pattern has a
#: *mechanism* in it - a call, a statement, an operator - and not merely a word:
#: a screen may legitimately be called "Import Center" or offer an action whose
#: label is "Update Selected", and the check has to tell the difference between
#: a name and something that would execute.
FORBIDDEN_MECHANISMS: Tuple[str, ...] = (
    "select(", "insert(", "execute(", "exec(",
    "__import__", "require(", "importlib",
    "eval(", "lambda ", "function(", "=>",
    "subprocess", "os.system", "popen(", "open(", "shutil.",
    "smtplib", "socket.", "requests.",
)

#: SQL as a statement, not as a word: `SELECT ... FROM`, `DELETE FROM ...`.
SQL_STATEMENT = re.compile(
    r"\b(select|insert|update|delete)\b[^;\n]{0,40}?"
    r"\b(from|into|table|set|where)\b", re.IGNORECASE)

#: Text that suggests an authorisation decision is being made here.
FORBIDDEN_AUTHORITY: Tuple[str, ...] = (
    "has_permission(", "check_permission(", "is_authorized", "authorize(",
    "current_user.", "session[",
)




def _strings(value, path="") -> Iterable[Tuple[str, str]]:
    """Every string inside a definition, with where it was found."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _strings(item, f"{path}[{index}]")


def check_declarative(payload, what: str = "contract") -> List[str]:
    """Mechanisms found inside a declarative definition."""
    problems = []
    for path, text in _strings(payload):
        lowered = text.lower()
        for needle in FORBIDDEN_MECHANISMS:
            if needle in lowered:
                problems.append(f"{what}: {path} carries {needle!r}")
        for needle in FORBIDDEN_AUTHORITY:
            if needle in lowered:
                problems.append(
                    f"{what}: {path} appears to decide access itself "
                    f"({needle!r}); authorisation stays in core/security")
        if SQL_STATEMENT.search(text):
            problems.append(f"{what}: {path} looks like SQL")
    return problems


def check_translations(contract: ExperienceContract) -> List[str]:
    """Translation keys that repeat with two different source strings.

    Two screens may need the same key - that is the point of a shared key - but
    if they disagree about what it says, one of them is wrong and a translator
    would be asked to translate two different things under one name.
    """
    problems = []
    seen: Dict[str, str] = {}
    for entry in contract.screen.translations:
        previous = seen.get(entry.key)
        if previous is not None and previous != entry.source:
            problems.append(
                f"{contract.interface_id}: key {entry.key} holds two source "
                f"strings ({previous!r} and {entry.source!r})")
        seen[entry.key] = entry.source
    return problems


def check_contract(contract: ExperienceContract) -> List[str]:
    """Everything wrong with one contract, in the reader's terms."""
    problems = []
    problems += check_declarative(contract.to_dict(), contract.interface_id)
    problems += check_translations(contract)

    # A destructive action without a confirmation cannot be presented safely.
    for action in contract.screen.actions:
        if action.destructive and not action.confirmation:
            problems.append(
                f"{contract.interface_id}: action {action.action_id} destroys "
                "data and declares no confirmation")
        if action.scope == "bulk" and not action.requires_selection:
            problems.append(
                f"{contract.interface_id}: bulk action {action.action_id} does "
                "not require a selection, so it cannot show its scope")

    # A screen with declared configuration must describe what it shows when
    # there is nothing to show.
    if contract.screen.declared and not contract.screen.states:
        problems.append(
            f"{contract.interface_id}: declared screen describes no state "
            "(an empty list is the state a reader meets first)")
    return problems


def check_all() -> List[str]:
    """Every contract in the application."""
    from .contract import contracts

    problems: List[str] = []
    for item in contracts():
        problems += check_contract(item)
    return problems


def check_translation_edit(source: str, translation: str) -> List[str]:
    """Whether a translation may be saved, and why not.

    This is the check the Translation Studio runs before accepting an edit:
    placeholders must survive. Wording is the translator's business.
    """
    problems = list(check_placeholders(source, translation))
    if not translation.strip():
        problems.append("translation is empty")
    if translation.count("{") != translation.count("}"):
        # Already reported as unbalanced braces; kept separate so the studio can
        # point at the editor rather than the placeholder list.
        pass
    if "{" in translation and not placeholders(source) and not problems:
        problems.append("translation adds a placeholder the source does not have")
    return problems


__all__ = [
    "FORBIDDEN_AUTHORITY",
    "FORBIDDEN_MECHANISMS",
    "check_all",
    "check_contract",
    "check_declarative",
    "check_translation_edit",
    "check_translations",
]
