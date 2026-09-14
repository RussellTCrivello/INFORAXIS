"""
Enhanced BaseRepository with transaction support and proper error handling.
"""
from contextlib import contextmanager
from typing import Optional, Any
import logging
import psycopg2
from psycopg2 import errors

from database.exceptions import QueryError, TransactionError

logger = logging.getLogger(__name__)


class BaseRepository:
    """
    Base repository with transaction support and connection pooling.
    
    Features:
    - Transaction management with rollback on errors
    - Connection pooling support
    - Standardized error handling
    - Support for both transactional and non-transactional operations
    """
    
    def __init__(self, db, connection: Optional[Any] = None):
        """
        Initialize repository.
        
        Args:
            db: Database instance
            connection: Optional existing connection for transaction context
        """
        self.db = db
        self._connection = connection  # For transaction context
    
    @contextmanager
    def get_cursor(self, commit: bool = True):
        """
        Get a cursor with automatic commit/rollback.
        
        Args:
            commit: If True, commit on success. If False, don't commit (for transactions).
                   When _connection is set (transaction context), commit is ignored.
        
        Yields:
            Database cursor
        """
        # Use existing connection if in transaction context
        if self._connection:
            # Check if connection is still valid
            if self._connection.closed:
                logger.error("Transaction connection is closed, cannot execute query")
                raise QueryError("Transaction connection is closed")
            
            # Comprehensive transaction state validation before executing queries
            # This prevents trying to use IDs from operations that will be rolled back
            try:
                # Check connection status first
                # Use transaction_status (available in psycopg2 2.5+) instead of status
                from psycopg2 import extensions
                
                # Check transaction status (preferred method for psycopg2 2.5+)
                if hasattr(self._connection, 'info') and hasattr(self._connection.info, 'transaction_status'):
                    transaction_status = self._connection.info.transaction_status
                    # If connection is in failed transaction state, rollback immediately
                    if transaction_status == extensions.TRANSACTION_STATUS_INERROR:
                        logger.warning("Connection in error state, attempting rollback before proceeding")
                        try:
                            self._connection.rollback()
                            logger.debug("Rolled back connection in error state")
                        except Exception as rollback_err:
                            logger.error(f"Failed to rollback connection in error state: {rollback_err}")
                            # Connection is likely bad - raise error (don't close, let transaction manager handle it)
                            raise QueryError("Connection in error state and rollback failed") from rollback_err
                # Fallback: try old status attribute for older psycopg2 versions (if it exists)
                elif hasattr(self._connection, 'status'):
                    # For older psycopg2 versions, try to check status directly
                    # Note: STATUS_IN_ERROR doesn't exist in all versions, so we'll use a try/except
                    try:
                        if hasattr(extensions, 'STATUS_IN_ERROR') and self._connection.status == extensions.STATUS_IN_ERROR:
                            logger.warning("Connection in error state (legacy check), attempting rollback before proceeding")
                            try:
                                self._connection.rollback()
                                logger.debug("Rolled back connection in error state")
                            except Exception as rollback_err:
                                logger.error(f"Failed to rollback connection in error state: {rollback_err}")
                                raise QueryError("Connection in error state and rollback failed") from rollback_err
                    except AttributeError:
                        # STATUS_IN_ERROR doesn't exist in this psycopg2 version - skip check
                        pass
                
                # Try to check transaction state with a simple query
                # If transaction is aborted, this will raise InFailedSqlTransaction
                # This is a lightweight check that doesn't affect the transaction
                test_cur = None
                try:
                    test_cur = self._connection.cursor()
                    test_cur.execute("SELECT 1")
                    test_cur.close()
                    test_cur = None
                except (errors.InFailedSqlTransaction, psycopg2.errors.InFailedSqlTransaction) as e:
                    # Transaction is already aborted - don't try to rollback here
                    # The transaction context manager will handle rollback
                    if test_cur:
                        try:
                            test_cur.close()
                        except:
                            pass
                    logger.error("Transaction is aborted, cannot execute query")
                    # Raise error - transaction context manager will handle cleanup
                    raise QueryError("Transaction is aborted, cannot execute query") from e
                except Exception as test_err:
                    # Unexpected error during test query
                    if test_cur:
                        try:
                            test_cur.close()
                        except:
                            pass
                    # Check if it's a transaction abort error
                    error_str = str(test_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        logger.error(f"Transaction aborted during state check: {test_err}")
                        raise QueryError("Transaction is aborted, cannot execute query") from test_err
                    # For other errors, log but proceed (might be a different issue)
                    logger.debug(f"Transaction state check had non-critical error (will proceed): {test_err}")
                    
            except QueryError:
                # Re-raise QueryError (already handled above)
                raise
            except Exception as e:
                # Check if it's a connection error
                error_str = str(e).lower()
                if 'connection' in error_str and ('closed' in error_str or 'bad' in error_str):
                    logger.error(f"Connection error during transaction state check: {e}")
                    raise QueryError(f"Connection error: {e}") from e
                # Check if it's a transaction abort error
                if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                    logger.error(f"Transaction aborted during state check: {e}")
                    raise QueryError("Transaction is aborted, cannot execute query") from e
                # Other errors - might be connection issues, log but let actual query handle it
                logger.debug(f"Transaction state check had non-critical error (will proceed): {e}")
            
            # In transaction context, don't commit here - let transaction manager handle it
            try:
                cur = self._connection.cursor()
            except Exception as e:
                logger.error(f"Failed to create cursor from transaction connection: {e}")
                raise QueryError(f"Failed to create cursor: {e}") from e
            
            try:
                yield cur
                # Don't commit when in transaction context - transaction manager handles it
            except (errors.InFailedSqlTransaction, psycopg2.errors.InFailedSqlTransaction) as e:
                # Transaction is now in failed state - rollback immediately
                logger.error(f"Query failed and transaction aborted: {e}")
                try:
                    if not self._connection.closed:
                        self._connection.rollback()
                        logger.debug("Rolled back transaction after query failure")
                except Exception as rollback_err:
                    logger.error(f"Failed to rollback after query error: {rollback_err}")
                raise QueryError(f"Query execution failed and transaction aborted: {e}") from e
            except Exception as e:
                # Check if this is a transaction-aborting error
                error_str = str(e).lower()
                if 'current transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                    logger.error(f"Transaction aborted error detected: {e}")
                    try:
                        if not self._connection.closed:
                            self._connection.rollback()
                            logger.debug("Rolled back transaction after abort error")
                    except Exception as rollback_err:
                        logger.error(f"Failed to rollback after abort error: {rollback_err}")
                logger.error(f"Query execution failed: {e}")
                raise QueryError(f"Query execution failed: {e}") from e
            finally:
                try:
                    cur.close()
                except Exception:
                    pass  # Ignore errors closing cursor
        else:
            # New connection for this operation
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                try:
                    yield cur
                    if commit:
                        conn.commit()
                except Exception as e:
                    if commit:
                        conn.rollback()
                    logger.error(f"Query execution failed: {e}")
                    raise QueryError(f"Query execution failed: {e}") from e
                finally:
                    cur.close()
    
    @contextmanager
    def transaction(self):
        """
        Transaction context manager for multi-step operations.
        
        Usage:
            with repo.transaction():
                repo.execute(...)
                repo.execute(...)
                # All operations commit together or rollback on error
        """
        conn = None
        try:
            conn = self.db.connect()
            # Create a new repository instance with this connection
            transactional_repo = self.__class__(self.db, connection=conn)
            yield transactional_repo
            conn.commit()
            logger.debug("Transaction committed successfully")
        except Exception as e:
            if conn:
                conn.rollback()
                logger.error(f"Transaction rolled back due to error: {e}")
            raise TransactionError(f"Transaction failed: {e}") from e
        finally:
            if conn:
                self.db.putconn(conn)
    
    def execute(
        self, 
        query: str, 
        params: Optional[tuple] = None, 
        fetchone: bool = False,
        fetchall: bool = False,
        single: bool = False,
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = True
    ):
        """
        Execute a query with proper error handling.
        
        Supports multiple calling conventions for backward compatibility:
        - execute(query, params, True) - positional fetchone
        - execute(query, params, False, True) - positional fetchone=False, fetchall=True
        - execute(query, params, fetchone=True) - keyword
        - execute(query, params, fetchall=True) - keyword
        - execute(query, params, single=True) - keyword (alias for fetchone)
        - execute(query, params, fetch_one=True) - keyword (alias for fetchone)
        - execute(query, params, fetch_all=True) - keyword (alias for fetchall)
        
        Args:
            query: SQL query string
            params: Query parameters
            fetchone: If True, return single row
            fetchall: If True, return all rows
            single: Alias for fetchone (for backward compatibility)
            fetch_one: Alias for fetchone (for backward compatibility)
            fetch_all: Alias for fetchall (for backward compatibility)
            commit: If True, commit transaction (False for transaction context)
        
        Returns:
            Query result based on fetch flags, or rowcount for INSERT/UPDATE/DELETE
        """
        # Normalize fetch flags - support all naming conventions
        should_fetchone = fetchone or single or fetch_one
        should_fetchall = fetchall or fetch_all
        
        with self.get_cursor(commit=commit) as cur:
            try:
                cur.execute(query, params)
                
                # Check if query has RETURNING clause (takes priority over fetch flags for INSERT/UPDATE/DELETE)
                query_upper = query.strip().upper()
                has_returning = 'RETURNING' in query_upper
                is_insert = query_upper.startswith('INSERT')
                is_update = query_upper.startswith('UPDATE')
                is_delete = query_upper.startswith('DELETE')
                
                # For INSERT/UPDATE/DELETE with RETURNING, always fetch the RETURNING result
                if (is_insert or is_update or is_delete) and has_returning:
                    if cur.rowcount > 0:
                        try:
                            result = cur.fetchone()
                            if result:
                                return result[0] if isinstance(result, tuple) and len(result) == 1 else result
                        except Exception as fetch_err:
                            logger.warning(f"Failed to fetch RETURNING result: {fetch_err}")
                            # Fallback to rowcount for INSERT, None for others
                            return cur.rowcount if is_insert else None
                    return None
                
                # Handle SELECT queries with fetch flags
                if should_fetchone:
                    return cur.fetchone()
                if should_fetchall:
                    return cur.fetchall()
                
                # For INSERT/UPDATE/DELETE without RETURNING
                if is_insert:
                    return cur.rowcount if cur.rowcount > 0 else None
                elif is_update or is_delete:
                    return cur.rowcount
                else:
                    # Other query types
                    return cur.rowcount
                    
            except (errors.InFailedSqlTransaction, psycopg2.errors.InFailedSqlTransaction) as e:
                logger.error(f"Query execution error (transaction aborted): {query[:100]}... - {e}")
                # Transaction is already aborted, rollback will be handled by get_cursor
                raise QueryError(f"Query execution failed: transaction aborted: {e}") from e
            except Exception as e:
                logger.error(f"Query execution error: {query[:100]}... - {e}")
                raise QueryError(f"Query execution failed: {e}") from e
    
    def create_temp_copy_to_words(self, query_export: str, buffer):
        """
        Create temporary table and copy words using COPY command.
        Uses transaction context if available, otherwise creates new connection.
        
        Enhanced with robust error handling, transaction state validation,
        and proper cleanup to prevent cascading failures.
        
        Args:
            query_export: SQL query to execute after COPY
            buffer: StringIO buffer with data to copy
        """
        # Validate buffer first
        if buffer is None:
            raise QueryError("Buffer is None, cannot perform COPY operation")
        
        # Reset buffer position
        try:
            buffer.seek(0)
            buffer_size = len(buffer.read())
            buffer.seek(0)
            if buffer_size == 0:
                logger.warning("Empty buffer provided to COPY operation - skipping")
                return  # Nothing to insert, return early
        except Exception as buffer_err:
            raise QueryError(f"Buffer validation failed: {buffer_err}") from buffer_err
        
        # Use transaction context if available, otherwise create new connection
        if self._connection and not self._connection.closed:
            # Comprehensive transaction state validation before proceeding
            try:
                # Check connection status
                if hasattr(self._connection, 'status'):
                    from psycopg2 import extensions
                    # Check transaction status (preferred method for psycopg2 2.5+)
                    if hasattr(self._connection, 'info') and hasattr(self._connection.info, 'transaction_status'):
                        transaction_status = self._connection.info.transaction_status
                        if transaction_status == extensions.TRANSACTION_STATUS_INERROR:
                            logger.error("Transaction is in error state, cannot proceed with bulk insert")
                            raise QueryError("Transaction is in error state, cannot proceed")
                    # Fallback: try old status attribute for older psycopg2 versions
                    elif hasattr(self._connection, 'status'):
                        try:
                            if hasattr(extensions, 'STATUS_IN_ERROR') and self._connection.status == extensions.STATUS_IN_ERROR:
                                logger.error("Transaction is in error state, cannot proceed with bulk insert")
                                raise QueryError("Transaction is in error state, cannot proceed")
                        except AttributeError:
                            # STATUS_IN_ERROR doesn't exist in this psycopg2 version - skip check
                            pass
                
                # PRODUCTION: Test transaction state with a simple query
                # This will raise InFailedSqlTransaction if transaction is aborted
                test_cur = self._connection.cursor()
                try:
                    test_cur.execute("SELECT 1")
                    test_cur.close()
                except (errors.InFailedSqlTransaction, psycopg2.errors.InFailedSqlTransaction) as e:
                    test_cur.close()
                    logger.error("Transaction is aborted, cannot proceed with bulk insert")
                    # PRODUCTION: Attempt rollback to clean up connection state
                    try:
                        self._connection.rollback()
                        logger.debug("Rolled back aborted transaction before bulk insert")
                    except Exception as rollback_err:
                        logger.debug(f"Could not rollback aborted transaction: {rollback_err}")
                    raise QueryError("Transaction is aborted, cannot proceed with bulk insert") from e
            except QueryError:
                raise
            except Exception as check_err:
                # PRODUCTION: Check if it's a transaction abort error
                error_str = str(check_err).lower()
                if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                    logger.error(f"Transaction is aborted (detected in check): {check_err}")
                    try:
                        self._connection.rollback()
                    except:
                        pass
                    raise QueryError("Transaction is aborted, cannot proceed with bulk insert") from check_err
                # If check fails for other reasons, log but continue (might be a different error)
                logger.debug(f"Transaction state check had issue: {check_err}")
            
            # Use existing transaction connection with robust error handling
            cur = None
            copy_in_progress = False
            temp_table_created = False
            
            try:
                # Create fresh cursor for this operation
                cur = self._connection.cursor()
                
                # Clean up any existing temp table first
                # Use a savepoint-like approach: drop if exists, ignore errors
                try:
                    cur.execute("DROP TABLE IF EXISTS tmp_words")
                except Exception as drop_err:
                    # Log but don't fail - table might not exist or transaction might be aborted
                    error_str = str(drop_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        logger.error(f"Transaction aborted while dropping temp table: {drop_err}")
                        raise QueryError(f"Transaction aborted before COPY: {drop_err}") from drop_err
                    logger.debug(f"Could not drop temp table (may not exist): {drop_err}")
                
                # Create temp table with explicit error handling
                try:
                    cur.execute("CREATE TEMP TABLE tmp_words (word TEXT)")
                    temp_table_created = True
                except (errors.InFailedSqlTransaction, psycopg2.errors.InFailedSqlTransaction) as create_err:
                    logger.error(f"Transaction aborted while creating temp table: {create_err}")
                    raise QueryError(f"Transaction aborted before COPY: {create_err}") from create_err
                except Exception as create_err:
                    # If CREATE fails, transaction might be aborted
                    error_str = str(create_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        raise QueryError(f"Transaction aborted before COPY: {create_err}") from create_err
                    # Check for "relation already exists" - this shouldn't happen but handle gracefully
                    if 'already exists' in error_str:
                        logger.warning("Temp table already exists, attempting to use existing table")
                        temp_table_created = True  # Assume table exists and is usable
                    else:
                        raise QueryError(f"Failed to create temp table: {create_err}") from create_err
                
                # PRODUCTION: Perform COPY operation with comprehensive error handling
                try:
                    # Ensure buffer is at start position
                    buffer.seek(0)
                    
                    # PRODUCTION: Perform COPY with explicit error handling
                    # Use copy_expert for better control
                    cur.copy_expert(
                        "COPY tmp_words (word) FROM STDIN WITH (FORMAT csv)", 
                        buffer
                    )
                    # PRODUCTION: COPY completed - ensure cursor is ready for next command
                    # The cursor is still active after COPY, but we need to ensure it's ready
                    # We'll close this cursor and use a fresh one for subsequent operations
                    copy_in_progress = False  # COPY completed successfully
                    logger.debug("COPY operation completed successfully")
                    
                except psycopg2.errors.InFailedSqlTransaction as copy_err:
                    copy_in_progress = False
                    logger.error(f"Transaction aborted during COPY: {copy_err}")
                    raise QueryError(f"Bulk word insert failed - transaction aborted during COPY: {copy_err}") from copy_err
                    
                except (psycopg2.errors.OperationalError, psycopg2.errors.InternalError_) as copy_err:
                    copy_in_progress = False
                    error_str = str(copy_err).lower()
                    
                    if 'no copy in progress' in error_str:
                        # COPY command wasn't properly initiated - cursor state issue
                        logger.warning(f"COPY operation failed: cursor not in COPY state: {copy_err}")
                        # Try to recover by closing cursor and retrying once
                        try:
                            cur.close()
                            cur = self._connection.cursor()
                            
                            # Recreate temp table
                            try:
                                cur.execute("DROP TABLE IF EXISTS tmp_words")
                            except:
                                pass
                            cur.execute("CREATE TEMP TABLE tmp_words (word TEXT)")
                            
                            # Retry COPY with fresh cursor
                            buffer.seek(0)
                            cur.copy_expert(
                                "COPY tmp_words (word) FROM STDIN WITH (FORMAT csv)", 
                                buffer
                            )
                            copy_in_progress = False
                            logger.debug("COPY operation succeeded on retry with fresh cursor")
                            
                        except Exception as retry_err:
                            logger.error(f"COPY operation failed on retry: {retry_err}")
                            error_str_retry = str(retry_err).lower()
                            if 'transaction is aborted' in error_str_retry or 'in failed sql transaction' in error_str_retry:
                                raise QueryError(f"Bulk word insert failed - transaction aborted during COPY retry: {retry_err}") from retry_err
                            raise QueryError(f"Bulk word insert failed - COPY operation failed on retry: {retry_err}") from retry_err
                    else:
                        # Other operational errors
                        raise QueryError(f"Bulk word insert failed - COPY operation failed: {copy_err}") from copy_err
                        
                except Exception as copy_err:
                    copy_in_progress = False
                    error_str = str(copy_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        raise QueryError(f"Bulk word insert failed - transaction aborted during COPY: {copy_err}") from copy_err
                    if 'no copy in progress' in error_str:
                        raise QueryError(f"Bulk word insert failed - COPY operation not properly initialized: {copy_err}") from copy_err
                    raise QueryError(f"Bulk word insert failed - COPY operation failed: {copy_err}") from copy_err
                
                # PRODUCTION: Execute the export query (INSERT from tmp_words to words)
                # IMPORTANT: After COPY, we need to ensure cursor is ready for next command
                # Close current cursor and create a fresh one to avoid "another command is already in progress"
                try:
                    # PRODUCTION: Close COPY cursor and create fresh cursor for export query
                    # This prevents "another command is already in progress" errors
                    cur.close()
                    cur = self._connection.cursor()
                    
                    cur.execute(query_export)
                    logger.debug("Export query executed successfully")
                except (psycopg2.errors.InFailedSqlTransaction, psycopg2.errors.UndefinedTable) as query_err:
                    error_str = str(query_err).lower()
                    if 'tmp_words' in error_str and 'does not exist' in error_str:
                        # Temp table was dropped or doesn't exist - this shouldn't happen
                        logger.error(f"Temp table tmp_words does not exist when executing export query: {query_err}")
                        raise QueryError(f"Bulk word insert failed - temp table does not exist: {query_err}") from query_err
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        raise QueryError(f"Bulk word insert failed - transaction aborted during insert: {query_err}") from query_err
                    raise QueryError(f"Bulk word insert failed - export query failed: {query_err}") from query_err
                except Exception as query_err:
                    error_str = str(query_err).lower()
                    if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                        raise QueryError(f"Bulk word insert failed - transaction aborted during insert: {query_err}") from query_err
                    if 'tmp_words' in error_str and 'does not exist' in error_str:
                        raise QueryError(f"Bulk word insert failed - temp table does not exist: {query_err}") from query_err
                    raise QueryError(f"Bulk word insert failed - export query failed: {query_err}") from query_err
                
                # Fix sequence if needed (only if not in a failed transaction)
                # This is non-critical, so we catch all exceptions
                try:
                    cur.execute("""
                        SELECT setval(
                            'public.words_id_seq', 
                            (SELECT COALESCE(MAX(id), 0) FROM words),
                            true
                        );
                    """)
                except Exception as seq_err:
                    # Sequence fix is not critical, log and continue
                    logger.debug(f"Could not fix sequence (non-critical): {seq_err}")
                
                # Clean up temp table (optional, but good practice)
                # Temp tables are automatically dropped at end of session, but explicit cleanup is cleaner
                try:
                    cur.execute("DROP TABLE IF EXISTS tmp_words")
                except Exception:
                    pass  # Non-critical cleanup
                
                # Don't commit here - let transaction manager handle it
                logger.debug("Bulk word insert completed successfully (in transaction)")
                
            except QueryError:
                # Re-raise QueryError (already wrapped with context)
                raise
            except (errors.InFailedSqlTransaction, psycopg2.errors.InFailedSqlTransaction) as e:
                logger.error(f"Bulk word insert failed - transaction aborted: {e}")
                raise QueryError(f"Bulk word insert failed - transaction aborted: {e}") from e
            except Exception as e:
                logger.error(f"Bulk word insert failed: {e}", exc_info=True)
                # Check if this error aborted the transaction
                error_str = str(e).lower()
                if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                    raise QueryError(f"Bulk word insert failed - transaction aborted: {e}") from e
                if 'no copy in progress' in error_str:
                    raise QueryError(f"Bulk word insert failed - COPY operation not properly initialized: {e}") from e
                if 'tmp_words' in error_str and 'does not exist' in error_str:
                    raise QueryError(f"Bulk word insert failed - temp table does not exist: {e}") from e
                raise QueryError(f"Bulk word insert failed: {e}") from e
            finally:
                # PRODUCTION: Comprehensive cleanup
                # IMPORTANT: Ensure cursor is properly closed to avoid "another command is already in progress"
                if cur:
                    try:
                        # If COPY is still in progress, try to cancel it
                        if copy_in_progress:
                            try:
                                cur.cancel()
                                logger.debug("Cancelled COPY operation in progress")
                            except Exception:
                                pass  # Ignore cancel errors
                        
                        # PRODUCTION: Ensure cursor is fully closed before cleanup
                        # This prevents "another command is already in progress" errors
                        try:
                            # Try to close cursor gracefully
                            if not cur.closed:
                                cur.close()
                                logger.debug("COPY cursor closed successfully")
                        except Exception as close_err:
                            # If close fails, try to cancel and close again
                            try:
                                if not cur.closed:
                                    cur.cancel()
                                    cur.close()
                            except Exception:
                                pass  # Ignore errors during forced close
                        
                        # Clean up temp table if it was created (use fresh cursor if needed)
                        if temp_table_created:
                            try:
                                cleanup_cur = self._connection.cursor()
                                cleanup_cur.execute("DROP TABLE IF EXISTS tmp_words")
                                cleanup_cur.close()
                            except Exception:
                                pass  # Ignore cleanup errors
                    except Exception:
                        pass  # Ignore errors during cleanup
        else:
            # Create new connection for this operation
            conn = None
            cur = None
            try:
                conn = self.db.connect()
                cur = conn.cursor()
                
                # Drop temp table if it exists (temp tables are session-scoped, but safer to drop)
                cur.execute("DROP TABLE IF EXISTS tmp_words")
                cur.execute("CREATE TEMP TABLE tmp_words (word TEXT)")
                cur.copy_expert(
                    "COPY tmp_words (word) FROM STDIN WITH (FORMAT csv)", 
                    buffer
                )
                cur.execute(query_export)
                
                cur.execute("""
                    SELECT setval(
                        'public.words_id_seq', 
                        (SELECT COALESCE(MAX(id), 0) FROM words),
                        true
                    );
                """)
                
                conn.commit()
                logger.debug("Bulk word insert completed successfully")
            except Exception as e:
                if conn:
                    conn.rollback()
                logger.error(f"Bulk word insert failed: {e}")
                raise QueryError(f"Bulk word insert failed: {e}") from e
            finally:
                if cur:
                    cur.close()
                if conn:
                    self.db.putconn(conn)


