from datetime import date
from typing import List, Optional, Dict, Tuple
from contextlib import contextmanager
import re
import logging
import psycopg2

from database.database.database import Database
from database.exceptions import QueryError

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


class ContentDBService:

    def __init__(self, db: Optional[Database] = None):
      
        self.db = db or Database()
        
        self._init_repositories()
    
    @contextmanager
    def transaction(self):
        """
        Transaction context manager for service-level operations.
        All repository operations within this context share the same transaction.
        
        Thread-safe: Creates new repository instances with transaction connection,
        avoiding modification of shared repository state.
        
        Usage:
            with service.transaction():
                service.create_hash(...)
                service.create_path(...)
                # All operations commit together or rollback on error
        """
        
        conn = None
        original_repos = {}
        transactional_repos = {}
        
        try:
            conn = self.db.connect()
            
            # Create new repository instances with transaction connection
            # This avoids modifying shared repository state and is thread-safe
            repo_names = ['sources_repo', 'sides_repo', 'hashs_repo', 'paths_repo', 
                         'words_repo', 'contents_repo', 'words_categorys_repo', 
                         'categorys_repo', 'keywords_repo', 'keywords_paths_repo',
                         'words_paths_repo', 'titles_content_repo', 'punctuation_repo',
                         'alerts_repo']
            
            for repo_name in repo_names:
                original_repo = getattr(self, repo_name, None)
                if original_repo:
                    # Store original repo
                    original_repos[repo_name] = original_repo
                    # Create new repository instance with transaction connection
                    repo_class = original_repo.__class__
                    transactional_repo = repo_class(self.db, connection=conn)
                    transactional_repos[repo_name] = transactional_repo
                    # Temporarily replace repo with transactional version
                    setattr(self, repo_name, transactional_repo)
            
            try:
                yield self
                # Only commit if we got here without exceptions
                if conn and not conn.closed:
                    try:
                        conn.commit()
                        logger.debug("Service transaction committed successfully")
                    except (psycopg2.errors.InFailedSqlTransaction, 
                            psycopg2.errors.IntegrityError,
                            psycopg2.errors.ForeignKeyViolation) as commit_err:
                        # Transaction is aborted or has constraint violations - rollback
                        logger.error(f"Commit failed (transaction error): {commit_err}, rolling back")
                        try:
                            conn.rollback()
                        except:
                            pass
                        raise
                    except Exception as commit_err:
                        # Check if commit failed due to aborted transaction
                        error_str = str(commit_err).lower()
                        if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                            logger.error(f"Commit failed (transaction aborted): {commit_err}, rolling back")
                            try:
                                conn.rollback()
                            except:
                                pass
                            raise psycopg2.errors.InFailedSqlTransaction(f"Transaction was aborted: {commit_err}")
                        logger.error(f"Commit failed: {commit_err}, rolling back")
                        try:
                            conn.rollback()
                        except:
                            pass
                        raise
            except (psycopg2.errors.InFailedSqlTransaction, 
                    psycopg2.errors.ForeignKeyViolation,
                    psycopg2.errors.IntegrityError) as e:
                # PRODUCTION: Immediate rollback for transaction errors
                try:
                    if conn and not conn.closed:
                        conn.rollback()
                        logger.error(f"Service transaction rolled back (transaction error): {e}")
                    else:
                        logger.warning(f"Connection already closed, skipping rollback: {e}")
                except Exception as rollback_error:
                    logger.error(f"Error during rollback: {rollback_error}")
                # Re-raise the original exception so calling code knows transaction failed
                raise
            except Exception as e:
                # PRODUCTION: Check if this is a QueryError wrapping a database error
                if isinstance(e, QueryError):
                    # QueryError wraps database errors - check if it's a transaction error
                    error_str = str(e).lower()
                    if any(keyword in error_str for keyword in ['foreign key', 'transaction aborted', 'violates constraint', 'integrity', 'temp table', 'copy operation']):
                        try:
                            if conn and not conn.closed:
                                conn.rollback()
                                logger.error(f"Service transaction rolled back (QueryError): {e}")
                        except Exception as rollback_error:
                            logger.error(f"Error during rollback: {rollback_error}")
                        raise
                
                # Check if this is a transaction-aborting error
                error_str = str(e).lower()
                if 'current transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                    try:
                        if conn and not conn.closed:
                            conn.rollback()
                            logger.error(f"Service transaction rolled back (aborted): {e}")
                    except Exception as rollback_error:
                        logger.error(f"Error during rollback: {rollback_error}")
                else:
                    # For other errors, still try to rollback
                    try:
                        if conn and not conn.closed:
                            conn.rollback()
                            logger.error(f"Service transaction rolled back: {e}")
                    except Exception as rollback_error:
                        logger.error(f"Error during rollback: {rollback_error}")
                # Re-raise the original exception so calling code knows transaction failed
                raise
            finally:
                # Clean up any temp tables that might have been created
                # This ensures temp tables don't persist and cause issues for subsequent operations
                if conn and not conn.closed:
                    try:
                        cleanup_cur = conn.cursor()
                        try:
                            # Drop temp table if it exists (non-blocking)
                            cleanup_cur.execute("DROP TABLE IF EXISTS tmp_words")
                            logger.debug("Cleaned up temp table tmp_words")
                        except Exception:
                            # Ignore errors - temp table might not exist or transaction might be aborted
                            pass
                        finally:
                            try:
                                cleanup_cur.close()
                            except:
                                pass
                    except Exception:
                        # Ignore cleanup errors - connection might be in bad state
                        pass
                
                # Restore original repository instances
                for repo_name in original_repos.keys():
                    setattr(self, repo_name, original_repos[repo_name])
        except Exception:
            # Re-raise transaction errors
            raise
        finally:
            # Always return connection to pool, even on error
            # But first check if it's in a valid state and clean up
            if conn:
                try:
                    # If connection is in a bad state, clean it up before returning to pool
                    if conn.closed:
                        logger.debug("Connection already closed, not returning to pool")
                    else:
                        # Ensure transaction is rolled back if still active and clean up temp tables
                        try:
                            # Check if connection is in a transaction or error state
                            # Use transaction_status (available in psycopg2 2.5+) instead of status
                            from psycopg2 import extensions
                            
                            # PRODUCTION: Check transaction status using version-compatible method
                            # Method 1: Try modern transaction_status (psycopg2 2.5+)
                            if hasattr(conn, 'info') and hasattr(conn.info, 'transaction_status'):
                                transaction_status = conn.info.transaction_status
                                # If in error state, rollback immediately
                                if hasattr(extensions, 'TRANSACTION_STATUS_INERROR'):
                                    if transaction_status == extensions.TRANSACTION_STATUS_INERROR:
                                        try:
                                            conn.rollback()
                                            logger.debug("Rolled back connection in error state before returning")
                                        except Exception as rollback_err:
                                            logger.warning(f"Failed to rollback connection in error state: {rollback_err}")
                                            # Connection is bad - close it instead of returning
                                            try:
                                                conn.close()
                                            except:
                                                pass
                                            return
                            
                            # PRODUCTION: Test transaction state with a simple query
                            # This will detect aborted transactions regardless of psycopg2 version
                            try:
                                test_cur = conn.cursor()
                                test_cur.execute("SELECT 1")
                                test_cur.close()
                            except (psycopg2.errors.InFailedSqlTransaction, Exception) as test_err:
                                # Transaction is aborted - rollback
                                error_str = str(test_err).lower()
                                if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                                    try:
                                        conn.rollback()
                                        logger.debug("Rolled back aborted transaction before returning connection")
                                    except Exception as rollback_err:
                                        logger.warning(f"Failed to rollback aborted transaction: {rollback_err}")
                                        # If rollback fails, connection might be bad - close it
                                        try:
                                            conn.close()
                                        except:
                                            pass
                                        return
                            
                            # Clean up any temp tables before returning connection to pool
                            # This prevents temp tables from persisting and causing issues
                            try:
                                cleanup_cur = conn.cursor()
                                try:
                                    cleanup_cur.execute("DROP TABLE IF EXISTS tmp_words")
                                    logger.debug("Cleaned up temp table before returning connection to pool")
                                except Exception:
                                    # Ignore errors - temp table might not exist
                                    pass
                                finally:
                                    try:
                                        cleanup_cur.close()
                                    except:
                                        pass
                            except Exception:
                                # Ignore cleanup errors - connection might be in bad state
                                pass
                                
                        except Exception as cleanup_err:
                            logger.warning(f"Error during connection cleanup: {cleanup_err}")
                            # Continue to try returning connection even if cleanup failed
                            # putconn will handle bad connections appropriately
                        
                        # CRITICAL: Always try to return connection to pool, even if cleanup failed
                        # putconn() handles bad connections gracefully
                        try:
                            self.db.putconn(conn)
                            logger.debug("Connection returned to pool")
                        except Exception as put_err:
                            logger.error(f"Error returning connection to pool: {put_err}")
                            # If we can't return it, close it to prevent leak
                            try:
                                if not conn.closed:
                                    conn.close()
                                    logger.debug("Closed connection that couldn't be returned to pool")
                            except Exception as close_err:
                                logger.error(f"Error closing connection: {close_err}")
                except Exception as e:
                    logger.error(f"Error in transaction finally block: {e}")
                    # Try to close connection if we can't return it
                    if conn and not conn.closed:
                        try:
                            conn.close()
                        except:
                            pass

    def _init_repositories(self):
        """Initialize all repository instances."""
        self.sources_repo = SourcesRepository(self.db)
        self.sides_repo = SidesRepository(self.db)
        self.hashs_repo = HashsRepository(self.db)
        self.paths_repo = PathsRepository(self.db)
        self.words_repo = WordsRepository(self.db)
        self.contents_repo = ContentsRepository(self.db)
        self.words_categorys_repo = WordsCategorysRepository(self.db)
        self.categorys_repo = CategorysRepository(self.db)
        self.keywords_repo = KeywordsRepository(self.db)
        self.keywords_paths_repo = KeywordsPathsRepository(self.db)
        self.words_paths_repo = WordsPathsRepository(self.db)
        self.titles_content_repo = TitlesContentRepository(self.db)
        self.punctuation_repo = PunctuationRepository(self.db)
        self.alerts_repo = AlertsRepository(self.db)

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

        try:
            # PRODUCTION: For very large word lists, process in batches to prevent memory issues
            # Bulk insert words - repository handles batching internally for large lists
            word_tuples = [(w,) for w in words]
            
            # Log if this is a very large word list
            if len(words) > 100000:
                logger.info(f"Processing large word list ({len(words):,} words) for path_id {path_id}")
            
            self.words_repo.bulk_insert_words(word_tuples)
        except (psycopg2.errors.InFailedSqlTransaction, QueryError) as bulk_err:
            # Transaction aborted or bulk insert failed - re-raise immediately
            error_str = str(bulk_err).lower()
            if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                logger.error(f"Transaction aborted during bulk word insert: {bulk_err}")
                raise
            # Check if it's a CSV/format error
            if 'extra data' in error_str or 'badcopyfileformat' in error_str or 'csv' in error_str:
                logger.error(f"CSV format error during bulk word insert: {bulk_err}")
                raise QueryError(f"Failed to insert words due to format error (likely contains unescaped commas or special characters): {bulk_err}") from bulk_err
            raise
        except Exception as bulk_err:
            # Check if it's a transaction abort error
            error_str = str(bulk_err).lower()
            if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                logger.error(f"Transaction aborted during bulk word insert: {bulk_err}")
                raise QueryError(f"Transaction aborted during bulk word insert: {bulk_err}") from bulk_err
            # Check if it's a CSV/format error
            if 'extra data' in error_str or 'badcopyfileformat' in error_str or 'csv' in error_str:
                logger.error(f"CSV format error during bulk word insert: {bulk_err}")
                raise QueryError(f"Failed to insert words due to format error (likely contains unescaped commas or special characters): {bulk_err}") from bulk_err
            raise

        # PRODUCTION: Get word IDs after bulk insert
        # IMPORTANT: Ensure COPY operation is fully completed and cursor is closed
        # before executing SELECT query to avoid "another command is already in progress"
        try:
            # Get word IDs (numbers from words table)
            # The bulk_insert_words should have properly closed its cursor
            word_ids = self.words_repo.select_content_ids_by_words(words)
        except (psycopg2.errors.InFailedSqlTransaction, QueryError) as select_err:
            # Transaction aborted - re-raise immediately
            error_str = str(select_err).lower()
            if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                logger.error(f"Transaction aborted during word ID selection: {select_err}")
                raise
            # Check for "another command is already in progress" - cursor conflict
            if 'another command is already in progress' in error_str:
                logger.warning(f"Cursor conflict during word ID selection, retrying: {select_err}")
                # Retry once after a brief delay to allow cursor cleanup
                import time
                time.sleep(0.05)  # 50ms delay
                try:
                    word_ids = self.words_repo.select_content_ids_by_words(words)
                except Exception as retry_err:
                    logger.error(f"Word ID selection failed on retry: {retry_err}")
                    raise QueryError(f"Word ID selection failed after retry: {retry_err}") from retry_err
            else:
                raise
        except Exception as select_err:
            error_str = str(select_err).lower()
            if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                logger.error(f"Transaction aborted during word ID selection: {select_err}")
                raise QueryError(f"Transaction aborted during word ID selection: {select_err}") from select_err
            # Check for "another command is already in progress" - cursor conflict
            if 'another command is already in progress' in error_str:
                logger.warning(f"Cursor conflict during word ID selection, retrying: {select_err}")
                # Retry once after a brief delay to allow cursor cleanup
                import time
                time.sleep(0.05)  # 50ms delay
                try:
                    word_ids = self.words_repo.select_content_ids_by_words(words)
                except Exception as retry_err:
                    logger.error(f"Word ID selection failed on retry: {retry_err}")
                    raise QueryError(f"Word ID selection failed after retry: {retry_err}") from retry_err
            else:
                raise
            raise
        
        try:
            # Store content as word IDs (compressed and pickled)
            self.contents_repo.store_text_content(word_ids, content_date, path_id)
        except (psycopg2.errors.InFailedSqlTransaction, QueryError) as store_err:
            # Transaction aborted - re-raise immediately
            error_str = str(store_err).lower()
            if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                logger.error(f"Transaction aborted during content storage: {store_err}")
                raise
            raise
        except Exception as store_err:
            error_str = str(store_err).lower()
            if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                logger.error(f"Transaction aborted during content storage: {store_err}")
                raise QueryError(f"Transaction aborted during content storage: {store_err}") from store_err
            raise

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
            words = self.words_repo.select_content_ids_by_words(word_ids)
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
       
        try:
            keywords_dict = self.get_all_keywords()
            keyword_count: Dict[int, int] = {}

            # Search for keyword patterns in content
            for kw_id, kw_pattern in keywords_dict.items():
                pattern_length = len(kw_pattern)
                
                # Slide through content looking for pattern
                for i in range(len(content_ids) - pattern_length + 1):
                    if content_ids[i:i + pattern_length] == kw_pattern:
                        keyword_count.setdefault(kw_id, 0)
                        keyword_count[kw_id] += 1

            # Insert keyword-path relationships
            if keyword_count:
                self.keywords_paths_repo.bulk_insert_keywords_paths(path_id, keyword_count)
                return True
            
            return False
        except Exception as e:
            print(f"Error processing keywords for path: {e}")
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
                matches = {}
                for keyword_id, pattern in decoded.items():
                    length = len(pattern)
                    count = sum(
                        1 for i in range(len(sequence) - length + 1)
                        if sequence[i:i + length] == pattern
                    )
                    if count:
                        matches[keyword_id] = count
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

        # Use service-level transaction for atomicity
        try:
            with self.transaction():
                # PRODUCTION: Track transaction state to prevent continuing after abort
                transaction_aborted = False
                
                # PRODUCTION: 1. Create hash (or get existing)
                # Check for duplicates first (before any operations that might abort transaction)
                try:
                    # Check for duplicate hash first - this is a read operation, less likely to abort
                    existing_hash_id = self.hashs_repo.check_duplicate(hash_value, source_id, side_id)
                    if existing_hash_id:
                        # Normalize existing_hash_id
                        existing_hash_id = existing_hash_id[0] if isinstance(existing_hash_id, tuple) else existing_hash_id
                        # Get existing path_id for this hash
                        existing_path_id = self.get_path_id_by_hash_id(existing_hash_id)
                        if existing_path_id:
                            # Normalize existing_path_id
                            existing_path_id = existing_path_id[0] if isinstance(existing_path_id, tuple) else existing_path_id
                            result['hash_id'] = existing_hash_id
                            result['path_id'] = existing_path_id
                            result['success'] = True
                            result['error'] = "Duplicate file - already processed"
                            logger.info(f"Duplicate file detected: hash={hash_value[:16]}..., existing path_id={existing_path_id}")
                            return result
                except (psycopg2.errors.InFailedSqlTransaction, QueryError) as dup_check_err:
                    # PRODUCTION: Transaction aborted during duplicate check - re-raise immediately
                    error_str = str(dup_check_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        result['error'] = f"Transaction aborted during duplicate check: {dup_check_err}"
                        logger.error(f"Transaction aborted checking duplicate for file: {file_name}, error={dup_check_err}")
                        raise
                    raise
                except Exception as dup_check_err:
                    # PRODUCTION: Check if it's a transaction abort error
                    error_str = str(dup_check_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        result['error'] = f"Transaction aborted during duplicate check: {dup_check_err}"
                        logger.error(f"Transaction aborted checking duplicate for file: {file_name}, error={dup_check_err}")
                        raise QueryError(f"Transaction aborted during duplicate check: {dup_check_err}") from dup_check_err
                    # For other errors during duplicate check, log but continue (might be a different issue)
                    logger.debug(f"Error checking duplicate (non-critical): {dup_check_err}")
                
                # Create new hash if not duplicate
                try:
                    hash_id = self.create_hash(hash_value, source_id, side_id)
                except (psycopg2.errors.InFailedSqlTransaction, QueryError) as hash_err:
                    # PRODUCTION: Transaction already aborted or hash creation failed
                    error_str = str(hash_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        result['error'] = f"Transaction aborted during hash creation: {hash_err}"
                        logger.error(f"Transaction aborted creating hash for file: {file_name}, error={hash_err}")
                        raise
                    raise
                except Exception as hash_err:
                    # PRODUCTION: Check if it's a transaction abort error
                    error_str = str(hash_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        result['error'] = f"Transaction aborted during hash creation: {hash_err}"
                        logger.error(f"Transaction aborted creating hash for file: {file_name}, error={hash_err}")
                        raise QueryError(f"Transaction aborted during hash creation: {hash_err}") from hash_err
                    # Re-raise other exceptions
                    raise
                
                # PRODUCTION: Normalize hash_id (might be tuple or int)
                if hash_id:
                    hash_id = hash_id[0] if isinstance(hash_id, tuple) else hash_id
                
                # PRODUCTION: If hash_id is None or 0, it means hash already exists (duplicate)
                # This should have been caught by the duplicate check above, but handle it here as fallback
                if not hash_id or hash_id <= 0:
                    # Hash already exists - try to get existing hash_id and path_id
                    # This is a fallback in case duplicate check above didn't catch it
                    try:
                        existing_hash_id = self.hashs_repo.check_duplicate(hash_value, source_id, side_id)
                        if existing_hash_id:
                            # Normalize existing_hash_id
                            existing_hash_id = existing_hash_id[0] if isinstance(existing_hash_id, tuple) else existing_hash_id
                            # Get existing path_id for this hash
                            existing_path_id = self.get_path_id_by_hash_id(existing_hash_id)
                            if existing_path_id:
                                # Normalize existing_path_id
                                existing_path_id = existing_path_id[0] if isinstance(existing_path_id, tuple) else existing_path_id
                                result['hash_id'] = existing_hash_id
                                result['path_id'] = existing_path_id
                                result['success'] = True
                                result['error'] = "Duplicate file - already processed"
                                logger.info(f"Duplicate file detected (fallback): hash={hash_value[:16]}..., existing path_id={existing_path_id}")
                                return result
                            else:
                                # Hash exists but no path - use the existing hash_id
                                hash_id = existing_hash_id
                                logger.info(f"Using existing hash_id={hash_id} (no path found)")
                    except (psycopg2.errors.InFailedSqlTransaction, QueryError) as dup_err:
                        # PRODUCTION: Transaction aborted during duplicate check - re-raise immediately
                        error_str = str(dup_err).lower()
                        if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                            result['error'] = f"Transaction aborted during duplicate check: {dup_err}"
                            logger.error(f"Transaction aborted checking duplicate for file: {file_name}, error={dup_err}")
                            raise
                        raise
                    except Exception as dup_err:
                        # PRODUCTION: Check if it's a transaction abort error
                        error_str = str(dup_err).lower()
                        if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                            result['error'] = f"Transaction aborted during duplicate check: {dup_err}"
                            logger.error(f"Transaction aborted checking duplicate for file: {file_name}, error={dup_err}")
                            raise QueryError(f"Transaction aborted during duplicate check: {dup_err}") from dup_err
                        # For other errors, log warning but continue (might be a data integrity issue)
                        logger.warning(f"Error checking duplicate (fallback): {dup_err}")
                        # If we can't get existing hash_id, raise error
                        raise QueryError(f"Hash insert returned None but duplicate check failed: {dup_err}") from dup_err
                
                # Validate hash_id is valid before proceeding
                if not hash_id or hash_id <= 0:
                    # Raise exception to ensure transaction rollback
                    error_msg = f"Invalid hash_id returned: {hash_id} for file: {file_name}"
                    logger.error(error_msg)
                    raise QueryError(error_msg)
                
                result['hash_id'] = hash_id

                # 2. Create path (with validated hash_id)
                # Verify hash_id exists before creating path (defensive check)
                try:
                    # Quick check to ensure hash_id exists in current transaction
                    hash_check = self.hashs_repo.get_hash_by_id(hash_id)
                    if not hash_check:
                        error_msg = f"Hash ID {hash_id} does not exist (transaction may have been rolled back)"
                        logger.error(error_msg)
                        raise QueryError(error_msg)
                except (psycopg2.errors.InFailedSqlTransaction, QueryError) as check_err:
                    # Transaction aborted during hash check
                    error_str = str(check_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        result['error'] = f"Transaction aborted during hash verification: {check_err}"
                        logger.error(f"Transaction aborted verifying hash for file: {file_name}, hash_id={hash_id}, error={check_err}")
                        raise
                    raise
                
                path_id = None
                try:
                    path_id = self.create_path(
                        file_name, file_path, file_size, file_type,
                        file_status, file_date, hash_id,
                        coordinates=coordinates,
                        extraction_provenance=extraction_provenance,
                        processing_status=processing_status,
                        status_detail=status_detail,
                        attempts=attempts
                    )
                    # Normalize path_id
                    if path_id:
                        path_id = path_id[0] if isinstance(path_id, tuple) else path_id
                except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.IntegrityError) as fk_err:
                    result['error'] = f"Foreign key violation creating path (hash_id={hash_id} may not exist): {fk_err}"
                    logger.error(f"Foreign key violation creating path for file: {file_name}, hash_id={hash_id}, error={fk_err}")
                    # Verify hash_id one more time - it might have been rolled back
                    try:
                        hash_check = self.hashs_repo.get_hash_by_id(hash_id)
                        if not hash_check:
                            logger.error(f"Hash ID {hash_id} confirmed missing - transaction was rolled back")
                    except:
                        pass
                    # Re-raise to ensure transaction rollback - don't return here
                    raise
                except (psycopg2.errors.InFailedSqlTransaction,) as tx_err:
                    # Transaction is already aborted - don't proceed
                    result['error'] = f"Transaction aborted before path creation: {tx_err}"
                    logger.error(f"Transaction aborted creating path for file: {file_name}, error={tx_err}")
                    # Re-raise to ensure transaction rollback
                    raise
                except Exception as path_err:
                    # Check if it's a transaction abort or wrapped foreign key violation
                    error_str = str(path_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        result['error'] = f"Transaction aborted creating path: {path_err}"
                        logger.error(f"Transaction aborted creating path for file: {file_name}, error={path_err}")
                        # Re-raise to ensure transaction rollback
                        raise
                    if 'foreign key' in error_str or 'violates foreign key constraint' in error_str:
                        result['error'] = f"Foreign key violation creating path (hash_id={hash_id} may not exist): {path_err}"
                        logger.error(f"Foreign key violation creating path for file: {file_name}, hash_id={hash_id}, error={path_err}")
                        # Re-raise to ensure transaction rollback
                        raise
                    # Re-raise other exceptions
                    raise
                
                # Validate path_id was created successfully
                # If transaction was aborted, path_id might be None or invalid
                if not path_id or path_id <= 0:
                    # Raise exception to ensure transaction rollback
                    error_msg = f"Failed to create path record (returned: {path_id}) for file: {file_name}"
                    logger.error(error_msg)
                    raise QueryError(error_msg)
                
                result['path_id'] = path_id

                # 3. Create content (only if path_id is valid)
                # PRODUCTION: Catch transaction abort errors and stop immediately
                # If transaction is aborted, don't continue with word linking or title creation
                # content_date stores a date mentioned in the content itself. If no date is mentioned, it will be empty (None).
                content_ids = None
                transaction_aborted = False
                try:
                    content_ids = self.create_content(content_words, path_id, content_date=content_date)
                    result['content_ids'] = content_ids
                except (psycopg2.errors.InFailedSqlTransaction, QueryError) as tx_err:
                    # PRODUCTION: Transaction aborted during content creation - stop immediately
                    transaction_aborted = True
                    result['error'] = f"Transaction aborted during content creation: {tx_err}"
                    logger.error(f"Transaction aborted creating content for file: {file_name}, path_id={path_id}, error={tx_err}")
                    # Re-raise to ensure transaction rollback - don't continue with word linking or title
                    raise
                except Exception as content_err:
                    # PRODUCTION: Check if it's a transaction abort error
                    error_str = str(content_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        transaction_aborted = True
                        result['error'] = f"Transaction aborted during content creation: {content_err}"
                        logger.error(f"Transaction aborted creating content for file: {file_name}, path_id={path_id}, error={content_err}")
                        # Re-raise to ensure transaction rollback
                        raise QueryError(f"Transaction aborted during content creation: {content_err}") from content_err
                    # Check for COPY errors specifically (includes "no copy in progress")
                    if 'no copy in progress' in error_str or ('copy' in error_str and 'bulk' in error_str):
                        transaction_aborted = True
                        result['error'] = f"Bulk insert failed during content creation: {content_err}"
                        logger.error(f"Bulk insert failed creating content for file: {file_name}, path_id={path_id}, error={content_err}")
                        raise QueryError(f"Bulk insert failed during content creation: {content_err}") from content_err
                    # Re-raise other exceptions to let transaction handler deal with them
                    raise
                
                # PRODUCTION: Only continue if transaction is still valid
                if transaction_aborted:
                    # Transaction was aborted - don't continue
                    raise QueryError("Transaction aborted, cannot continue with word linking or title creation")

                # 3.5 Store the structured raw text for display fidelity
                # (contents_raw, migration m0010). Same transaction as the
                # word-ID store so the two never diverge. Failure here must
                # NOT fail the ingest - the word-join fallback still works.
                if raw_text:
                    try:
                        self.contents_repo.store_raw_content(path_id, raw_text)
                    except psycopg2.errors.InFailedSqlTransaction:
                        # The transaction is already aborted - re-raise so the
                        # whole ingest rolls back (never half-store).
                        raise
                    except Exception as raw_store_err:
                        # Non-aborting failure (e.g. oversized payload): the
                        # word-join fallback still displays, so continue.
                        logger.warning(
                            "Could not store raw display text for file %s (path_id=%s): %s",
                            file_name, path_id, raw_store_err,
                        )

                # 4. Link words to path (only if path_id and content_ids are valid)
                # PRODUCTION: Only proceed if content_ids were successfully created and transaction is still valid
                if content_ids and not transaction_aborted:
                    try:
                        self.link_words_to_path(path_id, content_ids)

                        # 5. Process keywords
                        self.process_keywords_for_path(path_id, content_ids)
                    except (psycopg2.errors.InFailedSqlTransaction, QueryError) as tx_err:
                        # PRODUCTION: Transaction aborted during word linking - stop immediately
                        transaction_aborted = True
                        result['error'] = f"Transaction aborted during word linking: {tx_err}"
                        logger.error(f"Transaction aborted linking words for file: {file_name}, path_id={path_id}, error={tx_err}")
                        # Re-raise to ensure transaction rollback - don't continue with title
                        raise
                    except Exception as link_err:
                        # PRODUCTION: Check if it's a transaction abort or foreign key error
                        error_str = str(link_err).lower()
                        if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                            transaction_aborted = True
                            result['error'] = f"Transaction aborted during word linking: {link_err}"
                            logger.error(f"Transaction aborted linking words for file: {file_name}, path_id={path_id}, error={link_err}")
                            # Re-raise to ensure transaction rollback
                            raise QueryError(f"Transaction aborted during word linking: {link_err}") from link_err
                        # Check for foreign key violations (path might not exist due to rollback)
                        if 'foreign key' in error_str or 'violates foreign key constraint' in error_str:
                            transaction_aborted = True
                            result['error'] = f"Foreign key violation linking words (path_id={path_id} may not exist due to transaction rollback): {link_err}"
                            logger.error(f"Foreign key violation linking words for file: {file_name}, path_id={path_id}, error={link_err}")
                            # Re-raise to ensure transaction rollback
                            raise QueryError(f"Foreign key violation during word linking: {link_err}") from link_err
                        # Re-raise other exceptions
                        raise

                # 6. Create title if provided
                # PRODUCTION: Only create title if transaction is still valid
                # Skip if transaction was aborted during content creation or word linking
                if title_words and not transaction_aborted:
                    try:
                        # PRODUCTION: Don't validate path_id - if transaction was aborted,
                        # create_title_content will fail with InFailedSqlTransaction
                        # We trust that path_id exists since we just created it in this transaction
                        title_ids = self.create_title_content(title_words, path_id)
                        result['title_ids'] = title_ids
                    except (psycopg2.errors.InFailedSqlTransaction, QueryError) as tx_err:
                        # Transaction aborted during title creation - re-raise to ensure transaction rollback
                        error_str = str(tx_err).lower()
                        if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                            logger.error(f"Transaction aborted during title creation for file: {file_name}, path_id={path_id}, error={tx_err}")
                        else:
                            logger.error(f"QueryError during title creation for file: {file_name}, path_id={path_id}, error={tx_err}")
                        # Re-raise to ensure transaction rollback
                        raise
                    except Exception as title_err:
                        error_str = str(title_err).lower()
                        if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                            logger.error(f"Transaction aborted during title creation for file: {file_name}, path_id={path_id}, error={title_err}")
                            # Re-raise to ensure transaction rollback
                            raise QueryError(f"Transaction aborted during title creation: {title_err}") from title_err
                        if 'foreign key' in error_str or 'violates foreign key constraint' in error_str:
                            logger.error(f"Foreign key violation during title creation for file: {file_name}, path_id={path_id}, error={title_err}")
                            # Re-raise to ensure transaction rollback
                            raise QueryError(f"Foreign key violation during title creation: {title_err}") from title_err
                        # For other title creation errors, log and re-raise to ensure transaction rollback
                        logger.error(f"Error creating title for file: {file_name}, path_id={path_id}, error={title_err}")
                        raise QueryError(f"Error creating title: {title_err}") from title_err

                result['success'] = True
                logger.info(f"Document processed successfully: path_id={path_id}, hash_id={hash_id}")
                return result

        except (psycopg2.errors.InFailedSqlTransaction, 
                psycopg2.errors.ForeignKeyViolation,
                psycopg2.errors.IntegrityError) as db_err:
            # Database constraint violation - transaction context manager will rollback
            logger.error(f"Database error processing document: {db_err}")
            result['error'] = f"Database error: {db_err}"
            # Re-raise so transaction context manager can rollback
            raise
        except Exception as e:
            # Check if it's a wrapped database error (QueryError wraps psycopg2 errors)
            if isinstance(e, QueryError):
                # QueryError wraps database errors - check the underlying error
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['foreign key', 'transaction aborted', 'violates constraint', 'integrity']):
                    logger.error(f"Database error (QueryError) processing document: {e}")
                    result['error'] = f"Database error: {e}"
                    # Re-raise so transaction context manager can rollback
                    raise
            # Check error message for database-related errors
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['foreign key', 'transaction aborted', 'violates constraint', 'integrity', 'query execution failed']):
                logger.error(f"Database error (wrapped) processing document: {e}")
                result['error'] = f"Database error: {e}"
                # Re-raise so transaction context manager can rollback
                raise
            logger.error(f"Unexpected error processing document: {e}", exc_info=True)
            result['error'] = str(e)
            # Re-raise so transaction can rollback
            raise

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
        
