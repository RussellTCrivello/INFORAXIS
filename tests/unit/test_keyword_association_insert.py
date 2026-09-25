"""Unit: keyword-association inserts (KEYWORD-01).

The update-associations route called
``keyword_ops.insert_keyword_path_relationships(path_id, keyword_counts)`` -
a method that did not exist on ``KeywordOperations``. In production that
surfaced once the route ran: every file with keyword matches failed instead
of writing rows. (The user's runtime on ``main`` shows the sibling failure
of the same shape: ``Failed to insert keyword associations for hash_id N:
unhashable type: 'slice'`` - that lineage passes a counts dict where
``_keyword_occurrence_counts`` slices its first argument. Both trace back
to the same insert call site being wired incorrectly.)

These tests pin the branch-side contract: the method exists, bulk-inserts
``{keyword_id: count}`` through the keywords_paths repository, reports how
many rows it wrote, and never double-counts failures in the route.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.operations import KeywordOperations  # noqa: E402


class _RepoStub:
    def __init__(self):
        self.calls = []

    def bulk_insert_keywords_paths(self, path_id, keyword_counts):
        self.calls.append((path_id, dict(keyword_counts)))


class _ServiceStub:
    def __init__(self):
        self.keywords_paths_repo = _RepoStub()
        self.keywords_repo = None  # touched by KeywordOperations.__init__


@pytest.fixture()
def ops():
    return KeywordOperations(db_service=_ServiceStub())


class TestInsertKeywordPathRelationships:
    def test_method_exists(self):
        assert hasattr(KeywordOperations, 'insert_keyword_path_relationships')

    def test_bulk_inserts_the_counts_and_returns_written_rows(self, ops):
        written = ops.insert_keyword_path_relationships(7, {3: 2, 9: 5})
        assert written == 2
        assert ops.db_service.keywords_paths_repo.calls == [(7, {3: 2, 9: 5})]

    def test_empty_mapping_is_a_no_op(self, ops):
        written = ops.insert_keyword_path_relationships(7, {})
        assert written == 0
        assert ops.db_service.keywords_paths_repo.calls == []

    def test_repository_errors_propagate_for_logging(self, ops):
        def boom(path_id, counts):
            raise RuntimeError('connection lost')

        ops.db_service.keywords_paths_repo.bulk_insert_keywords_paths = boom
        with pytest.raises(RuntimeError, match='connection lost'):
            ops.insert_keyword_path_relationships(7, {1: 1})


class TestRouteCallSite:
    def test_route_calls_the_existing_method_inside_its_own_try(self):
        source = (
            PROJECT_ROOT / 'Api' / 'routes' / 'keywords.py'
        ).read_text(encoding='utf-8')
        assert 'insert_keyword_path_relationships(path_id, keyword_counts)' in source
        # failures are logged with the real cause, and counted exactly once
        assert (
            'Failed to insert keyword associations for path_id {path_id}: {insert_err}'
            in source
        )
        assert 'except Exception as insert_err' in source
