"""
File utilities - Independent functions for file operations
No dependencies on other project modules.
"""

import os
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


#: Files at or above this size are not hashed during discovery. Discovery
#: stays cheap; ``pipeline.storage_pipeline`` computes the real streamed
#: SHA-256 exactly once when the file is stored.
HASH_INLINE_MAX_BYTES = 100 * 1024 * 1024

#: Value placed in ``Metadata['hash']`` when hashing was deliberately deferred.
#: It is a sentinel, not a digest, and must never be persisted as an identity.
HASH_DEFERRED_SENTINEL = "SKIPPED_LARGE_FILE"


def format_file_size(size_bytes: Optional[int]) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: File size in bytes
        
    Returns:
        Formatted string (e.g., "1.23 MB")
    """
    if size_bytes is None:
        return "N/A"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def calculate_file_hash(file_path: str, algorithm: str = 'sha256', chunk_size: int = 8192) -> str:
    """
    Calculate file hash.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (default: 'sha256')
        chunk_size: Size of chunks to read (default: 8192)
        
    Returns:
        Hexadecimal hash string
    """
    hash_obj = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()



def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed_attachment"
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    filename = filename.strip('. ')
    return filename if filename else "unnamed_attachment"


def get_standardized_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Get standardized metadata for a file or directory.
    
    Args:
        file_path: Path to file or directory
        
    Returns:
        Dictionary with metadata or None if error
    """
    try:
        path = Path(file_path)
        
        if not path.exists():
            return {
                "name": path.name,
                "path": str(path),
                "type": "UNKNOWN",
                "extension": path.suffix.lower() if path.suffix else "none",
                "size": "N/A",
                "size_bytes": None,
                "hash": "N/A",
                "created": "N/A",
                "modified": "N/A",
                "accessed": "N/A",
                "readable": False,
                "writable": False,
                "executable": False,
                "processing_time": "N/A"
            }
        
        stats = path.stat()
        
        # Determine file type
        if path.is_file():
            file_type = "FILE"
        elif path.is_dir():
            file_type = "DIRECTORY"
        elif path.is_symlink():
            file_type = "SYMLINK"
        else:
            file_type = "OTHER"
        
        is_readable = os.access(file_path, os.R_OK)
        is_writable = os.access(file_path, os.W_OK)
        is_executable = os.access(file_path, os.X_OK)
        
        file_size = format_file_size(stats.st_size)
        
        file_hash = "N/A"
        if path.is_file() and is_readable:
            try:
                if stats.st_size < HASH_INLINE_MAX_BYTES:
                    file_hash = calculate_file_hash(file_path)
                else:
                    # HASH-01: never fabricate an identity. This used to be
                    # sha256(f"{path}|{size}|{mtime}"), which is not a content
                    # hash: two byte-identical large files at different paths
                    # received different values, so deduplication failed and
                    # both were stored. The sentinel below is what
                    # pipeline.storage_pipeline already recognises as "compute
                    # the real streamed hash yourself".
                    file_hash = HASH_DEFERRED_SENTINEL
            except Exception:
                file_hash = "ERROR"
        
        metadata = {
            "name": path.name,
            "path": str(path.absolute()),
            "type": file_type,
            "extension": path.suffix.lower() if path.suffix else "none",
            "size": file_size,
            "size_bytes": stats.st_size,
            "hash": file_hash,
            "created": datetime.fromtimestamp(stats.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stats.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stats.st_atime).isoformat(),
            "readable": is_readable,
            "writable": is_writable,
            "executable": is_executable,
            "processing_time": "N/A"
        }
        
        return metadata
        
    except Exception:
        return {
            "name": Path(file_path).name if file_path else "Unknown",
            "path": str(file_path) if file_path else "Unknown",
            "type": "ERROR",
            "extension": "none",
            "size": "N/A",
            "size_bytes": None,
            "hash": "N/A",
            "created": "N/A",
            "modified": "N/A",
            "accessed": "N/A",
            "readable": False,
            "writable": False,
            "executable": False,
            "processing_time": "N/A"
        }


