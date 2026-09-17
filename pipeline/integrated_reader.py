"""
Integrated File Reader - Complete Implementation
Handles parallel file processing with database storage
Uses concurrency managers for proper resource management and synchronization
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import threading
import time

from core.console import console
from core.file_utils import get_standardized_metadata, iter_tree, read_tree
from reader_file.main_specify_method import main_specify_method_of_reading_the_file
# DatabaseHub is optional - import will be handled conditionally in _init_storage
from pipeline.storage_pipeline import StoragePipeline
from pipeline.progress_ledger import (
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_RETRYABLE,
    OUTCOME_SKIPPED,
    OUTCOME_UNSUPPORTED,
    ProgressLedger,
    classify_result,
)
from settings import get_storage_config, get_processing_config
from Hdg_Err_Ex_Log import (
    handle_error, is_connection_error,
    ErrorCategory, ErrorSeverity
)
from concurrency import (
    ConcurrencyHub, ThreadPriority, ThreadState,
    PoolPriority
)

logger = logging.getLogger(__name__)

#: Serializes the carriage-return progress lines so concurrent workers cannot
#: interleave two writes into one garbled line.
_PROGRESS_PRINT_LOCK = threading.Lock()

#: Process-wide limit on concurrent storage operations.
#
# Every StoragePipeline shares one connection pool, so the per-reader limiter
# that used to exist here (``pool_size // 4`` for *each* nested reader) did not
# bound the aggregate: a container processed by four workers, each starting a
# nested reader with its own limiter, could drive far more concurrent store
# transactions than the pool has connections.  The semaphore is shared by all
# readers in the process and sized once from the safe pool size.
_STORAGE_SEMAPHORE_LOCK = threading.Lock()
_STORAGE_SEMAPHORE: Optional[threading.Semaphore] = None
_STORAGE_SEMAPHORE_SIZE: Optional[int] = None


def _get_storage_semaphore(requested_concurrency: int) -> threading.Semaphore:
    """Return the process-wide storage concurrency limiter.

    The limiter is sized from the connection pool (never smaller than 2 and
    never larger than the pool) and shared by every reader, so nested readers
    cannot multiply concurrent storage transactions beyond the pool.
    """
    global _STORAGE_SEMAPHORE, _STORAGE_SEMAPHORE_SIZE
    size = max(1, int(requested_concurrency))
    with _STORAGE_SEMAPHORE_LOCK:
        if _STORAGE_SEMAPHORE is None:
            _STORAGE_SEMAPHORE = threading.Semaphore(size)
            _STORAGE_SEMAPHORE_SIZE = size
        return _STORAGE_SEMAPHORE


#: Extensions whose files are processed last (OCR is the slowest stage) and
#: second-to-last (PDF pages).  Kept as module constants so the discovery
#: inventory and the phase streams classify files identically.
IMAGE_EXTENSIONS = frozenset({
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg',
    '.ico', '.heic', '.heif',
})
PDF_EXTENSIONS = frozenset({'.pdf'})
PHASE_NAMES = ('other', 'pdf', 'image')

#: How many per-file result dictionaries ``process_folder`` keeps in memory by
#: default.  Each carries the extracted content (~5 KB measured), so retaining
#: every result of a large corpus would hold the whole extraction in RAM.
DEFAULT_RESULT_RETENTION = 10000

#: Byte ceiling for the retained result window.  A count bound alone is not
#: enough: results from word-dense files are megabytes each (measured: an 8 KB
#: limit of count still held ~800 MB when the corpus contained 4 MB text files
#: - 10 000 retained results x ~4 MB of extracted content).  Once the window
#: costs more than this, further results are counted and discarded, exactly as
#: they are when the count bound is reached.  The database remains the system of
#: record, so this changes reporting memory, never what is stored.
DEFAULT_RESULT_RETENTION_BYTES = 64 * 1024 * 1024


def _object_footprint(value: Any) -> int:
    """Best-effort size of a retained Python object (content dominates).

    Used only to bound the reporting window, so an approximation is acceptable;
    string length is the dominant term and non-ASCII text is slightly
    over-counted, which is the safe direction for a memory ceiling.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return 8
    if isinstance(value, str):
        return len(value) + 49
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value) + 33
    if isinstance(value, dict):
        return sum(_object_footprint(k) + _object_footprint(v)
                   for k, v in value.items()) + 64
    if isinstance(value, (list, tuple, set, frozenset)):
        return sum(_object_footprint(item) for item in value) + 56
    try:
        return len(value) + 49  # e.g. numpy arrays expose len()
    except Exception:
        return 100


