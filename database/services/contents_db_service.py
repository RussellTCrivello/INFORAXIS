from datetime import date
from typing import List, Optional, Dict, Tuple
from contextlib import contextmanager
import re
import logging
import psycopg2

from database.database.database import Database
from database.database.repository.transaction_scope import TransactionScope
from database.exceptions import QueryError, TransactionAbortedError

from core.word_limits import MAX_WORD_BYTES, word_exceeds_db_limit

logger = logging.getLogger(__name__)
from database.database.repository.sources_repo import SourcesRepository
from database.database.repository.contents_repo import ContentsRepository
from database.database.repository.words_repo import WordsRepository
from database.database.repository.paths_repo import PathsRepository
from database.database.repository.keywords_repo import KeywordsRepository
from database.database.repository.categorys_repo import CategorysRepository
from database.database.repository.sides_repo import SidesRepository
from database.database.repository.words_paths_repo import WordsPathsRepository
from database.database.repository.keywords_paths_repo import KeywordsPathsRepository
from database.database.repository.words_categorys_repo import WordsCategorysRepository
from database.database.repository.hashs_repo import HashsRepository
from database.database.repository.titles_content_repo import TitlesContentRepository
from database.database.repository.punctuation_repo import PunctuationRepository
from database.database.repository.alerts_repo import AlertsRepository
from core.serialization import pack_int_list, unpack_int_list


def _as_id(value):
    """Normalize a repository result into a plain integer id (or None).

    Repositories sometimes return the id directly, sometimes a one-element
    tuple (depending on the driver path taken by ``execute``).  Callers in
    this module need one representation.
    """
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        value = value[0] if value else None
        if value is None:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None



def _keyword_occurrence_counts(sequence, patterns):
    """Count overlapping occurrences of id patterns inside ``sequence``.

    ``sequence`` is a list of ids (word ids, possibly ``None`` for unknown
    gaps); ``patterns`` maps a keyword id to the list of word ids that make up
    the keyword phrase.

    Positions are indexed by the first id of each pattern, so the work is
    proportional to the number of candidate positions instead of scanning the
    whole document once per keyword.  The previous nested loop was
    O(document length x keywords) and was a visible contributor to the CPU
    saturation reported by the resource monitor during large ingests.

    Returns:
        ``{keyword_id: count}`` for the patterns that occur at least once.
    """
    if not sequence or not patterns:
        return {}

    positions = {}
    for index, value in enumerate(sequence):
        positions.setdefault(value, []).append(index)

    counts = {}
    length_of = len(sequence)
    for keyword_id, pattern in patterns.items():
        if not pattern:
            continue
        pattern_length = len(pattern)
        candidates = positions.get(pattern[0])
        if not candidates:
            continue
        if pattern_length == 1:
            counts[keyword_id] = len(candidates)
            continue
        last_start = length_of - pattern_length
        tail = pattern[1:]
        count = 0
        for start in candidates:
            if start <= last_start and sequence[start + 1:start + pattern_length] == tail:
                count += 1
        if count:
            counts[keyword_id] = count
    return counts


