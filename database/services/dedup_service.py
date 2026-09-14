"""Deduplication service (DB-04) - single authoritative implementation.

Semantic model (documented in docs/DATABASE.md):

    identity = (content_hash, source_id, side_id)

A stored file is a **duplicate** if and only if a row in ``hashs`` with the
same ``(hash, source_id, side_id)`` exists **and has at least one live
``paths`` row** referencing it.  Three older competing duplicate checks were
removed; every caller must go through this service.

Concurrency is protected by the UNIQUE constraint on
``hashs (hash, source_id, side_id)`` plus ``ON CONFLICT ... DO NOTHING``
insert semantics, so two workers ingesting identical content cannot create
two hash rows.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


class DeduplicationService:
    """All duplicate detection and hash registration flows through here."""

    def __init__(self, connection_factory):
        self._connection_factory = connection_factory

    def _conn(self):
        return self._connection_factory()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def find_live_path(
        self, content_hash: str, source_id: int, side_id: int
    ) -> Optional[int]:
        """Return the path id of a live stored copy, or None.

        A hash row with zero path rows is an orphan (DB-05) and does NOT make
        content a duplicate.
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id
                FROM hashs h
                JOIN paths p ON p.hash_id = h.id
                WHERE h.hash = %s AND h.source_id = %s AND h.side_id = %s
                ORDER BY p.id
                LIMIT 1
                """,
                (content_hash, source_id, side_id),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def check_duplicate(
        self, content_hash: str, source_id: int, side_id: int
    ) -> tuple[bool, Optional[int]]:
        """Return ``(is_duplicate, existing_path_id)``."""
        path_id = self.find_live_path(content_hash, source_id, side_id)
        return (path_id is not None, path_id)

    def hash_exists_with_live_path(
        self, content_hash: str, source_id: Optional[int] = None
    ) -> bool:
        """Replacement for the legacy ``hash_exists`` (which counted orphan
        hash rows as duplicates, permanently blocking re-ingestion - DB-05)."""
        with self._conn() as conn, conn.cursor() as cur:
            if source_id is None:
                cur.execute(
                    """
                    SELECT 1
                    FROM hashs h JOIN paths p ON p.hash_id = h.id
                    WHERE h.hash = %s LIMIT 1
                    """,
                    (content_hash,),
                )
            else:
                cur.execute(
                    """
                    SELECT 1
                    FROM hashs h JOIN paths p ON p.hash_id = h.id
                    WHERE h.hash = %s AND h.source_id = %s LIMIT 1
                    """,
                    (content_hash, source_id),
                )
            row = cur.fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register_content(
        self,
        content_hash: str,
        source_id: int,
        side_id: int,
        path_row: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Atomically register content identity + path record.

        ``path_row`` must contain: file_name, file_path, file_size, file_type,
        file_date, date_creation (and optionally coordinates).

        Returns ``{"path_id": int, "hash_id": int, "duplicate": bool}``.
        """
        insert_hash = """
            INSERT INTO hashs (hash, side_id, source_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (hash, source_id, side_id) DO NOTHING
            RETURNING id
        """
        select_hash = """
            SELECT id FROM hashs WHERE hash = %s AND source_id = %s AND side_id = %s
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(insert_hash, (content_hash, side_id, source_id))
            row = cur.fetchone()
            if row is None:
                cur.execute(select_hash, (content_hash, source_id, side_id))
                row = cur.fetchone()
            hash_id = row[0]

            cur.execute(
                """
                INSERT INTO paths (file_name, file_path, file_size, file_type,
                                   file_date, date_creation, hash_id, coordinates)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    path_row["file_name"],
                    path_row["file_path"],
                    path_row["file_size"],
                    path_row["file_type"],
                    path_row["file_date"],
                    path_row["date_creation"],
                    hash_id,
                    path_row.get("coordinates"),
                ),
            )
            path_id = cur.fetchone()[0]
            conn.commit()
        return {"path_id": path_id, "hash_id": hash_id, "duplicate": False}

    # ------------------------------------------------------------------
    # Deletion / orphan lifecycle (DB-05)
    # ------------------------------------------------------------------
    def delete_path(self, path_id: int) -> Dict[str, Any]:
        """Delete a path row and clean up its hash if no other path needs it.

        Transactional: path deletion and hash orphan-cleanup commit together,
        so a file can never become permanently non-reingestable (DB-05).

        Returns ``{"path_deleted": bool, "hash_deleted": bool}``.
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM paths WHERE id = %s RETURNING hash_id", (path_id,))
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return {"path_deleted": False, "hash_deleted": False}
            hash_id = row[0]
            cur.execute(
                "SELECT 1 FROM paths WHERE hash_id = %s LIMIT 1", (hash_id,)
            )
            orphaned = cur.fetchone() is None
            hash_deleted = False
            if orphaned:
                cur.execute("DELETE FROM hashs WHERE id = %s", (hash_id,))
                hash_deleted = cur.rowcount > 0
            conn.commit()
        return {"path_deleted": True, "hash_deleted": hash_deleted}

    def cleanup_orphaned_hashes(self, dry_run: bool = False) -> int:
        """Remove hash rows that reference zero live paths.

        Used by the data-repair tool (Phase 22).  Orphaned hash rows are the
        exact defect that made deleted files permanently non-reingestable.
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT h.id FROM hashs h
                WHERE NOT EXISTS (SELECT 1 FROM paths p WHERE p.hash_id = h.id)
                """
            )
            ids = [r[0] for r in cur.fetchall()]
            if ids and not dry_run:
                cur.execute("DELETE FROM hashs WHERE id = ANY(%s)", (ids,))
                conn.commit()
        return len(ids)