class IntegratedFileReader:
    """
    Integrated file reader with parallel processing and storage
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        enable_monitoring: bool = True,
        enable_storage: bool = True,
        storage_source: str = "default",
        storage_side: str = "default",
        use_priority: bool = False,
        use_multiprocessing: bool = False,
        checkpoint_file: Optional[str] = None,
        progress_ledger: Optional[ProgressLedger] = None,
        result_retention_limit: Optional[int] = DEFAULT_RESULT_RETENTION,
        result_retention_bytes: Optional[int] = DEFAULT_RESULT_RETENTION_BYTES
         ):
        """
        Initialize IntegratedFileReader with concurrency management
        
        Args:
            max_workers: Number of parallel workers
            enable_monitoring: Enable monitoring
            enable_storage: Enable database storage
            storage_source: Source name for storage
            storage_side: Side name for storage
            use_priority: Use priority-based scheduling
            use_multiprocessing: Use multiprocessing instead of threading
            checkpoint_file: Optional path to checkpoint file for resume functionality
            progress_ledger: Shared work ledger. Nested readers (archive members,
                email attachments, embedded objects) are handed the *parent's*
                ledger so dynamically discovered children grow the same
                denominator the user is watching. When omitted the reader owns a
                private ledger.
            result_retention_limit: How many per-file result dictionaries to
                keep in the list ``process_folder`` returns. Each result holds
                the extracted content, so retaining one per file means holding
                the whole corpus's extracted text in memory: measured at ~5 KB
                per file, i.e. ~5 GB for a million files. Aggregates (counts,
                bytes processed) are tracked exactly regardless of this bound,
                and the database remains the system of record - the bound only
                limits the in-RAM window. ``None`` keeps every result (legacy
                behaviour for small, programmatic callers).
        """
        # Apply safe worker count from resource coordinator
        try:
            from core.resource_coordinator import get_safe_worker_count
            max_workers = get_safe_worker_count(max_workers)
        except Exception:
            # If coordinator not available, use requested value
            pass

        # Optional adaptive scheduling (COMPUTE_ADAPTIVE_SCHEDULING=1): the
        # compute gateway may reduce - never raise - the worker count when the
        # host is under memory pressure, so an ingestion cannot push the machine
        # into swap.  Off by default: the coordinator's number stays
        # authoritative, and the gateway's admission control is available for
        # work submitted from outside the pipeline.
        if os.environ.get("COMPUTE_ADAPTIVE_SCHEDULING", "0") not in ("0", "false", "False"):
            try:
                from core.compute import get_compute_gateway

                advised = get_compute_gateway().suggested_workers(max_workers)
                if advised != max_workers:
                    logger.warning(
                        "Adaptive scheduling reduced workers %s -> %s under host pressure",
                        max_workers, advised,
                    )
                max_workers = advised
            except Exception as exc:
                logger.debug("Adaptive scheduling unavailable: %s", exc)
        
        self.max_workers = max_workers
        self.enable_monitoring = enable_monitoring
        self.enable_storage = enable_storage
        self.storage_source = storage_source
        self.storage_side = storage_side
        self.use_priority = use_priority
        self.use_multiprocessing = use_multiprocessing
        
        # Initialize storage concurrency limiter
        # Limit concurrent storage operations to prevent connection pool exhaustion
        # Formula: max(2, pool_max_conn // 4) - ensures we don't exhaust the pool
        try:
            from settings import get_database_config
            from core.resource_coordinator import get_safe_db_pool_size
            db_config = get_database_config()
            pool_size = get_safe_db_pool_size(db_config.pool_max_conn)
            # This limit is PROCESS-WIDE (see _get_storage_semaphore): every
            # reader shares one connection pool, so a per-reader semaphore would
            # let nested readers multiply the number of concurrent storage
            # transactions past the number of pooled connections.
            self._storage_semaphore = _get_storage_semaphore(max(2, pool_size // 4))
            logger.info(
                "Storage concurrency limit: %s concurrent operations (pool size: %s, process-wide)",
                getattr(self._storage_semaphore, '_value', '?'), pool_size,
            )
        except Exception as e:
            # Fallback: use 2 concurrent storage operations
            logger.warning(f"Could not determine optimal storage concurrency limit: {e}, using default: 2")
            self._storage_semaphore = _get_storage_semaphore(2)
        
        # Initialize concurrency hub
        self.concurrency_hub = ConcurrencyHub()
        if enable_monitoring:
            self.concurrency_hub.set_monitoring_interval(2.0)
        
        # Initialize concurrency managers
        self.thread_manager = None
        self.pool_manager = None
        
        if use_multiprocessing:
            # Use multiprocessing pool manager
            self.pool_manager = self.concurrency_hub.pool_mgr
            # Create a pool for file processing
            self.processing_pool_id = self.pool_manager.create_pool(
                name="File Processing Pool",
                worker_count=max_workers,
                priority=PoolPriority.NORMAL
            )
            # Get the pool object
            self.processing_pool = self.pool_manager.pools.get(self.processing_pool_id)
        else:
            # Use thread manager
            self.thread_manager = self.concurrency_hub.thread_mgr
        
        # Thread synchronization
        self._results_lock = threading.Lock()
        self._stats_lock = threading.Lock()

        # PROGRESS: the ledger is the single source of truth for work
        # accounting. ``_processing_stats`` is kept as a compatibility *view*
        # of it (get_statistics()/legacy callers) and is refreshed from the
        # ledger rather than mutated independently - two writable copies of the
        # same counters is what let nested work go missing before.
        #: Bounded in-RAM window of per-file results (see the constructor
        #: docstring).  ``DEFAULT_RESULT_RETENTION`` keeps a generous window for
        #: interactive/programmatic use while making a million-file run
        #: impossible to OOM through result retention alone.
        self._result_retention_limit = result_retention_limit
        self._result_retention_bytes = result_retention_bytes
        self._results_truncated = 0
        self._results_retained = 0
        self._results_retained_bytes = 0
        self._bytes_processed = 0

        self._owns_ledger = progress_ledger is None
        self.progress_ledger = progress_ledger or ProgressLedger(
            name=f"reader-{id(self):x}"
        )
        self._processing_stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'in_progress': 0
        }
        self._sync_stats_view()

        # Units opened by *this* reader and not yet settled (bounded by
        # concurrency, not by workload size).
        self._units_lock = threading.Lock()
        self._open_units = set()
        #: Paths handed to a worker and not yet settled; prevents the same file
        #: from being submitted to two workers at once.
        self._reserved_paths = set()
        #: Thread ids created by *this* reader (the thread manager is shared).
        self._owned_thread_ids = set()

        # JOB-SYSTEM: cooperative control hooks (used by the unified job
        # manager; inert unless requested). Cancellation is cooperative -
        # in-flight files finish, no *new* files are started. Pause behaves
        # the same but the job can be resumed (checkpointing skips already
        # processed files; deduplication makes re-scans safe).
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._current_file = None
        self._current_phase = None
        self.progress_callback = None  # fn(stats_snapshot) -> None, throttled by caller

        # Only the ledger's owner drives outward notification, so a nested
        # reader reporting into a shared ledger does not also need its own
        # (unset) callback - the parent's reaches the job system directly.
        if self._owns_ledger:
            self.progress_ledger.attach_notifier(self._on_ledger_change)

        # Initialize database if storage enabled
        self.db_hub = None
        self.storage_pipeline = None
        
        if enable_storage:
            self._init_storage()
        
        # Initialize checkpoint manager if checkpoint file provided
        self.checkpoint_manager = None
        if checkpoint_file:
            try:
                from core.checkpoint_manager import CheckpointManager
                # Checkpoint manager will be initialized when folder path is known
                self.checkpoint_file = checkpoint_file
            except ImportError as e:
                logger.warning(f"Checkpoint manager not available: {e}. Resume functionality disabled.")
                self.checkpoint_file = None
        else:
            self.checkpoint_file = None
    
    def _init_storage(self):
        """Initialize database connection and storage pipeline"""
        try:
            storage_cfg = get_storage_config()
            # CRITICAL FIX: Pass None to StoragePipeline so it uses shared DatabaseHub instance
            # This prevents connection pool exhaustion from multiple DatabaseHub instances
            # StoragePipeline will create/use shared singleton DatabaseHub internally
            self.storage_pipeline = StoragePipeline(
                db_hub=None,  # None = use shared singleton instance
                source_name=self.storage_source,
                side_name=self.storage_side
            )
            # Get the shared db_hub instance from storage_pipeline for backward compatibility
            self.db_hub = self.storage_pipeline.db_hub
            # A reader only owns a hub it created itself.  StoragePipeline hands
            # out the class-shared hub, so readers must NOT close it on exit -
            # a nested reader (one per extracted archive) used to close the
            # parent's hub mid-flight, which is what produced the
            # "Database connection unhealthy, attempting reconnect..." cascade.
            self._owns_db_hub = bool(getattr(self.storage_pipeline, 'db_hub_owned', False))
            logger.info("Database storage initialized with shared connection pool")
        except Exception as e:
            handle_error(
                e,
                category=ErrorCategory.DATABASE_CONNECTION if is_connection_error(e) else ErrorCategory.CONFIGURATION,
                severity=ErrorSeverity.HIGH,
                context={'operation': '_init_storage', 'storage_source': self.storage_source},
                suggested_action='Storage disabled, files will be processed but not stored to database'
            )
            self.enable_storage = False
            self.db_hub = None
            self.storage_pipeline = None
    
    def process_single_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Process a single file.

        PROGRESS: this is the entry point for single-object ingestion (one
        uploaded file, one ``path`` that is a file rather than a folder). It
        used to leave ``_processing_stats['total']`` at 0 for the whole run and
        never called ``_notify_progress()``, so ``get_live_progress()`` reported
        percent=0 from start to finish and the job manager only stamped 100%
        once everything was already over. That is the "0% then jump to 100%"
        path. The file is therefore registered as discovered work up front, and
        if it turns out to be a container its children grow the same ledger
        dynamically.

        Args:
            file_path: Path to file

        Returns:
            Processing result dictionary or None
        """
        if self._control_requested():
            logger.warning("Control requested: single-file processing not started")
            return None

        # Register before doing any work so the denominator exists immediately
        # and the first snapshot the UI receives is 0/1 (0%), not 0/0 (blank).
        self.progress_ledger.add_discovered(
            1, key=f"single::{file_path}", initial=self._owns_ledger
        )
        self._set_current(file_path=file_path, phase='Processing file')
        self._notify_progress()

        unit = self.progress_ledger.begin(
            path=file_path, phase='Processing file', depth=0, parent=None
        )
        with self._units_lock:
            self._open_units.add(unit)
        outcome = OUTCOME_COMPLETED

        try:
            # Validate file path
            if not file_path or not isinstance(file_path, str):
                handle_error(
                    ValueError(f"Invalid file_path: {file_path}"),
                    category=ErrorCategory.VALIDATION,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': 'process_single_file'}
                )
                outcome = OUTCOME_FAILED
                return None
            
            # PRODUCTION: Always create file_info, even if file doesn't exist or can't be accessed
            file_info = None
            file_exists = os.path.exists(file_path)
            
            if not file_exists:
                # Create minimal file_info for non-existent files
                file_info = {
                    'path': file_path,
                    'name': os.path.basename(file_path),
                    'extension': os.path.splitext(file_path)[1].lower(),
                    'type': 'FILE',
                    'size': 0,
                    'size_bytes': 0,
                    'readable': False,
                    'error': 'File not found'
                }
                handle_error(
                    FileNotFoundError(f"File not found: {file_path}"),
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': 'process_single_file'}
                )
                # Don't return None - still attempt to store
            else:
                # Get metadata
                try:
                    file_info = get_standardized_metadata(file_path)
                    if not file_info:
                        # Create minimal file_info if metadata retrieval fails
                        file_info = {
                            'path': file_path,
                            'name': os.path.basename(file_path),
                            'extension': os.path.splitext(file_path)[1].lower(),
                            'type': 'FILE',
                            'size': 0,
                            'size_bytes': 0,
                            'readable': False,
                            'error': 'Failed to get metadata'
                        }
                        handle_error(
                            Exception(f"Failed to get metadata for: {file_path}"),
                            category=ErrorCategory.FILE_PROCESSING,
                            severity=ErrorSeverity.MEDIUM,
                            context={'operation': 'process_single_file', 'file_path': file_path}
                        )
                        # Don't return None - still attempt to store
                except Exception as e:
                    # Create minimal file_info on exception
                    file_info = {
                        'path': file_path,
                        'name': os.path.basename(file_path),
                        'extension': os.path.splitext(file_path)[1].lower(),
                        'type': 'FILE',
                        'size': 0,
                        'size_bytes': 0,
                        'readable': False,
                        'error': f'Metadata error: {str(e)}'
                    }
                    handle_error(
                        e,
                        category=ErrorCategory.FILE_PROCESSING,
                        severity=ErrorSeverity.MEDIUM,
                        context={'operation': 'get_standardized_metadata', 'file_path': file_path}
                    )
                    # Don't return None - still attempt to store
            
            # Process file
            try:
                result = main_specify_method_of_reading_the_file(file_info, collect=True, depth=0,
                                          storage_source=getattr(self, 'storage_source', None),
                                          storage_side=getattr(self, 'storage_side', None),
                                          storage_pipeline=getattr(self, 'storage_pipeline', None),
                                          store_result=False,
                                          progress_ledger=self.progress_ledger)
            except Exception as e:
                handle_error(
                    e,
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': 'main_specify_method_of_reading_the_file', 'file_path': file_path}
                )
                # Create error result so file can still be stored
                from core.file_utils import create_standardized_result
                result = create_standardized_result(
                    file_path,
                    {"error": f"Processing failed: {str(e)}"},
                    0
                )
            
            # Store to database if enabled - ALWAYS store, even if result is None or has errors
            if self.enable_storage and self.storage_pipeline:
                try:
                    # If result is None, create a minimal result with error
                    if not result:
                        from core.file_utils import create_standardized_result
                        result = create_standardized_result(
                            file_path,
                            {"error": "Processing returned no result"},
                            0
                        )
                    
                    # Validate result is a dictionary
                    if not isinstance(result, dict):
                        logger.warning(f"Invalid result type for storage: {type(result).__name__}, expected dict. Creating error result.")
                        from core.file_utils import create_standardized_result
                        result = create_standardized_result(
                            file_path,
                            {"error": f"Invalid result type: {type(result).__name__}"},
                            0
                        )
                    
                    # Limit concurrent storage operations to prevent connection pool exhaustion
                    # Use semaphore to ensure only limited number of storage operations run simultaneously
                    with self._storage_semaphore:
                        # ALWAYS attempt to store, even if file has errors
                        path_id = self.storage_pipeline._store_file_sync(
                            file_info, 
                            result,
                            source_name=self.storage_source,
                            side_name=self.storage_side
                        )
                    if path_id:
                        result['database_path_id'] = path_id

                        # DEDUP ACCOUNTING: a path that resolved to an
                        # already-stored document is not new work.  Counting it
                        # as succeeded made a re-run report "1 succeeded, 0
                        # stored, 1 duplicate" - inconsistent in the Jobs UI
                        # and API.  It is reported as skipped (the file was
                        # accounted for, nothing new was written) while the
                        # storage statistics keep the duplicate count.
                        outcome = self._outcome_after_store(file_path, result, outcome)
                        # Storage success message is already logged by _store_file_sync
                        # Just add a brief confirmation here
                        file_name = file_info.get('name', Path(file_path).name)
                        logger.info(f"✅ Storage confirmed: '{file_name}' → Database (Path ID: {path_id})")
                        
                        # Mark file as processed in checkpoint manager (non-blocking, error-safe)
                        if self.checkpoint_manager:
                            try:
                                self.checkpoint_manager.mark_processed(file_info)
                            except Exception as cp_err:
                                # Don't let checkpoint errors interfere with storage success
                                logger.debug(f"Checkpoint marking failed (non-critical): {cp_err}")
                    else:
                        # Storage failed - provide clear error message
                        file_name = file_info.get('name', Path(file_path).name)
                        logger.error(f"❌ STORAGE FAILED: '{file_name}' was NOT stored in database")
                        logger.error(f"   File path: {file_path}")
                        logger.error("   Check database connection and logs above for details")
                except Exception as e:
                    handle_error(
                        e,
                        category=ErrorCategory.DATABASE if not is_connection_error(e) else ErrorCategory.DATABASE_CONNECTION,
                        severity=ErrorSeverity.MEDIUM,
                        context={
                            'operation': 'store_file_sync',
                            'file_path': file_path
                        },
                        suggested_action='File processed but not stored to database'
                    )
                    # Don't fail the entire operation if storage fails
                    # The file was successfully processed, just not stored
        
            if outcome == OUTCOME_COMPLETED:
                outcome = classify_result(result)
            return result
        except Exception as e:
            # Catch-all for any unexpected errors
            handle_error(
                e,
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.HIGH,
                context={'operation': 'process_single_file', 'file_path': file_path},
                suggested_action='Check file permissions and format'
            )
            outcome = OUTCOME_FAILED
            return None
        finally:
            with self._units_lock:
                self._open_units.discard(unit)
            unit.settle(outcome)
            self._set_current(phase='Completed')
            self._notify_progress()
    
    def process_folder(self, folder_path: str) -> List[Dict[str, Any]]:
        """
        Process all files in a folder with proper concurrency management and continuous processing.
        Uses generator-based processing to handle millions of files efficiently.
        
        Args:
            folder_path: Path to folder
        
        Returns:
            List of processing results
        """
        # Initialize checkpoint manager if checkpoint file is provided
        if self.checkpoint_file and not self.checkpoint_manager:
            try:
                from core.checkpoint_manager import CheckpointManager
                self.checkpoint_manager = CheckpointManager(
                    checkpoint_file=self.checkpoint_file,
                    folder_path=folder_path,
                    storage_source=self.storage_source,
                    storage_side=self.storage_side,
                    auto_save_interval=50  # OPTIMIZED: Save checkpoint every 50 files (reduced I/O)
                )
                logger.info(f"Checkpoint manager initialized: {self.checkpoint_file}")
            except Exception as e:
                logger.warning(f"Failed to initialize checkpoint manager: {e}. Continuing without resume support.")
                self.checkpoint_manager = None
        
        # PRODUCTION: Read directory tree with comprehensive error handling
        # ------------------------------------------------------------------
        # Discovery: one streaming pass to size the workload, then one
        # streaming pass per phase.
        #
        # The old implementation materialised the whole tree (metadata for
        # ~1.7 KB per entry - measured - so ~1.7 GB for a million files), built
        # three more full lists out of it, and hashed every file while doing so
        # (a serialized read of the entire corpus before processing started).
        # Discovery is now incremental: memory is bounded by the batch size,
        # not by the corpus, and hashing happens once - in the parallel store
        # stage, which computes the identical streamed SHA-256.
        # ------------------------------------------------------------------
        print("\n📂 Reading directory tree...")
        try:
            inventory = self._inventory_tree(folder_path)
        except Exception as tree_err:
            logger.error(f"Critical error reading directory tree: {tree_err}")
            # Record the root so at least it is stored, exactly as before.
            inventory = {
                'files': 0, 'errors': 1, 'skipped': 0, 'total': 1,
                'phases': dict.fromkeys(PHASE_NAMES, 0),
                'root_error': {
                    'path': folder_path,
                    'name': os.path.basename(folder_path),
                    'type': 'ERROR',
                    'extension': 'none',
                    'size': 0,
                    'size_bytes': 0,
                    'readable': False,
                    'error': f'Failed to read directory tree: {str(tree_err)}'
                },
            }

        file_count = inventory['files']
        error_count = inventory['errors']
        skipped_count = inventory['skipped']
        total_files = inventory['total'] - skipped_count
        remaining_files = total_files

        print(f"Found {file_count} files" + (f" and {error_count} items with errors" if error_count > 0 else ""))

        if error_count > 0:
            logger.warning(f"⚠️  {error_count} files/folders have access errors but will still be stored in database")

        if skipped_count > 0:
            print(f"Resuming: {skipped_count} files already processed, {remaining_files} remaining")
            # DATA-04: checkpoint-resumed files count as skipped, not discovered.
            if self.storage_pipeline is not None:
                self.storage_pipeline.record_skipped(
                    skipped_count, reason='checkpoint_already_processed'
                )

        # PROGRESS: skipped work is still accounted. It enters the denominator
        # and the terminal bucket in one step, so a resumed job can reach 100%
        # instead of stranding under it forever.
        if skipped_count:
            self.progress_ledger.record(
                OUTCOME_SKIPPED, skipped_count, parent=folder_path
            )

        if not total_files:
            if self.checkpoint_manager:
                checkpoint_stats = self.checkpoint_manager.get_statistics()
                print(f"\n✅ All files already processed! (Total: {checkpoint_stats['processed_count']} files)")
            # Still publish: the ledger may hold skipped/terminal work and the
            # job system needs a snapshot showing the run reached its end state.
            self.progress_ledger.set_phase('Completed')
            self._notify_progress()
            return []

        # For very large file sets, process in batches to conserve memory
        # This enables continuous processing without loading all files into memory
        batch_size = 1000  # Process 1000 files at a time for continuous processing

        phase_counts = inventory['phases']
        print(f"  📄 Priority files: {phase_counts['other']}")
        print(f"  📑 PDF files: {phase_counts['pdf']} (will be processed second-to-last)")
        print(f"  🖼️  Image files: {phase_counts['image']} (will be processed last)")

        # PROGRESS: register the discovered workload in the shared ledger.
        #
        # This replaces the old ``_processing_stats['total'] = len(files)``,
        # which was the root of the "0% then 100%" defect: it counted only
        # files visible on the filesystem *before* processing began, and it was
        # the sole denominator for the whole run. Containers opened later grow
        # the ledger dynamically (see FileRouterService._process_extracted_files).
        #
        # ``key=folder_path`` makes registration idempotent: the router registers
        # an extraction directory when it discovers it, and this nested reader
        # re-registers the same directory with its post-checkpoint count, which
        # reconciles instead of double-counting.
        #
        # ``initial=True`` records the first (top-level) workload separately so
        # the snapshot can report "initial" vs "total discovered" (spec item 3).
        self.progress_ledger.add_discovered(
            total_files,
            key=folder_path,
            initial=self._owns_ledger,
        )
        # Publish immediately: the UI now has a real denominator before the
        # first file finishes, instead of showing 0/0 (which renders as nothing).
        self._set_current(phase='Discovering files')
        self._notify_progress()

        # DATA-04: feed the persistent statistics service so dashboards and
        # consistency checks see discovered counts (previously never wired).
        if self.storage_pipeline is not None:
            self.storage_pipeline.record_discovered(total_files)

        # Process files in three phases: priority files first, then PDFs, then
        # images.  Each phase streams its own batches from the directory walk,
        # so neither the file list nor the whole-tree metadata is ever held in
        # memory at once.
        results = []

        #: (phase key, phase label for _set_current, header line, completion line,
        #:  control-request log wording)
        phase_plan = [
            ('other', 'Phase 1/3: documents & data',
             f"\n📄 PHASE 1: Processing {phase_counts['other']} priority files...",
             f"✅ PHASE 1 complete: {phase_counts['other']} priority files processed",
             "priority-file"),
            ('pdf', 'Phase 2/3: PDF files',
             f"\n📑 PHASE 2: Processing {phase_counts['pdf']} PDF files (after priority files are complete)...",
             f"✅ PHASE 2 complete: {phase_counts['pdf']} PDF files processed",
             "PDF"),
            ('image', 'Phase 3/3: images & OCR',
             f"\n🖼️  PHASE 3: Processing {phase_counts['image']} image files (after all other files are complete)...",
             f"✅ PHASE 3 complete: {phase_counts['image']} image files processed",
             "image"),
        ]

        for phase_key, phase_label, header, completion, control_wording in phase_plan:
            phase_total = phase_counts[phase_key]
            if not phase_total or self._control_requested():
                continue
            self._set_current(phase=phase_label)
            print(header)
            if phase_total > batch_size:
                print(f"   Processing in batches of {batch_size} for continuous processing...")

            batch_number = 0
            processed_in_phase = 0
            for batch in self._iter_phase_batches(folder_path, phase_key, batch_size,
                                                  inventory.get('root_error')):
                if self._control_requested():
                    logger.warning(f"Control requested: skipping remaining {control_wording} batches")
                    break
                batch_number += 1
                batch_start = processed_in_phase
                processed_in_phase += len(batch)
                if phase_total > batch_size:
                    print(f"   Batch {batch_number}: Processing files "
                          f"{batch_start + 1}-{processed_in_phase}...")
                results.extend(self._run_batch(batch))

            print(completion)

        
        # PROGRESS: end-of-run reconciliation.
        #
        # ``_reconcile_outstanding`` settles only units *this* reader opened, so
        # a nested reader sharing its parent's ledger cannot close the parent's
        # in-flight container unit. The pending sweep below is owner-only for
        # the same reason: a nested reader must not decide the fate of work its
        # parent has queued but not started.
        self._reconcile_outstanding(
            OUTCOME_SKIPPED if self._control_requested() else OUTCOME_FAILED
        )
        if self._owns_ledger:
            snapshot = self.progress_ledger.snapshot()
            outstanding = snapshot.get('files_pending', 0)
            if outstanding > 0:
                # Cancel/pause cut a submission loop short, so these files were
                # discovered but never entered a worker. They are terminal work
                # now (skipped) - leaving them pending would mean the indicator
                # could never honestly reach 100% for a cancelled job.
                logger.warning(
                    "%d discovered file(s) never reached a worker; recording as skipped",
                    outstanding,
                )
                # abandon(), not record(): these units are already in the
                # denominator, so only their terminal state is missing.
                self.progress_ledger.abandon(outstanding, OUTCOME_SKIPPED)
            self.progress_ledger.set_phase(
                'Cancelled' if self.is_cancel_requested()
                else 'Paused' if self.is_pause_requested()
                else 'Completed'
            )
            self._notify_progress()

        # PRODUCTION: Final verification - ensure all files were processed
        processed_count = len([r for r in results if r])
        failed_count = total_files - processed_count
        
        if failed_count > 0:
            logger.warning(f"⚠️  {failed_count} files may not have been processed. Check logs for details.")
            print(f"\n⚠️  Warning: {failed_count} files may not have been fully processed")
        
        # Finalize checkpoint if checkpoint manager is active
        if self.checkpoint_manager:
            self.checkpoint_manager.finalize()
            checkpoint_stats = self.checkpoint_manager.get_statistics()
            print(f"\n💾 Checkpoint saved: {checkpoint_stats['processed_count']} files processed")
        
        # PRODUCTION: Final summary
        print("\n📊 Processing Summary:")
        print(f"   Total files found: {total_files}")
        print(f"   Files processed: {processed_count}")
        if failed_count > 0:
            print(f"   Files with issues: {failed_count}")
        if self.enable_storage and self.storage_pipeline:
            storage_stats = self.get_storage_statistics()
            print(f"   Files stored in database: {storage_stats.get('completed', 0)}")
            print(f"   Duplicate files: {storage_stats.get('duplicates', 0)}")
            print(f"   Storage failures: {storage_stats.get('failed', 0)}")
        
        return results
    
    # ------------------------------------------------------------------
    # Streaming discovery
    #
    # The list-returning form (``read_tree``) costs ~1.7 KB of resident memory
    # per entry (measured) and therefore cannot be used for a corpus of
    # millions of files.  These helpers walk the tree with a generator and hand
    # the workers one batch at a time, so discovery memory is O(batch), not
    # O(corpus).
    # ------------------------------------------------------------------
    @staticmethod
    def _phase_of(file_info: Dict[str, Any]) -> str:
        """Which processing phase a record belongs to."""
        path = file_info.get('path', '') if isinstance(file_info, dict) else ''
        ext = os.path.splitext(path)[1].lower() if isinstance(path, str) else ''
        if ext in IMAGE_EXTENSIONS:
            return 'image'
        if ext in PDF_EXTENSIONS:
            return 'pdf'
        return 'other'

    def _inventory_tree(self, folder_path: str) -> Dict[str, Any]:
        """Size the workload with one streaming pass (no metadata retained).

        Counts exactly what the old list-based code counted: FILE records,
        ERROR records, the per-phase split, and how many files the checkpoint
        already knows about.  Records that were already processed are excluded
        from ``total`` (they are recorded as terminal *skipped* work instead),
        which is the existing accounting contract.
        """
        files = 0
        errors = 0
        skipped = 0
        phases = dict.fromkeys(PHASE_NAMES, 0)
        root_error = None
        for file_info in iter_tree(folder_path, compute_hashes=False):
            record_type = file_info.get('type')
            if record_type not in ('FILE', 'ERROR'):
                continue
            if root_error is None and record_type == 'ERROR' \
                    and file_info.get('path') == folder_path and folder_path:
                # A record describing the root itself (unreadable/absent root).
                root_error = file_info
            if self.checkpoint_manager and self.checkpoint_manager.is_processed(file_info):
                skipped += 1
                continue
            if record_type == 'FILE':
                files += 1
            else:
                errors += 1
            phases[self._phase_of(file_info)] += 1
        return {
            'files': files,
            'errors': errors,
            'skipped': skipped,
            'total': files + errors,
            'phases': phases,
            'root_error': root_error,
        }

    def _iter_phase_batches(self, folder_path: str, phase: str, batch_size: int,
                            root_error: Optional[Dict[str, Any]] = None):
        """Yield batches of records for one phase, streaming from disk.

        Yields lists of at most ``batch_size`` records, in tree order, skipping
        records the checkpoint already processed.  Nothing is accumulated
        beyond the batch currently being built.
        """
        batch: List[Dict[str, Any]] = []
        yielded_root_error = False
        for file_info in iter_tree(folder_path, compute_hashes=False):
            record_type = file_info.get('type')
            if record_type not in ('FILE', 'ERROR'):
                continue
            if self._phase_of(file_info) != phase:
                continue
            if self.checkpoint_manager and self.checkpoint_manager.is_processed(file_info):
                continue
            if root_error is not None and file_info is root_error:
                yielded_root_error = True
            batch.append(file_info)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _run_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process one batch with the configured concurrency mechanism."""
        if self.max_workers > 1:
            if self.use_multiprocessing and self.pool_manager:
                return self._process_with_pool(batch)
            return self._process_with_threads(batch)
        return self._process_sequential(batch)

    def _process_with_threads(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process files with a bounded window of worker threads.

        Scheduling model (this is what makes large corpora feasible):

        * **Bounded in-flight window.** At most ``max_workers`` (at least 2)
          workers run at a time.  The previous implementation created a thread
          for *every* file in the batch up front (1000-file batches meant 1000
          concurrent threads, each with its own queues and metrics), which
          exhausted memory and the thread registry instead of using the
          configured concurrency.
        * **Completion-order collection.** Finished workers are collected as
          they finish.  Waiting for worker N before looking at worker N+1 let a
          single slow file stall an entire batch whose other files were done.
        * **No fixed sleeps, no blocking reads that cannot pay off.** The old
          loop slept 50 ms per file and then waited up to twice 100 ms on an
          already-drained outbox; that alone capped ingestion at roughly four
          files per second regardless of CPU, worker count, or disk speed.  The
          collector now drains non-blockingly and only yields when nothing is
          ready, and the thread registry is pruned as workers are collected so
          a long run cannot accumulate one dead thread object per file.
        """
        results: List[Dict[str, Any]] = []
        total_files = len(files)

        # Determine priority based on file size for within-phase prioritization
        # All files are prioritized, with larger files getting higher priority
        def get_priority(file_info: Dict) -> ThreadPriority:
            if not self.use_priority:
                return ThreadPriority.NORMAL

            # Use size-based priority (larger files get higher priority for faster processing)
            # This ensures large files don't block smaller files, but large files are prioritized
            size = file_info.get('size_bytes', 0)
            if size > 100 * 1024 * 1024:  # > 100MB - highest priority
                return ThreadPriority.HIGH
            elif size > 10 * 1024 * 1024:  # > 10MB - high priority
                return ThreadPriority.HIGH
            elif size > 1 * 1024 * 1024:  # > 1MB - normal priority
                return ThreadPriority.NORMAL
            else:
                return ThreadPriority.NORMAL  # Small files also get normal priority (all files prioritized)

        # Get base timeout from processing config (default: 1200 seconds = 20 minutes)
        try:
            processing_cfg = get_processing_config()
            base_timeout = getattr(processing_cfg, 'file_processing_timeout', 1200)
            if base_timeout < 600:
                logger.warning(
                    f"File processing timeout ({base_timeout}s) is less than recommended minimum (600s). "
                    f"Large files may timeout. Consider increasing to at least 1200s."
                )
            logger.info(f"Using file processing timeout: {base_timeout}s (base) with dynamic scaling for large files")
        except Exception as e:
            logger.warning(f"Could not get processing config, using default timeout: {e}")
            base_timeout = 1200  # 20 minutes default
            logger.info(f"Using fallback timeout: {base_timeout}s")

        def calculate_file_timeout(file_info: Dict[str, Any], base_timeout: int) -> int:
            """
            Calculate dynamic timeout based on file size.
            PRODUCTION-READY: Handles terabyte-scale files with appropriate timeouts.
            Larger files get proportionally more time, with special handling for very large files.
            """
            if not isinstance(file_info, dict):
                return base_timeout

            file_size = file_info.get('size_bytes', 0) or 0
            if file_size == 0:
                return base_timeout

            # Base timeout for small files (< 1MB)
            if file_size < 1024 * 1024:
                return base_timeout

            size_mb = file_size / (1024 * 1024)
            size_gb = size_mb / 1024
            size_tb = size_gb / 1024

            # PRODUCTION: Different timeout calculation for different file size ranges
            if size_tb >= 1.0:
                # Terabyte-scale files: use more aggressive timeout scaling
                # Formula: base_timeout + (size_in_tb * 3600 seconds per TB) + buffer
                # This allows 1 hour per TB, with minimum 2 hours for any TB file
                extra_time = int(size_tb * 3600)  # 1 hour per TB
                dynamic_timeout = max(base_timeout * 2, base_timeout + extra_time)  # Minimum 2x base
                max_timeout = base_timeout * 20  # Cap at 20x base (e.g., 6.7 hours for 20min base)
                final_timeout = min(dynamic_timeout, max_timeout)
                logger.info(f"Terabyte file detected ({size_tb:.2f}TB), timeout: {final_timeout}s ({final_timeout/3600:.2f} hours)")
            elif size_gb >= 1.0:
                # Gigabyte-scale files: moderate scaling
                # Formula: base_timeout + (size_in_gb * 60 seconds per GB)
                extra_time = int(size_gb * 60)  # 60 seconds per GB
                dynamic_timeout = base_timeout + extra_time
                max_timeout = base_timeout * 10  # Cap at 10x base
                final_timeout = min(dynamic_timeout, max_timeout)
                logger.debug(f"Large file detected ({size_gb:.2f}GB), timeout: {final_timeout}s ({final_timeout/60:.1f} minutes)")
            else:
                # Megabyte-scale files: standard scaling
                # Formula: base_timeout + (size_in_mb * 30 seconds per MB)
                extra_time = int(size_mb * 30)  # 30 seconds per MB
                dynamic_timeout = base_timeout + extra_time
                max_timeout = base_timeout * 3  # Cap at 3x base
                final_timeout = min(dynamic_timeout, max_timeout)
                logger.debug(f"File size: {size_mb:.2f}MB, calculated timeout: {final_timeout}s (base: {base_timeout}s)")

            return final_timeout

        #: Number of workers allowed in flight.  ``max_workers`` is the
        #: configured concurrency; the extra factor covers the short window
        #: between a worker finishing its body and the collector reaping it,
        #: which would otherwise idle a core.
        try:
            configured_workers = int(getattr(self, 'max_workers', 4) or 4)
        except (TypeError, ValueError):
            configured_workers = 4
        in_flight_limit = max(2, configured_workers + max(1, configured_workers // 4))

        file_iterator = iter(enumerate(files))
        pending: List[list] = []          # [thread_id, thread, file_info, deadline]
        submission_stopped = False
        completed = 0

        def submit_next() -> bool:
            """Start one more worker (bounded window). False when input is done."""
            nonlocal submission_stopped
            if submission_stopped:
                return False
            for idx, file_info in file_iterator:
                # JOB-SYSTEM: cooperative stop - no new files after cancel/pause
                if self._control_requested():
                    logger.warning(
                        "Control requested (%s): stopping file submission after %d of %d files",
                        'cancel' if self.is_cancel_requested() else 'pause', idx, total_files,
                    )
                    submission_stopped = True
                    return False

                file_path = file_info.get('path', f'file_{idx}') if isinstance(file_info, dict) else f'file_{idx}'
                self._set_current(file_path=file_path, phase='Processing files')

                # A file that another worker of this reader is already processing
                # must not be submitted twice: the duplicate worker would store
                # the same document again and the extra unit would land in the
                # accounting as a "duplicate".  The path stays reserved until the
                # worker settles it (see ``_release_path``).
                if not self._reserve_path(file_path):
                    logger.debug("Skipping duplicate submission for %s (already in progress)", file_path)
                    continue

                priority = get_priority(file_info)

                thread_id = self.thread_manager.create_thread(
                    name=f"Process-{os.path.basename(file_path)}",
                    target=self._process_file_worker,
                    args=(file_info,),
                    priority=priority,
                    auto_start=True
                )
                # Get the thread object
                with self.thread_manager.lock:
                    thread = self.thread_manager.threads.get(thread_id)
                if thread is not None:
                    # Remember which threads this reader started.  The thread
                    # manager is shared with every other reader in the process, and
                    # a nested reader that joined the *parent's* still-running
                    # thread raised RuntimeError("cannot join current thread") -
                    # which aborted the parallel pass the container had already
                    # completed and made the caller reprocess it sequentially.
                    self._owned_thread_ids.add(thread_id)

                deadline = time.monotonic() + max(30, calculate_file_timeout(file_info, base_timeout))
                pending.append([thread_id, thread, file_info, deadline])
                return True
            submission_stopped = True
            return False

        def drain_outbox(thread_id: str) -> Optional[Dict[str, Any]]:
            """Collect a finished worker's messages without blocking.

            The worker posts progress strings and finally its result dict, so
            the outbox is drained until empty and the last dict wins.  No fixed
            delay is needed or wanted here: the thread has already finished, so
            anything it will ever post is already in the queue.
            """
            result = None
            for _ in range(10000):  # hard bound: never spin forever on a rogue producer
                msg = self.thread_manager.receive_from_thread_nowait(thread_id)
                if msg is None:
                    break
                if isinstance(msg, dict):
                    result = msg
            return result

        def finalize(entry: list) -> None:
            """Handle one finished (or expired) worker exactly once."""
            nonlocal completed
            thread_id, thread, file_info = entry[0], entry[1], entry[2]
            file_path = file_info.get('path', 'unknown') if isinstance(file_info, dict) else 'unknown'

            current_thread = threading.current_thread()
            if thread is not None and getattr(thread, 'ident', None) and thread.ident == current_thread.ident:
                logger.warning(
                    f"Skipping join for current thread {thread_id}. "
                    f"This can happen in nested parallel processing scenarios."
                )
                result = self._process_file_worker(file_info)
                self._count_processed_bytes(result)
                self._retain_result(results, result)
            elif thread is None:
                # Thread wasn't created, process synchronously
                result = self._process_file_worker(file_info)
                self._count_processed_bytes(result)
                self._retain_result(results, result)
            elif thread.is_alive():
                # Exceeded its deadline: report it, stop it, and settle as
                # retryable so it stays distinguishable from real failures.
                file_size_mb = file_info.get('size_bytes', 0) / (1024 * 1024) if isinstance(file_info, dict) else 0
                file_timeout = calculate_file_timeout(file_info, base_timeout)
                recommended_timeout = max(base_timeout, int(file_size_mb * 60) + 600)  # 60s per MB + 10 min base

                error_msg = (
                    f"File processing timeout: {os.path.basename(file_path)} "
                    f"({file_size_mb:.2f}MB) exceeded {file_timeout}s timeout "
                    f"(base: {base_timeout}s, dynamic: +{file_timeout - base_timeout}s). "
                    f"Recommended timeout for this file size: {recommended_timeout}s"
                )

                logger.error(error_msg)

                handle_error(
                    Exception(f"File processing timeout after {file_timeout}s (base: {base_timeout}s)"),
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.MEDIUM,
                    context={
                        'operation': '_process_with_threads',
                        'file_path': file_path,
                        'timeout': file_timeout,
                        'base_timeout': base_timeout,
                        'file_size_mb': round(file_size_mb, 2),
                        'recommended_timeout': recommended_timeout,
                        'suggested_action': (
                            f'Increase file_processing_timeout in settings.json to at least {recommended_timeout}s '
                            f'(current: {base_timeout}s). Or process this file individually with a longer timeout.'
                        )
                    }
                )

                # Try to stop the thread gracefully
                try:
                    self.thread_manager.stop_thread(thread_id, timeout=5.0)
                except Exception as stop_error:
                    logger.debug(f"Could not stop timed-out thread gracefully: {stop_error}")

                # PROGRESS: a timed-out worker is abandoned but may still be
                # running. settle_path() closes its unit exactly once as
                # retryable; if the worker settles first, this is a no-op -
                # so a file is never counted twice. Retryable is reported in
                # its own bucket, keeping it distinguishable from work that
                # terminally succeeded or failed.
                self.progress_ledger.settle_path(file_path, OUTCOME_RETRYABLE)
                self._release_path(file_path)
                self._notify_progress()
                self._discard_finished_thread(thread_id)
                completed += 1
                console.progress(f"Progress: {completed}/{total_files}")
                return
            elif thread.metrics.state == ThreadState.ERROR:
                handle_error(
                    Exception(thread.metrics.error_msg or "Thread processing failed"),
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': '_process_with_threads', 'file_path': file_path}
                )
                # PROGRESS: the thread died before its worker could settle,
                # so close the unit here. settle_path() is a no-op when the
                # worker already did it.
                self.progress_ledger.settle_path(file_path, OUTCOME_FAILED)
                self._release_path(file_path)
            else:
                # Try to get result from outbox
                result = None
                try:
                    result = drain_outbox(thread_id)

                    # If no result reached the outbox, only reprocess when the
                    # worker has not already stored the file.  Re-running the
                    # full worker unconditionally re-read and re-stored the
                    # document, which showed up as duplicate store attempts and
                    # inflated the duplicate counters for a job that had in fact
                    # stored the file once.
                    if not result:
                        pipeline = getattr(self, 'storage_pipeline', None)
                        already_stored = False
                        if pipeline is not None and file_path:
                            try:
                                already_stored = pipeline.get_store_outcome(file_path) is not None
                            except Exception:
                                already_stored = False
                        if already_stored:
                            logger.debug(
                                "No result in outbox for %s, but it was already stored - not reprocessing",
                                file_path,
                            )
                        else:
                            logger.debug(f"No result from thread {thread_id} outbox, reprocessing synchronously")
                            result = self._process_file_worker(file_info)
                except Exception as e:
                    handle_error(
                        e,
                        category=ErrorCategory.FILE_PROCESSING,
                        severity=ErrorSeverity.MEDIUM,
                        context={'operation': '_process_with_threads', 'file_path': file_path}
                    )
                    self.progress_ledger.settle_path(file_path, OUTCOME_FAILED)
                    self._release_path(file_path)

                # Count the file's size for the exact total, then retain the
                # result while the bounded window allows it.
                self._count_processed_bytes(result)
                self._retain_result(results, result)

            self._discard_finished_thread(thread_id)
            completed += 1
            console.progress(f"Progress: {completed}/{total_files}")
            self._notify_progress()

        while True:
            # Keep the window full.
            while len(pending) < in_flight_limit:
                if not submit_next():
                    break

            if not pending:
                break

            progressed = False
            now = time.monotonic()
            for entry in list(pending):
                thread = entry[1]
                state = None
                try:
                    state = thread.metrics.state if thread is not None else None
                except Exception:
                    state = None
                finished = (
                    thread is None
                    or not thread.is_alive()
                    or state in (ThreadState.COMPLETED, ThreadState.ERROR, ThreadState.STOPPED)
                )
                expired = now >= entry[3]
                if not (finished or expired):
                    continue
                pending.remove(entry)
                progressed = True
                finalize(entry)

            if not progressed and pending:
                # Nothing ready yet: yield briefly instead of busy-waiting.
                # 1 ms keeps wake-ups cheap while still reaping a completion
                # within a millisecond of it happening.
                time.sleep(0.001)

        # Anything this reader opened but never closed (thread stopped, join
        # interrupted) is settled here so it cannot stay pending forever.
        self._reconcile_outstanding(
            OUTCOME_SKIPPED if self._control_requested() else OUTCOME_FAILED
        )
        console.end_progress()  # Terminate the in-place progress line
        return results

    def _process_with_pool(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process files using multiprocessing pool manager"""
        results = []
        
        if not self.processing_pool:
            logger.error("Processing pool not available")
            # These files were discovered and registered, so they must still
            # reach a terminal state or the bar can never legitimately hit 100%.
            self.progress_ledger.abandon(len(files), OUTCOME_FAILED)
            self._notify_progress()
            return results
        
        # Submit all tasks to the pool
        task_ids = []
        for idx, file_info in enumerate(files):
            # Submit task using pool manager
            task_id = self.pool_manager.submit_task(
                pool_id=self.processing_pool_id,
                func=self._process_file_worker,
                args=(file_info,),
                kwargs={}
            )
            task_ids.append((task_id, file_info))
        
        # Wait for tasks to complete
        completed = 0
        for task_id, file_info in task_ids:
            # Wait for task result using pool manager
            task_result = self.pool_manager.wait_for_task(
                pool_id=self.processing_pool_id,
                task_id=task_id,
                timeout=300  # 5 minutes max per file
            )
            
            completed += 1
            console.progress(f"Progress: {completed}/{len(files)}")
            
            if task_result:
                if task_result.success:
                    result = task_result.result
                    self._retain_result(results, result)
                else:
                    # Task failed
                    file_path = file_info.get('path', 'unknown')
                    handle_error(
                        Exception(task_result.error or "Task processing failed"),
                        category=ErrorCategory.FILE_PROCESSING,
                        severity=ErrorSeverity.MEDIUM,
                        context={'operation': '_process_with_pool', 'file_path': file_path}
                    )
                    self.progress_ledger.settle_path(file_path, OUTCOME_FAILED)
            else:
                # Timeout
                file_path = file_info.get('path', 'unknown')
                handle_error(
                    Exception(f"Task timeout for {file_path}"),
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': '_process_with_pool', 'file_path': file_path}
                )
                self.progress_ledger.settle_path(file_path, OUTCOME_RETRYABLE)

            # PROGRESS: publish only; the ledger owns the counters.
            self._notify_progress()

        self._reconcile_outstanding(OUTCOME_FAILED)
        console.end_progress()  # Terminate the in-place progress line
        return results
    
    def _process_sequential(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process files sequentially"""
        results = []

        for idx, file_info in enumerate(files, 1):
            # JOB-SYSTEM: honour cooperative cancel/pause here too. The threaded
            # and pool paths both stop submitting new files on a control
            # request, but this path passed no check_stop and tested nothing, so
            # a single-worker job (max_workers == 1) ran its entire workload
            # after being cancelled. Stopping at a file boundary is exactly the
            # documented contract.
            if self._control_requested():
                logger.warning(
                    "Control requested (%s): stopping sequential processing after %d of %d files",
                    'cancel' if self.is_cancel_requested() else 'pause', idx - 1, len(files),
                )
                break

            console.progress(f"Progress: {idx}/{len(files)}")

            result = self._process_file_worker(file_info)
            self._count_processed_bytes(result)
            self._retain_result(results, result)

            # PROGRESS: the worker already settled this unit in the ledger, so
            # the counters are authoritative here - this loop only has to
            # publish. It previously wrote ``completed = idx`` straight into
            # ``_processing_stats`` and never notified at all, which is why a
            # single-worker run reported no live progress whatsoever.
            self._notify_progress()

        self._reconcile_outstanding(OUTCOME_FAILED)
        console.end_progress()  # Terminate the in-place progress line
        return results

    def _process_file_worker(
        self, 
        file_info: Dict[str, Any],
        check_pause=None,
        check_stop=None,
        send_message=None
         ) -> Optional[Dict[str, Any]]:
        """
        Worker function for processing a single file
        Supports pause/stop controls from concurrency managers
        
        Args:
            file_info: File information dictionary
            check_pause: Optional pause check function (from thread manager)
            check_stop: Optional stop check function (from thread manager)
            send_message: Optional message sending function (from thread manager)
        """
        file_path = file_info.get('path', 'unknown') if file_info else 'unknown'

        # PROGRESS: account for this file the instant a worker picks it up and
        # settle it on *every* exit path via the finally clause at the bottom.
        # Doing it here instead of in the join loop is what makes progress
        # real-time - the join loop in _process_with_threads runs in submission
        # order, so one slow container in slot 0 used to hold ``completed`` at 0
        # while every other worker had already finished.
        unit = self._begin_unit(
            file_info if isinstance(file_info, dict) else {'path': file_path}
        )
        outcome = OUTCOME_COMPLETED

        try:
            # Check for stop signal
            if check_stop and check_stop():
                logger.info(f"Processing stopped for: {file_path}")
                outcome = OUTCOME_SKIPPED
                return None
            
            # CRITICAL: Validate file_info but create minimal version if invalid to prevent data loss
            if not file_info or not isinstance(file_info, dict):
                handle_error(
                    ValueError(f"Invalid file_info: {file_info}"),
                    category=ErrorCategory.VALIDATION,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': '_process_file_worker'}
                )
                # Create minimal file_info to ensure file can still be processed
                file_info = {
                    'path': str(file_info) if file_info else 'unknown',
                    'name': 'unknown',
                    'extension': '',
                    'size': 0
                }
                logger.warning(f"Created minimal file_info: {file_info}")
            
            # CRITICAL: Validate file path exists and is accessible
            file_path = file_info.get('path', 'unknown')
            if not file_path or not isinstance(file_path, str):
                logger.error(f"Invalid file path: {file_path}")
                # Create error result for storage
                from core.file_utils import create_standardized_result
                error_result = create_standardized_result(
                    str(file_path),
                    {"error": f"Invalid file path: {file_path}"},
                    0
                )
                # Still attempt to store with error information
                if self.enable_storage and self.storage_pipeline:
                    try:
                        with self._storage_semaphore:
                            path_id = self.storage_pipeline._store_file_sync(
                                file_info,
                                error_result,
                                source_name=self.storage_source,
                                side_name=self.storage_side
                            )
                        if path_id:
                            logger.info(f"✅ Stored file with invalid path error: Path ID: {path_id}")
                    except Exception as storage_error:
                        logger.error(
                            f"❌ Failed to store file with invalid path: {type(storage_error).__name__}: {storage_error}"
                        )
                        import traceback
                        logger.debug(f"Storage error traceback: {traceback.format_exc()}")
                outcome = OUTCOME_FAILED
                return None

            # PRODUCTION: Check file accessibility and handle permission errors gracefully
            file_exists = os.path.exists(file_path)
            file_readable = False
            
            if file_exists:
                try:
                    file_readable = os.access(file_path, os.R_OK)
                except Exception:
                    file_readable = False
            
            # PRODUCTION: If file is not readable, create error result but still attempt to store
            if file_exists and not file_readable:
                logger.warning(f"File exists but is not readable (permission denied): {file_path}")
                # Create error result for storage
                from core.file_utils import create_standardized_result
                error_result = create_standardized_result(
                    file_path,
                    {"error": "File is not readable (permission denied)"},
                    0
                )
                # Still attempt to store with error information
                if self.enable_storage and self.storage_pipeline:
                    try:
                        with self._storage_semaphore:
                            path_id = self.storage_pipeline._store_file_sync(
                                file_info,
                                error_result,
                                source_name=self.storage_source,
                                side_name=self.storage_side
                            )
                        if path_id:
                            logger.info(f"✅ Stored file with permission error: Path ID: {path_id}")
                        outcome = OUTCOME_FAILED
                        return error_result
                    except Exception as storage_error:
                        logger.error(
                            f"❌ Failed to store file with permission error: {type(storage_error).__name__}: {storage_error}"
                        )
                        import traceback
                        logger.debug(f"Storage error traceback: {traceback.format_exc()}")
                outcome = OUTCOME_FAILED
                return error_result

            # Check if file exists (but don't fail - some files might be processed from memory)
            if not file_exists:
                logger.warning(f"File does not exist: {file_path} - will attempt processing anyway")
                # Don't return None - some readers can handle non-existent files or process from memory
            
            # Check for pause
            if check_pause:
                check_pause()
            
            # Send progress message if available
            if send_message:
                send_message(f"Processing: {os.path.basename(file_path)}")
            
            # Process file
            try:
                # DATA-01/ARCH-04: storage context is passed explicitly (no
                # function-attribute globals). The worker owns persistence of
                # the top-level file (store_result=False); the router still
                # persists child artifacts (extracted members, attachments).
                #
                # PROGRESS: the ledger travels the same explicit route. It is
                # what lets a container's children - discovered only after this
                # worker started - register into the denominator the job is
                # already reporting against, instead of into a private counter
                # on a second reader that nobody reads.
                if self.enable_storage:
                    result = main_specify_method_of_reading_the_file(
                        file_info, collect=True, depth=0,
                        storage_source=self.storage_source,
                        storage_side=self.storage_side,
                        storage_pipeline=self.storage_pipeline,
                        store_result=False,
                        progress_ledger=self.progress_ledger,
                    )
                else:
                    result = main_specify_method_of_reading_the_file(
                        file_info, collect=True, depth=0,
                        progress_ledger=self.progress_ledger,
                    )
            except Exception as e:
                handle_error(
                    e,
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': '_process_file_worker', 'file_path': file_path}
                )
                # Create error result so file can still be stored
                from core.file_utils import create_standardized_result
                result = create_standardized_result(
                    file_path,
                    {"error": f"Processing failed: {str(e)}"},
                    0
                )
                # PROGRESS: outcome is derived from the result below, so the
                # ledger (not a hand-incremented counter) records the failure.
                outcome = OUTCOME_FAILED

            # Check for stop signal again
            if check_stop and check_stop():
                logger.info(f"Processing stopped after file read: {file_path}")
                outcome = OUTCOME_SKIPPED
                return None
            
            # Store if enabled - ALWAYS store, even if result is None or has errors
            if self.enable_storage and self.storage_pipeline:
                try:
                    # If result is None, create a minimal result with error
                    if not result:
                        from core.file_utils import create_standardized_result
                        result = create_standardized_result(
                            file_path,
                            {"error": "Processing returned no result"},
                            0
                        )
                    
                    # Validate result is a dictionary before storing
                    if not isinstance(result, dict):
                        logger.warning(f"Invalid result type for storage: {type(result).__name__}, expected dict. Creating error result.")
                        from core.file_utils import create_standardized_result
                        result = create_standardized_result(
                            file_path,
                            {"error": f"Invalid result type: {type(result).__name__}"},
                            0
                        )
                    
                    # Limit concurrent storage operations to prevent connection pool exhaustion
                    # Use semaphore to ensure only limited number of storage operations run simultaneously
                    try:
                        with self._storage_semaphore:
                            # ALWAYS attempt to store, even if file has errors
                            path_id = self.storage_pipeline._store_file_sync(
                                file_info, 
                                result,
                                source_name=self.storage_source,
                                side_name=self.storage_side
                            )
                    except Exception as storage_exception:
                        # Log storage exception but don't fail the entire operation
                        file_name = file_info.get('name', os.path.basename(file_path))
                        logger.error(
                            f"❌ Storage exception for '{file_name}': {type(storage_exception).__name__}: {storage_exception}"
                        )
                        import traceback
                        logger.debug(f"Storage exception traceback: {traceback.format_exc()}")
                        path_id = None
                    
                    if path_id:
                        if not result:
                            result = {}
                        result['database_path_id'] = path_id

                        # DEDUP ACCOUNTING: a path that resolved to an
                        # already-stored document is not new work.  Counting it
                        # as succeeded made a re-run report "1 succeeded, 0
                        # stored, 1 duplicate" - inconsistent in the Jobs UI
                        # and API.  It is reported as skipped (the file was
                        # accounted for, nothing new was written) while the
                        # storage statistics keep the duplicate count.
                        outcome = self._outcome_after_store(file_path, result, outcome)
                        # Storage success message is already logged by _store_file_sync
                        # Just add a brief confirmation for batch processing
                        file_name = file_info.get('name', os.path.basename(file_path))
                        if send_message:
                            send_message(f"✅ Stored: {file_name} → Database (Path ID: {path_id})")
                        
                        # Mark file as processed in checkpoint manager (non-blocking, error-safe)
                        if self.checkpoint_manager:
                            try:
                                self.checkpoint_manager.mark_processed(file_info)
                            except Exception as cp_err:
                                # Don't let checkpoint errors interfere with storage success
                                logger.debug(f"Checkpoint marking failed (non-critical): {cp_err}")
                    else:
                        # Storage failed - provide clear error message
                        file_name = file_info.get('name', os.path.basename(file_path))
                        logger.error(f"❌ STORAGE FAILED: '{file_name}' was NOT stored in database")
                        logger.error(f"   File path: {file_path}")
                        if send_message:
                            send_message(f"❌ Storage failed: {file_name}")
                except Exception as e:
                    handle_error(
                        e,
                        category=ErrorCategory.DATABASE if not is_connection_error(e) else ErrorCategory.DATABASE_CONNECTION,
                        severity=ErrorSeverity.MEDIUM,
                        context={'operation': '_process_file_worker', 'file_path': file_path},
                        suggested_action='File processed but not stored to database'
                    )
                    # Don't fail - file was processed successfully
            
            # Send result via send_message if available (for thread manager to retrieve)
            # This is critical because thread manager doesn't capture return values
            if send_message and result:
                try:
                    send_message(result)
                except Exception as e:
                    logger.debug(f"Error sending result via send_message: {e}")

            # PROGRESS: classify the real outcome - an unsupported type, an
            # error payload or a timeout each land in their own bucket, so
            # skipped/unsupported objects stay visible in the accounting
            # instead of silently vanishing.
            if outcome == OUTCOME_COMPLETED:
                outcome = classify_result(result)
            return result
        except Exception as e:
            # Catch-all for any unexpected errors
            # CRITICAL: Still attempt to store file metadata even on unexpected errors
            handle_error(
                e,
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.MEDIUM,
                context={'operation': '_process_file_worker', 'file_path': file_path}
            )
            
            # Attempt to store file with error information
            if self.enable_storage and self.storage_pipeline:
                try:
                    # Create error result for storage
                    from core.file_utils import create_standardized_result
                    error_result = create_standardized_result(
                        file_path,
                        {"error": f"Unexpected error during processing: {str(e)}"},
                        0
                    )
                    
                    # Limit concurrent storage operations to prevent connection pool exhaustion
                    try:
                        with self._storage_semaphore:
                            # Store with error information
                            path_id = self.storage_pipeline._store_file_sync(
                                file_info if file_info and isinstance(file_info, dict) else {'path': file_path, 'name': os.path.basename(file_path)},
                                error_result,
                                source_name=self.storage_source,
                                side_name=self.storage_side
                            )
                        if path_id:
                            logger.info(f"✅ Stored file with error information: {os.path.basename(file_path)} (Path ID: {path_id})")
                    except Exception as storage_exception:
                        logger.error(
                            f"❌ Failed to store file even after error: {os.path.basename(file_path)} - "
                            f"{type(storage_exception).__name__}: {storage_exception}"
                        )
                        import traceback
                        logger.debug(f"Storage exception traceback: {traceback.format_exc()}")
                except Exception as storage_error:
                    logger.error(
                        f"❌ Failed to store file even after error: {os.path.basename(file_path)} - "
                        f"{type(storage_error).__name__}: {storage_error}"
                    )
                    import traceback
                    logger.debug(f"Storage error traceback: {traceback.format_exc()}")
            
            outcome = OUTCOME_FAILED
            return None
        finally:
            # Exactly-once settlement: if this worker was already abandoned on
            # timeout the unit is settled and this is a no-op, so a file can
            # never be counted twice.
            self._finish_unit(unit, outcome)
            # The file is no longer in flight, so it may be submitted again
            # (for example by a later phase or a resumed job).
            self._release_path(file_path)

    def _outcome_after_store(self, file_path: str, result, outcome: str) -> str:
        """Refine a completed outcome with the storage pipeline's verdict.

        A store attempt that resolved to an already-stored document wrote
        nothing new, so the file is accounted for as *skipped* (with
        ``duplicate`` flagged on the result) instead of *succeeded*.  Live
        progress, job statistics and the storage counters then agree.

        Never raises: accounting must not break an ingest that actually
        succeeded.
        """
        pipeline = getattr(self, 'storage_pipeline', None)
        if pipeline is None:
            return outcome
        try:
            store_outcome = pipeline.get_store_outcome(file_path)
        except Exception:
            return outcome
        if store_outcome == 'duplicate':
            if isinstance(result, dict):
                result['duplicate'] = True
            return OUTCOME_SKIPPED
        return outcome

    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup with proper resource management"""
        # Wait for the workers *this* reader started.
        #
        # The thread manager (ConcurrencyHub) is process-wide, so its registry
        # also holds threads created by other readers - including the caller's
        # own thread when this reader is the nested one processing an archive's
        # extracted files.  Joining that thread raises
        # RuntimeError("cannot join current thread"), which used to abort an
        # already-successful parallel pass and send the container through the
        # sequential fallback again (storing every member twice).
        if self.thread_manager:
            current_ident = threading.current_thread().ident
            with self.thread_manager.lock:
                threads = [
                    self.thread_manager.threads[tid]
                    for tid in self._owned_thread_ids
                    if tid in self.thread_manager.threads
                ]
            for thread in threads:
                if thread.ident is not None and thread.ident == current_ident:
                    logger.warning(
                        "Skipping join for the current thread (%s) during cleanup",
                        thread.name,
                    )
                    continue
                if thread.metrics.state in [ThreadState.RUNNING, ThreadState.PAUSED]:
                    try:
                        thread.join(timeout=30)  # Wait up to 30 seconds
                    except RuntimeError as join_err:
                        # Defensive: a thread can never be joined from itself.
                        logger.warning(
                            "Could not join thread %s during cleanup: %s", thread.name, join_err
                        )
        
        if self.pool_manager and hasattr(self, 'processing_pool_id'):
            # Wait for all tasks in the pool to complete
            self.pool_manager.wait_all_tasks(self.processing_pool_id, timeout=60)
            # Close the pool
            self.pool_manager.close_pool(self.processing_pool_id)
        
        # Close the database handle only when this reader created it.  The
        # storage pipeline hands out a class-shared hub, and a nested reader
        # (one per extracted archive/email) closing it pulled the pool out from
        # under every other in-flight worker - the origin of the repeated
        # "Database connection unhealthy, attempting reconnect..." sequence.
        if self.db_hub and getattr(self, '_owns_db_hub', False):
            self.db_hub.close()
        
        # Finalize checkpoint if active
        if self.checkpoint_manager:
            self.checkpoint_manager.finalize()

        # Shutdown concurrency managers if monitoring was enabled
        if self.enable_monitoring:
            try:
                # Note: We don't shutdown the hub here as it might be used elsewhere
                # Individual managers will clean up their own resources
                pass
            except Exception as e:
                logger.warning(f"Error during concurrency manager cleanup: {e}")
    
    # ------------------------------------------------------------------
    # JOB-SYSTEM: cooperative control + live progress API
    # ------------------------------------------------------------------
    def request_cancel(self) -> None:
        """Cooperatively cancel: finish in-flight files, start no new ones."""
        self._cancel_event.set()

    def request_pause(self) -> None:
        """Cooperatively pause: finish in-flight files, start no new ones."""
        self._pause_event.set()

    def clear_pause(self) -> None:
        self._pause_event.clear()

    def is_cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def is_pause_requested(self) -> bool:
        return self._pause_event.is_set()

    def _control_requested(self) -> bool:
        return self._cancel_event.is_set() or self._pause_event.is_set()

    def get_live_progress(self) -> Dict[str, Any]:
        """Real worker-state snapshot for the job system's progress panel.

        Read from the shared ledger, so it includes work discovered *after*
        processing began - archive members, email attachments, embedded
        Office/OpenDocument objects and recursively nested containers.
        """
        snapshot = self.progress_ledger.snapshot()
        self._sync_stats_view(snapshot)
        return snapshot

    def _sync_stats_view(self, snapshot: Optional[Dict[str, Any]] = None) -> None:
        """Refresh the legacy ``_processing_stats`` dict from the ledger."""
        snap = snapshot if snapshot is not None else self.progress_ledger.snapshot()
        with self._stats_lock:
            self._processing_stats['total'] = snap.get('total_files', 0)
            self._processing_stats['completed'] = snap.get('files_completed', 0)
            self._processing_stats['failed'] = (
                snap.get('files_failed', 0)
                + snap.get('files_retryable', 0)
            )
            self._processing_stats['in_progress'] = snap.get('in_progress', 0)
            # Extended counters, additive - existing consumers keep working.
            self._processing_stats['skipped'] = snap.get('files_skipped', 0)
            self._processing_stats['unsupported'] = snap.get('files_unsupported', 0)
            self._processing_stats['retryable'] = snap.get('files_retryable', 0)
            self._processing_stats['nested'] = snap.get('files_nested', 0)
            self._processing_stats['initial_total'] = snap.get('files_initial', 0)
            self._processing_stats['pending'] = snap.get('files_pending', 0)
            self._processing_stats['percent'] = snap.get('percent', 0)
            self._processing_stats['done'] = snap.get('files_done', 0)

    def _set_current(self, file_path: Optional[str] = None, phase: Optional[str] = None) -> None:
        if file_path is not None:
            self._current_file = file_path
            self.progress_ledger.set_current(file_path)
        if phase is not None:
            self._current_phase = phase
            self.progress_ledger.set_phase(phase)

    def _on_ledger_change(self, snapshot: Dict[str, Any]) -> None:
        """Ledger -> outward callback bridge (installed only by the owner)."""
        self._sync_stats_view(snapshot)
        cb = self.progress_callback
        if cb is None:
            return
        try:
            cb(snapshot)
        except Exception:
            logger.debug("progress callback raised", exc_info=True)

    def _notify_progress(self) -> None:
        """Push a snapshot out through ``progress_callback``."""
        cb = self.progress_callback
        if cb is not None:
            try:
                cb(self.get_live_progress())
            except Exception:
                logger.debug("progress callback raised", exc_info=True)

    # ------------------------------------------------------------------
    # PROGRESS: per-unit bookkeeping
    #
    # The reader tracks only the units *it* opened. That matters because a
    # nested reader shares the parent's ledger while running inside the
    # parent's worker: if it reconciled every in-flight unit on exit it would
    # settle the parent's own container unit early.
    # ------------------------------------------------------------------
    def _reserve_path(self, path: Optional[str]) -> bool:
        """Reserve ``path`` for one worker; False when it is already reserved.

        A file may only be in flight once per reader.  Without this guard the
        phase-based submission in ``_process_with_threads`` (and the nested
        per-extraction readers) could hand the same file to two workers, which
        stored it twice and then reported the second attempt as a duplicate.
        """
        if not path:
            return True
        with self._units_lock:
            if path in self._reserved_paths:
                return False
            self._reserved_paths.add(path)
            return True

    def _release_path(self, path: Optional[str]) -> None:
        """Release a reservation made by :meth:`_reserve_path`."""
        if not path:
            return
        with self._units_lock:
            self._reserved_paths.discard(path)

    def _retain_result(self, results: List[Dict[str, Any]], result: Any) -> None:
        """Collect one worker result into the caller-visible list, bounded.

        The list returned by ``process_folder`` is a *reporting* convenience;
        the database is the system of record.  Keeping it proportional to the
        corpus (with extracted content in every entry) is what would make a
        million-file run run out of memory, so it is a bounded window and the
        exact totals live in ``get_statistics()``: ``bytes_processed`` and
        ``results_truncated`` are maintained for every file whether or not its
        dictionary is retained.
        """
        if not result:
            return
        if not isinstance(result, dict):
            logger.warning("Worker returned invalid result type: %s. Skipping.", type(result).__name__)
            return
        size = self._result_footprint(result)
        with self._results_lock:
            # The bound is reader-wide, not per call: process_folder runs one
            # collection per phase (priority/PDF/image), so a per-list bound
            # multiplied the window by the number of phases instead of capping
            # it (measured: a 25k-file run retained all 25k results).
            limit = self._result_retention_limit
            byte_limit = self._result_retention_bytes
            if limit is not None and self._results_retained >= limit:
                self._results_truncated += 1
                return
            # A strict ceiling: it never grows past the budget, even for the
            # first result.  A result bigger than the whole budget is counted
            # as truncated like any other - the database still has it.
            if byte_limit is not None and self._results_retained_bytes + size > byte_limit:
                self._results_truncated += 1
                return
            self._results_retained += 1
            self._results_retained_bytes += size
            results.append(result)

    @staticmethod
    def _result_footprint(result: Any) -> int:
        """Approximate bytes a result dictionary costs while retained.

        Content dominates and is usually a ``str``: its length is the number of
        code points, which for the ASCII-heavy text this pipeline extracts is
        the byte count (a small over-estimate is returned for non-ASCII, which
        is the safe direction for a memory bound).
        """
        total = 0
        if not isinstance(result, dict):
            return 0
        for value in result.values():
            total += _object_footprint(value)
        return total

    def _count_processed_bytes(self, result: Any) -> None:
        """Add one file's size to the exact byte total, retained or not."""
        size = 0
        if isinstance(result, dict):
            metadata = result.get("Metadata")
            if isinstance(metadata, dict):
                size = metadata.get("FileSize") or 0
            if not size:
                size = result.get("file_size") or 0
        try:
            self._bytes_processed += int(size)
        except (TypeError, ValueError):
            pass

    def _discard_finished_thread(self, thread_id) -> None:
        """Drop a collected worker from the shared thread registry.

        Called only for threads this reader owns and has already collected, so
        a long ingestion cannot retain one dead thread object (plus its queues
        and metrics) per processed file.
        """
        if not thread_id or self.thread_manager is None:
            return
        if thread_id not in self._owned_thread_ids:
            return
        try:
            if self.thread_manager.discard_finished_thread(thread_id):
                self._owned_thread_ids.discard(thread_id)
        except Exception:
            logger.debug("Could not discard finished thread %s", thread_id, exc_info=True)

    def _begin_unit(self, file_info: Dict[str, Any], phase: Optional[str] = None):
        """Open a ledger unit for one file and remember it for reconciliation."""
        path = None
        if isinstance(file_info, dict):
            path = file_info.get('path')
        unit = self.progress_ledger.begin(
            path=path,
            phase=phase or self._current_phase or 'Processing files',
            depth=0,
            parent=None,
        )
        with self._units_lock:
            self._open_units.add(unit)
        return unit

    def _finish_unit(self, unit, outcome: str) -> bool:
        """Settle a unit exactly once and stop tracking it."""
        if unit is None:
            return False
        with self._units_lock:
            self._open_units.discard(unit)
        return unit.settle(outcome)

    def _reconcile_outstanding(self, outcome: str = OUTCOME_SKIPPED) -> int:
        """Settle units this reader opened but never closed.

        Called when a batch ends (including on cancel/pause). Without it, work
        that was discovered but abandoned would stay ``pending`` forever and the
        indicator could never legitimately reach 100%.
        """
        with self._units_lock:
            units = list(self._open_units)
            self._open_units.clear()
        settled = 0
        for unit in units:
            if unit.settle(outcome):
                settled += 1
        return settled

    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics with concurrency metrics.

        ``bytes_processed`` and the result-window counters are exact even when
        the per-file result dictionaries are bounded (see
        :meth:`_retain_result`), so callers that used to sum sizes over the
        returned list have an authoritative aggregate to use instead.
        """
        # Ledger is authoritative; refresh the compatibility view first.
        self._sync_stats_view()
        with self._stats_lock:
            stats = self._processing_stats.copy()
        stats['bytes_processed'] = self._bytes_processed
        stats['results_retained'] = self._results_retained
        stats['results_truncated'] = self._results_truncated
        stats['result_retention_limit'] = self._result_retention_limit
        stats['result_retention_bytes'] = self._result_retention_bytes
        stats['results_retained_bytes'] = self._results_retained_bytes
        
        # Add concurrency metrics
        if self.thread_manager:
            thread_stats = self.thread_manager.get_statistics()
            stats['active_threads'] = thread_stats.get('running', 0)
            stats['total_threads'] = thread_stats.get('total', 0)
            stats['completed_threads'] = thread_stats.get('completed', 0)
            stats['failed_threads'] = thread_stats.get('errors', 0)
            stats['paused_threads'] = thread_stats.get('paused', 0)
        
        if self.pool_manager and hasattr(self, 'processing_pool_id'):
            pool = self.pool_manager.pools.get(self.processing_pool_id)
            if pool:
                stats['pool_tasks_submitted'] = pool.metrics.tasks_submitted
                stats['pool_tasks_completed'] = pool.metrics.tasks_completed
                stats['pool_tasks_failed'] = pool.metrics.tasks_failed
        
        return stats
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """Get storage statistics from storage pipeline"""
        if self.storage_pipeline:
            stats = self.storage_pipeline.get_statistics()
            return {
                'completed': stats.get('files_stored', 0),
                'duplicates': stats.get('files_duplicates', 0),
                'failed': stats.get('files_failed', 0),
                'processed': stats.get('files_processed', 0)
            }
        return {
            'completed': 0,
            'duplicates': 0,
            'failed': 0,
            'processed': 0
        }


# Standalone worker for multiprocessing (must be at module level)
def _standalone_process_file_worker(file_info):
    """Standalone worker for multiprocessing"""
    return main_specify_method_of_reading_the_file(file_info, collect=True, depth=0)
