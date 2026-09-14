"""
Enhanced Database class with connection pooling and transaction support.
"""
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from typing import Optional, Dict, Any
import logging
import threading

from database.database.config import DatabaseConfig

logger = logging.getLogger(__name__)


class Database:
    """
    Database connection manager with connection pooling.
    
    Features:
    - Connection pooling for better performance
    - Environment-based configuration
    - Health check support
    - Proper resource cleanup
    """
    
    _file_size_schema_lock = threading.Lock()
    _file_size_schema_checked = False

    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Initialize database with configuration.
        
        Args:
            config: DatabaseConfig instance. If None, loads from environment.
        """
        self.config = config or DatabaseConfig.from_env()
        self._pool: Optional[pool.ThreadedConnectionPool] = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize the connection pool."""
        try:
            # Validate pool size is reasonable
            if self.config.max_connections < self.config.min_connections:
                logger.warning(
                    f"max_connections ({self.config.max_connections}) < min_connections "
                    f"({self.config.min_connections}), setting max to min"
                )
                self.config.max_connections = self.config.min_connections
            
            # Warn if pool size is very small (might cause exhaustion with concurrent workers)
            # With concurrent workers, each worker may need 2-3 connections
            # Minimum recommended: (workers * 3) + buffer
            if self.config.max_connections < 10:
                logger.warning(
                    f"Connection pool size ({self.config.max_connections}) may be too small for concurrent processing. "
                    f"Recommended: at least 15-25 connections for 4 workers. "
                    f"Current setting may cause 'connection pool exhausted' errors."
                )
            
            self._pool = pool.ThreadedConnectionPool(
                minconn=self.config.min_connections,
                maxconn=self.config.max_connections,
                **self.config.to_dict()
            )
            logger.info(
                f"Connection pool initialized: "
                f"{self.config.min_connections}-{self.config.max_connections} connections"
            )
            
            # Verify pool was actually created
            if not self._pool:
                raise ConnectionError("Connection pool creation returned None")

            # Older installations may predate migration 0008 and still have
            # paths.file_size as INTEGER.  The application can be started
            # without the installer/bootstrap path, so repair this one safe,
            # additive schema change when the pool is first created as well.
            self._ensure_large_file_sizes()
                
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            self._pool = None
            # Re-raise the exception so callers know initialization failed
            raise ConnectionError(f"Failed to initialize connection pool: {e}") from e
    
    def _ensure_large_file_sizes(self):
        """Ensure legacy databases accept files larger than 2 GiB.

        This is intentionally limited to the additive BIGINT widening covered
        by migration 0008.  It is a compatibility bridge for deployments that
        start the web app directly instead of running the installer; the
        migration remains the authoritative upgrade path.
        """
        cls = type(self)
        if cls._file_size_schema_checked:
            return
        with cls._file_size_schema_lock:
            if cls._file_size_schema_checked:
                return
            conn = None
            try:
                conn = self._pool.getconn()
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND table_name = 'paths' AND column_name = 'file_size'"
                    )
                    row = cur.fetchone()
                    if row and row[0] == 'integer':
                        cur.execute(
                            "ALTER TABLE paths ALTER COLUMN file_size TYPE BIGINT"
                        )
                        conn.commit()
                        logger.info("Upgraded paths.file_size from INTEGER to BIGINT")
                    elif row:
                        conn.rollback()
                cls._file_size_schema_checked = True
            except Exception:
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                # Do not make an otherwise usable pool unavailable because a
                # compatibility check could not run (for example during a
                # first-install race). The normal migration reports failures.
                logger.warning("Could not verify paths.file_size schema", exc_info=True)
            finally:
                if conn is not None:
                    self._pool.putconn(conn)

    def connect(self, timeout=30):
        """
        Get a connection from the pool with improved waiting and retry logic.
        
        When the pool is exhausted, this method will wait and retry with exponential backoff
        to allow connections to be returned to the pool.
        
        Args:
            timeout: Maximum time to wait for a connection (seconds)
        
        Returns:
            psycopg2 connection object
            
        Raises:
            ConnectionError: If connection cannot be obtained after timeout
        """
        if not self._pool:
            raise ConnectionError("Connection pool not initialized")
        
        import time
        max_retries = max(10, int(timeout * 2))  # More retries for longer waits
        retry_count = 0
        start_time = time.time()
        
        while retry_count < max_retries:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                raise ConnectionError(f"Connection pool exhausted - timeout after {timeout}s (pool size: {self.config.max_connections})")
            
            try:
                # Try to get connection from pool
                # Note: psycopg2's getconn() raises PoolError when pool is exhausted
                conn = self._pool.getconn()
                if not conn:
                    raise ConnectionError("Failed to get connection from pool: got None")
                
                # Check if connection is still valid
                if conn.closed:
                    logger.warning(f"Got closed connection from pool (attempt {retry_count + 1}), closing and retrying...")
                    try:
                        conn.close()
                    except:
                        pass
                    retry_count += 1
                    # Short wait before retrying
                    time.sleep(0.05)
                    continue
                
                # Verify connection is actually usable
                try:
                    test_cur = conn.cursor()
                    test_cur.execute("SELECT 1")
                    test_cur.close()
                except Exception as test_err:
                    logger.warning(f"Connection failed health check (attempt {retry_count + 1}): {test_err}, retrying...")
                    try:
                        if not conn.closed:
                            conn.close()
                    except:
                        pass
                    # Return connection to pool before retrying
                    try:
                        self.putconn(conn)
                    except:
                        pass
                    retry_count += 1
                    time.sleep(0.05)
                    continue
                
                # Connection is valid
                return conn
                
            except psycopg2.pool.PoolError as pool_err:
                # PoolError is in psycopg2.pool, not psycopg2.errors
                # Pool is exhausted - wait and retry
                error_str = str(pool_err).lower()
                if 'connection pool exhausted' in error_str or 'could not get connection' in error_str:
                    retry_count += 1
                    # Exponential backoff with jitter
                    wait_time = min(0.1 * (2 ** min(retry_count, 5)), 2.0)  # Max 2 seconds
                    if retry_count % 5 == 0:  # Log every 5th attempt
                        logger.warning(
                            f"Connection pool exhausted (attempt {retry_count}/{max_retries}), "
                            f"waiting {wait_time:.2f}s... (pool size: {self.config.max_connections}, "
                            f"elapsed: {elapsed:.1f}s)"
                        )
                    time.sleep(wait_time)
                    continue
                else:
                    # Other pool errors - re-raise
                    raise ConnectionError(f"Pool error: {pool_err}") from pool_err
                    
            except ConnectionError:
                raise
            except Exception as e:
                error_str = str(e).lower()
                if 'connection pool exhausted' in error_str or 'could not get connection' in error_str:
                    # Pool exhaustion - wait and retry
                    retry_count += 1
                    wait_time = min(0.1 * (2 ** min(retry_count, 5)), 2.0)
                    if retry_count % 5 == 0:
                        logger.warning(
                            f"Connection pool exhausted (attempt {retry_count}/{max_retries}), "
                            f"waiting {wait_time:.2f}s... (pool size: {self.config.max_connections})"
                        )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Failed to get connection (attempt {retry_count + 1}): {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise ConnectionError(f"Failed to get connection after {max_retries} attempts: {e}") from e
                    # Wait before retrying (exponential backoff)
                    time.sleep(0.1 * retry_count)
        
        raise ConnectionError(
            f"Connection pool exhausted after {max_retries} attempts "
            f"(timeout: {timeout}s, pool size: {self.config.max_connections}). "
            f"Consider increasing pool_max_conn or reducing concurrent operations."
        )
    
    def putconn(self, conn):
        """
        Return a connection to the pool.
        Ensures connection is in a valid state before returning.
        
        Args:
            conn: Connection to return
        """
        if not self._pool or not conn:
            return
        
        try:
            # Check if connection is closed - don't return closed connections to pool
            if conn.closed:
                logger.debug("Connection is closed, not returning to pool")
                return
            
            # PRODUCTION: Reset connection state if it's in a bad transaction state
            # Fix psycopg2 version compatibility - use safe attribute checking
            try:
                from psycopg2 import extensions
                
                # PRODUCTION: Check transaction status using version-compatible method
                needs_rollback = False
                
                # Method 1: Try modern transaction_status (psycopg2 2.5+)
                if hasattr(conn, 'info') and hasattr(conn.info, 'transaction_status'):
                    try:
                        transaction_status = conn.info.transaction_status
                        # Check for error states that need rollback
                        # PRODUCTION: Check for error state (version-compatible)
                        if hasattr(extensions, 'TRANSACTION_STATUS_INERROR'):
                            if transaction_status == extensions.TRANSACTION_STATUS_INERROR:
                                needs_rollback = True
                        # PRODUCTION: For other transaction states, test with a query
                        # This works regardless of psycopg2 version
                        if not needs_rollback:
                            try:
                                test_cur = conn.cursor()
                                test_cur.execute("SELECT 1")
                                test_cur.close()
                            except (psycopg2.errors.InFailedSqlTransaction, Exception) as test_err:
                                # Transaction is aborted
                                error_str = str(test_err).lower()
                                if 'transaction is aborted' in error_str or 'in failed sql transaction' in error_str:
                                    needs_rollback = True
                    except (AttributeError, Exception):
                        pass  # Attribute doesn't exist in this version
                
                # Method 2: Try legacy status attribute (older psycopg2)
                if not needs_rollback and hasattr(conn, 'status'):
                    try:
                        # Use STATUS_IN_TRANSACTION (not TRANSACTION_STATUS_INTRANSACTION)
                        if hasattr(extensions, 'STATUS_IN_TRANSACTION'):
                            if conn.status == extensions.STATUS_IN_TRANSACTION:
                                # Test if transaction is aborted
                                try:
                                    test_cur = conn.cursor()
                                    test_cur.execute("SELECT 1")
                                    test_cur.close()
                                except (psycopg2.errors.InFailedSqlTransaction, Exception):
                                    needs_rollback = True
                    except (AttributeError, Exception):
                        pass  # Attribute doesn't exist in this version
                
                # Method 3: Always try rollback if we can't determine state (safe fallback)
                if not needs_rollback:
                    # Test transaction state with a simple query
                    try:
                        test_cur = conn.cursor()
                        test_cur.execute("SELECT 1")
                        test_cur.close()
                    except (psycopg2.errors.InFailedSqlTransaction, Exception):
                        needs_rollback = True
                
                # Perform rollback if needed
                if needs_rollback:
                    try:
                        conn.rollback()
                        logger.debug("Rolled back transaction before returning connection to pool")
                    except Exception as rollback_err:
                        # If rollback fails, connection is likely bad - don't return it
                        error_str = str(rollback_err).lower()
                        if 'no transaction' not in error_str:
                            logger.warning(f"Connection in bad state (rollback failed: {rollback_err}), closing instead of returning to pool")
                            try:
                                conn.close()
                            except:
                                pass
                            return
                else:
                    # No rollback needed, but try a safe rollback anyway to clear any pending state
                    try:
                        conn.rollback()
                    except Exception:
                        pass  # No transaction or already committed - that's OK
                        
            except Exception as e:
                # PRODUCTION: If we can't check state, try to rollback anyway to be safe
                # This ensures connections are always clean when returned to pool
                try:
                    if not conn.closed:
                        conn.rollback()
                        logger.debug("Rolled back transaction (fallback) before returning connection to pool")
                except Exception as rollback_err:
                    error_str = str(rollback_err).lower()
                    if 'no transaction' not in error_str:
                        logger.debug(f"Rollback attempt failed (may be expected): {rollback_err}")
                    # If rollback fails, close the connection to be safe
                    try:
                        if not conn.closed:
                            conn.close()
                    except:
                        pass
                    return
            
            # Return connection to pool
            try:
                self._pool.putconn(conn)
            except Exception as put_err:
                logger.error(f"Error putting connection back to pool: {put_err}")
                # If putting back fails, try to close the connection
                try:
                    if not conn.closed:
                        conn.close()
                except:
                    pass
        except Exception as e:
            logger.error(f"Error returning connection to pool: {e}")
            # Try to close the connection if returning fails
            try:
                if not conn.closed:
                    conn.close()
            except:
                pass
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for getting and returning connections.
        
        Usage:
            with db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT ...")
                conn.commit()
        """
        conn = None
        try:
            conn = self.connect()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.putconn(conn)
    
    def health_check(self) -> bool:
        """
        Check if database connection is healthy.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
                return True
        except (psycopg2.pool.PoolError, ConnectionError) as pool_err:
            # Pool errors are expected when pool is exhausted - not a health issue
            logger.debug(f"Health check: Pool error (expected): {pool_err}")
            return False
        except Exception as e:
            # Log the error type and message for debugging
            error_type = type(e).__name__
            error_msg = str(e)
            logger.debug(f"Health check failed: {error_type}: {error_msg}")
            return False
    
    def check_tables_exist(self, table_names: Optional[list] = None) -> Dict[str, bool]:
        """
        Check if required tables exist in the database.
        
        Args:
            table_names: List of table names to check. If None, checks all standard tables.
        
        Returns:
            Dictionary mapping table names to existence status
        """
        # Default list of all tables in the system
        if table_names is None:
            table_names = [
                'words', 'categorys', 'words_categorys', 'words_paths',
                'keywords_paths', 'keywords', 'contents', 'titles_content',
                'sides', 'sources', 'hashs', 'paths',
                'punctuation', 'alerts'
            ]
        
        result = {}
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                for table_name in table_names:
                    try:
                        cur.execute(
                            """
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_schema = 'public' 
                                AND table_name = %s
                            )
                            """,
                            (table_name,)
                        )
                        exists = cur.fetchone()[0]
                        result[table_name] = exists
                    except Exception as e:
                        logger.warning(f"Error checking table {table_name}: {e}")
                        result[table_name] = False
                cur.close()
        except Exception as e:
            logger.error(f"Error checking tables: {e}")
            # Return all False if connection fails
            result = {table: False for table in table_names}
        
        return result
    
    def validate_schema(self) -> Dict[str, Any]:
        """
        Validate that all required tables exist.
        
        Returns:
            Dictionary with validation results:
            - 'valid': bool - True if all tables exist
            - 'missing_tables': list - List of missing table names
            - 'existing_tables': list - List of existing table names
            - 'table_status': dict - Status of each table
        """
        table_status = self.check_tables_exist()
        missing_tables = [table for table, exists in table_status.items() if not exists]
        existing_tables = [table for table, exists in table_status.items() if exists]
        
        return {
            'valid': len(missing_tables) == 0,
            'missing_tables': missing_tables,
            'existing_tables': existing_tables,
            'table_status': table_status
        }
    
    def close_all(self):
        """Close all connections in the pool."""
        if self._pool:
            try:
                # Check if pool is already closed before trying to close it
                if hasattr(self._pool, 'closed') and self._pool.closed:
                    logger.debug("Connection pool already closed, skipping close_all()")
                    return
                self._pool.closeall()
                logger.info("All connections closed")
            except (AttributeError, psycopg2.pool.PoolError) as e:
                # Pool might already be closed or in an invalid state
                error_str = str(e).lower()
                if 'closed' in error_str or 'pool is closed' in error_str:
                    logger.debug(f"Connection pool already closed: {e}")
                else:
                    logger.warning(f"Error closing pool: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error closing pool: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup."""
        self.close_all()