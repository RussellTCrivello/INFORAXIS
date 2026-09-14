"""SQL queries for words_paths table"""
from .base_queries import BaseQueries


class WordPathQueries(BaseQueries):
    """SQL queries for word-path relationships"""
    
    @staticmethod
    def insert_word_path(placeholders = '(%s, %s, %s)') -> str:
        """Insert word-path relationship"""
        return f"""
            INSERT INTO words_paths (path_id, word_id, word_count, position_indexer)
            VALUES {placeholders}
        """
    
    @staticmethod
    def batch_insert_word_paths() -> str:
        """Insert one word-path relationship, skipping existing pairs.

        AUDIT (DB-01): the previous statement used
        ``ON CONFLICT (path_id, word_id) DO UPDATE ... RETURNING id``, but the
        ``words_paths`` table created by ``m0001_initial_schema`` has **no**
        primary key, no ``id`` column and no unique index - only the
        non-unique ``idx_words_paths_path_word``. PostgreSQL therefore
        rejected 100% of these inserts with
        ``there is no unique or exclusion constraint matching the ON CONFLICT
        specification`` (and ``column "id" does not exist``).

        Adding the unique constraint is a schema change and is tracked as a
        separate, controlled activity. This version keeps the documented
        contract ("never duplicate a (path_id, word_id) pair") using
        ``WHERE NOT EXISTS``, which is valid against the current schema.
        The caller gets a row back only when the pair was actually inserted.
        """
        return """
            INSERT INTO words_paths (path_id, word_id, word_count, position_indexer)
            SELECT %s, %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1
                FROM words_paths existing
                WHERE existing.path_id = %s
                  AND existing.word_id = %s
            )
            RETURNING path_id;
        """
    
    @staticmethod
    def get_word_positions_by_path() -> str:
        """Get word positions for a path"""
        return """
            SELECT word_id, position_indexer
            FROM words_paths
            WHERE path_id = %s
        """

