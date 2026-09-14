"""
Archive file reader - Safe extraction (SEC-05)

Supports: ZIP, TAR (.tar/.tar.gz/.tar.bz2/.tar.xz), GZ, BZ2, RAR, 7Z.

All extraction goes through :mod:`core.archive_safety`, which enforces
path-traversal rejection, symlink/hardlink refusal, depth / file-count /
byte / ratio limits and timeouts. The legacy implementation used
``extractall`` (zip-slip / tar-slip vulnerable) and is replaced entirely.
"""

import os
from typing import Dict, Any, Optional, Set
from pathlib import Path

from core.path_utils import get_extraction_name_file
from core import archive_safety
from core.archive_safety import ArchiveEncrypted, ArchiveSafetyError

from .base_reader import BaseReader

from Hdg_Err_Ex_Log import (
    handle_error,
    ErrorCategory,
    ErrorSeverity,
    format_validation_error
)

import logging
logger = logging.getLogger(__name__)


class ArchiveFileReader(BaseReader):
    """
    Reader for archive files.

    Follows database design principles:
    - All functions are within the class
    - Inherits from BaseReader
    - Consistent error handling
    - Proper resource management
    """

    def get_supported_extensions(self) -> Set[str]:
        """Return set of supported archive extensions"""
        return {
            '.zip',
            '.tar',
            '.gz',
            '.bz2',
            '.rar',
            '.7z'
        }

    def read_file(self, file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Read archive file and extract contents safely.

        Args:
            file_info: Dictionary containing file information with 'path' key

        Returns:
            Dictionary with extraction path or error information
        """
        # Validate file info using base class method
        is_valid, error_msg = self.validate_file_info(file_info)
        if not is_valid:
            return self.create_error_result(error_msg or "Invalid file info", file_info.get("path", "unknown"))

        file_path = str(file_info.get("path"))
        # DETECT-01: dispatch on the content-verified type, not the filename.
        ext = self.effective_extension(file_info)

        try:
            extraction_path = None

            if ext == '.zip':
                extraction_path = self.extract_zip(file_path)
            elif ext in ('.tar', '.tar.gz', '.tar.bz2', '.tar.xz'):
                extraction_path = self.extract_tar(file_path, ext)
            elif ext == '.gz':
                extraction_path = self.extract_gz(file_path)
            elif ext == '.bz2':
                extraction_path = self.extract_bz2(file_path)
            elif ext == '.rar':
                extraction_path = self.extract_rar(file_path)
            elif ext == '.7z':
                extraction_path = self.extract_7z(file_path)
            else:
                error_msg = f"Unsupported archive type: {ext or Path(file_path).suffix}"
                return self.handle_read_error(ValueError(error_msg), file_path, "read_file")

            # STANDARDIZED: Always return dict
            if extraction_path:
                result, extraction_path = extraction_path
                files = getattr(result, "files_extracted", 0) if result else 0
                payload = {
                    "extraction_path": extraction_path,
                    "status": "success",
                    "archive_type": ext.lstrip('.'),
                    # archive_safety measures these; without surfacing them a
                    # 1000-member archive and one that yielded nothing are
                    # indistinguishable downstream.
                    "files_extracted": files,
                    "bytes_extracted": getattr(result, "bytes_extracted", 0) if result else 0,
                    "skipped_members": list(getattr(result, "skipped", []) or []),
                }
                if files == 0:
                    # An empty archive is legitimate; an archive the backend
                    # could not actually parse is not. rarfile, for instance,
                    # opens a corrupt RAR5 and reports an empty namelist rather
                    # than raising, so this is the only place the distinction
                    # can be recorded rather than lost.
                    payload["extraction_info"] = {
                        "warning": "archive_opened_but_no_members_extracted",
                        "detail": (
                            "The archive was opened without error but yielded no "
                            "members. It may be genuinely empty, corrupt, or in a "
                            "format the installed backend cannot decode."
                        ),
                    }
                return payload
            else:
                error_msg = "Extraction failed"
                return self.handle_read_error(Exception(error_msg), file_path, "read_file")

        except ArchiveEncrypted as e:
            # A locked archive is actionable (supply a password) and must not be
            # recorded as though the file were corrupt.
            logger.info("Archive is password-protected: %s", file_path)
            result = self.handle_read_error(e, file_path, "read_file")
            result["archive_locked"] = True
            result["extraction_info"] = {
                "warning": "archive_password_protected",
                "detail": (
                    "The archive is encrypted. No password was supplied, so no "
                    "members could be read. This is not corruption: the "
                    "container was identified and opened."
                ),
            }
            return result
        except ArchiveSafetyError as e:
            # Safety violations are reported as rejected archives (client-safe).
            logger.warning("Archive rejected by safety policy: %s (%s)", file_path, e)
            return self.handle_read_error(e, file_path, "read_file")
        except Exception as e:
            return self.handle_read_error(e, file_path, "read_file")

    # ------------------------------------------------------------------
    # Extraction backends - all via core.archive_safety
    # ------------------------------------------------------------------
    def extract_zip(self, file_path):
        """Extract ZIP files safely (zip-slip protected)."""
        extract_to = get_extraction_name_file(file_path, '.zip')
        result = archive_safety.extract_zip(file_path, extract_to)
        logger.info("Extracted %d files from %s", result.files_extracted, file_path)
        return result, str(extract_to)

    def extract_tar(self, file_path, extension=None):
        """Extract TAR files safely (.tar, .tar.gz, .tar.bz2, .tar.xz).

        Args:
            file_path: Path to the tarball.
            extension: Effective (content-verified) extension. When omitted it
                is derived from the filename, which is wrong for a tarball
                whose declared extension disagrees with its contents.
        """
        if extension not in ('.tar.gz', '.tar.bz2', '.tar.xz'):
            extension = '.tar'

        extract_to = get_extraction_name_file(file_path, extension)
        result = archive_safety.extract_tar(file_path, extract_to)
        logger.info("Extracted %d files from %s", result.files_extracted, file_path)
        return result, str(extract_to)

    def extract_gz(self, file_path):
        """Extract GZ files (single file compression) safely."""
        extract_to = get_extraction_name_file(file_path, '.gz')
        result = archive_safety.extract_single_file(file_path, extract_to, codec="gzip")
        return result, str(extract_to)

    def extract_bz2(self, file_path):
        """Extract BZ2 files (single file compression) safely."""
        extract_to = get_extraction_name_file(file_path, '.bz2')
        result = archive_safety.extract_single_file(file_path, extract_to, codec="bzip2")
        return result, str(extract_to)

    def extract_rar(self, file_path):
        """Extract RAR files safely (requires rarfile package and UnRAR tool)."""
        try:
            import rarfile  # noqa: F401
        except ImportError:
            logger.warning("rarfile not installed. Install with: pip install rarfile")
            return None

        extract_to = get_extraction_name_file(file_path, '.rar')
        try:
            result = archive_safety.extract_rar(file_path, extract_to)
            logger.info("Extracted %d files from %s", result.files_extracted, file_path)
            return result, str(extract_to)
        except ArchiveSafetyError:
            # Re-raise: read_file's handler reports the specific reason. Turning
            # it into None here made every rejection surface as a generic
            # "Extraction failed", discarding which policy was hit.
            raise
        except Exception as e:
            # rarfile.RarCannotExec lands here: the UnRAR tool is missing.
            logger.warning("RAR extraction unavailable for %s: %s", file_path, e.__class__.__name__)
            return None

    def extract_7z(self, file_path):
        """Extract 7Z files safely (requires py7zr package)."""
        try:
            import py7zr  # noqa: F401
        except ImportError:
            logger.warning("py7zr not installed. Install with: pip install py7zr")
            return None

        extract_to = get_extraction_name_file(file_path, '.7z')
        try:
            result = archive_safety.extract_7z(file_path, extract_to)
            logger.info("Extracted %d files from %s", result.files_extracted, file_path)
            return result, str(extract_to)
        except ArchiveSafetyError:
            raise  # see extract_rar: read_file reports the specific reason
        except Exception as e:
            logger.error("Error extracting 7z file %s: %s", file_path, e.__class__.__name__)
            return None
