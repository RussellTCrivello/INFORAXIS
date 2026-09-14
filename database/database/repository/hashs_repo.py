from .best_repo import BaseRepository
from ..queries.hash_queries import HashQueries

class HashsRepository(BaseRepository):

    def insert_info_hashs(self, hash_value, source_id, side_id):
        """Insert or update a hash record and return its ID"""
        # Don't use commit=True in transaction context - let transaction manager handle commits
        # commit parameter is ignored when _connection is set (transaction context)
        return self.execute(
            HashQueries.insert_hash(),
            (hash_value, source_id, side_id)
        )
    
    def select_hashs(self):
        """Return all hashes with their source IDs"""
        return self.execute(
            HashQueries.get_all(),
            None,
            fetchall=True
        )
    

    def hash_exists(self, hash_value, source_id, side_id) -> bool:
        """Check if hash already exists and is linked to a path"""
        row = self.execute(
            HashQueries.check_hash_exists(),
            (hash_value, source_id, side_id),
            fetchone=True
        )
        return row is not None
    
    def get_hash_records(self, hash_value):
        """Get all records related to a hash value"""
        return self.execute(
            HashQueries.get_hash_records(),
            (hash_value,),
            fetchone=True
        )

    def get_hash_by_id(self, hash_id):
        """Return hash string by hash ID"""
        row = self.execute(
            HashQueries.get_hash_by_id(),
            (hash_id,),
            fetchone=True
        )
        return row[0] if row else None

    def check_duplicate(self, hash_value, source_id, side_id):
        """Return the id of the *stored path* for this hash, or None.

        A duplicate requires a live path referencing the hash row (DB-04/DB-05
        semantics: an orphaned hash row does not make content a duplicate, so a
        deleted file can be ingested again).  The value is a **path** id.
        """
        row = self.execute(
            HashQueries.check_duplicate(),
            (hash_value, source_id, side_id),
            fetchone=True
        )
        return row[0] if row else None

    def get_duplicate_document(self, hash_value, source_id, side_id):
        """Return ``(hash_id, path_id)`` when this file is already stored.

        Both ids come from the same row, so callers cannot mix up the two id
        spaces (a path id used as a hash id resolves to an unrelated file).
        ``None`` means no live path references the hash.
        """
        row = self.execute(
            HashQueries.check_duplicate_document(),
            (hash_value, source_id, side_id),
            fetchone=True
        )
        if not row:
            return None
        return int(row[0]), int(row[1])

    def get_hash_id_by_value(self, hash_value, source_id, side_id):
        """Return the hash row id for this value/source/side, or None.

        Used when the hash row already exists but has no path yet (for
        example after a rolled-back attempt): the row is reused instead of
        being duplicated.
        """
        row = self.execute(
            HashQueries.get_hash_id_by_value(),
            (hash_value, source_id, side_id),
            fetchone=True
        )
        return row[0] if row else None
    
    def check_hash_exists_for_source(self, hash_value, source_id):
        """Check if hash exists for given source (any side)"""
        row = self.execute(
            HashQueries.check_hash_exists_for_source(),
            (hash_value, source_id),
            fetchone=True
        )
        return row is not None
    