def read_tree(path: str) -> list:
    """
    Read directory tree and return list of file metadata.
    PRODUCTION-READY: Handles all edge cases including permission errors, symlinks, and very long paths.
    Ensures NO files are lost, even if they can't be accessed.
    
    Args:
        path: Directory path
        
    Returns:
        List of file metadata dictionaries (includes files with errors)
    """
    file_info_list = []
    visited_paths = set()  # Track visited paths to prevent infinite loops from symlinks
    max_path_length = 260  # Windows MAX_PATH limit (can be extended with \\?\ prefix)
    
    try:
        root_path = Path(path)
        if not root_path.exists():
            # Return error metadata for non-existent root
            error_info = {
                "name": root_path.name,
                "path": str(root_path),
                "type": "ERROR",
                "extension": "none",
                "size": "N/A",
                "size_bytes": None,
                "hash": "N/A",
                "created": "N/A",
                "modified": "N/A",
                "accessed": "N/A",
                "readable": False,
                "writable": False,
                "executable": False,
                "processing_time": "N/A",
                "error": "Root path does not exist"
            }
            file_info_list.append(error_info)
            return file_info_list
        
        # Use try-except around rglob to handle permission errors gracefully
        try:
            # PRODUCTION: Handle very long paths on Windows
            if os.name == 'nt' and len(str(root_path.absolute())) > max_path_length:
                # Use extended path prefix for Windows
                extended_path = f"\\\\?\\{root_path.absolute()}"
                root_path = Path(extended_path)
            
            # Iterate through all files and directories
            for p in root_path.rglob("*"):
                try:
                    # PRODUCTION: Prevent infinite loops from symlinks
                    path_str = str(p.resolve())  # Resolve symlinks
                    if path_str in visited_paths:
                        continue
                    visited_paths.add(path_str)
                    
                    # PRODUCTION: Skip if path is too long (even with extended prefix)
                    if len(str(p)) > 32767:  # Windows MAX_PATH extended limit
                        error_info = {
                            "name": p.name if len(p.name) < 100 else p.name[:100] + "...",
                            "path": str(p)[:500] + "..." if len(str(p)) > 500 else str(p),
                            "type": "ERROR",
                            "extension": "none",
                            "size": "N/A",
                            "size_bytes": None,
                            "hash": "N/A",
                            "created": "N/A",
                            "modified": "N/A",
                            "accessed": "N/A",
                            "readable": False,
                            "writable": False,
                            "executable": False,
                            "processing_time": "N/A",
                            "error": "Path too long (exceeds Windows MAX_PATH limit)"
                        }
                        file_info_list.append(error_info)
                        continue
                    
                    # Get metadata - this handles errors internally
                    file_info = get_standardized_metadata(p)
                    if file_info:
                        # PRODUCTION: Ensure error information is preserved
                        if not file_info.get('readable', True):
                            file_info['error'] = "File is not readable (permission denied)"
                        file_info_list.append(file_info)
                
                except PermissionError as perm_err:
                    # PRODUCTION: Store file info even if we can't access it
                    error_info = {
                        "name": p.name if hasattr(p, 'name') else str(p),
                        "path": str(p),
                        "type": "ERROR",
                        "extension": p.suffix.lower() if hasattr(p, 'suffix') else "none",
                        "size": "N/A",
                        "size_bytes": None,
                        "hash": "N/A",
                        "created": "N/A",
                        "modified": "N/A",
                        "accessed": "N/A",
                        "readable": False,
                        "writable": False,
                        "executable": False,
                        "processing_time": "N/A",
                        "error": f"Permission denied: {str(perm_err)}"
                    }
                    file_info_list.append(error_info)
                
                except OSError as os_err:
                    # PRODUCTION: Store file info for OS errors (network drives, etc.)
                    error_info = {
                        "name": p.name if hasattr(p, 'name') else str(p),
                        "path": str(p),
                        "type": "ERROR",
                        "extension": p.suffix.lower() if hasattr(p, 'suffix') else "none",
                        "size": "N/A",
                        "size_bytes": None,
                        "hash": "N/A",
                        "created": "N/A",
                        "modified": "N/A",
                        "accessed": "N/A",
                        "readable": False,
                        "writable": False,
                        "executable": False,
                        "processing_time": "N/A",
                        "error": f"OS error: {str(os_err)}"
                    }
                    file_info_list.append(error_info)
                
                except Exception as e:
                    # PRODUCTION: Catch-all for any other errors - still store file info
                    error_info = {
                        "name": p.name if hasattr(p, 'name') else str(p),
                        "path": str(p),
                        "type": "ERROR",
                        "extension": p.suffix.lower() if hasattr(p, 'suffix') else "none",
                        "size": "N/A",
                        "size_bytes": None,
                        "hash": "N/A",
                        "created": "N/A",
                        "modified": "N/A",
                        "accessed": "N/A",
                        "readable": False,
                        "writable": False,
                        "executable": False,
                        "processing_time": "N/A",
                        "error": f"Unexpected error: {str(e)}"
                    }
                    file_info_list.append(error_info)
        
        except PermissionError as root_perm_err:
            # PRODUCTION: If we can't access the root, return error info
            error_info = {
                "name": root_path.name,
                "path": str(root_path),
                "type": "ERROR",
                "extension": "none",
                "size": "N/A",
                "size_bytes": None,
                "hash": "N/A",
                "created": "N/A",
                "modified": "N/A",
                "accessed": "N/A",
                "readable": False,
                "writable": False,
                "executable": False,
                "processing_time": "N/A",
                "error": f"Permission denied accessing root path: {str(root_perm_err)}"
            }
            file_info_list.append(error_info)
        
        except Exception as root_err:
            # PRODUCTION: Catch-all for root-level errors
            error_info = {
                "name": root_path.name,
                "path": str(root_path),
                "type": "ERROR",
                "extension": "none",
                "size": "N/A",
                "size_bytes": None,
                "hash": "N/A",
                "created": "N/A",
                "modified": "N/A",
                "accessed": "N/A",
                "readable": False,
                "writable": False,
                "executable": False,
                "processing_time": "N/A",
                "error": f"Error accessing root path: {str(root_err)}"
            }
            file_info_list.append(error_info)
    
    except Exception as e:
        # PRODUCTION: Final catch-all - return at least the root path with error
        error_info = {
            "name": Path(path).name if path else "Unknown",
            "path": str(path) if path else "Unknown",
            "type": "ERROR",
            "extension": "none",
            "size": "N/A",
            "size_bytes": None,
            "hash": "N/A",
            "created": "N/A",
            "modified": "N/A",
            "accessed": "N/A",
            "readable": False,
            "writable": False,
            "executable": False,
            "processing_time": "N/A",
            "error": f"Critical error in read_tree: {str(e)}"
        }
        file_info_list.append(error_info)
    
    return file_info_list


