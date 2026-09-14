from .best_repo import BaseRepository
import logging
import zlib
from ..queries.content_queries import ContentQueries
from ..queries.word_queries import WordQueries
from core.serialization import pack_mapping, unpack_mapping

logger = logging.getLogger(__name__)

class ContentsRepository(BaseRepository):
    """
    Repository for content operations.
    
    Note: Content is stored as compressed, pickled symbol pairs:
    [(word_id, punct_before_id, punct_after_id, spacing_id, char_position), ...]
    
    This design allows:
    - Efficient storage (compression + normalization)
    - Fast retrieval by word ID
    - Complete preservation of punctuation, spacing, and position information
    - Referential integrity with the words table
    """

    def store_text_content(self, ids, date, path_id):
        """
        Store content as symbol pairs format (converted from word IDs).
        All content is stored using the complete symbol pairs format:
        [(word_id, punct_before_id, punct_after_id, spacing_id, char_position), ...]
        
        Args:
            ids: List of word IDs (integers) from the words table
            date: Content date
            path_id: Path ID to associate content with
        
        Returns:
            List of content record IDs (one per chunk if content is large)
        
        Note: Word IDs are converted to symbol pairs format with default values:
        - punct_before_id: None (0)
        - punct_after_id: None (0)
        - spacing_id: 1 (space) between words
        - char_position: sequential position (0, 1, 2, ...)
        Then stored as Pickle → zlib compressed → BYTEA
        """
        if not ids:
            return []
        
        # Convert word IDs to symbol pairs format
        # Default: space between words, no punctuation, sequential position
        symbol_pairs = []
        for position, word_id in enumerate(ids):
            symbol_pairs.append((
                word_id,      # word_id
                None,         # punct_before_id (None = 0)
                None,         # punct_after_id (None = 0)
                1,            # spacing_id (1 = space)
                position      # char_position (sequential)
            ))
        
        # Use store_symbol_pairs to store in Pickle format
        return self.store_symbol_pairs(symbol_pairs, date, path_id)
    
    def load_text_content(self, path_id):
        """
        Load the text content of a file for display.

        Prefers the structured raw text (contents_raw, migration m0010):
        the extractor's combined text with worksheet/slide/page markers,
        original casing, punctuation, tabs and line breaks - everything the
        type-aware display formatters need. Files ingested before m0010 (or
        whose raw text was too large to store) fall back to the legacy
        word-join reconstruction.

        Args:
            path_id: Path ID to load content for

        Returns:
            The file's text content (structured when available).
        """
        try:
            raw = self.load_raw_content(path_id)
            if raw is not None:
                return raw
        except Exception as raw_err:
            # Missing table (pre-m0010 database) or transient error: fall
            # back to the legacy reconstruction rather than failing (this is
            # a read path - the caller only wants text to display).
            logger.warning(
                "Raw content unavailable for path %s, falling back to word "
                "join: %s", path_id, raw_err,
            )

        return self._load_word_join_content(path_id)

    def _load_word_join_content(self, path_id):
        """
        Legacy reconstruction: word IDs joined with single spaces.
        Reads Pickle format symbol pairs: [(word_id, punct_before_id, punct_after_id, spacing_id, char_position), ...]

        Args:
            path_id: Path ID to load content for

        Returns:
            Space-separated string of words

        Note: This method loads compressed Pickle symbol pairs, extracts word IDs,
        and looks up the actual words from the words table.
        """
        rows = self.execute(ContentQueries.load_content(), (path_id,), fetchall=True)
        if not rows:
            return ""
        
        # Get all word IDs from all content chunks
        all_word_ids = []
        for row in rows:
            if row and len(row) >= 2:
                compressed = row[1]  # content_data is at index 1
                try:
                    packed = zlib.decompress(compressed)
                    
                    # Load Pickle format symbol pairs
                    symbol_pairs = unpack_mapping(packed)
                    if isinstance(symbol_pairs, list) and len(symbol_pairs) > 0:
                        # Extract word_ids from symbol pairs (first element of each tuple)
                        if isinstance(symbol_pairs[0], (tuple, list)) and len(symbol_pairs[0]) >= 1:
                            # New format: symbol pairs
                            word_ids = [pair[0] for pair in symbol_pairs if isinstance(pair, (tuple, list)) and len(pair) >= 1]
                            all_word_ids.extend(word_ids)
                        else:
                            # Fallback: if it's just a list of word IDs (shouldn't happen in new format)
                            all_word_ids.extend(symbol_pairs)
                except Exception as e:
                    logger.warning(
                        "Could not decode content chunk for path %s: %s", path_id, e
                    )
                    continue

        if not all_word_ids:
            return ""

        # Convert word IDs to words, looking up only the ids this document
        # actually contains (the previous implementation loaded the entire
        # words table on every display request).
        dictionary = {}
        unique_ids = list(dict.fromkeys(all_word_ids))
        batch_size = 10000
        for start in range(0, len(unique_ids), batch_size):
            batch = unique_ids[start:start + batch_size]
            word_rows = self.execute(
                WordQueries.get_words_by_ids(), (batch,), fetchall=True
            )
            if word_rows:
                dictionary.update({row[0]: row[1] for row in word_rows})

        return " ".join(dictionary.get(i, f"[ID:{i}]") for i in all_word_ids)

    def store_raw_content(self, path_id, text, chunk_size=1024 * 1024):
        """Store the extractor's structured text verbatim (display fidelity).

        Chunked TEXT rows in contents_raw. Called inside the same
        transaction as the word-ID content store so both stores stay
        consistent. Returns the number of chunks stored.
        """
        if text is None:
            return 0
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)] or [""]
        for seq, chunk in enumerate(chunks):
            self.execute(
                ContentQueries.insert_raw_content(),
                (path_id, seq, chunk, len(chunk)),
            )
        return len(chunks)

    def load_raw_content(self, path_id):
        """Load the raw structured text for a file, or None if not stored."""
        rows = self.execute(ContentQueries.load_raw_content(), (path_id,), fetchall=True)
        if not rows:
            return None
        return "".join(row[0] if isinstance(row, (tuple, list)) else row for row in rows)

    def delete_raw_content(self, path_id):
        """Delete raw content chunks for a file (mirrors delete_content)."""
        self.execute(ContentQueries.delete_raw_content(), (path_id,))
    
    def load_content_word_ids(self, path_id):
        """
        Load content and return the raw word IDs (numbers from words table).
        Reads Pickle format symbol pairs: [(word_id, punct_before_id, punct_after_id, spacing_id, char_position), ...]
        
        Args:
            path_id: Path ID to load content for
        
        Returns:
            List of word IDs (integers) from the words table
        
        Note: This method loads compressed Pickle symbol pairs and extracts word IDs
        directly without converting to text.
        """
        rows = self.execute(ContentQueries.load_content(), (path_id,), fetchall=True)
        if not rows:
            return []
        
        all_word_ids = []
        for row in rows:
            if row and len(row) >= 2:
                compressed = row[1]  # content_data is at index 1
                try:
                    packed = zlib.decompress(compressed)
                    
                    # Load Pickle format symbol pairs
                    symbol_pairs = unpack_mapping(packed)
                    if isinstance(symbol_pairs, list) and len(symbol_pairs) > 0:
                        # Extract word_ids from symbol pairs (first element of each tuple)
                        if isinstance(symbol_pairs[0], (tuple, list)) and len(symbol_pairs[0]) >= 1:
                            # Symbol pairs format
                            word_ids = [pair[0] for pair in symbol_pairs if isinstance(pair, (tuple, list)) and len(pair) >= 1]
                            all_word_ids.extend(word_ids)
                        else:
                            # Fallback: if it's just a list of word IDs (shouldn't happen in new format)
                            all_word_ids.extend(symbol_pairs)
                except Exception as e:
                    # If decompression/parsing fails, skip this chunk
                    logger.warning("Error loading content chunk for path %s: %s", path_id, e)
                    continue
        
        return all_word_ids
    

    
    def get_content_chunks(self, path_id, limit):
        """Return raw content chunks"""
        return self.execute(
            ContentQueries.get_content_chunks(),
            (path_id, limit)
        )

    def get_content_count(self, path_id):
        """Return number of chunks for a file"""
        row = self.execute(
            ContentQueries.get_content_count(),
            (path_id,),
            single=True
        )
        return row[0]

    def get_content_stats(self, path_id):
        """Return chunk count and total byte size"""
        row = self.execute(
            ContentQueries.get_content_stats(),
            (path_id,),
            single=True
        )
        return {
            "chunk_count": row[0],
            "total_bytes": row[1]
        }

    def delete_content(self, path_id):
        self.delete_raw_content(path_id)
        """Delete all content for a file"""
        return self.execute(
            ContentQueries.delete_content(),
            (path_id,)
        )
    
    def get_content_with_positions(self, path_id):
        """
        Get content word IDs with their positions in the content.
        
        Args:
            path_id: Path ID to get content for
        
        Returns:
            List of tuples: (word_id, position) ordered by position
        """
        word_ids = self.load_content_word_ids(path_id)
        if not word_ids:
            return []
        
        # Get positions from words_paths table
        from ..repository.words_paths_repo import WordsPathsRepository
        words_paths_repo = WordsPathsRepository(self.db)
        word_positions_map = words_paths_repo.get_word_positions_by_path(path_id)
        
        # Build list of (word_id, position) tuples
        result = []
        for position, word_id in enumerate(word_ids):
            # Check if word has specific positions stored
            if word_id in word_positions_map:
                # Use stored positions if available
                stored_positions = word_positions_map[word_id]
                if stored_positions and position in stored_positions:
                    result.append((word_id, position))
                else:
                    result.append((word_id, position))
            else:
                # Use sequential position
                result.append((word_id, position))
        
        return result
    
    def store_symbol_pairs(self, symbol_pairs, date, path_id, max_chunk_size=1024*1024):
        """
        Store content as symbol pairs in Pickle format, compressed with zlib.
        If content is very large, it will be divided into several rows in the database.
        
        Args:
            symbol_pairs: List of symbol pairs, each as:
                (word_id, punct_before_id, punct_after_id, spacing_id, char_position)
                - word_id: int - Word ID from words table
                - punct_before_id: int or None - Punctuation ID before word (0 if None)
                - punct_after_id: int or None - Punctuation ID after word (0 if None)
                - spacing_id: int - Spacing type (0=none, 1=space, 2=tab, 3=newline)
                - char_position: int - Spatial position: page_number * 1000000 + y_coord * 1000 + x_coord
            date: Content date
            path_id: Path ID to associate content with
            max_chunk_size: Maximum compressed size per chunk in bytes (default: 1MB)
        
        Returns:
            List of content record IDs (one per chunk)
        
        Note: Symbol pairs are stored as Pickle, then compressed with zlib, then stored as BYTEA.
        Format: Pickle array of symbol pairs → zlib compressed → BYTEA
        If content exceeds max_chunk_size, it will be split into multiple rows.
        """
        if not symbol_pairs:
            return []
        
        # Ensure all symbol pairs are tuples with exactly 5 elements
        # Handle None values by keeping them as None (Pickle handles None natively)
        normalized_pairs = []
        for pair in symbol_pairs:
            if isinstance(pair, (tuple, list)) and len(pair) >= 5:
                normalized_pairs.append((
                    pair[0],  # word_id
                    pair[1] if pair[1] is not None else 0,  # punct_before_id
                    pair[2] if pair[2] is not None else 0,  # punct_after_id
                    pair[3],  # spacing_id
                    pair[4]   # char_position
                ))
            else:
                raise ValueError(f"Invalid symbol pair format: {pair}. Expected (word_id, punct_before_id, punct_after_id, spacing_id, char_position)")
        
        # Try to serialize and compress the entire content first
        pickled_data = pack_mapping(normalized_pairs)
        compressed = zlib.compress(pickled_data)
        
        # If compressed size is within limit, store as single chunk
        if len(compressed) <= max_chunk_size:
            # Errors are NOT swallowed here: returning [] would make the
            # caller believe the content was stored while the document kept
            # only its word index, and the failure would stay invisible in
            # the logs.  Let the transaction owner decide (it rolls back).
            last_id = self.execute(
                ContentQueries.insert_content(), (compressed, date, path_id), True)
            return [last_id] if last_id else []
        
        # Content is too large, split into chunks
        chunk_ids = []
        total_pairs = len(normalized_pairs)
        chunk_start = 0
        
        while chunk_start < total_pairs:
            # Binary search to find the largest chunk that fits within max_chunk_size
            best_chunk_end = chunk_start + 1
            
            # Start with a reasonable chunk size estimate
            # Estimate: each symbol pair tuple is ~50 bytes when pickled, compressed ~15 bytes
            estimated_pairs_per_chunk = max_chunk_size // 15
            chunk_end = min(chunk_start + estimated_pairs_per_chunk, total_pairs)
            
            # Binary search for optimal chunk size
            low = chunk_start + 1
            high = total_pairs
            
            while low <= high:
                mid = (low + high) // 2
                chunk_data = normalized_pairs[chunk_start:mid]
                
                # Serialize and compress this chunk
                chunk_pickled = pack_mapping(chunk_data)
                chunk_compressed = zlib.compress(chunk_pickled)
                
                if len(chunk_compressed) <= max_chunk_size:
                    best_chunk_end = mid
                    low = mid + 1
                else:
                    high = mid - 1
            
            # Store the chunk
            chunk_data = normalized_pairs[chunk_start:best_chunk_end]
            chunk_pickled = pack_mapping(chunk_data)
            chunk_compressed = zlib.compress(chunk_pickled)
            
            # Propagate chunk failures: a partially stored document is worse
            # than a clean rollback (the caller must not keep ids of content
            # rows whose transaction is going to be discarded).
            last_id = self.execute(
                ContentQueries.insert_content(), (chunk_compressed, date, path_id), True)
            if last_id:
                chunk_ids.append(last_id)

            chunk_start = best_chunk_end
        
        return chunk_ids
    
    def load_symbol_pairs(self, path_id):
        """
        Load content as symbol pairs from compressed Pickle.
        Reads complete symbol pairs: [(word_id, punct_before_id, punct_after_id, spacing_id, char_position), ...]
        
        Args:
            path_id: Path ID to load content for
        
        Returns:
            List of symbol pairs, each as:
                (word_id, punct_before_id, punct_after_id, spacing_id, char_position)
        """
        rows = self.execute(ContentQueries.load_content(), (path_id,), fetchall=True)
        if not rows:
            return []
        
        all_symbol_pairs = []
        for row in rows:
            if row and len(row) >= 2:
                compressed = row[1]  # content_data is at index 1
                try:
                    # Decompress
                    packed = zlib.decompress(compressed)
                    
                    # Load Pickle format symbol pairs
                    symbol_pairs = unpack_mapping(packed)
                    if isinstance(symbol_pairs, list):
                        # Validate and normalize symbol pairs
                        for pair in symbol_pairs:
                            if isinstance(pair, (tuple, list)) and len(pair) >= 5:
                                # Convert 0 back to None for punctuation IDs if needed
                                all_symbol_pairs.append((
                                    pair[0],  # word_id
                                    pair[1] if pair[1] != 0 else None,  # punct_before_id
                                    pair[2] if pair[2] != 0 else None,  # punct_after_id
                                    pair[3],  # spacing_id
                                    pair[4]   # char_position
                                ))
                            else:
                                # Invalid format - skip
                                logger.warning("Invalid symbol pair format: %s", pair)
                    else:
                        logger.warning("Expected list of symbol pairs, got %s", type(symbol_pairs).__name__)
                except Exception as e:
                    logger.warning("Error loading symbol pairs for path %s: %s", path_id, e)
                    continue
        
        return all_symbol_pairs
