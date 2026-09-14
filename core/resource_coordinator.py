"""
Resource Coordinator - Prevents system freezes by managing resource allocation
across multiple application instances (CLI and Web).

This module:
- Detects running application instances
- Calculates safe worker counts based on system resources
- Limits database connections per instance
- Monitors CPU/memory to prevent overload
"""

import os
import sys
import multiprocessing
import threading
import time
import json
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass
import logging

# Try to import psutil, but handle gracefully if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    # Create a minimal fallback
    class _FakePsutil:
        @staticmethod
        def cpu_count():
            return multiprocessing.cpu_count()
        
        @staticmethod
        def virtual_memory():
            class _Memory:
                total = 8 * 1024**3  # Assume 8GB default
                available = 4 * 1024**3
                percent = 50.0
            return _Memory()
        
        @staticmethod
        def cpu_percent(interval=None):
            return 50.0  # Assume moderate load
    
    psutil = _FakePsutil()

logger = logging.getLogger(__name__)


@dataclass
class ResourceLimits:
    """Resource limits for an application instance"""
    max_workers: int
    db_pool_max: int
    cpu_limit_percent: float = 80.0
    memory_limit_percent: float = 80.0


class ResourceCoordinator:
    """
    Coordinates resource usage across multiple application instances.
    Prevents system freezes by intelligently allocating resources.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            # Get project root for lock file
            try:
                from core.path_utils import setup_path
                project_root = setup_path()
            except:
                project_root = Path.cwd()
            
            self.lock_file = project_root / '.app_instance.lock'
            self.instance_id = f"{os.getpid()}_{int(time.time())}"
            self.instance_type = self._detect_instance_type()
            
            # System resources
            self.cpu_count = multiprocessing.cpu_count()
            try:
                self.total_memory_gb = psutil.virtual_memory().total / (1024**3)
            except Exception:
                # Fallback if psutil fails
                self.total_memory_gb = 8.0  # Assume 8GB default
            
            # Resource limits
            self._update_resource_limits()
            
            # Register this instance
            self._register_instance()
            
            # Start monitoring thread
            self._monitoring = False
            self._monitor_thread = None
            self._start_monitoring()
            
            # Cleanup on exit
            import atexit
            atexit.register(self._cleanup)
            
            self._initialized = True
            
            logger.info(f"Resource Coordinator initialized for {self.instance_type}")
            logger.info(f"  Instance ID: {self.instance_id}")
            logger.info(f"  CPU cores: {self.cpu_count}")
            logger.info(f"  Total memory: {self.total_memory_gb:.1f} GB")
            logger.info(f"  Allocated workers: {self.resource_limits.max_workers}")
            logger.info(f"  Allocated DB pool: {self.resource_limits.db_pool_max}")
    
    def _detect_instance_type(self) -> str:
        """Detect if this is CLI or Web instance"""
        script_name = Path(sys.argv[0]).name.lower()
        if 'run_cli' in script_name or 'cli' in script_name:
            return 'cli'
        elif 'run_web' in script_name or 'web' in script_name or 'flask' in script_name:
            return 'web'
        else:
            return 'unknown'
    
    def _get_running_instances(self) -> Dict[str, Dict]:
        """Get all running application instances from lock file"""
        instances = {}
        
        if not self.lock_file.exists():
            return instances
        
        try:
            with open(self.lock_file, 'r') as f:
                data = json.load(f)
                # Filter out stale instances (older than 5 minutes)
                current_time = time.time()
                for instance_id, info in data.items():
                    if current_time - info.get('last_update', 0) < 300:  # 5 minutes
                        instances[instance_id] = info
        except Exception as e:
            logger.debug(f"Error reading lock file: {e}")
        
        return instances
    
    def _register_instance(self):
        """Register this instance in the lock file"""
        instances = self._get_running_instances()
        
        instances[self.instance_id] = {
            'pid': os.getpid(),
            'type': self.instance_type,
            'started_at': time.time(),
            'last_update': time.time(),
            'workers': self.resource_limits.max_workers,
            'db_pool': self.resource_limits.db_pool_max
        }
        
        try:
            with open(self.lock_file, 'w') as f:
                json.dump(instances, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not write lock file: {e}")
    
    def _update_instance(self):
        """Update this instance's timestamp in lock file"""
        instances = self._get_running_instances()
        
        if self.instance_id in instances:
            instances[self.instance_id]['last_update'] = time.time()
            instances[self.instance_id]['workers'] = self.resource_limits.max_workers
            instances[self.instance_id]['db_pool'] = self.resource_limits.db_pool_max
            
            try:
                with open(self.lock_file, 'w') as f:
                    json.dump(instances, f, indent=2)
            except Exception as e:
                logger.debug(f"Could not update lock file: {e}")
    
    def _update_resource_limits(self):
        """Calculate safe resource limits based on running instances"""
        instances = self._get_running_instances()
        
        # Count instances by type
        cli_count = sum(1 for inst in instances.values() if inst.get('type') == 'cli')
        web_count = sum(1 for inst in instances.values() if inst.get('type') == 'web')
        total_instances = len(instances)
        
        # If this is a new instance, don't count it yet
        if self.instance_id not in instances:
            if self.instance_type == 'cli':
                cli_count += 1
            elif self.instance_type == 'web':
                web_count += 1
            total_instances += 1
        
        # Calculate safe worker count
        # Reserve 2 cores for system, divide remaining cores among instances
        available_cores = max(1, self.cpu_count - 2)
        
        if total_instances == 1:
            # Only this instance - use more resources
            max_workers = min(4, available_cores)
        elif total_instances == 2:
            # Two instances - split resources
            max_workers = max(1, available_cores // 2)
        else:
            # Multiple instances - be conservative
            max_workers = max(1, available_cores // total_instances)
        
        # For web instances, use fewer workers (they're usually lighter)
        if self.instance_type == 'web':
            max_workers = max(1, max_workers - 1)
        
        # Ensure minimum of 1 worker
        max_workers = max(1, min(max_workers, 4))
        
        # Calculate database pool size
        # Need enough connections for concurrent workers + buffer
        # Each worker may need 2-3 connections (transaction + nested operations + bulk inserts)
        # Formula: (max_workers * 3) + buffer for other operations
        base_pool_size = (max_workers * 3) + 6  # 3 connections per worker + 6 buffer
        
        # Split among instances if multiple instances running
        if total_instances == 1:
            db_pool_max = min(base_pool_size, 25)  # Allow up to 25 for single instance
        elif total_instances == 2:
            db_pool_max = min(base_pool_size // 2, 20)  # Split but allow up to 20 per instance
        else:
            # For multiple instances, be more generous - allow at least 15 per instance
            # This prevents connection exhaustion during heavy operations
            db_pool_max = max(15, min(base_pool_size // total_instances, 20))
        
        # Ensure minimum of 10 connections (needed for concurrent processing with bulk operations)
        # Increased from 6 to 10 to handle concurrent web requests better
        db_pool_max = max(10, db_pool_max)
        
        self.resource_limits = ResourceLimits(
            max_workers=max_workers,
            db_pool_max=db_pool_max
        )
        
        logger.debug(f"Resource limits updated: {max_workers} workers, {db_pool_max} DB connections")
        logger.debug(f"  Running instances: CLI={cli_count}, Web={web_count}, Total={total_instances}")
    
    def _start_monitoring(self):
        """Start background monitoring thread"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="ResourceMonitor"
        )
        self._monitor_thread.start()
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        self._system_overload = False
        self._last_cpu_percent = 0.0
        self._last_memory_percent = 0.0
        
        while self._monitoring:
            try:
                # Update instance registration
                self._update_instance()
                
                # Check system resources
                try:
                    cpu_percent = psutil.cpu_percent(interval=0.5)  # Faster detection
                    memory = psutil.virtual_memory()
                    memory_percent = memory.percent
                    
                    self._last_cpu_percent = cpu_percent
                    self._last_memory_percent = memory_percent
                except Exception as e:
                    logger.debug(f"Error checking system resources: {e}")
                    continue  # Skip this monitoring cycle
                
                # If system is overloaded, reduce workers and set overload flag
                overload_threshold = 85.0  # Lower threshold for proactive response
                was_overloaded = self._system_overload
                
                if cpu_percent > overload_threshold or memory_percent > overload_threshold:
                    self._system_overload = True
                    if not was_overloaded:  # Only log when overload state changes
                        logger.warning(
                            f"System overload detected: CPU={cpu_percent:.1f}%, "
                            f"Memory={memory_percent:.1f}%"
                        )
                        # Immediately yield CPU to prevent freezing
                        try:
                            time.sleep(0.1)  # Small yield to prevent immediate freeze
                        except:
                            pass
                    # Aggressively reduce workers when overloaded
                    if self.resource_limits.max_workers > 1:
                        # Reduce by 2 if severely overloaded (>95%), otherwise by 1
                        reduction = 2 if cpu_percent > 95.0 or memory_percent > 95.0 else 1
                        self.resource_limits.max_workers = max(1, self.resource_limits.max_workers - reduction)
                        logger.info(
                            f"Reduced workers to {self.resource_limits.max_workers} "
                            f"(reduced by {reduction}) due to system load"
                        )
                else:
                    # System recovered - gradually increase workers if below limit
                    if self._system_overload:
                        self._system_overload = False
                        logger.info(
                            f"System recovered: CPU={cpu_percent:.1f}%, "
                            f"Memory={memory_percent:.1f}%"
                        )
                    # Gradually restore workers when system is stable (below 70%)
                    if cpu_percent < 70 and memory_percent < 70:
                        if self.resource_limits.max_workers < self._calculate_optimal_workers():
                            self.resource_limits.max_workers = min(
                                self.resource_limits.max_workers + 1,
                                self._calculate_optimal_workers()
                            )
                
                # Sleep for monitoring interval
                time.sleep(5)  # Check every 5 seconds for faster response
                
            except Exception as e:
                logger.debug(f"Error in monitoring loop: {e}")
                time.sleep(5)
    
    def _calculate_optimal_workers(self) -> int:
        """Calculate optimal worker count based on available resources"""
        instances = self._get_running_instances()
        total_instances = len(instances)
        if self.instance_id not in instances:
            total_instances += 1
        
        available_cores = max(1, self.cpu_count - 2)
        if total_instances == 1:
            return min(4, available_cores)
        elif total_instances == 2:
            return max(1, available_cores // 2)
        else:
            return max(1, available_cores // total_instances)
    
    def _cleanup(self):
        """Clean up instance registration"""
        try:
            instances = self._get_running_instances()
            if self.instance_id in instances:
                del instances[self.instance_id]
                
                if instances:
                    with open(self.lock_file, 'w') as f:
                        json.dump(instances, f, indent=2)
                else:
                    # No more instances, remove lock file
                    if self.lock_file.exists():
                        self.lock_file.unlink()
        except Exception as e:
            logger.debug(f"Error during cleanup: {e}")
        
        self._monitoring = False
    
    def get_safe_worker_count(self, requested: Optional[int] = None) -> int:
        """
        Get safe worker count for this instance.
        
        Args:
            requested: Requested worker count (from settings)
        
        Returns:
            Safe worker count that won't overload the system
        """
        # Update limits based on current instances
        self._update_resource_limits()
        
        if requested is None:
            return self.resource_limits.max_workers
        
        # Use the minimum of requested and calculated safe limit
        return min(requested, self.resource_limits.max_workers)
    
    def get_safe_db_pool_size(self, requested: Optional[int] = None) -> int:
        """
        Get safe database pool size for this instance.
        
        Args:
            requested: Requested pool size (from settings)
        
        Returns:
            Safe pool size that won't exhaust database connections
        """
        # Update limits based on current instances
        self._update_resource_limits()
        
        if requested is None:
            return self.resource_limits.db_pool_max
        
        # Use the minimum of requested and calculated safe limit
        return min(requested, self.resource_limits.db_pool_max)
    
    def is_system_overloaded(self) -> bool:
        """
        Check if system is currently overloaded.
        
        Returns:
            True if system is overloaded (CPU > 85% or Memory > 85%)
        """
        return self._system_overload
    
    def should_yield(self, aggressive: bool = False) -> bool:
        """
        Check if current operation should yield to prevent system overload.
        
        Args:
            aggressive: If True, use more aggressive thresholds for yielding
        
        Returns:
            True if operation should yield/pause
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Use aggressive thresholds if requested, or if system is already overloaded
            cpu_threshold = 75.0 if aggressive or self._system_overload else 90.0
            memory_threshold = 75.0 if aggressive or self._system_overload else 90.0
            
            return cpu_percent > cpu_threshold or memory_percent > memory_threshold
        except Exception:
            return False
    
    def get_yield_duration(self) -> float:
        """
        Get recommended yield duration based on current system load.
        
        Returns:
            Seconds to sleep/yield (0.0 to 0.1)
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            if cpu_percent > 95:
                return 0.1  # 100ms for severe overload
            elif cpu_percent > 85:
                return 0.05  # 50ms for high load
            elif cpu_percent > 75:
                return 0.01  # 10ms for moderate load
            else:
                return 0.0  # No yield needed
        except Exception:
            return 0.01  # Default small yield if monitoring fails
    
    def get_resource_status(self) -> Dict:
        """Get current resource status"""
        instances = self._get_running_instances()
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)
        except Exception:
            cpu_percent = 0.0
            memory_percent = 0.0
            memory_available_gb = 0.0
        
        return {
            'instance_id': self.instance_id,
            'instance_type': self.instance_type,
            'cpu_count': self.cpu_count,
            'cpu_percent': cpu_percent,
            'memory_total_gb': self.total_memory_gb,
            'memory_percent': memory_percent,
            'memory_available_gb': memory_available_gb,
            'max_workers': self.resource_limits.max_workers,
            'db_pool_max': self.resource_limits.db_pool_max,
            'system_overload': getattr(self, '_system_overload', False),
            'running_instances': {
                'total': len(instances),
                'cli': sum(1 for inst in instances.values() if inst.get('type') == 'cli'),
                'web': sum(1 for inst in instances.values() if inst.get('type') == 'web')
            }
        }


# Global instance
_coordinator: Optional[ResourceCoordinator] = None
_coordinator_lock = threading.Lock()


def get_resource_coordinator() -> ResourceCoordinator:
    """Get the global resource coordinator instance"""
    global _coordinator
    if _coordinator is None:
        with _coordinator_lock:
            if _coordinator is None:
                _coordinator = ResourceCoordinator()
    return _coordinator


def get_safe_worker_count(requested: Optional[int] = None) -> int:
    """
    Get safe worker count for current instance.
    
    Args:
        requested: Requested worker count from settings
    
    Returns:
        Safe worker count
    """
    coordinator = get_resource_coordinator()
    return coordinator.get_safe_worker_count(requested)


def get_safe_db_pool_size(requested: Optional[int] = None) -> int:
    """
    Get safe database pool size for current instance.
    
    Args:
        requested: Requested pool size from settings
    
    Returns:
        Safe pool size
    """
    coordinator = get_resource_coordinator()
    return coordinator.get_safe_db_pool_size(requested)


def get_resource_status() -> Dict:
    """Get current resource status"""
    coordinator = get_resource_coordinator()
    return coordinator.get_resource_status()


def is_system_overloaded() -> bool:
    """
    Check if system is currently overloaded.
    
    Returns:
        True if system is overloaded (CPU > 85% or Memory > 85%)
    """
    coordinator = get_resource_coordinator()
    return coordinator.is_system_overloaded()

def should_yield(aggressive: bool = False) -> bool:
    """
    Check if current operation should yield to prevent system overload.
    
    Args:
        aggressive: If True, use more aggressive thresholds for yielding
    
    Returns:
        True if operation should yield/pause
    """
    coordinator = get_resource_coordinator()
    return coordinator.should_yield(aggressive)


def get_yield_duration() -> float:
    """
    Get recommended yield duration based on current system load.
    
    Returns:
        Seconds to sleep/yield (0.0 to 0.1)
    """
    coordinator = get_resource_coordinator()
    return coordinator.get_yield_duration()