class ContentDBService:

    def __init__(self, db: Optional[Database] = None):
      
        self.db = db or Database()
        
        self._init_repositories()
    
    @contextmanager
    def transaction(self):
        """
        Transaction context manager for service-level operations.

        All repository operations on this service share one connection for the
        duration of the block, so hash, path, content, word links and title are
        committed together or not at all.

        Thread safety: the connection is bound in a
        :class:`TransactionScope` (context-local), **not** by assigning
        connection-bound clones onto this shared service instance.  Two worker
        threads storing documents at the same time therefore keep their own
        connections; the previous attribute-swapping implementation let thread
        B overwrite thread A's repositories, which sent thread A's statements
        to thread B's session (``relation "tmp_words" does not exist``,
        ``no COPY in progress``, then the aborted-transaction cascade).

        Inside an existing transaction the block becomes a savepoint: a nested
        failure rolls back only its own statements, never the surrounding unit
        of work.

        Usage:
            with service.transaction():
                service.create_hash(...)
                service.create_path(...)
                # All operations commit together or rollback on error
        """
        scope = self._scope

        # Nested transaction: reuse the outer connection, contain failures.
        if scope.active:
            with scope.savepoint():
                yield self
            return

        conn = self.db.connect()
        token = scope.bind(conn)
        try:
            yield self
            conn.commit()
            logger.debug("Service transaction committed successfully")
        except BaseException as exc:
            # Roll back once, here, at the only party that owns the unit of
            # work - and then surface the original exception (callers classify
            # on TransactionAbortedError / QueryError).
            try:
                if conn and not conn.closed:
                    conn.rollback()
                    logger.error("Service transaction rolled back: %s", exc)
            except Exception as rollback_err:
                logger.error("Error during rollback: %s", rollback_err)
            raise
        finally:
            scope.release(token)
            try:
                self.db.putconn(conn)
            except Exception as put_err:
                logger.error("Error returning connection to pool: %s", put_err)
                try:
                    if conn and not conn.closed:
                        conn.close()
                except Exception:
                    pass

    @contextmanager
    def savepoint(self, name: Optional[str] = None):
        """Run a block inside a ``SAVEPOINT`` of the current transaction.

        Used for optional work (raw display text, keyword links, titles): a
        failure inside the block is contained and cannot poison the rest of
        the document transaction.
        """
        with self._scope.savepoint(name):
            yield self

    def _init_repositories(self):
        """Initialize all repository instances.

        Every repository shares one :class:`TransactionScope`.  When
        :meth:`transaction` binds a connection to the calling thread/task, all
        of them pick it up for the duration of the block - without mutating
        this (shared) service instance, which is what made concurrent storage
        run statements on another thread's connection.
        """
        self._scope = TransactionScope(name="contents_db_service")
        self.sources_repo = SourcesRepository(self.db, scope=self._scope)
        self.sides_repo = SidesRepository(self.db, scope=self._scope)
        self.hashs_repo = HashsRepository(self.db, scope=self._scope)
        self.paths_repo = PathsRepository(self.db, scope=self._scope)
        self.words_repo = WordsRepository(self.db, scope=self._scope)
        self.contents_repo = ContentsRepository(self.db, scope=self._scope)
        self.words_categorys_repo = WordsCategorysRepository(self.db, scope=self._scope)
        self.categorys_repo = CategorysRepository(self.db, scope=self._scope)
        self.keywords_repo = KeywordsRepository(self.db, scope=self._scope)
        self.keywords_paths_repo = KeywordsPathsRepository(self.db, scope=self._scope)
        self.words_paths_repo = WordsPathsRepository(self.db, scope=self._scope)
        self.titles_content_repo = TitlesContentRepository(self.db, scope=self._scope)
        self.punctuation_repo = PunctuationRepository(self.db, scope=self._scope)
        self.alerts_repo = AlertsRepository(self.db, scope=self._scope)

    # def categories(self):
    #     result = self.categorys_repo.select_categorys_word_id()
    #     print(result)
    #     result = self.categorys_repo.select_category_by_word_id(35)
    #     print(result)
    #     result = self.categorys_repo.get_categories_by_file(27)
    #     print(result)
    #     result = self.categorys_repo.search_categories('word', 10, 0)
    #     print(result)
    #     result = self.categorys_repo.get_categories_with_stats(5)
    #     print(result)
    #     result = self.categorys_repo.update_category_by_id(36, 10)
    #     print(result)
    #     result = self.categorys_repo.update_category_by_word_id(10, 36)
    #     print(result)

    # ============================================================
    # SOURCE OPERATIONS
    # ============================================================

    def get_all_sources(self) -> List[Tuple[int, str]]:
     
        return self.sources_repo.select_info_sources()

    def create_source(
        self,
        name: str,
        country: str,
        job: str,
        importance: float,
        city: str = "",
        description: str = "",
        accounts: str = "",
        note: str = "",
        attachments: str = "",
        ownership: str = "",
        access_status: str = "",
        entry_date: Optional[date] = None,
        id_categorys: Optional[int] = None
    ) -> int:

        # Use provided entry_date or default to today
        if entry_date is None:
            entry_date = date.today()
        
        return self.sources_repo.insert_info_sources(
            name, country, job, importance, city, description,
            accounts, note, attachments, ownership, access_status,
            entry_date, date.today(), id_categorys
        )

    def get_source_by_id(self, source_id: int) -> Optional[Dict]:
        """Get source details by ID."""
        # Implement based on your repository method
        pass

    # ============================================================
    # SIDE OPERATIONS
    # ============================================================

    def get_all_sides(self) -> List[Tuple[int, str]]:
       
        return self.sides_repo.select_info_sides()

    def create_side(self, name: str, importance: float, date_creation: Optional[date] = None) -> int:
        """Create a new side"""
        if date_creation is None:
            date_creation = date.today()
        return self.sides_repo.insert_info_sides(name, importance, date_creation)

    def get_or_create_source(self, name: str, importance: float = 1.0,
                             country: str = "", job: str = "") -> Optional[int]:
        """Return the id of ``name``, creating the source if it is missing.

        Uses the repository's ``INSERT ... ON CONFLICT (name) DO UPDATE ...
        RETURNING id`` upsert, so concurrent workers storing their first file
        of an ingestion cannot race each other into
        ``duplicate key value violates unique constraint "sources_name_key"``
        - the previous read-then-insert pattern made every worker but the
        winner fail, which cost the file its real source (the code fell back to
        ``__FALLBACK_SOURCE__``).
        """
        row = self.sources_repo.get_or_create_source(
            name, job or "", importance, country or "", date.today()
        )
        return _as_id(row)

    def get_or_create_side(self, name: str, importance: float = 1.0) -> Optional[int]:
        """Return the id of ``name``, creating the side if it is missing.

        Concurrency-safe counterpart of :meth:`create_side` (see
        :meth:`get_or_create_source`).
        """
        row = self.sides_repo.get_or_create_side(name, importance, date.today())
        return _as_id(row)

    # ============================================================
    # HASH OPERATIONS
    # ============================================================

    def create_hash(
        self,
        hash_value: str,
        source_id: int,
        side_id: int
    ) -> Optional[int]:
     
        # Check if hash already exists for this source and side
        existing_id = self.hashs_repo.check_duplicate(hash_value, source_id, side_id)
        if existing_id:
            return None  # Return None for duplicates as expected by tests
        
        # Insert hash - let exceptions propagate so transaction can rollback
        try:
            hash_id = self.hashs_repo.insert_info_hashs(hash_value, source_id, side_id)
            
            # Validate hash_id was actually created
            if not hash_id:
                logger.error(f"Hash insert returned None or 0")
                raise ValueError(f"Hash insert failed: returned {hash_id}")
            
            # Normalize hash_id
            if isinstance(hash_id, tuple):
                hash_id = hash_id[0] if len(hash_id) > 0 else None
            
            if not hash_id or hash_id <= 0:
                logger.error(f"Hash insert returned invalid ID: {hash_id}")
                raise ValueError(f"Hash insert failed: returned invalid ID {hash_id}")
            
            return hash_id
        except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.IntegrityError) as fk_err:
            logger.error(f"Foreign key violation creating hash (source_id={source_id}, side_id={side_id} may not exist): {fk_err}")
            raise
        except Exception as e:
            # Check if it's a wrapped foreign key violation
            error_str = str(e).lower()
            if 'foreign key' in error_str or 'violates foreign key constraint' in error_str:
                logger.error(f"Foreign key violation creating hash: {e}")
                raise
            raise

    def hash_exists(self, hash_value: str, source_id: int) -> bool:
        """Check if hash exists for given source."""
        return self.hashs_repo.check_hash_exists_for_source(hash_value, source_id)

    # ============================================================
    # PATH OPERATIONS
    # ============================================================

    def create_path(
        self,
        file_name: str,
        file_path: str,
        file_size: int,
        file_type: str,
        file_status: str,
        file_date: date,
        hash_id: int,
        coordinates: Optional[str] = None,
        extraction_provenance: Optional[dict] = None,
        processing_status: str = "discovered",
        status_detail: Optional[str] = None,
        attempts: int = 0
    ) -> int:
        # Note: Parameter order matches the params tuple in insert_info_paths, not the method signature
        # params tuple order: file_name, file_path, file_size, file_type, file_status, file_date, hash_id, date_creation, coordinates
        return self.paths_repo.insert_info_paths(
            file_name, file_path, file_size, file_type,
            file_status=file_status,
            hash_id=hash_id,
            file_date=file_date,
            date_creation=date.today(),
            coordinates=coordinates or "",
            extraction_provenance=extraction_provenance,
            processing_status=processing_status,
            status_detail=status_detail,
            attempts=attempts
        )
    
    def get_path_id_by_hash_id(self, hash_id: int) -> Optional[int]:
        """Get path ID by hash ID"""
        return self.paths_repo.get_path_id_by_hash_id(hash_id)

    # ============================================================
    # SPACING MAPPING
    # ============================================================
    
    # Spacing type constants
    SPACING_NONE = 0      # No spacing
    SPACING_SPACE = 1     # Single space
    SPACING_TAB = 2       # Tab character (\t)
    SPACING_NEWLINE = 3   # Newline character (\n)
    SPACING_PIPE = 4      # Pipe symbol (|) for headings
    
    @staticmethod
    def get_spacing_id(space_char: str) -> int:
        """
        Get spacing ID for a space character.
        
        Args:
            space_char: Space character string
        
        Returns:
            Spacing ID constant
        """
        if not space_char or space_char == '':
            return ContentDBService.SPACING_NONE
        elif space_char == ' ':
            return ContentDBService.SPACING_SPACE
        elif space_char == '\t':
            return ContentDBService.SPACING_TAB
        elif space_char == '\n' or space_char == '\r\n':
            return ContentDBService.SPACING_NEWLINE
        elif space_char == '|':
            return ContentDBService.SPACING_PIPE
        else:
            # Default to space for unknown characters
            return ContentDBService.SPACING_SPACE
    
    @staticmethod
    def calculate_char_position(page_number: int, y_coord: int, x_coord: int) -> int:
        """
        Calculate character position using spatial formula.
        
        Formula: page_number * 1000000 + y_coord * 1000 + x_coord
        
        Args:
            page_number: Page number (0-indexed or 1-indexed)
            y_coord: Y coordinate (vertical position)
            x_coord: X coordinate (horizontal position)
        
        Returns:
            Calculated character position
        """
        return page_number * 1000000 + y_coord * 1000 + x_coord
    
    # ============================================================
    # CONTENT OPERATIONS
    # ============================================================

    def create_content(
        self,
        words: List[str],
        path_id: int,
        content_date: Optional[date] = None
    ) -> List[int]:
        """
        Create content from a list of words.

        Steps (all inside the caller's transaction):
          1. insert the words missing from the dictionary;
          2. resolve the ids of every word of this document;
          3. store the content as compressed pickled symbol pairs.

        Args:
            words: List of word strings
            path_id: Path ID to associate content with
            content_date: Optional date mentioned in content (None if no date mentioned)

        Returns:
            List of word IDs (integers from words table)

        Note: Content is stored as compressed, pickled symbol pairs:
        [(word_id, punct_before_id, punct_after_id, spacing_id, char_position), ...]
        The content preserves complete formatting information including punctuation, spacing, and positions.

        Note: content_date stores a date mentioned in the content itself.
        If no date is mentioned, it will be empty (None).
        """
        # content_date should remain None if no date was found in content
        # Do not default to today's date
        if words and len(words) > 100000:
            logger.info(
                "Processing large word list (%s words) for path_id %s",
                f"{len(words):,}", path_id,
            )

        # 1. Bulk insert words - the repository batches internally for large lists.
        # Nothing else may run on this connection in between: a failure here
        # aborts the transaction and the caller rolls it back (the previous
        # implementation continued after swallowed errors and referenced ids
        # that no longer existed).
        self.words_repo.bulk_insert_words([(w,) for w in words])

        # 2. Resolve the word ids (only the words of this document are looked up).
        word_ids = self.words_repo.select_content_ids_by_words(words)

        # 3. Store content as compressed symbol pairs.
        self.contents_repo.store_text_content(word_ids, content_date, path_id)

        return word_ids

    def get_content_word_ids(self, path_id: int) -> List[int]:
        """
        Get content as word IDs (numbers from words table).
        
        Args:
            path_id: Path ID to get content for
        
        Returns:
            List of word IDs (integers from words table)
        
        Note: Content consists of numbers (word IDs) from the words table.
        This method returns the raw word IDs without converting to text.
        """
        return self.contents_repo.load_content_word_ids(path_id)
    
    def get_content_as_text(self, path_id: int) -> str:
        """
        Get content as text (converts word IDs to words).
        
        Args:
            path_id: Path ID to get content for
        
        Returns:
            Space-separated string of words
        
        Note: This method retrieves word IDs from content and converts
        them to actual words by looking them up in the words table.
        """
        return self.contents_repo.load_text_content(path_id)
    
    def get_content_as_array(self, path_id: int) -> List[Dict[str, any]]:
        """
        Get content as an array with words, tags, and word order.
        
        Args:
            path_id: Path ID to get content for
        
        Returns:
            List of dictionaries, each containing:
            - word: str - The word text
            - word_id: int - Word ID from words table
            - tags: List[str] - Category names (tags) associated with the word
            - order: int - Position/order of the word in the content (0-indexed)
        
        Example:
            [
                {
                    "word": "example",
                    "word_id": 123,
                    "tags": ["noun", "common"],
                    "order": 0
                },
                {
                    "word": "test",
                    "word_id": 456,
                    "tags": ["verb"],
                    "order": 1
                }
            ]
        
        Note: Content consists of numbers (word IDs) from the words table.
        This method enriches the word IDs with word text, tags (categories), and order.
        """
        # Get word IDs with positions
        word_ids = self.get_content_word_ids(path_id)
        if not word_ids:
            return []
        
        # Get all words dictionary {id: word}
        word_rows = self.words_repo.select_all_words()
        words_dict = dict(word_rows) if word_rows else {}
        
        # Get categories (tags) for all words
        # Build a map of word_id -> list of category names
        tags_map = {}
        unique_word_ids = set(word_ids)
        
        # Get all category-word relationships at once for efficiency
        for word_id in unique_word_ids:
            category_rows = self.words_categorys_repo.get_categories_by_word_id(word_id)
            tags = []
            if category_rows:
                for cat_row in category_rows:
                    if cat_row and len(cat_row) >= 2:
                        # Query returns: (category_id, category_name)
                        category_name = cat_row[1]  # category_name from query
                        tags.append(category_name)
            tags_map[word_id] = tags
        
        # Build result array with word, tags, and order
        result = []
        
        # Import CPU management for large loops
        try:
            from core.resource_coordinator import should_yield, get_yield_duration
            import time
            cpu_management_available = True
        except ImportError:
            cpu_management_available = False
        
        for order, word_id in enumerate(word_ids):
            # Yield periodically during large loops
            if cpu_management_available and order > 0 and order % 1000 == 0:
                if should_yield():
                    time.sleep(get_yield_duration())
            word_text = words_dict.get(word_id, f"[ID:{word_id}]")
            tags = tags_map.get(word_id, [])
            
            result.append({
                "word": word_text,
                "word_id": word_id,
                "tags": tags,
                "order": order
            })
        
        return result
    
    def create_content_from_symbols(
        self,
        symbols: List[Tuple[str, str, str, str, int, int, int]],
        path_id: int,
        content_date: Optional[date] = None
    ) -> List[Tuple[int, Optional[int], Optional[int], int, int]]:
        """
        Create content from extracted symbols.
        
        Args:
            symbols: List of symbol tuples, each as:
                (word, punct_before, punct_after, space, page_number, y_coord, x_coord)
            path_id: Path ID to associate content with
            content_date: Optional date mentioned in content (None if no date mentioned)
        
        Returns:
            List of symbol pairs: (word_id, punct_before_id, punct_after_id, spacing_id, char_position)
        
        Note: This method:
        1. Extracts unique words and punctuation marks
        2. Resolves word IDs (batch operation)
        3. Resolves punctuation IDs (batch operation)
        4. Creates symbol pairs with spatial positions
        5. Stores content as compressed Pickle symbol pairs: [(word_id, punct_before_id, punct_after_id, spacing_id, char_position), ...]
        
        Note: content_date stores a date mentioned in the content itself.
        If no date is mentioned, it will be empty (None).
        """
        # content_date should remain None if no date was found in content
        # Do not default to today's date
        
        if not symbols:
            return []
        
        # Extract unique words and punctuation marks
        unique_words = set()
        unique_punctuation = set()
        
        for word, punct_before, punct_after, space, _, _, _ in symbols:
            if word:
                unique_words.add(word)
            if punct_before:
                unique_punctuation.add(punct_before)
            if punct_after:
                unique_punctuation.add(punct_after)
        
        # Resolve word IDs (batch operation)
        word_id_map = self.words_repo.resolve_word_ids_batch(list(unique_words))
        
        # Resolve punctuation IDs (batch operation)
        punct_id_map = self.punctuation_repo.resolve_punctuation_ids_batch(list(unique_punctuation))
        
        # Create symbol pairs
        symbol_pairs = []
        for word, punct_before, punct_after, space, page_num, y_coord, x_coord in symbols:
            word_id = word_id_map.get(word, 0)
            if word_id == 0:
                continue  # Skip if word not found
            
            punct_before_id = punct_id_map.get(punct_before) if punct_before else None
            punct_after_id = punct_id_map.get(punct_after) if punct_after else None
            spacing_id = self.get_spacing_id(space)
            char_position = self.calculate_char_position(page_num, y_coord, x_coord)
            
            symbol_pairs.append((
                word_id,
                punct_before_id,
                punct_after_id,
                spacing_id,
                char_position
            ))
        
        # Store symbol pairs
        self.contents_repo.store_symbol_pairs(symbol_pairs, content_date, path_id)
        
        return symbol_pairs
    
    def extract_symbols_from_text(
        self,
        text: str,
        page_number: int = 0,
        start_y: int = 0,
        start_x: int = 0,
        line_height: int = 20
    ) -> List[Tuple[str, str, str, str, int, int, int]]:
        """
        Extract symbols from text with spatial coordinates.
        
        Symbol formula: (word, preceding punctuation, following punctuation, space, character position)
        
        Args:
            text: Text to extract symbols from
            page_number: Page number for spatial calculation
            start_y: Starting Y coordinate
            start_x: Starting X coordinate
            line_height: Height of each line (for Y coordinate calculation)
        
        Returns:
            List of symbol tuples: (word, punct_before, punct_after, space, page_number, y_coord, x_coord)
        
        Note:
        - Table cells are separated by tabs (\t)
        - Headings use pipe symbols (|) or newline breaks
        - Preserves punctuation and spaces for accurate reconstruction
        """
        if not text:
            return []
        
        symbols = []
        current_y = start_y
        current_x = start_x
        
        # Split text into lines to handle newlines
        lines = text.split('\n')
        
        # Import CPU management for large text processing
        try:
            from core.resource_coordinator import should_yield, get_yield_duration
            import time
            cpu_management_available = True
        except ImportError:
            cpu_management_available = False
        
        for line_idx, line in enumerate(lines):
            # Yield periodically during large text processing
            if cpu_management_available and line_idx > 0 and line_idx % 500 == 0:
                if should_yield():
                    time.sleep(get_yield_duration())
            if line_idx > 0:
                # Add newline symbol for line breaks (except first line)
                symbols.append(('', '', '', '\n', page_number, current_y, current_x))
                current_y += line_height
                current_x = start_x
            
            # Handle table cells (separated by tabs)
            if '\t' in line:
                cells = line.split('\t')
                for cell_idx, cell in enumerate(cells):
                    # Yield periodically during cell processing
                    if cpu_management_available and cell_idx > 0 and cell_idx % 100 == 0:
                        if should_yield():
                            time.sleep(get_yield_duration())
                    if cell_idx > 0:
                        # Add tab symbol
                        symbols.append(('', '', '', '\t', page_number, current_y, current_x))
                        current_x += 100  # Approximate tab width
                    
                    # Process cell content
                    cell_symbols = self._extract_symbols_from_line(
                        cell, page_number, current_y, current_x
                    )
                    symbols.extend(cell_symbols)
                    if cell_symbols:
                        current_x = cell_symbols[-1][6] + 50  # Update X position
            else:
                # Process regular line
                line_symbols = self._extract_symbols_from_line(
                    line, page_number, current_y, current_x
                )
                symbols.extend(line_symbols)
                if line_symbols:
                    current_x = line_symbols[-1][6] + 50  # Update X position
        
        return symbols
    
    def _extract_symbols_from_line(
        self,
        line: str,
        page_number: int,
        y_coord: int,
        start_x: int
    ) -> List[Tuple[str, str, str, str, int, int, int]]:
        """
        Extract symbols from a single line of text.
        
        Args:
            line: Line of text
            page_number: Page number
            y_coord: Y coordinate
            start_x: Starting X coordinate
        
        Returns:
            List of symbol tuples
        """
        if not line:
            return []
        
        symbols = []
        current_x = start_x
        word_width = 50  # Approximate character width
        
        # Pattern to match words with surrounding punctuation
        # Matches: optional punctuation, word, optional punctuation, optional space
        pattern = r'([^\w\s]*)(\w+)([^\w\s]*)(\s*)'
        
        matches = re.finditer(pattern, line)
        
        for match in matches:
            punct_before = match.group(1) or ''
            word = match.group(2)
            punct_after = match.group(3) or ''
            space = match.group(4) or ''
            
            # Handle pipe symbols (headings)
            if '|' in line and (punct_before == '|' or punct_after == '|'):
                space = '|'
            
            symbols.append((
                word,
                punct_before,
                punct_after,
                space,
                page_number,
                y_coord,
                current_x
            ))
            
            # Update X position (approximate)
            current_x += len(word) * word_width
            if punct_before:
                current_x += len(punct_before) * word_width
            if punct_after:
                current_x += len(punct_after) * word_width
            if space:
                current_x += len(space) * word_width
        
        return symbols
    
    def get_content_symbol_pairs(self, path_id: int) -> List[Tuple[int, Optional[int], Optional[int], int, int]]:
        """
        Get content as symbol pairs.
        
        Args:
            path_id: Path ID to get content for
        
        Returns:
            List of symbol pairs: (word_id, punct_before_id, punct_after_id, spacing_id, char_position)
        """
        return self.contents_repo.load_symbol_pairs(path_id)
    
    def reconstruct_text_from_symbols(self, path_id: int) -> str:
        """
        Reconstruct text from stored symbol pairs.
        
        Args:
            path_id: Path ID to reconstruct content for
        
        Returns:
            Reconstructed text string
        """
        symbol_pairs = self.get_content_symbol_pairs(path_id)
        if not symbol_pairs:
            return ""
        
        # Get word and punctuation dictionaries
        word_rows = self.words_repo.select_all_words()
        words_dict = dict(word_rows) if word_rows else {}
        
        punct_rows = self.punctuation_repo.select_all_punctuation()
        punctuation_dict = {punct_id: punct_text for punct_id, punct_text in punct_rows} if punct_rows else {}
        
        # Sort by char_position to maintain spatial order
        symbol_pairs_sorted = sorted(symbol_pairs, key=lambda x: x[4])  # Sort by char_position
        
        # Reconstruct text
        text_parts = []
        for word_id, punct_before_id, punct_after_id, spacing_id, _ in symbol_pairs_sorted:
            # Add preceding punctuation
            if punct_before_id:
                punct_text = punctuation_dict.get(punct_before_id, '')
                text_parts.append(punct_text)
            
            # Add word
            word_text = words_dict.get(word_id, f"[ID:{word_id}]")
            text_parts.append(word_text)
            
            # Add following punctuation
            if punct_after_id:
                punct_text = punctuation_dict.get(punct_after_id, '')
                text_parts.append(punct_text)
            
            # Add spacing
            if spacing_id == self.SPACING_SPACE:
                text_parts.append(' ')
            elif spacing_id == self.SPACING_TAB:
                text_parts.append('\t')
            elif spacing_id == self.SPACING_NEWLINE:
                text_parts.append('\n')
            elif spacing_id == self.SPACING_PIPE:
                text_parts.append('|')
            # SPACING_NONE adds nothing
        
        return ''.join(text_parts)
    
    # ============================================================
    # CATEGORY OPERATIONS
    # ============================================================

    def create_category(self, category_word: str) -> Optional[int]:
        try:
            word_id = self.words_repo.insert_by_word(category_word)
            return self.categorys_repo.insert_category(word_id)
        except Exception as e:
            print(f"Error creating category: {e}")
            return None

    def link_word_to_category(self, word: str, category_word: str) -> bool:
       
        try:
            word_id = self.words_repo.insert_by_word(word)
            category_word_id = self.words_repo.insert_by_word(category_word)
            
            category_id = self.categorys_repo.select_category_by_word_id(category_word_id)
            
            if category_id:
                self.words_categorys_repo.insert_word_category(word_id, category_id)
                return True
            return False
        except Exception as e:
            print(f"Error linking word to category: {e}")
            return False

    # ============================================================
    # KEYWORD OPERATIONS
    # ============================================================

    def create_keyword(self, keyword_phrase: str, category_word: str) -> bool:
        
        try:
            # Split phrase into words
            words = keyword_phrase.split()
            
            # Bulk insert words
            self.words_repo.bulk_insert_words([(w,) for w in words])
            
            # Get word IDs
            keyword_ids = self.words_repo.select_content_ids_by_words(words)
            
            # Get category ID
            category_word_id = self.words_repo.insert_by_word(category_word)
            category_id = self.categorys_repo.select_category_by_word_id(category_word_id)
            
            # Insert keyword
            self.keywords_repo.insert_keywords(category_id, keyword_ids)
            return True
        except Exception as e:
            print(f"Error creating keyword: {e}")
            return False

    def get_all_keywords(self) -> Dict[int, List[int]]:
      
        return self.keywords_repo.select_all_keywords()

    def get_keywords_as_words(self) -> List[List[str]]:
        
        keywords_dict = self.get_all_keywords()
        keyword_words = []
        
        for kw_id, word_ids in keywords_dict.items():
            # ``word_ids`` are ids: resolve them to text (the previous call to
            # select_content_ids_by_words() treated the ids as words, so this
            # method always returned empty keyword lists).
            words = self.words_repo.select_words_by_ids(word_ids)
            keyword_words.append(words)
        
        return keyword_words

    # ============================================================
    # WORD-PATH RELATIONSHIP
    # ============================================================

    def link_words_to_path(self, path_id: int, content_ids: List[int]) -> int:
        # Build position tracking
        word_positions: Dict[int, List[int]] = {}
        
        # Import CPU management for large loops
        try:
            from core.resource_coordinator import should_yield, get_yield_duration
            import time
            cpu_management_available = True
        except ImportError:
            cpu_management_available = False
        
        for position, word_id in enumerate(content_ids):
            # Yield periodically during large loops
            if cpu_management_available and position > 0 and position % 1000 == 0:
                if should_yield():
                    time.sleep(get_yield_duration())
            word_positions.setdefault(word_id, []).append(position)

        # Prepare bulk data
        bulk_data = [
            (path_id, word_id, len(positions), pack_int_list(positions))
            for word_id, positions in word_positions.items()
        ]
        # print(bulk_data)
        result = self.words_paths_repo.bulk_insert_words_paths(bulk_data)
        # Return number of words linked (or True if no explicit return)
        return len(bulk_data) if result is None else result

    # ============================================================
    # KEYWORD-PATH RELATIONSHIP
    # ============================================================

    def process_keywords_for_path(self, path_id: int, content_ids: List[int]) -> bool:
        """Link the document to the keywords it contains.

        Returns True when at least one keyword matched.  Failures propagate:
        the caller decides (the ingestion path contains them in a savepoint and
        logs them) instead of this method printing and pretending success.
        """
        if True:
            keywords_dict = self.get_all_keywords()

            # Search for keyword patterns in content.  The matcher indexes
            # positions by first id, so a document is not rescanned once per
            # keyword.
            keyword_count = _keyword_occurrence_counts(content_ids, keywords_dict)

            # Insert keyword-path relationships
            if keyword_count:
                self.keywords_paths_repo.bulk_insert_keywords_paths(path_id, keyword_count)
                return True

            return False

    def refresh_keyword_associations(self, keyword_ids=None) -> Dict[str, int]:
        """Reconcile keyword-to-file links after keyword definitions change.

        Keyword links were historically created only while a file was ingested,
        so adding a keyword later left existing files invisible to that keyword.
        Rebuild only the affected keywords and candidate paths immediately.
        """
        try:
            if keyword_ids:
                keyword_rows = []
                for keyword_id in keyword_ids:
                    row = self.keywords_repo.execute(
                        "SELECT id, keyword FROM keywords WHERE id = %s",
                        (int(keyword_id),), fetchone=True,
                    )
                    if row:
                        keyword_rows.append(row)
            else:
                keyword_rows = self.keywords_repo.execute(
                    "SELECT id, keyword FROM keywords", None, fetchall=True
                )

            decoded = {}
            candidate_words = set()
            for keyword_id, blob in keyword_rows or []:
                try:
                    pattern = unpack_int_list(blob) if blob else []
                except Exception:
                    pattern = []
                if pattern:
                    decoded[int(keyword_id)] = pattern
                    candidate_words.update(pattern)
            if not decoded:
                return {"paths_checked": 0, "associations_added": 0}

            # Only paths containing at least one term can match. This avoids
            # rescanning every document when a keyword is added.
            placeholders = ",".join(["%s"] * len(candidate_words))
            candidate_rows = self.words_paths_repo.execute(
                f"SELECT DISTINCT path_id FROM words_paths WHERE word_id IN ({placeholders})",
                tuple(candidate_words), fetchall=True,
            )
            added = 0
            checked = 0
            for (path_id,) in candidate_rows or []:
                positions = self.words_paths_repo.get_word_positions_by_path(path_id)
                if not positions:
                    continue
                max_position = max((max(v) for v in positions.values() if v), default=-1)
                sequence = [None] * (max_position + 1)
                for word_id, indexes in positions.items():
                    for index in indexes:
                        if 0 <= index < len(sequence):
                            sequence[index] = word_id
                matches = _keyword_occurrence_counts(sequence, decoded)
                if matches:
                    self.keywords_paths_repo.bulk_insert_keywords_paths(path_id, matches)
                    added += len(matches)
                checked += 1
            return {"paths_checked": checked, "associations_added": added}
        except Exception:
            logger.exception("Failed to refresh keyword associations")
            raise

    # ============================================================
    # TITLE CONTENT OPERATIONS
    # ============================================================

    def create_title_content(
        self,
        title_words: List[str],
        path_id: int,
        title_status: str = "Main",
        parent_title_id: Optional[int] = None
        ) -> List[int]:
        
        # PRODUCTION: Skip path_id validation to avoid false negatives in aborted transactions
        # If transaction was aborted, the bulk_insert_words or insert_titles_content will fail
        # with InFailedSqlTransaction, which we'll catch and handle properly
        # This prevents "Path ID does not exist" errors when the transaction is actually aborted
        # We trust that path_id exists since it was just created in the same transaction
        
        # Bulk insert words
        word_tuples = [(w,) for w in title_words]
        self.words_repo.bulk_insert_words(word_tuples)

        # Get word IDs
        word_ids = self.words_repo.select_content_ids_by_words(title_words)

        # Insert title content
        self.titles_content_repo.insert_titles_content(
            word_ids, path_id, title_status, parent_title_id
        )

        return word_ids

    def get_title_content(self, record_id: int) -> Optional[Dict]:
       
        return self.titles_content_repo.Get_titles_content(record_id)
    

    # def 

    # ============================================================
    # TRANSACTION/BATCH OPERATIONS
    # ============================================================

    def process_full_document(
        self,
        hash_value: str,
        source_id: int,
        side_id: int,
        file_name: str,
        file_path: str,
        file_size: int,
        file_type: str,
        file_status: str,
        file_date: date,
        content_words: List[str],
        title_words: Optional[List[str]] = None,
        coordinates: Optional[str] = None,
        content_date: Optional[date] = None,
        extraction_provenance: Optional[dict] = None,
        processing_status: str = "discovered",
        status_detail: Optional[str] = None,
        attempts: int = 0,
        raw_text: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Process a complete document with all steps in a single transaction.
        All operations are atomic - either all succeed or all rollback.
        
        Args:
            hash_value: Document hash
            source_id: Source ID
            side_id: Side ID
            file_name: File name
            file_path: File path
            file_size: File size
            file_type: File type
            file_status: File status ('Read' if content exists, 'Unread' otherwise)
            file_date: File creation date (from file system, not metadata)
            content_words: List of content words
            title_words: Optional list of title words
            coordinates: Optional GPS coordinates string (from images or elsewhere)
            content_date: Optional date mentioned in content (None if no date mentioned)
        
        Returns:
            Dictionary with success status and operation results
        
        Note:
            - file_date stores the file's creation date, not any other date
            - file_status is 'Read' if file contains content, otherwise 'Unread'
            - coordinates stores any GPS coordinates in images or elsewhere
            - content_date stores a date mentioned in the content itself. If no date is mentioned, it will be empty (None).
            - extraction_provenance records how each extractor derived its data
              (engine, version, confidence, derived flag). Stored as JSONB in
              paths.extraction_provenance so recognised text is never
              indistinguishable from authored text.
        """
        result = {
            'success': False,
            'hash_id': None,
            'path_id': None,
            'content_ids': None,
            'title_ids': None,
            'warnings': [],
            'error': None
        }

        # INDEX SAFETY: PostgreSQL btree indexes cap entries at ~1/3 of a
        # buffer page (2704 bytes).  A single oversized token (a multi-KB
        # base64/data-URI run survives tokenization as one "word") would
        # otherwise abort the whole document transaction with
        # ProgramLimitExceeded ("index row size ... exceeds btree version 4
        # maximum 2704 for index words_word_key"), so such tokens are
        # dropped from the word index up front.  The raw display store
        # (raw_text) keeps the verbatim text for viewing and in-document
        # search, so nothing is lost except the unindexable blob itself.
        if content_words:
            safe_words = [w for w in content_words if not word_exceeds_db_limit(w)]
            dropped = len(content_words) - len(safe_words)
            if dropped:
                logger.warning(
                    "Dropped %d oversized token(s) from %s exceeding the "
                    "%d-byte PostgreSQL btree index limit; the document is "
                    "stored normally and the raw display text is unaffected.",
                    dropped, file_name, MAX_WORD_BYTES,
                )
            content_words = safe_words
        if title_words:
            title_words = [w for w in title_words if not word_exceeds_db_limit(w)]

        try:
            # One transaction per document: hash, path, content, word index
            # and title commit together or not at all.  Optional/derived
            # steps (raw display text, keywords, title) are contained in
            # savepoints so their failure cannot discard the document or
            # poison the transaction for later statements.
            with self.transaction():
                # 1. Duplicate detection -----------------------------------
                # A hash that already has a stored path means the file was
                # ingested before; report the existing ids instead of
                # creating a second copy.
                existing = self._find_stored_document(hash_value, source_id, side_id)
                if existing is not None:
                    hash_id, path_id = existing
                    result.update(
                        hash_id=hash_id,
                        path_id=path_id,
                        success=True,
                        error="Duplicate file - already processed",
                    )
                    logger.info(
                        "Duplicate file detected: hash=%s..., existing path_id=%s",
                        hash_value[:16], path_id,
                    )
                    return result

                # 2. Hash ---------------------------------------------------
                hash_id = _as_id(self.create_hash(hash_value, source_id, side_id))
                if not hash_id:
                    # ``create_hash`` returns None when the hash already
                    # exists but has no path yet (e.g. a previous attempt was
                    # rolled back): reuse the existing dictionary row.  The
                    # lookup asks for the *hash* id explicitly - the duplicate
                    # helper returns a path id, which is a different id space.
                    hash_id = _as_id(
                        self.hashs_repo.get_hash_id_by_value(
                            hash_value, source_id, side_id
                        )
                    )
                    if hash_id:
                        logger.info(
                            "Reusing existing hash_id=%s (no path stored yet) for %s",
                            hash_id, file_name,
                        )
                if not hash_id or hash_id <= 0:
                    raise QueryError(
                        f"Could not create or resolve a hash record for "
                        f"{file_name} (hash={hash_value[:16]}...)"
                    )

                # The hash must be visible to this transaction before the
                # dependent path row is inserted; a missing row here means
                # the transaction was rolled back underneath us.
                if not self.hashs_repo.get_hash_by_id(hash_id):
                    raise QueryError(
                        f"Hash ID {hash_id} does not exist (transaction may "
                        f"have been rolled back) for file: {file_name}"
                    )
                result['hash_id'] = hash_id

                # 3. Path ---------------------------------------------------
                path_id = _as_id(self.create_path(
                    file_name, file_path, file_size, file_type,
                    file_status, file_date, hash_id,
                    coordinates=coordinates,
                    extraction_provenance=extraction_provenance,
                    processing_status=processing_status,
                    status_detail=status_detail,
                    attempts=attempts
                ))
                if not path_id or path_id <= 0:
                    raise QueryError(
                        f"Failed to create path record (returned: {path_id}) "
                        f"for file: {file_name}"
                    )
                result['path_id'] = path_id

                # 4. Content (word dictionary + compressed symbol pairs) -----
                content_ids = self.create_content(
                    content_words, path_id, content_date=content_date
                )
                result['content_ids'] = content_ids

                # 5. Raw display text (optional) -----------------------------
                # Kept in the same transaction as the word store so the two
                # never diverge, but contained in a savepoint: the word-join
                # reconstruction still displays the document if the raw text
                # is rejected (e.g. payload too large).
                if raw_text:
                    try:
                        with self.savepoint():
                            self.contents_repo.store_raw_content(path_id, raw_text)
                    except TransactionAbortedError:
                        raise
                    except Exception as raw_err:
                        self._note_optional_failure(
                            result, 'raw_text', raw_err, file_name, path_id
                        )

                # 6. Word index (core) ---------------------------------------
                # words_paths powers search; a failure here would leave the
                # document stored but unsearchable, so it must roll back.
                if content_ids:
                    self.link_words_to_path(path_id, content_ids)
                else:
                    logger.warning(
                        "No indexable content for %s (path_id=%s): the file "
                        "is stored but has no word entries.", file_name, path_id,
                    )

                # 7. Keyword index (derived) ---------------------------------
                if content_ids:
                    try:
                        with self.savepoint():
                            self.process_keywords_for_path(path_id, content_ids)
                    except TransactionAbortedError:
                        raise
                    except Exception as kw_err:
                        self._note_optional_failure(
                            result, 'keywords', kw_err, file_name, path_id
                        )

                # 8. Title (derived) -----------------------------------------
                if title_words:
                    try:
                        with self.savepoint():
                            result['title_ids'] = self.create_title_content(
                                title_words, path_id
                            )
                    except TransactionAbortedError:
                        raise
                    except Exception as title_err:
                        self._note_optional_failure(
                            result, 'title', title_err, file_name, path_id
                        )

                result['success'] = True
                logger.info(
                    "Document processed successfully: path_id=%s, hash_id=%s",
                    path_id, hash_id,
                )
                return result

        except Exception as e:
            # The transaction context has already rolled the unit of work
            # back; surface the failure so the caller counts this file as
            # not stored (never as a silent partial write).
            result['error'] = f"{type(e).__name__}: {e}"
            logger.error(
                "Failed to store document '%s': %s: %s",
                file_name, type(e).__name__, e, exc_info=True,
            )
            raise

    def _find_stored_document(self, hash_value, source_id, side_id):
        """Return ``(hash_id, path_id)`` when this file is already stored.

        Both ids are read from the same row (paths and hashs are independent
        id spaces, so they can never be derived from one another).

        ``None`` means no path exists for the hash, so the caller should
        continue with the normal ingest (the hash row alone, without a path,
        is not a stored document - it can be left over from a rolled-back
        attempt and is reused rather than duplicated).
        """
        return self.hashs_repo.get_duplicate_document(hash_value, source_id, side_id)

    @staticmethod
    def _note_optional_failure(result, step, error, file_name, path_id):
        """Record a contained failure of a derived-data step.

        The document is still stored; the warning is logged loudly and carried
        in the result so monitoring can spot systematic degradation instead of
        the failure being silently swallowed.
        """
        message = f"{step} step failed: {type(error).__name__}: {error}"
        result['warnings'].append(message)
        logger.error(
            "Optional %s step failed for file '%s' (path_id=%s), the document "
            "itself is stored: %s",
            step, file_name, path_id, error,
        )

    # ============================================================
    # PUNCTUATION OPERATIONS
    # ============================================================

    def create_punctuation(self, punctuation_text: str) -> Optional[int]:
        """Create or get punctuation entry."""
        try:
            result = self.punctuation_repo.get_or_create_punctuation(punctuation_text)
            if result:
                return result[0] if isinstance(result, tuple) else result
            return None
        except Exception as e:
            logger.error(f"Error creating punctuation: {e}")
            return None

    def get_all_punctuation(self) -> List[Tuple[int, str]]:
        """Get all punctuation entries."""
        return self.punctuation_repo.select_all_punctuation()

    def get_punctuation_by_id(self, punctuation_id: int) -> Optional[Tuple]:
        """Get punctuation by ID."""
        return self.punctuation_repo.get_by_id(punctuation_id)

    def get_punctuation_by_text(self, punctuation_text: str) -> Optional[Tuple]:
        """Get punctuation by text."""
        return self.punctuation_repo.get_by_text(punctuation_text)

    def search_punctuation(self, search: Optional[str] = None, limit: int = 50) -> List[Tuple]:
        """Search punctuation entries."""
        return self.punctuation_repo.search_punctuation(search, limit)

    def update_punctuation(self, punctuation_id: int, punctuation_text: str) -> bool:
        """Update punctuation text."""
        try:
            self.punctuation_repo.update_punctuation(punctuation_id, punctuation_text)
            return True
        except Exception as e:
            logger.error(f"Error updating punctuation: {e}")
            return False

    def delete_punctuation(self, punctuation_id: int) -> bool:
        """Delete punctuation entry."""
        try:
            self.punctuation_repo.delete_punctuation(punctuation_id)
            return True
        except Exception as e:
            logger.error(f"Error deleting punctuation: {e}")
            return False

    # ============================================================
    # ALERT OPERATIONS
    # ============================================================

    def create_alert(
        self,
        alert_type: str,
        priority: str,
        title: str,
        message: str,
        file_id: Optional[int] = None,
        file_name: Optional[str] = None,
        file_path: Optional[str] = None,
        event_date: Optional[date] = None,
        metadata: Optional[Dict[str, any]] = None,
        read: bool = False,
        dismissed: bool = False
        ) -> Optional[int]:
        """Create a new alert."""
        try:
            result = self.alerts_repo.insert_alert(
                alert_type, priority, title, message, file_id, file_name,
                file_path, event_date, metadata, read, dismissed
            )
            if result:
                return result[0] if isinstance(result, tuple) else result
            return None
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            return None

    def get_all_alerts(self) -> List[Tuple]:
        """Get all alerts."""
        return self.alerts_repo.select_all_alerts()

    def get_alert_by_id(self, alert_id: int) -> Optional[Tuple]:
        """Get alert by ID."""
        return self.alerts_repo.get_by_id(alert_id)

    def get_unread_alerts(self, limit: int = 50) -> List[Tuple]:
        """Get unread alerts."""
        return self.alerts_repo.get_unread_alerts(limit)

    def get_active_alerts(self, limit: int = 50) -> List[Tuple]:
        """Get active (not dismissed) alerts."""
        return self.alerts_repo.get_active_alerts(limit)

    def get_alerts_by_file_id(self, file_id: int) -> List[Tuple]:
        """Get alerts by file ID."""
        return self.alerts_repo.get_by_file_id(file_id)

    def get_alerts_by_type(self, alert_type: str, limit: int = 50) -> List[Tuple]:
        """Get alerts by type."""
        return self.alerts_repo.get_by_type(alert_type, limit)

    def get_alerts_by_priority(self, priority: str, limit: int = 50) -> List[Tuple]:
        """Get alerts by priority."""
        return self.alerts_repo.get_by_priority(priority, limit)

    def search_alerts(
        self,
        alert_type: Optional[str] = None,
        priority: Optional[str] = None,
        read: Optional[bool] = None,
        dismissed: Optional[bool] = None,
        search_text: Optional[str] = None,
        limit: int = 50
    ) -> List[Tuple]:
        """Search alerts with multiple filters."""
        return self.alerts_repo.search_alerts(
            alert_type, priority, read, dismissed, search_text, limit
        )

    def mark_alert_as_read(self, alert_id: int) -> bool:
        """Mark alert as read."""
        try:
            self.alerts_repo.mark_as_read(alert_id)
            return True
        except Exception as e:
            logger.error(f"Error marking alert as read: {e}")
            return False

    def mark_alert_as_dismissed(self, alert_id: int) -> bool:
        """Mark alert as dismissed."""
        try:
            self.alerts_repo.mark_as_dismissed(alert_id)
            return True
        except Exception as e:
            logger.error(f"Error marking alert as dismissed: {e}")
            return False

    def update_alert(
        self,
        alert_id: int,
        alert_type: Optional[str] = None,
        priority: Optional[str] = None,
        title: Optional[str] = None,
        message: Optional[str] = None,
        file_id: Optional[int] = None,
        file_name: Optional[str] = None,
        file_path: Optional[str] = None,
        event_date: Optional[date] = None,
        metadata: Optional[Dict[str, any]] = None,
        read: Optional[bool] = None,
        dismissed: Optional[bool] = None
    ) -> bool:
        """Update alert."""
        try:
            self.alerts_repo.update_alert(
                alert_id, alert_type, priority, title, message, file_id,
                file_name, file_path, event_date, metadata, read, dismissed
            )
            return True
        except Exception as e:
            logger.error(f"Error updating alert: {e}")
            return False

    def delete_alert(self, alert_id: int) -> bool:
        """Delete alert."""
        try:
            self.alerts_repo.delete_alert(alert_id)
            return True
        except Exception as e:
            logger.error(f"Error deleting alert: {e}")
            return False

    def count_unread_alerts(self) -> int:
        """Count unread alerts."""
        return self.alerts_repo.count_unread()

    def count_active_alerts(self) -> int:
        """Count active (not dismissed) alerts."""
        return self.alerts_repo.count_active()
        
