"""
Checkpoint Manager - Handles pause/resume functionality for file processing

This module provides checkpoint/resume capabilities to allow processing to continue
from where it left off after power outages, device shutdowns, or other interruptions.
"""

import json
import hashlib
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Manages checkpoint state for file processing operations.
    
    Tracks processed files and allows resuming from the last checkpoint.
    Checkpoints are saved to disk periodically to ensure progress is not lost.
    """
    
    def __init__(
        self,
        checkpoint_file: str,
        folder_path: str,
        storage_source: Optional[str] = None,
        storage_side: Optional[str] = None,
        auto_save_interval: int = 10
    ):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_file: Path to checkpoint JSON file
            folder_path: Path to folder being processed
            storage_source: Optional storage source name (for checkpoint identification)
            storage_side: Optional storage side name (for checkpoint identification)
            auto_save_interval: Number of files processed before auto-saving checkpoint
        """
        self.checkpoint_file = Path(checkpoint_file)
        self.folder_path = Path(folder_path).resolve()
        self.storage_source = storage_source
        self.storage_side = storage_side
        self.auto_save_interval = auto_save_interval
        
        # Thread-safe tracking
        self._lock = threading.Lock()
        self._processed_files: Set[str] = set()
        self._processed_count = 0
        self._last_save_count = 0
        
        # Background thread for non-blocking checkpoint saves
        self._save_thread = None
        self._save_event = threading.Event()
        self._shutdown = False
        
        # Load existing checkpoint if available
        self._load_checkpoint()
        
        # Start background save thread for non-blocking saves (only if enabled)
        # OPTIMIZATION: Use lazy initialization to avoid creating thread if not needed
        self._save_thread = None
        self._thread_started = False
    
    def _get_file_identifier(self, file_info: Dict[str, Any]) -> str:
        """
        Generate unique identifier for a file.
        
        Uses file path + modification time for uniqueness.
        This allows detecting if a file was modified since last processing.
        
        OPTIMIZED: Avoids expensive Path.resolve() call - uses path as-is with normalization.
        
        Args:
            file_info: File metadata dictionary
            
        Returns:
            Unique identifier string
        """
        file_path = file_info.get('path', '')
        modified = file_info.get('modified', '')
        
        # OPTIMIZATION: Use path as-is, just normalize separators (much faster than resolve())
        # Path.resolve() is expensive and not necessary for checkpoint tracking
        # Normalize path separators to handle Windows/Unix differences
        normalized_path = file_path.replace('\\', '/').lower()
        
        identifier = f"{normalized_path}|{modified}"
        
        # Use hash for consistent length and to handle long paths
        return hashlib.sha256(identifier.encode('utf-8')).hexdigest()
    
    def _load_checkpoint(self) -> None:
        """Load checkpoint state from file if it exists."""
        if not self.checkpoint_file.exists():
            logger.info(f"No existing checkpoint found at {self.checkpoint_file}")
            return
        
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate checkpoint matches current folder and storage settings
            checkpoint_folder = data.get('folder_path', '')
            checkpoint_source = data.get('storage_source')
            checkpoint_side = data.get('storage_side')
            
            # OPTIMIZATION: Normalize paths without expensive resolve()
            # Just normalize separators for comparison
            checkpoint_folder_normalized = checkpoint_folder.replace('\\', '/').lower()
            current_folder_normalized = str(self.folder_path).replace('\\', '/').lower()
            
            if checkpoint_folder_normalized != current_folder_normalized:
                logger.warning(
                    f"Checkpoint folder mismatch: checkpoint={checkpoint_folder_normalized}, "
                    f"current={current_folder_normalized}. Ignoring checkpoint."
                )
                return
            
            # Check storage settings match (if specified)
            if self.storage_source and checkpoint_source != self.storage_source:
                logger.warning(
                    f"Checkpoint source mismatch: checkpoint={checkpoint_source}, "
                    f"current={self.storage_source}. Ignoring checkpoint."
                )
                return
            
            if self.storage_side and checkpoint_side != self.storage_side:
                logger.warning(
                    f"Checkpoint side mismatch: checkpoint={checkpoint_side}, "
                    f"current={self.storage_side}. Ignoring checkpoint."
                )
                return
            
            # Load processed files
            processed_files = data.get('processed_files', [])
            self._processed_files = set(processed_files)
            self._processed_count = data.get('processed_count', len(processed_files))
            self._last_save_count = self._processed_count
            
            logger.info(
                f"Loaded checkpoint: {len(self._processed_files)} files already processed "
                f"(from {data.get('last_updated', 'unknown')})"
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid checkpoint file format: {e}. Starting fresh.")
            self._processed_files = set()
        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}. Starting fresh.")
            self._processed_files = set()
    
    def _save_checkpoint(self, blocking: bool = False) -> None:
        """
        Save current checkpoint state to file.
        
        OPTIMIZED: Can save in background thread to avoid blocking processing.
        
        Args:
            blocking: If True, save synchronously. If False, trigger background save.
        """
        if blocking:
            # Synchronous save (for finalization)
            self._save_checkpoint_sync()
        else:
            # Lazy start background thread only when needed
            if not self._thread_started:
                self._save_thread = threading.Thread(
                    target=self._background_save_worker,
                    name="CheckpointSaveThread",
                    daemon=True
                )
                self._save_thread.start()
                self._thread_started = True
            
            # Trigger background save (non-blocking)
            self._save_event.set()
    
    def _save_checkpoint_sync(self) -> None:
        """
        Synchronously save checkpoint state to file.
        
        OPTIMIZED: Minimal I/O, compact JSON format, error handling.
        """
        try:
            # Ensure checkpoint directory exists
            self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Get current state (with minimal lock time)
            with self._lock:
                processed_files_list = list(self._processed_files)
                processed_count = self._processed_count
                folder_path_str = str(self.folder_path)
                source = self.storage_source
                side = self.storage_side
            
            # OPTIMIZATION: Use compact JSON (no indentation) to reduce I/O
            data = {
                'folder_path': folder_path_str,
                'storage_source': source,
                'storage_side': side,
                'processed_files': processed_files_list,
                'processed_count': processed_count,
                'last_updated': datetime.now().isoformat(),
                'version': '1.0'  # For future compatibility
            }
            
            # Write to temporary file first, then rename (atomic operation)
            # OPTIMIZATION: Use compact JSON format (no indent) for faster I/O
            temp_file = self.checkpoint_file.with_suffix('.tmp')
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, separators=(',', ':'), ensure_ascii=False)  # Compact format
                
                # Atomic rename
                temp_file.replace(self.checkpoint_file)
                
                # Update last save count (with lock)
                with self._lock:
                    self._last_save_count = processed_count
                
                logger.debug(f"Checkpoint saved: {processed_count} files processed")
            except IOError as io_err:
                # I/O errors are non-critical - don't block processing
                logger.warning(f"Checkpoint I/O error (non-critical): {io_err}")
            except Exception as save_err:
                logger.warning(f"Checkpoint save error (non-critical): {save_err}")
            
        except Exception as e:
            # Don't let checkpoint errors interfere with processing
            logger.warning(f"Checkpoint save failed (non-critical): {e}")
    
    def _background_save_worker(self) -> None:
        """Background thread worker for non-blocking checkpoint saves."""
        while not self._shutdown:
            # Wait for save event
            if self._save_event.wait(timeout=1.0):
                # Save checkpoint
                self._save_checkpoint_sync()
                # Clear event
                self._save_event.clear()
    
    def is_processed(self, file_info: Dict[str, Any]) -> bool:
        """
        Check if a file has already been processed.
        
        OPTIMIZED: Calculates identifier outside lock to minimize lock time.
        
        Args:
            file_info: File metadata dictionary
            
        Returns:
            True if file was already processed, False otherwise
        """
        # Calculate identifier outside lock (faster)
        file_id = self._get_file_identifier(file_info)
        with self._lock:
            return file_id in self._processed_files
    
    def mark_processed(self, file_info: Dict[str, Any]) -> None:
        """
        Mark a file as processed and save checkpoint if needed.
        
        OPTIMIZED: Non-blocking checkpoint saves with reduced frequency to avoid I/O overload.
        
        Args:
            file_info: File metadata dictionary
        """
        # Calculate identifier outside lock (faster)
        file_id = self._get_file_identifier(file_info)
        
        should_save = False
        with self._lock:
            if file_id not in self._processed_files:
                self._processed_files.add(file_id)
                self._processed_count += 1
                
                # OPTIMIZATION: Increase save interval to reduce I/O overhead
                # Save less frequently to avoid system overload
                # Check if we need to save (but don't save in lock)
                if self._processed_count - self._last_save_count >= self.auto_save_interval:
                    should_save = True
        
        # Trigger background save if needed (non-blocking, lazy thread start)
        if should_save:
            try:
                self._save_checkpoint(blocking=False)
            except Exception as e:
                # Don't let checkpoint errors interfere with processing
                logger.warning(f"Checkpoint save failed (non-critical): {e}")
    
    def filter_processed_files(
        self,
        files: List[Dict[str, Any]]
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Filter out already processed files from a list.
        
        OPTIMIZED: Batch operation - calculates all identifiers first, then checks in single lock.
        
        Args:
            files: List of file metadata dictionaries
            
        Returns:
            Tuple of (unprocessed_files, skipped_count)
        """
        # OPTIMIZATION: Calculate all identifiers first (outside lock)
        file_ids = [self._get_file_identifier(file_info) for file_info in files]
        
        # Single lock acquisition to check all files at once
        with self._lock:
            processed_set = self._processed_files
        
        # Filter files (no lock needed here)
        unprocessed = []
        skipped = 0
        
        for file_info, file_id in zip(files, file_ids):
            if file_id in processed_set:
                skipped += 1
            else:
                unprocessed.append(file_info)
        
        if skipped > 0:
            logger.info(f"Resuming: Skipping {skipped} already processed files, {len(unprocessed)} remaining")
        
        return unprocessed, skipped
    
    def save_checkpoint(self, blocking: bool = True) -> None:
        """
        Manually save checkpoint (thread-safe).
        
        Args:
            blocking: If True, wait for save to complete. If False, trigger background save.
        """
        self._save_checkpoint(blocking=blocking)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get checkpoint statistics.
        
        Returns:
            Dictionary with checkpoint statistics
        """
        with self._lock:
            return {
                'processed_count': self._processed_count,
                'processed_files': len(self._processed_files),
                'checkpoint_file': str(self.checkpoint_file),
                'last_save_count': self._last_save_count
            }
    
    def clear_checkpoint(self) -> None:
        """Clear checkpoint and delete checkpoint file."""
        with self._lock:
            self._processed_files.clear()
            self._processed_count = 0
            self._last_save_count = 0
            
            if self.checkpoint_file.exists():
                try:
                    self.checkpoint_file.unlink()
                    logger.info(f"Checkpoint cleared: {self.checkpoint_file}")
                except Exception as e:
                    logger.error(f"Error deleting checkpoint file: {e}")
    
    def finalize(self) -> None:
        """
        Finalize checkpoint - save final state and optionally clean up.
        
        Call this when processing is complete to ensure final state is saved.
        """
        # Shutdown background thread
        self._shutdown = True
        self._save_event.set()  # Trigger final save
        
        # Wait for background thread to finish current save
        if self._save_thread and self._save_thread.is_alive():
            self._save_thread.join(timeout=5.0)
        
        # Final synchronous save to ensure everything is saved
        self._save_checkpoint_sync()
        
        with self._lock:
            logger.info(
                f"Checkpoint finalized: {self._processed_count} files processed. "
                f"Checkpoint saved to {self.checkpoint_file}"
            )
