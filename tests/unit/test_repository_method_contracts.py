"""Unit: every repository method the pipeline calls must actually exist.

This closes a whole defect class, not just the two instances found. Two calls in
storage_pipeline's error-recovery fallback named methods that do not exist:

    self.db_service.paths_repo.insert_path(...)     # PathsRepository has no insert_path
    self.db_service.hashs_repo.insert_hash(...)     # HashsRepository has no insert_hash

The real methods are insert_info_paths and insert_info_hashs. Because both sat
inside an ``except`` handler, the resulting AttributeError was swallowed by the
enclosing handler, so the recovery path silently did nothing: a file whose full
processing failed left no record at all. ``hasattr`` confirmed neither name
existed, on the repository or on its base class.

Static verification is the right tool here. The fallback only runs after a
storage failure, so an integration test would have to manufacture that failure
to reach it - and the defect is invisible when it is reached, because the
exception is swallowed. Resolving the attribute names against the real classes
catches every instance, including ones not yet written.
"""

import ast
import inspect
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.services.contents_db_service import ContentDBService  # noqa: E402

#: Files whose calls into ``self.db_service.<repo>.<method>`` are checked.
SCANNED_FILES = [
    PROJECT_ROOT / "pipeline" / "storage_pipeline.py",
    PROJECT_ROOT / "database" / "services" / "contents_db_service.py",
]


def _repo_attributes():
    """Map ``db_service`` attribute name -> repository class, from the source.

    Derived from the class rather than hardcoded, so a repository added later is
    covered automatically instead of silently skipped. The whole class is
    scanned, not one method: the assignments live in _init_repositories, and
    naming a specific method made this return an empty map - which is exactly
    what test_repo_map_was_actually_discovered exists to catch.
    """
    # getsource returns the class with its module-level indentation intact,
    # which ast.parse rejects; dedent first.
    source = textwrap.dedent(inspect.getsource(ContentDBService))
    tree = ast.parse(source)
    mapping = {}
    for node in ast.walk(tree):
        # self.<attr> = <ClassName>(self.db)
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                and target.value.id == "self"):
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            continue
        mapping[target.attr] = call.func.id
    return mapping


REPO_ATTRS = _repo_attributes()


def _repository_class(class_name):
    import importlib
    import pkgutil

    package = importlib.import_module("database.database.repository")
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"database.database.repository.{module_name}")
        candidate = getattr(module, class_name, None)
        if isinstance(candidate, type):
            return candidate
    return None


def _calls_into_repos(path):
    """Yield (lineno, attr, method) for every self.db_service.<attr>.<method>(...)."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        receiver = node.func.value
        if not (isinstance(receiver, ast.Attribute) and isinstance(receiver.value, ast.Attribute)):
            continue
        if receiver.value.attr != "db_service":
            continue
        yield node.lineno, receiver.attr, method


def test_repo_map_was_actually_discovered():
    """Guard the guard: if the map came back empty the test proves nothing."""
    assert REPO_ATTRS, "no repository attributes discovered from __init__"
    assert "paths_repo" in REPO_ATTRS and "hashs_repo" in REPO_ATTRS, sorted(REPO_ATTRS)


def test_every_repository_class_resolves():
    for attr, class_name in sorted(REPO_ATTRS.items()):
        assert _repository_class(class_name) is not None, (attr, class_name)


@pytest.mark.parametrize("path", SCANNED_FILES, ids=[p.name for p in SCANNED_FILES])
def test_no_phantom_repository_methods(path):
    """Every ``db_service.<repo>.<method>()`` must name a real method."""
    assert path.exists(), path
    offenders = []
    for lineno, attr, method in _calls_into_repos(path):
        class_name = REPO_ATTRS.get(attr)
        if class_name is None:
            # Not a repository attribute (e.g. db_service.db, .transaction);
            # only repository dispatch is under test here.
            continue
        klass = _repository_class(class_name)
        if klass is None:
            offenders.append((lineno, attr, method, "class not found"))
            continue
        if not hasattr(klass, method):
            offenders.append((lineno, attr, method, class_name))
    assert not offenders, (
        f"{path.name} calls repository methods that do not exist: {offenders}. "
        "These raise AttributeError at runtime, and when the call sits inside an "
        "error handler the failure is swallowed and the operation silently "
        "does nothing."
    )


def test_the_two_known_broken_names_are_fixed():
    """Pins the specific instances that were found, by name."""
    from database.database.repository.hashs_repo import HashsRepository
    from database.database.repository.paths_repo import PathsRepository

    assert hasattr(PathsRepository, "insert_info_paths")
    assert hasattr(HashsRepository, "insert_info_hashs")
    assert not hasattr(PathsRepository, "insert_path"), (
        "insert_path has appeared; callers must use insert_info_paths"
    )
    assert not hasattr(HashsRepository, "insert_hash"), (
        "insert_hash has appeared; callers must use insert_info_hashs"
    )


def test_no_source_file_calls_the_phantom_names():
    """Textual sweep, because an AST walk alone cannot prove absence in strings."""
    for path in SCANNED_FILES:
        text = path.read_text()
        for phantom in ("paths_repo.insert_path(", "hashs_repo.insert_hash("):
            occurrences = [
                i + 1 for i, line in enumerate(text.splitlines())
                if phantom in line and not line.strip().startswith("#")
            ]
            assert not occurrences, f"{path.name}: {phantom} at lines {occurrences}"


def test_insert_info_paths_accepts_the_status_columns():
    """The fallback now records a truthful failed status; the signature must allow it."""
    from database.database.repository.paths_repo import PathsRepository

    params = inspect.signature(PathsRepository.insert_info_paths).parameters
    for name in ("processing_status", "status_detail", "attempts",
                 "file_name", "file_path", "file_size", "file_type",
                 "file_status", "file_date", "hash_id", "coordinates"):
        assert name in params, (name, list(params))


def test_insert_info_hashs_signature_matches_the_call():
    from database.database.repository.hashs_repo import HashsRepository

    params = inspect.signature(HashsRepository.insert_info_hashs).parameters
    assert list(params) == ["self", "hash_value", "source_id", "side_id"], list(params)
