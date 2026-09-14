"""Integration: identical large files must deduplicate end to end (HASH-01).

Runs the real ``StoragePipeline._store_file_sync`` against a disposable
PostgreSQL database. Before HASH-01, ``Metadata['hash']`` for a file at or
above the inline-hash threshold was ``sha256(path|size|mtime)``; the pipeline
accepted it as the content identity, so two byte-identical large files at
different paths were stored as two distinct pieces of content.

The inline threshold is lowered so the deferred path is exercised without
writing 100 MB fixtures.
"""

import datetime
import os
import sys
from pathlib import Path

import psycopg2
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.integration

import core.file_utils as file_utils  # noqa: E402
from core.file_utils import create_standardized_result, get_standardized_metadata  # noqa: E402
from core.hashing import hash_file, is_valid_digest  # noqa: E402


@pytest.fixture
def force_deferred_hashing(monkeypatch):
    """Make small fixtures take the large-file (deferred) hashing path."""
    monkeypatch.setattr(file_utils, "HASH_INLINE_MAX_BYTES", 8)


@pytest.fixture
def conn(pg_db):
    c = psycopg2.connect(
        host=pg_db["host"], port=pg_db["port"], user=pg_db["user"],
        password=pg_db["password"], dbname=pg_db["database"],
    )
    yield c
    c.rollback()
    c.close()


@pytest.fixture
def source_side(conn):
    today = datetime.date.today()
    tag = os.getpid()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sides (name, importance, date_creation)"
            " VALUES (%s, 0.5, %s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name"
            " RETURNING id",
            (f"_hash01_side_{tag}", today),
        )
        side_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO sources (name, job, importance, country, date_creation)"
            " VALUES (%s, 'test', 0.5, 'test', %s) ON CONFLICT (name) DO NOTHING"
            " RETURNING id",
            (f"_hash01_source_{tag}", today),
        )
        row = cur.fetchone()
        source_id = row[0] if row else None
        if source_id is None:
            cur.execute(
                "SELECT id FROM sources WHERE name = %s", (f"_hash01_source_{tag}",)
            )
            source_id = cur.fetchone()[0]
    conn.commit()
    return f"_hash01_source_{tag}", f"_hash01_side_{tag}", source_id, side_id


def store(pipeline, path: Path, source_name, side_name):
    """Push one file through the real storage pipeline."""
    metadata = get_standardized_metadata(str(path))
    file_info = {
        "path": str(path),
        "name": path.name,
        "extension": path.suffix.lower(),
        "type": "FILE",
        "size": path.stat().st_size,
    }
    result = create_standardized_result(str(path), {"content": path.read_text()}, 0.0)
    # Prove the producer emitted the sentinel, not a digest.
    assert metadata["hash"] == file_utils.HASH_DEFERRED_SENTINEL
    assert not is_valid_digest(metadata["hash"])
    return pipeline._store_file_sync(
        file_info, result, source_name=source_name, side_name=side_name
    )


def test_identical_large_files_share_one_content_identity(
    pg_db, conn, source_side, tmp_path, force_deferred_hashing
):
    from pipeline.storage_pipeline import StoragePipeline

    source_name, side_name, source_id, side_id = source_side

    first = tmp_path / "alpha" / "report.txt"
    second = tmp_path / "beta" / "renamed-report.txt"
    for path in (first, second):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("identical payload for deduplication check", encoding="utf-8")

    # Sanity: the files are byte-identical and above the (lowered) threshold.
    assert hash_file(str(first)) == hash_file(str(second))

    pipeline = StoragePipeline()
    first_id = store(pipeline, first, source_name, side_name)
    second_id = store(pipeline, second, source_name, side_name)
    assert first_id, "first file was not stored"
    assert second_id, "second file was not stored"

    # Documented dedup semantics (DB-04): a duplicate does not create a second
    # record, it resolves to the existing one.
    assert second_id == first_id, (
        f"identical content was stored twice (paths {first_id} and {second_id})"
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT h.hash, COUNT(p.id) AS copies
            FROM hashs h
            JOIN paths p ON p.hash_id = h.id
            WHERE h.source_id = %s AND h.side_id = %s
            GROUP BY h.hash
            """,
            (source_id, side_id),
        )
        rows = cur.fetchall()

    # Exactly one content identity for the whole source/side.
    assert len(rows) == 1, f"expected one identity, got {rows}"
    stored_hash, _copies = rows[0]
    assert stored_hash == hash_file(str(first)), (
        "the stored identity must be the real content hash, "
        "not a path/mtime-derived value"
    )
    assert is_valid_digest(stored_hash)
