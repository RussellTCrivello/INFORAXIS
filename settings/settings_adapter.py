"""
Settings Adapter - Backward Compatibility Layer
File: settings/settings_adapter.py

Provides backward compatibility with existing code that uses:
- settings.get_interface_manager()
- settings.get_settings()
- Old interface patterns
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .settings_manager import get_settings_manager
from .settings_models import AllSettings, InterfaceConfig

logger = logging.getLogger(__name__)


#: Interface switches that no longer correspond to anything. ``file_upload``
#: was the "core" twin of ``upload_files``: it pointed at the same endpoint and
#: gated no route (the endpoint map resolves files.upload_page to
#: ``upload_files``), so Settings offered two switches for one page. The key is
#: not deleted from anyone's settings file - it is simply no longer listed, so
#: a stored value cannot break anything and the listing always matches the
#: interface registry above.
RETIRED_INTERFACES = frozenset({"file_upload"})

#: What each interface switch controls: label, one-line explanation, icon
#: and the endpoint it gates. Kept next to the retired-key set above so every
#: listing (Settings' grouped view and the flat API view) describes an
#: interface the same way - a switch whose label disagrees with the page it
#: opens is how "Upload Files" outlived the page it named.
INTERFACE_METADATA: Dict[str, Dict[str, str]] = {
    "dashboard": {
        "name": "Dashboard",
        "description": "Main dashboard with overview statistics",
        "icon": "bi-speedometer2",
        "endpoint": "index"
    },
    "comprehensive_dashboard": {
        "name": "Comprehensive Dashboard",
        "description": "Detailed dashboard with comprehensive analytics",
        "icon": "bi-graph-up",
        "endpoint": "comprehensive_dashboard"
    },
    "charts_dashboard": {
        "name": "Charts Dashboard",
        "description": "Dashboard with interactive charts and visualizations",
        "icon": "bi-bar-chart",
        "endpoint": "charts_dashboard"
    },
    "file_analysis": {
        "name": "INFORAXIS",
        "description": "Analyze individual files and their properties",
        "icon": "bi-file-earmark-text",
        "endpoint": "archives_page"
    },
    "path_analysis": {
        "name": "Path Analysis",
        "description": "Analyze file paths and directory structures",
        "icon": "bi-folder",
        "endpoint": "path_analysis_page"
    },
    "batch_analysis": {
        "name": "Batch Analysis",
        "description": "Analyze multiple files in batches",
        "icon": "bi-files",
        "endpoint": "analysis_batch"
    },
    "sources": {
        "name": "Sources",
        "description": "Manage data sources",
        "icon": "bi-database",
        "endpoint": "sources_list"
    },
    "sides": {
        "name": "Sides",
        "description": "Manage data sides",
        "icon": "bi-layers",
        "endpoint": "sides_list"
    },
    "email_words": {
        "name": "Email Words",
        "description": "Manage email-related words",
        "icon": "bi-envelope",
        "endpoint": "email_words"
    },
    "search": {
        "name": "Search",
        "description": "Basic search functionality",
        "icon": "bi-search",
        "endpoint": "search_page"
    },
    "advanced_search": {
        "name": "Advanced Search",
        "description": "Advanced search with filters and options",
        "icon": "bi-search-heart",
        "endpoint": "search_advanced"
    },
    "upload_files": {
        # One interface, named for what it now is: /operations/input is
        # the single surface for a single file, a whole folder, a server
        # path and the jobs they create. The old "Upload Files" page is
        # a redirect to it, so the switch keeps its original meaning
        # (does the operator see a way in from the menu) and its
        # original key (existing settings files stay valid).
        "name": "Input / Ingestion",
        "description": "Bring evidence in - one file, a whole folder, or "
                       "a path on the server - and follow the jobs it creates",
        "icon": "bi-folder-plus",
        "endpoint": "operations_input_page"
    },
    "file_library": {
        "name": "File Library",
        "description": "Browse and manage file library",
        "icon": "bi-folder2-open",
        "endpoint": "files.files_list"
    },
    "keywords": {
        "name": "Keywords",
        "description": "Manage keywords",
        "icon": "bi-tags",
        "endpoint": "keywords_list"
    },
    "words": {
        "name": "Words",
        "description": "Manage words dictionary",
        "icon": "bi-book",
        "endpoint": "words_list"
    },
    "categories": {
        "name": "Categories",
        "description": "Manage categories",
        "icon": "bi-tags",
        "endpoint": "categories_list"
    },
    "notifications": {
        "name": "Notifications",
        "description": "View and manage notifications",
        "icon": "bi-bell",
        "endpoint": "notifications_page"
    },
    "settings": {
        "name": "Settings",
        "description": "System settings and configuration",
        "icon": "bi-gear",
        "endpoint": "settings_page"
    },
    "file_browser": {
        "name": "File Browser",
        "description": "Core file browser functionality",
        "icon": "bi-folder",
        "endpoint": "files.files_list",
        "category": "core"
    },
    "analytics": {
        "name": "Analytics",
        "description": "System analytics and reporting",
        "icon": "bi-graph-up-arrow",
        "endpoint": "analytics",
        "category": "analysis"
    },
    "page_tips": {
        "name": "Page Tips & Documentation",
        "description": "Enable or disable comprehensive tips and instructions on each page. Tips explain all interface elements, features, how to use them, and how to add/manage data. When enabled, tips appear at the top of each page with detailed explanations.",
        "icon": "bi-lightbulb",
        "endpoint": "",
        "category": "user"
    }
}


class SettingsAdapter:
    """
    Adapter class that provides backward compatibility with old settings API.
    
    This allows existing code to work with the new settings system without
    requiring immediate changes.
    """
    
    def __init__(self):
        self._manager = get_settings_manager()
    
    @property
    def settings(self) -> AllSettings:
        """Get settings object (for backward compatibility)"""
        return self._manager.settings

    @property
    def version(self) -> str:
        """Application settings version.

        AUDIT (OPS-01): ``Api/routes/health.py`` probes ``settings.version`` on
        this adapter during its settings health check. The adapter only
        forwarded ``.settings``, so the probe raised AttributeError on every
        boot and /health permanently returned
        ``{"status":"degraded","checks":{"settings":"error: AttributeError"}}``
        - precisely the signal a container orchestrator uses to restart or
        remove an instance from a load-balancer pool.
        """
        try:
            return self.settings.version
        except AttributeError:
            try:
                from version import get_version as _get_version
            except Exception:  # pragma: no cover - defensive
                return "unknown"
            return _get_version()

    def get(self, category: str = None, key: str = None, default: Any = None) -> Any:
        """
        Get a setting value (old API style).
        
        Supports both old API (single key) and new API (category.key):
        - get('theme') -> tries to find 'theme' in any category
        - get('theme', 'custom_css') -> gets theme.custom_css
        - get('system', 'language') -> gets system.language
        
        Args:
            category: Settings category (e.g., 'system', 'display') or single key
            key: Setting key (optional if category is a single key)
            default: Default value if not found
            
        Returns:
            Setting value
        """
        # Backward compatibility: if only one argument, treat as single key
        if key is None:
            # Single key lookup - try to find in common categories
            single_key = category
            if single_key is None:
                return default
            
            # Try direct access to settings attributes
            if hasattr(self.settings, single_key):
                attr = getattr(self.settings, single_key)
                if hasattr(attr, 'to_dict'):
                    return attr.to_dict()
                return attr
            
            # Try common category.key patterns
            common_categories = ['system', 'display', 'search', 'processing', 
                               'notifications', 'theme', 'database', 'storage']
            for cat in common_categories:
                if hasattr(self.settings, cat):
                    cat_obj = getattr(self.settings, cat)
                    if hasattr(cat_obj, single_key):
                        return getattr(cat_obj, single_key)
            
            return default
        
        # Two-argument call: category.key
        # Special handling for interfaces
        if category == "interfaces":
            # For interfaces, check if it's a nested key like interfaces.page_tips.enabled
            if key in self.settings.interfaces.interfaces:
                interface_config = self.settings.interfaces.interfaces[key]
                return interface_config.to_dict()
            # Try to get via manager for nested keys
            full_key = f"{category}.{key}"
            return self._manager.get(full_key, default)
        
        full_key = f"{category}.{key}"
        return self._manager.get(full_key, default)
    
    def set(self, category: str, key: str, value: Any, save_to_file: bool = True) -> bool:
        """
        Set a setting value (old API style).
        
        Args:
            category: Settings category
            key: Setting key
            value: New value
            save_to_file: Whether to save immediately
            
        Returns:
            True if successful
        """
        full_key = f"{category}.{key}"
        success, error = self._manager.set(full_key, value, validate=True)
        
        if success and save_to_file:
            self._manager.save()
        
        return success
    
    def get_all(self) -> Dict[str, Any]:
        """Get all settings as dictionary (old API style)"""
        return self._manager.export()
    
    def get_system_config(self) -> Dict[str, Any]:
        """Get system configuration (old API style)"""
        return self.settings.system.to_dict()
    
    def get_display_config(self) -> Dict[str, Any]:
        """Get display configuration (old API style)"""
        return self.settings.display.to_dict()
    
    def get_search_config(self) -> Dict[str, Any]:
        """Get search configuration (old API style)"""
        return self.settings.search.to_dict()
    
    def get_processing_config(self) -> Dict[str, Any]:
        """Get processing configuration (old API style)"""
        return self.settings.processing.to_dict()
    
    def get_storage_config(self) -> Dict[str, Any]:
        """Get storage configuration (old API style)"""
        return self.settings.storage.to_dict()
    
    def get_all_interfaces(self) -> Dict[str, Dict[str, Any]]:
        """Get all interfaces with metadata (old API style)"""
        interface_metadata = INTERFACE_METADATA

        interfaces = {}
        for interface_id, config in self.settings.interfaces.interfaces.items():
            if interface_id in RETIRED_INTERFACES:
                continue
            interface_dict = config.to_dict()
            # Add metadata if available
            if interface_id in interface_metadata:
                metadata = interface_metadata[interface_id]
                interface_dict.update({
                    "name": metadata.get("name", interface_id.replace("_", " ").title()),
                    "description": metadata.get("description", ""),
                    "icon": metadata.get("icon", "bi-gear"),
                    "endpoint": metadata.get("endpoint", interface_id)
                })
            else:
                # Default metadata
                interface_dict.update({
                    "name": interface_id.replace("_", " ").title(),
                    "description": "",
                    "icon": "bi-gear",
                    "endpoint": interface_id
                })
            interfaces[interface_id] = interface_dict
        return interfaces
    
    def get_interfaces_by_category(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get interfaces grouped by category (old API style)"""
        by_category = {}
        for interface_id, config in self.settings.interfaces.interfaces.items():
            if interface_id in RETIRED_INTERFACES:
                continue
            category = config.category
            if category not in by_category:
                by_category[category] = {}
            entry = config.to_dict()
            metadata = INTERFACE_METADATA.get(interface_id)
            if metadata:
                # Settings renders this entry, so it must name the interface and
                # the page it opens - not a title-cased id from a retired page.
                entry.update(metadata)
            by_category[category][interface_id] = entry
        return by_category
    
    def set_interface_enabled(self, interface_id: str, enabled: bool) -> None:
        """Set interface enabled status (old API style)"""
        full_key = f"interfaces.{interface_id}.enabled"
        self._manager.set(full_key, enabled, validate=True)
        self._manager.save()
    
    def reset_interfaces_to_defaults(self) -> None:
        """Reset all interfaces to defaults (old API style)"""
        for interface_id in self.settings.interfaces.interfaces.keys():
            self._manager.set(f"interfaces.{interface_id}.enabled", True)
        self._manager.save()
    
    def is_interface_enabled(self, interface_id: str) -> bool:
        """
        Check if an interface is enabled (old API style).
        
        Args:
            interface_id: Interface identifier (e.g., 'dashboard', 'search')
            
        Returns:
            True if interface is enabled, False otherwise
        """
        return self.settings.interfaces.get_interface_enabled(interface_id)
    
    def is_interface_enabled_by_endpoint(self, endpoint: str) -> bool:
        """
        Check if an interface is enabled by Flask endpoint name (old API style).
        
        Maps common endpoints to interface IDs and checks if enabled.
        
        Args:
            endpoint: Flask endpoint name (e.g., 'index', 'search_page')
            
        Returns:
            True if interface is enabled, False otherwise
        """
        # Map endpoints to interface IDs
        endpoint_to_interface = {
            'index': 'dashboard',
            'comprehensive_dashboard': 'dashboard',
            'charts_dashboard': 'dashboard',
            'dashboard': 'dashboard',
            
            'archives_page': 'file_analysis',
            'path_analysis_page': 'path_analysis',
            'analysis_batch': 'batch_analysis',
            
            'search_page': 'search',
            'search_advanced': 'advanced_search',
            'search_enhanced_page': 'advanced_search',
            'analyst_categorization_page': 'analyst_categorization',
            
            'sources_list': 'sources',
            'sides_list': 'sides',
            'email_words': 'email_words',
            'keywords_list': 'keywords',
            'words_list': 'words',
            'categories_list': 'categories',
            
            # Both spellings of the one ingestion surface resolve to the
            # interface that owns it: /operations/input and the /upload
            # alias kept for bookmarks.
            'operations_input_page': 'upload_files',
            'files.upload_page': 'upload_files',
            'files.files_list': 'file_library',
            'files.file_detail': 'file_library',
            
            'notifications_page': 'notifications',
            'settings_page': 'settings',
        }
        
        # Get interface ID from endpoint
        interface_id = endpoint_to_interface.get(endpoint)
        if interface_id:
            return self.is_interface_enabled(interface_id)
        
        # If endpoint not in mapping, default to enabled (backward compatibility)
        return True
    
    def reload_from_file(self) -> bool:
        """Reload settings from file (old API style)"""
        return self._manager.reload()
    
    def verify_settings_completeness(self) -> Dict[str, Any]:
        """Verify settings completeness (old API style)"""
        # Check if all required categories exist
        required_categories = ['system', 'display', 'search', 'processing', 
                              'notifications', 'theme', 'database', 'storage', 'interfaces']
        
        missing = []
        for category in required_categories:
            if not hasattr(self.settings, category):
                missing.append(category)
        
        # AUDIT (OPS-01): ``SettingsManager`` has no ``.version`` attribute -
        # the version lives on ``AllSettings`` / the ``version`` module. This
        # AttributeError made /health report
        # {"status":"degraded","checks":{"settings":"error: AttributeError"}}
        # on every boot, which is exactly the signal an orchestrator watches.
        try:
            from version import get_version as _get_version
        except Exception:  # pragma: no cover - defensive
            _get_version = None

        version = getattr(self.settings, 'version', None)
        if version is None:
            version = _get_version() if _get_version else None

        return {
            'complete': len(missing) == 0,
            'missing_categories': missing,
            'version': version
        }
    
    def check_file_changes(self) -> bool:
        """Check if settings file has changed (old API style)"""
        return self._manager.has_changed()
    
    @property
    def settings_file(self) -> Path:
        """Get settings file path (old API style)"""
        return self._manager.settings_file
    
    # Expose settings objects for direct access (backward compatibility)
    @property
    def system(self):
        """Direct access to system settings"""
        return self.settings.system
    
    @property
    def display(self):
        """Direct access to display settings"""
        return self.settings.display
    
    @property
    def processing(self):
        """Direct access to processing settings"""
        return self.settings.processing
    
    @property
    def storage(self):
        """Direct access to storage settings"""
        return self.settings.storage
    
    @property
    def database(self):
        """Direct access to database settings"""
        return self.settings.database
    
    # Project root management (for backward compatibility)
    @property
    def project_root(self) -> Optional[Path]:
        """
        Get project root path.
        
        The project root is inferred from the settings file location:
        - If settings.json is in data/ folder, project root is parent of data
        - If settings.json is directly in project root, that's the project root
        - Also checks PROJECT_ROOT environment variable
        """
        import os
        # First check environment variable (set by set_project_root)
        env_root = os.getenv('PROJECT_ROOT')
        if env_root:
            return Path(env_root)
        
        # Try to infer from settings file location
        settings_file = self._manager.settings_file
        if settings_file:
            # If settings.json is in data/ folder, project root is parent of data
            if settings_file.parent.name == 'data':
                return settings_file.parent.parent
            # If settings.json is directly in project root
            if settings_file.name == 'settings.json':
                return settings_file.parent
        return None
    
    def set_project_root(self, root_path: Path) -> None:
        """
        Set project root path (backward compatibility).
        
        Note: The project root is primarily inferred from the settings file location.
        This method is provided for backward compatibility but the actual project root
        is determined by where settings.json is located (typically in data/ folder).
        """
        # Store project root in a module-level variable for backward compatibility
        # The actual project root is inferred from settings file location
        import os
        if root_path:
            os.environ['PROJECT_ROOT'] = str(root_path.resolve())
    
    @property
    def uploads_dir(self) -> Optional[Path]:
        """Get uploads directory path"""
        if self.project_root:
            return self.project_root / 'uploads'
        return None
    
    @property
    def logs_dir(self) -> Optional[Path]:
        """Get logs directory path"""
        if self.project_root:
            return self.project_root / 'logs'
        return None
    
    def set_setting(self, key: str, value: Any, save_to_file: bool = True) -> None:
        """Set a setting using dot notation (backward compatibility)"""
        success, error = self._manager.set(key, value, validate=True)
        if not success:
            raise ValueError(f"Failed to set {key}: {error}")
        if save_to_file:
            self._manager.save()
    
    def _save_to_file(self) -> None:
        """Save settings to file (backward compatibility)"""
        self._manager.save()
    
    def _create_complete_settings_file(self) -> None:
        """Create complete settings file (backward compatibility)"""
        # Settings file is created automatically by SettingsManager
        self._manager.save()


# Global singleton instance
_interface_manager: Optional[SettingsAdapter] = None
_adapter_lock = __import__('threading').Lock()


def get_interface_manager() -> SettingsAdapter:
    """
    Get interface manager (backward compatibility function).
    
    This function provides the same interface as the old system,
    allowing existing code to work without changes.
    """
    global _interface_manager
    
    if _interface_manager is None:
        with _adapter_lock:
            if _interface_manager is None:
                _interface_manager = SettingsAdapter()
    
    return _interface_manager


# Additional backward compatibility functions
def get_settings() -> SettingsAdapter:
    """Get settings (backward compatibility)"""
    return get_interface_manager()


def get_user_settings() -> SettingsAdapter:
    """Get user settings (backward compatibility)"""
    return get_interface_manager()


def get_settings_integration() -> SettingsAdapter:
    """Get settings integration (backward compatibility)"""
    return get_interface_manager()


def reset_adapter():
    """Reset the adapter singleton instance (useful for testing)"""
    global _interface_manager
    with _adapter_lock:
        _interface_manager = None

