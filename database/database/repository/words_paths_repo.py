from .best_repo import BaseRepository
from ..queries.word_path_queries import WordPathQueries
from core.serialization import pack_int_list, unpack_int_list
import logging

logger = logging.getLogger(__name__)

class WordsPathsRepository(BaseRepository):

    #: Rows per INSERT statement.  A large document can produce tens of
    #: thousands of (path, word) pairs; one statement per pair set would build
    #: a multi-megabyte SQL string and bind an unbounded parameter array, so the
    #: pairs are sent in bounded batches inside the caller's transaction.
    WORDS_PATHS_BATCH_SIZE = 5000

    def bulk_insert_words_paths(self, tuple_path_id_and_word_id_and_counts_and_position):
        """Insert ``(path_id, word_id, word_count, positions)`` rows.

        Batched so the statement size stays bounded for very large documents.
        The rows are inserted inside the caller's transaction, so a failure in
        any batch rolls the whole document back.
        """
        if not tuple_path_id_and_word_id_and_counts_and_position:
            return

        tuples_rows = list(tuple_path_id_and_word_id_and_counts_and_position)
        batch_size = self.WORDS_PATHS_BATCH_SIZE

        for start in range(0, len(tuples_rows), batch_size):
            batch = tuples_rows[start:start + batch_size]
            placeholders = ",".join(["(%s,%s,%s,%s)"] * len(batch))
            query = WordPathQueries.insert_word_path(placeholders)

            flat_values = [item for row in batch for item in row]
            # AUDIT (DB-02): this used to ``print(query)``, dumping the full
            # INSERT statement (hundreds of parameter slots) to stdout on every
            # ingestion batch. Removed - real logging belongs in the logger.
            self.execute(query, flat_values)

    def insert_words_paths(self, content_id, word_id, word_count, list_position_indexer):
        """Insert a single word-path relationship if it does not exist yet.

        Returns the inserted ``path_id`` when a new row was created, or
        ``None`` when a ``(path_id, word_id)`` row already existed.
        """
        position_byte = pack_int_list(list_position_indexer)

        # The guard clause needs the pair twice (INSERT values + NOT EXISTS).
        params = (
            content_id, word_id, word_count, position_byte,
            content_id, word_id,
        )

        return self.execute(WordPathQueries.batch_insert_word_paths(), params, True)
    
    def get_word_positions_by_path(self, path_id):
        """Get word positions for a path"""
        rows = self.execute(
            WordPathQueries.get_word_positions_by_path(),
            (path_id,),
            fetchall=True
        )
        result = {}
        for row in rows:
            if row and len(row) >= 2:
                word_id = row[0]
                position_byte = row[1]
                try:
                    positions = unpack_int_list(position_byte)
                    result[word_id] = positions
                except Exception as e:
                    logger.warning(
                        "Could not decode positions for word_id %s (path %s): %s",
                        word_id, path_id, e,
                    )
        return result