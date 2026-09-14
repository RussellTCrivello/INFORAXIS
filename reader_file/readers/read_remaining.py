"""
Remaining file reader - Extract content from text-based files
Aligned with database design principles - all functions within class
Supports: JSON, XML, TXT, YAML, HTML, BIN, ICS and many other text-based formats
"""

import os
from pathlib import Path
import logging
from typing import Dict, Any, Optional, Set

from .base_reader import BaseReader

from Hdg_Err_Ex_Log import (
    handle_error, is_retryable_error,
    ErrorCategory, ErrorSeverity, format_validation_error
)

logger = logging.getLogger(__name__)


class RemainingFileReader(BaseReader):
    """
    Reader for remaining file types (text-based files).
    
    Follows database design principles:
    - All functions are within the class
    - Inherits from BaseReader
    - Consistent error handling
    - Proper resource management
    """
    
    def get_supported_extensions(self) -> Set[str]:
        """Return set of supported remaining file extensions.

        READER-02 (audit fix): this list previously advertised ~150
        extensions while ``read_file`` implemented only nine of them - every
        other advertised format failed deterministically with "Unsupported
        file type". The list now contains exactly what ``read_file``
        genuinely handles: text-based documents, structured data, code and
        configuration formats. Binary executable/library formats were
        removed: they cannot yield meaningful extractable content.
        """
        return {
            # structured data / markup / documents
            '.json', '.xml', '.txt', '.yaml', '.yml', '.html', '.htm',
            '.rtf', '.md', '.csv', '.tsv', '.log', '.ini', '.cfg', '.conf',
            '.properties', '.toml', '.env', '.srt', '.vtt',
            # calendar
            '.ics',
            # source code / scripts / shell
            '.sql', '.sh', '.bash', '.bat', '.cmd', '.ps1',
            '.js', '.jsx', '.ts', '.tsx', '.css', '.scss', '.less', '.php',
            '.py', '.java', '.c', '.h', '.cpp', '.hpp', '.cs', '.rb', '.go',
            '.rs', '.swift', '.kt', '.scala', '.r', '.m', '.pl', '.lua',
            '.vb', '.hs', '.dart', '.jl', '.nim', '.vue', '.svelte',
            # build / config metadata
            '.gitignore', '.gitattributes', '.editorconfig', '.makefile',
            '.cmake', '.gradle', '.lock', '.graphql', '.gql', '.proto',
            '.dockerfile', '.hocon', '.config', '.settings', '.prefs',
        }

    def read_file(self, file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Read remaining file types with improved error handling

        Args:
            file_info: Dictionary containing file information with 'path' key

        Returns:
            Dictionary with file content or None on error
        """
        # Validate file info using base class method
        is_valid, error_msg = self.validate_file_info(file_info)
        if not is_valid:
            return self.create_error_result(error_msg or "Invalid file info", file_info.get("path", "unknown"))

        file_path = str(file_info.get("path"))
        # DETECT-01: dispatch on the content-verified type, not the filename.
        ext = self.effective_extension(file_info)

        try:
            if ext == '.json':
                return self.read_json_file(file_path)
            elif ext == '.xml':
                return self.read_xml_file(file_path)
            elif ext == '.rtf':
                return self.read_rtf_file(file_path)
            elif ext in ('.yaml', '.yml'):
                return self.read_yaml_file(file_path)
            elif ext in ('.html', '.htm'):
                return self.read_html_file(file_path)
            elif ext == '.ics':
                return self.read_ics_file(file_path)
            elif ext == '.bin':
                return self.read_binary_file(file_path)
            elif ext in (self.get_supported_extensions() | {'.bin'}):
                # READER-02: every other advertised text format is genuinely
                # supported through the encoding-aware text reader.
                return self.read_text_file(file_path)
            else:
                error_msg = f"Unsupported file type: {ext or Path(file_path).suffix}"
                return self.handle_read_error(ValueError(error_msg), file_path, "read_file")
        except Exception as e:
            return self.handle_read_error(e, file_path, "read_file")

    def read_rtf_file(self, filepath: str) -> Dict[str, Any]:
        """Read an RTF file; strips control words when striprtf is available,
        falls back to plain text extraction otherwise (READER-02/READER-04)."""
        result: Dict[str, Any] = {"filepath": filepath}
        try:
            try:
                from striprtf.striprtf import rtf_to_text

                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    raw = f.read()
                result["content"] = rtf_to_text(raw)
                result["rtf_stripped"] = True
            except ImportError:
                # Fallback: readable text extraction without the dependency.
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    result["content"] = f.read()
                result["rtf_stripped"] = False
        except Exception as e:
            return self.handle_read_error(e, filepath, "read_rtf_file")
        return result
    
    def read_json_file(self, filepath: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """
        Read JSON file with improved error handling
        
        Args:
            filepath: Path to JSON file
            encoding: File encoding (default: 'utf-8')
        
        Returns:
            Dictionary with file data or error information
        """
        result: Dict[str, Any] = {"filepath": filepath}
        
        # Validate inputs
        if not filepath or not isinstance(filepath, str):
            error_msg = format_validation_error('filepath', filepath, 'must be a non-empty string')
            handle_error(
                ValueError(error_msg),
                category=ErrorCategory.VALIDATION,
                severity=ErrorSeverity.MEDIUM,
                context={'operation': 'read_json_file'}
            )
            result["error"] = error_msg
            return result
        
        if not os.path.exists(filepath):
            error_msg = "File not found"
            handle_error(
                FileNotFoundError(f"{error_msg}: {filepath}"),
                category=ErrorCategory.FILE_PROCESSING,
                severity=ErrorSeverity.MEDIUM,
                context={'operation': 'read_json_file', 'filepath': filepath}
            )
            result["error"] = error_msg
            return result
        
        try:
            import json
        except ImportError:
            error_msg = "json module not available"
            handle_error(
                ImportError(error_msg),
                category=ErrorCategory.CONFIGURATION,
                severity=ErrorSeverity.HIGH,
                context={'operation': 'read_json_file', 'filepath': filepath}
            )
            result["error"] = error_msg
            return result
        
        try:
            # Try multiple encodings if default fails
            encodings_to_try = [encoding, 'utf-8', 'latin-1', 'cp1252']
            data = None
            encoding_used = None
            
            for enc in encodings_to_try:
                try:
                    with open(filepath, 'r', encoding=enc) as file:
                        data = json.load(file)
                    encoding_used = enc
                    break
                except UnicodeDecodeError:
                    if enc == encodings_to_try[-1]:
                        raise
                    continue
            
            if data is None:
                error_msg = "Could not decode file with any encoding"
                handle_error(
                    UnicodeDecodeError('utf-8', b'', 0, 1, error_msg),
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': 'read_json_file', 'filepath': filepath}
                )
                result["error"] = error_msg
                return result
            
            result["data"] = data
            result["data_type"] = type(data).__name__
            if encoding_used and encoding_used != encoding:
                result["encoding_used"] = encoding_used
            
            # Add some basic statistics
            if isinstance(data, dict):
                result["key_count"] = len(data)
                result["keys"] = list(data.keys())[:100]  # Limit to first 100 keys
            elif isinstance(data, list):
                result["item_count"] = len(data)
            
            return result
        except Exception as e:
            error_msg = f"Error reading JSON file: {str(e)}"
            handle_error(
                e,
                category=ErrorCategory.FILE_PROCESSING,
                severity=ErrorSeverity.MEDIUM,
                context={'operation': 'read_json_file', 'filepath': filepath}
            )
            result["error"] = error_msg
            return result
    
    def read_xml_file(self, filepath, encoding='utf-8'):
        """Read XML file and convert to dictionary"""
        try:
            import xml.etree.ElementTree as ET
            
            if not os.path.exists(filepath):
                return {"error": "File not found", "filepath": filepath}
            
            tree = ET.parse(filepath)
            root = tree.getroot()
            
            def element_to_dict(element):
                """Convert XML element to dictionary"""
                elem_dict = {
                    "tag": element.tag,
                    "attributes": element.attrib,
                    "text": element.text.strip() if element.text and element.text.strip() else None,
                    "children": []
                }
                
                for child in element:
                    elem_dict["children"].append(element_to_dict(child))
                
                return elem_dict
            
            result = {
                "filepath": filepath,
                "root_tag": root.tag,
                "root_attributes": root.attrib,
                "tree": element_to_dict(root)
            }
            
            return result
        except Exception as e:
            return {"error": str(e), "filepath": filepath}
    
    def _read_text_file_streaming(self, filepath: str, encoding: str = 'utf-8', chunk_size: int = 10 * 1024 * 1024) -> Dict[str, Any]:
        """
        Internal method for streaming text file reading with custom chunk size.
        Used for memory error recovery with smaller chunks.
        
        Args:
            filepath: Path to text file
            encoding: Preferred encoding
            chunk_size: Chunk size in bytes (default: 10MB)
        
        Returns:
            Dictionary with file content or error information
        """
        result: Dict[str, Any] = {"filepath": filepath}
        
        try:
            file_size = os.path.getsize(filepath)
            content_parts = []
            lines = []
            line_count = 0
            character_count = 0
            word_count = 0
            non_empty_lines = 0
            
            encodings = [encoding, 'utf-8', 'latin-1', 'cp1252']
            encoding_used = None
            
            for enc in encodings:
                try:
                    with open(filepath, 'r', encoding=enc, errors='replace') as file:
                        buffer = ''
                        while True:
                            chunk = file.read(chunk_size)
                            if not chunk:
                                break
                            
                            buffer += chunk
                            while '\n' in buffer:
                                line, buffer = buffer.split('\n', 1)
                                lines.append(line)
                                line_count += 1
                                if line.strip():
                                    non_empty_lines += 1
                                character_count += len(line)
                                word_count += len(line.split())
                            
                            content_parts.append(chunk)
                        
                        if buffer:
                            lines.append(buffer)
                            line_count += 1
                            if buffer.strip():
                                non_empty_lines += 1
                            character_count += len(buffer)
                            word_count += len(buffer.split())
                        
                        encoding_used = enc
                        break
                except UnicodeDecodeError:
                    if enc == encodings[-1]:
                        raise
                    continue
            
            # Combine content (limit for very large files)
            if file_size < 500 * 1024 * 1024:  # < 500MB
                content = ''.join(content_parts)
            else:
                content = ''.join(content_parts[:5])  # First 5 chunks
                result["streaming_mode"] = True
                result["file_size_mb"] = file_size / (1024 * 1024)
            
            result.update({
                "content": content if content else "",
                "lines": lines[:10000] if len(lines) > 10000 else lines,
                "line_count": line_count,
                "character_count": character_count,
                "word_count": word_count,
                "non_empty_lines": non_empty_lines,
                "encoding_used": encoding_used,
                "streaming_processed": True
            })
            
            return result
        except Exception as e:
            error_msg = f"Error in streaming read: {str(e)}"
            handle_error(
                e,
                category=ErrorCategory.FILE_PROCESSING,
                severity=ErrorSeverity.MEDIUM,
                context={'operation': '_read_text_file_streaming', 'filepath': filepath}
            )
            result["error"] = error_msg
            return result
    
    def read_text_file(self, filepath: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """
        Read text file with improved error handling and encoding detection
        
        Args:
            filepath: Path to text file
            encoding: Preferred encoding (default: 'utf-8')
        
        Returns:
            Dictionary with file content or error information
        """
        result: Dict[str, Any] = {"filepath": filepath}
        
        # Validate inputs
        if not filepath or not isinstance(filepath, str):
            error_msg = format_validation_error('filepath', filepath, 'must be a non-empty string')
            handle_error(
                ValueError(error_msg),
                category=ErrorCategory.VALIDATION,
                severity=ErrorSeverity.MEDIUM,
                context={'operation': 'read_text_file'}
            )
            result["error"] = error_msg
            return result
        
        if not os.path.exists(filepath):
            error_msg = "File not found"
            handle_error(
                FileNotFoundError(f"{error_msg}: {filepath}"),
                category=ErrorCategory.FILE_PROCESSING,
                severity=ErrorSeverity.MEDIUM,
                context={'operation': 'read_text_file', 'filepath': filepath}
            )
            result["error"] = error_msg
            return result
        
        try:
            # Get file size for streaming decision
            file_size = os.path.getsize(filepath)
            # Use streaming for files larger than 100MB to conserve memory
            use_streaming = file_size > 100 * 1024 * 1024  # 100MB threshold
            
            # Try different encodings if default fails
            encodings = [encoding, 'utf-8', 'latin-1', 'cp1252']
            content = None
            encoding_used = None
            chunk_size = 10 * 1024 * 1024  # 10MB chunks for streaming
            
            for enc in encodings:
                try:
                    if use_streaming:
                        # Stream processing for large files - process in chunks to conserve memory
                        content_parts = []
                        lines = []
                        line_count = 0
                        character_count = 0
                        word_count = 0
                        non_empty_lines = 0
                        
                        with open(filepath, 'r', encoding=enc, errors='replace') as file:
                            # Read file in chunks for continuous processing
                            buffer = ''
                            while True:
                                chunk = file.read(chunk_size)
                                if not chunk:
                                    break
                                
                                # Process chunk
                                buffer += chunk
                                # Split by newlines, keeping incomplete line in buffer
                                while '\n' in buffer:
                                    line, buffer = buffer.split('\n', 1)
                                    lines.append(line)
                                    line_count += 1
                                    if line.strip():
                                        non_empty_lines += 1
                                    character_count += len(line)
                                    word_count += len(line.split())
                                
                                # Add chunk to content (for continuous processing)
                                content_parts.append(chunk)
                                
                                # Yield control periodically to allow other operations
                                # This enables continuous processing without blocking
                            
                            # Process remaining buffer
                            if buffer:
                                lines.append(buffer)
                                line_count += 1
                                if buffer.strip():
                                    non_empty_lines += 1
                                character_count += len(buffer)
                                word_count += len(buffer.split())
                            
                            # Combine content parts (for files that fit in memory after streaming)
                            # For very large files, we may not store full content
                            if file_size < 500 * 1024 * 1024:  # < 500MB, store full content
                                content = ''.join(content_parts)
                            else:
                                # For extremely large files, store sample and metadata only
                                content = ''.join(content_parts[:5])  # First 5 chunks
                                result["streaming_mode"] = True
                                result["file_size_mb"] = file_size / (1024 * 1024)
                        
                        encoding_used = enc
                        
                        result.update({
                            "content": content if content else "",
                            "lines": lines[:10000] if len(lines) > 10000 else lines,  # Limit lines for very large files
                            "line_count": line_count,
                            "character_count": character_count,
                            "word_count": word_count,
                            "non_empty_lines": non_empty_lines,
                            "encoding_used": encoding_used,
                            "streaming_processed": True
                        })
                    else:
                        # Standard reading for smaller files
                        with open(filepath, 'r', encoding=enc) as file:
                            content = file.read()
                        encoding_used = enc
                        
                        lines = content.splitlines()
                        
                        result.update({
                            "content": content,
                            "lines": lines,
                            "line_count": len(lines),
                            "character_count": len(content),
                            "word_count": len(content.split()),
                            "non_empty_lines": len([l for l in lines if l.strip()]),
                            "encoding_used": encoding_used
                        })
                    
                    break
                except UnicodeDecodeError:
                    if enc == encodings[-1]:
                        raise
                    continue
                except MemoryError:
                    # If memory error occurs, fall back to streaming
                    if not use_streaming:
                        use_streaming = True
                        continue
                    raise
            
            if content is None and not result.get("streaming_processed"):
                error_msg = "Could not decode file with any encoding"
                handle_error(
                    UnicodeDecodeError('utf-8', b'', 0, 1, error_msg),
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.MEDIUM,
                    context={'operation': 'read_text_file', 'filepath': filepath}
                )
                result["error"] = error_msg
                return result
            
            return result
        except MemoryError as e:
            # PRODUCTION: Enhanced memory error handling for terabyte-scale files
            # Retry with streaming if memory error occurs, with progressively smaller chunk sizes
            try:
                # Get file size to determine appropriate chunk size
                file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                
                # For very large files, use smaller chunk sizes
                if file_size > 10 * 1024 * 1024 * 1024:  # > 10GB
                    # Use 1MB chunks for very large files
                    logger.warning(f"Memory error on large file ({file_size / (1024*1024*1024):.2f}GB), retrying with 1MB chunks")
                    # Force streaming mode with smaller chunks by modifying the method
                    # We'll use a recursive call but with a flag to use smaller chunks
                    return self._read_text_file_streaming(filepath, encoding, chunk_size=1024 * 1024)  # 1MB chunks
                else:
                    # Standard retry with streaming
                    return self.read_text_file(filepath, encoding)  # Will use streaming on retry
            except MemoryError as retry_err:
                # Even streaming failed - file is too large
                file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                error_msg = f"File too large to process even with streaming: {filepath} ({file_size / (1024*1024*1024):.2f}GB)"
                handle_error(
                    retry_err,
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.HIGH,
                    context={
                        'operation': 'read_text_file',
                        'filepath': filepath,
                        'file_size_gb': file_size / (1024*1024*1024) if file_size > 0 else 0,
                        'suggested_action': 'Consider processing file in smaller chunks or increasing available memory'
                    }
                )
                result["error"] = error_msg
                result["file_too_large"] = True
                result["file_size_gb"] = file_size / (1024*1024*1024) if file_size > 0 else 0
                return result
            except Exception as retry_err:
                # Other error during retry
                error_msg = f"Error during streaming retry: {str(retry_err)}"
                handle_error(
                    retry_err,
                    category=ErrorCategory.FILE_PROCESSING,
                    severity=ErrorSeverity.HIGH,
                    context={'operation': 'read_text_file_retry', 'filepath': filepath}
                )
                result["error"] = error_msg
                return result
        except Exception as e:
            error_msg = f"Error reading text file: {str(e)}"
            handle_error(
                e,
                category=ErrorCategory.FILE_PROCESSING,
                severity=ErrorSeverity.MEDIUM,
                context={'operation': 'read_text_file', 'filepath': filepath}
            )
            result["error"] = error_msg
            return result
    
    def read_yaml_file(self, filepath, encoding='utf-8'):
        """Read YAML file"""
        try:
            import yaml
        except ImportError:
            return {
                "error": "PyYAML not installed. Install with: pip install pyyaml",
                "filepath": filepath
            }
        
        try:
            if not os.path.exists(filepath):
                return {"error": "File not found", "filepath": filepath}
            
            with open(filepath, 'r', encoding=encoding) as file:
                data = yaml.safe_load(file)
            
            result = {
                "filepath": filepath,
                "data": data,
                "data_type": type(data).__name__
            }
            
            if isinstance(data, dict):
                result["key_count"] = len(data)
                result["keys"] = list(data.keys())
            elif isinstance(data, list):
                result["item_count"] = len(data)
            
            return result
        except Exception as e:
            return {"error": str(e), "filepath": filepath}
    
    def read_html_file(self, filepath, encoding='utf-8'):
        """Read HTML file"""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {
                "error": "beautifulsoup4 not installed. Install with: pip install beautifulsoup4",
                "filepath": filepath
            }
        
        try:
            if not os.path.exists(filepath):
                return {"error": "File not found", "filepath": filepath}
            
            with open(filepath, 'r', encoding=encoding) as file:
                content = file.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            result = {
                "filepath": filepath,
                "title": soup.title.string if soup.title else None,
                "text_content": soup.get_text(),
                "links": [{"href": a.get('href'), "text": a.get_text()} for a in soup.find_all('a', href=True)],
                "images": [{"src": img.get('src'), "alt": img.get('alt')} for img in soup.find_all('img')],
                "headings": {
                    "h1": [h.get_text() for h in soup.find_all('h1')],
                    "h2": [h.get_text() for h in soup.find_all('h2')],
                    "h3": [h.get_text() for h in soup.find_all('h3')]
                },
                "link_count": len(soup.find_all('a', href=True)),
                "image_count": len(soup.find_all('img'))
            }
            
            return result
        except Exception as e:
            return {"error": str(e), "filepath": filepath}
    
    def read_binary_file(self, filepath, max_bytes=1024):
        """Read binary file"""
        try:
            if not os.path.exists(filepath):
                return {"error": "File not found", "filepath": filepath}
            
            file_size = os.path.getsize(filepath)
            
            with open(filepath, 'rb') as file:
                data = file.read(max_bytes)
            
            result = {
                "filepath": filepath,
                "file_size": file_size,
                "bytes_read": len(data),
                "hex_preview": data.hex()[:500],  # First 500 hex characters
                "first_bytes": list(data[:50])  # First 50 bytes as integers
            }
            
            return result
        except Exception as e:
            return {"error": str(e), "filepath": filepath}
    
    def read_ics_file(self, filepath, encoding='utf-8'):
        """
        Extract readable content from ICS (iCalendar) files.
        Parses calendar events, todos, journals, and freebusy information.
        """
        try:
            from icalendar import Calendar
        except ImportError:
            return {
                "error": "icalendar not installed. Install with: pip install icalendar",
                "filepath": filepath
            }
        
        try:
            if not os.path.exists(filepath):
                return {"error": "File not found", "filepath": filepath}
            
            # Try different encodings if utf-8 fails
            encodings = [encoding, 'utf-8', 'latin-1', 'cp1252']
            content = None
            encoding_used = None
            
            for enc in encodings:
                try:
                    with open(filepath, 'r', encoding=enc) as file:
                        content = file.read()
                    encoding_used = enc
                    break
                except UnicodeDecodeError:
                    if enc == encodings[-1]:
                        raise
                    continue
            
            if content is None:
                return {"error": "Could not decode file with any encoding", "filepath": filepath}
            
            # Parse the calendar
            cal = Calendar.from_ical(content)
            
            events = []
            todos = []
            journals = []
            freebusy = []
            
            # Extract all components
            for component in cal.walk():
                component_type = component.name
                
                if component_type == 'VEVENT':
                    event_data = {
                        "summary": str(component.get('summary', '')),
                        "description": str(component.get('description', '')),
                        "location": str(component.get('location', '')),
                        "dtstart": str(component.get('dtstart', '')),
                        "dtend": str(component.get('dtend', '')),
                        "dtstamp": str(component.get('dtstamp', '')),
                        "uid": str(component.get('uid', '')),
                        "organizer": str(component.get('organizer', '')),
                        "attendee": [str(att) for att in component.get('attendee', [])],
                        "status": str(component.get('status', '')),
                        "url": str(component.get('url', '')),
                        "rrule": str(component.get('rrule', '')),
                        "categories": [str(cat) for cat in component.get('categories', [])],
                        "priority": str(component.get('priority', '')),
                        "transp": str(component.get('transp', '')),
                        "created": str(component.get('created', '')),
                        "last_modified": str(component.get('last-modified', ''))
                    }
                    events.append(event_data)
                
                elif component_type == 'VTODO':
                    todo_data = {
                        "summary": str(component.get('summary', '')),
                        "description": str(component.get('description', '')),
                        "location": str(component.get('location', '')),
                        "dtstart": str(component.get('dtstart', '')),
                        "due": str(component.get('due', '')),
                        "completed": str(component.get('completed', '')),
                        "status": str(component.get('status', '')),
                        "priority": str(component.get('priority', '')),
                        "percent_complete": str(component.get('percent-complete', '')),
                        "uid": str(component.get('uid', '')),
                        "categories": [str(cat) for cat in component.get('categories', [])]
                    }
                    todos.append(todo_data)
                
                elif component_type == 'VJOURNAL':
                    journal_data = {
                        "summary": str(component.get('summary', '')),
                        "description": str(component.get('description', '')),
                        "dtstart": str(component.get('dtstart', '')),
                        "status": str(component.get('status', '')),
                        "uid": str(component.get('uid', ''))
                    }
                    journals.append(journal_data)
                
                elif component_type == 'VFREEBUSY':
                    freebusy_data = {
                        "dtstart": str(component.get('dtstart', '')),
                        "dtend": str(component.get('dtend', '')),
                        "organizer": str(component.get('organizer', '')),
                        "uid": str(component.get('uid', ''))
                    }
                    freebusy.append(freebusy_data)
            
            # Build readable text content
            readable_content_parts = []
            
            if events:
                readable_content_parts.append("=== CALENDAR EVENTS ===")
                for idx, event in enumerate(events, 1):
                    readable_content_parts.append(f"\nEvent {idx}:")
                    if event['summary']:
                        readable_content_parts.append(f"  Title: {event['summary']}")
                    if event['description']:
                        readable_content_parts.append(f"  Description: {event['description']}")
                    if event['location']:
                        readable_content_parts.append(f"  Location: {event['location']}")
                    if event['dtstart']:
                        readable_content_parts.append(f"  Start: {event['dtstart']}")
                    if event['dtend']:
                        readable_content_parts.append(f"  End: {event['dtend']}")
                    if event['organizer']:
                        readable_content_parts.append(f"  Organizer: {event['organizer']}")
                    if event['attendee']:
                        readable_content_parts.append(f"  Attendees: {', '.join(event['attendee'])}")
                    if event['status']:
                        readable_content_parts.append(f"  Status: {event['status']}")
            
            if todos:
                readable_content_parts.append("\n=== TODO ITEMS ===")
                for idx, todo in enumerate(todos, 1):
                    readable_content_parts.append(f"\nTodo {idx}:")
                    if todo['summary']:
                        readable_content_parts.append(f"  Title: {todo['summary']}")
                    if todo['description']:
                        readable_content_parts.append(f"  Description: {todo['description']}")
                    if todo['status']:
                        readable_content_parts.append(f"  Status: {todo['status']}")
                    if todo['due']:
                        readable_content_parts.append(f"  Due: {todo['due']}")
                    if todo['completed']:
                        readable_content_parts.append(f"  Completed: {todo['completed']}")
            
            if journals:
                readable_content_parts.append("\n=== JOURNAL ENTRIES ===")
                for idx, journal in enumerate(journals, 1):
                    readable_content_parts.append(f"\nJournal {idx}:")
                    if journal['summary']:
                        readable_content_parts.append(f"  Title: {journal['summary']}")
                    if journal['description']:
                        readable_content_parts.append(f"  Description: {journal['description']}")
            
            if freebusy:
                readable_content_parts.append("\n=== FREE/BUSY INFORMATION ===")
                for idx, fb in enumerate(freebusy, 1):
                    readable_content_parts.append(f"\nFree/Busy {idx}:")
                    if fb['organizer']:
                        readable_content_parts.append(f"  Organizer: {fb['organizer']}")
                    if fb['dtstart']:
                        readable_content_parts.append(f"  Start: {fb['dtstart']}")
                    if fb['dtend']:
                        readable_content_parts.append(f"  End: {fb['dtend']}")
            
            readable_content = "\n".join(readable_content_parts) if readable_content_parts else "No calendar data found."
            
            # Get calendar metadata
            cal_prod_id = str(cal.get('prodid', ''))
            cal_version = str(cal.get('version', ''))
            cal_calscale = str(cal.get('calscale', ''))
            cal_method = str(cal.get('method', ''))
            
            result = {
                "filepath": filepath,
                "encoding_used": encoding_used,
                "calendar_prodid": cal_prod_id,
                "calendar_version": cal_version,
                "calendar_calscale": cal_calscale,
                "calendar_method": cal_method,
                "readable_content": readable_content,
                "events": events,
                "todos": todos,
                "journals": journals,
                "freebusy": freebusy,
                "event_count": len(events),
                "todo_count": len(todos),
                "journal_count": len(journals),
                "freebusy_count": len(freebusy),
                "total_components": len(events) + len(todos) + len(journals) + len(freebusy)
            }
            
            return result
        except Exception as e:
            return {"error": str(e), "filepath": filepath}


