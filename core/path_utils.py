"""
Path utilities for project setup
Path utilities - Independent functions for path operations

Provides setup_path function for configuring Python path
No dependencies on other project modules.
"""

from pathlib import Path
from typing import Optional


def setup_path(file_path: Optional[str] = None, levels_up: int = 0) -> Path:
    """
    Set up Python path by adding project root to sys.path
    
    Args:
        file_path: Path to the file calling this function (usually __file__)
        levels_up: Number of directory levels to go up from file_path to reach project root
    
    Returns:
        Path object to project root
    """
    import sys
    
    try:
        if file_path is None:
            file_path = __file__
        
        current_file = Path(file_path).resolve()
        project_root = current_file.parent
        
        # Go up the specified number of levels
        for _ in range(levels_up):
            project_root = project_root.parent
        
        project_root_str = str(project_root)
        
        # Add to sys.path if not already there
        if project_root_str not in sys.path:
            sys.path.insert(0, project_root_str)
        
        return project_root
    except Exception:
        # Fallback to current working directory
        return Path.cwd()



def get_extraction_base_folder(base_path: Optional[Path] = None) -> Path:
    """
    Get base folder for file extractions.
    Creates the folder if it doesn't exist.
    
    Args:
        base_path: Optional base path for extraction folder.
                   If None, uses EXTRACTION_FOLDER environment variable or current directory.
    
    Returns:
        Path object to extraction base folder
    """
    if base_path:
        extraction_base = Path(base_path)
    else:
        import os
        extraction_folder_env = os.getenv('EXTRACTION_FOLDER')
        if extraction_folder_env:
            extraction_base = Path(extraction_folder_env)
        else:
            # Phase 19: derive from the application data root, never the CWD,
            # so behaviour is identical regardless of launch directory.
            from core.app_paths import get_extracted_dir
            extraction_base = get_extracted_dir()
    
    extraction_base.mkdir(parents=True, exist_ok=True)
    return extraction_base


def get_extraction_name_file(
    file_path: str,
    extension: Optional[str] = None,
    base_path: Optional[Path] = None
) -> str:
    """
    Get extraction folder name for a file.
    Creates unique folder name if one already exists.
    
    Args:
        file_path: Path to file
        extension: Optional file extension to remove from name
        base_path: Optional base path for extraction folder
        
    Returns:
        String path to extraction folder
    """
    path = Path(file_path)
    name = path.name
    
    if extension:
        folder_name = name[:-len(extension)] if name.endswith(extension) else name
    else:
        folder_name = path.stem
    
    extraction_base = get_extraction_base_folder(base_path)
    extract_to = extraction_base / folder_name
    
    counter = 1
    original_extract_to = extract_to
    while extract_to.exists():
        extract_to = Path(f"{original_extract_to}_{counter}")
        counter += 1
    
    return str(extract_to)

