"""SQL queries for hashs table"""
from .base_queries import BaseQueries


class HashQueries(BaseQueries):
    """SQL queries related to hashes"""
    
    @staticmethod
    def insert_hash() -> str:
        """Insert hash with conflict handling"""
        return """
            INSERT INTO hashs (hash, source_id, side_id) 
            VALUES (%s, %s, %s)
            ON CONFLICT (hash, source_id, side_id) DO UPDATE SET hash = EXCLUDED.hash
            RETURNING id
        """
    @staticmethod
    def get_all():
        return"""
            SELECT hash, source_id FROM hashs
        """
    @staticmethod
    def check_hash_exists() -> str:
        """Check if hash exists with specific source/side"""
        return """
            SELECT 1
            FROM hashs h
            INNER JOIN paths p ON p.hash_id = h.id
            WHERE h.hash = %s AND h.source_id = %s AND h.side_id = %s
            LIMIT 1
        """
    
    @staticmethod
    def get_hash_records() -> str:
        """Get all hash records for a hash value"""
        return """
            SELECT h.id, h.source_id, h.side_id,
                   CASE WHEN p.id IS NOT NULL THEN TRUE ELSE FALSE END AS has_paths
            FROM hashs h
            LEFT JOIN paths p ON p.hash_id = h.id
            WHERE h.hash = %s
        """
    
    @staticmethod
    def get_hash_by_id() -> str:
        """Get hash string by ID"""
        return "SELECT hash FROM hashs WHERE id = %s"
    
    @staticmethod
    def check_duplicate() -> str:
        """Check if content is a duplicate.

        DB-04/DB-05 semantics: a duplicate requires a *live path* referencing
        the hash row. An orphaned hash row (all paths deleted) does not make
        content a duplicate - otherwise a deleted file could never be
        ingested again.
        Returns the existing path id.
        """
        return """
            SELECT p.id
            FROM hashs h
            JOIN paths p ON p.hash_id = h.id
            WHERE h.hash = %s AND h.source_id = %s AND h.side_id = %s
            ORDER BY p.id
            LIMIT 1
        """

    @staticmethod
    def check_hash_exists_for_source() -> str:
        """Check if a hash with a live path exists for given source (any side).

        DB-05: orphaned hash rows (zero referencing paths) do not count.
        """
        return """
            SELECT h.id
            FROM hashs h
            JOIN paths p ON p.hash_id = h.id
            WHERE h.hash = %s AND h.source_id = %s
            LIMIT 1
        """