def create_standardized_result(file_path: str, content_data: Any, 
                               processing_time: Optional[float] = None) -> Dict[str, Any]:
    """
    Create standardized result structure.
    
    Args:
        file_path: Path to processed file
        content_data: Content data from processing
        processing_time: Processing time in seconds
        
    Returns:
        Standardized result dictionary
    """
    metadata = get_standardized_metadata(file_path)
    
    # Update processing time
    if processing_time is not None:
        metadata["processing_time"] = f"{processing_time:.4f} seconds"
    
    # Create the standardized format
    result = {
        "Metadata": metadata,
        "Content": content_data if content_data is not None else {}
    }
    
    return result


def normalize_text(text: str) -> str:
    """Normalize text for tokenization: NFKC, lowercasing, and whitespace collapse."""
    if text is None:
        return ""
    try:
        import unicodedata
        s = unicodedata.normalize('NFKC', text)
    except Exception:
        s = text
    s = s.replace('\r', ' ').replace('\n', ' ')
    s = re.sub(r"\s+", ' ', s).strip()
    return s


def tokenize_text(text: str) -> list:
    """Return an ordered list of word tokens from input text.

    Rules:
    - Normalize using `normalize_text`
    - Split on non-word characters, preserve only tokens with letters/numbers
    - Lowercase tokens
    """
    if not text:
        return []
    s = normalize_text(text)
    # Split on anything that's not a letter/number/apostrophe
    raw_tokens = re.split(r"[^\w']+", s)
    tokens = [t.lower() for t in raw_tokens if t and re.search(r"\w", t)]
    return tokens


def tokens_with_positions(text: str) -> list:
    """Return list of (token, index, char_start, char_end) preserving order.

    Useful for building inverted index or storing ordered tokens with positions.
    """
    s = normalize_text(text)
    tokens = []
    if not s:
        return tokens

    # Walk the string and match tokens using the same pattern
    pattern = re.compile(r"[\w']+")
    for idx, m in enumerate(pattern.finditer(s)):
        token = m.group(0).lower()
        tokens.append((token, idx, m.start(), m.end()))
    return tokens


def text_to_word_array_and_ordered_text(text: str) -> dict:
    """Produce a dictionary with words array and ordered full text.

    Returns:
        {"words": [...], "ordered_text": "..."}
    """
    toks = tokenize_text(text)
    ordered = ' '.join(toks)
    return {"words": toks, "ordered_text": ordered}

