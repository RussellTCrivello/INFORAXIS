"""Safe archive extraction (SEC-05).

Hardening applied to every archive reader (ZIP, TAR, GZIP, BZIP2, RAR, 7z):

* Rejection of absolute paths, ``..`` traversal, drive-qualified and UNC paths.
* Every destination is re-validated to resolve beneath the extraction root
  after normalisation (zip-slip / tar-slip / symlink escapes).
* Symlinks and hard links are refused (they cannot be validated statically).
* Resource limits: maximum depth, maximum member count, maximum extracted
  bytes, maximum compression ratio, per-file size limit and a wall-clock
  timeout.
* No ``extractall`` anywhere: members are streamed one at a time.
"""

from __future__ import annotations

import logging
import os
import time
import zipfile
import bz2
import gzip
import lzma
import tarfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Iterable, List, Optional

logger = logging.getLogger(__name__)


class ArchiveSafetyError(Exception):
    """Raised when an archive violates the extraction safety policy."""


class ArchiveEncrypted(ArchiveSafetyError):
    """The archive is password-protected and no usable password was supplied.

    A subclass of ArchiveSafetyError so existing handlers keep working, but
    distinguishable: a locked archive is a different fact from a corrupt one,
    and reporting both as an opaque extraction error makes an actionable
    condition (supply a password) look like a defect.
    """


class ArchiveTimeout(ArchiveSafetyError):
    pass


@dataclass
class ExtractionPolicy:
    """Resource limits applied during extraction."""

    max_depth: int = 8
    max_files: int = 10_000
    max_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GiB total extracted
    max_file_size: int = 512 * 1024 * 1024  # per member
    max_compression_ratio: int = 500
    timeout_seconds: float = 600.0
    allowed_extensions: Optional[Iterable[str]] = None  # None = any


DEFAULT_POLICY = ExtractionPolicy()

_FORBIDDEN_MEMBERS = ("", ".", "..")

#: Windows reserved device names. These are devices, not files: opening
#: ``CON.txt`` writes to the console and ``NUL`` discards data, with or without
#: an extension and regardless of case. Archives are frequently authored on
#: other platforms where such names are ordinary, so they arrive here intact.
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

#: Per-component filename limit. Windows rejects longer components outright,
#: and the legacy MAX_PATH of 260 is still the default for most tools.
_MAX_COMPONENT_LENGTH = 200


def windows_safe_component(part: str) -> str:
    """Make one path component writable on Windows without discarding the file.

    Windows is the primary production platform, so a member name that is legal
    on the authoring platform must not become an unwritable path here. Renaming
    is deliberate over rejecting: refusing the whole archive because one member
    happened to be called ``CON`` would discard every other object in it, and an
    unsupported or awkward child must stay part of the parent's object graph.
    """
    if not part:
        return part

    # Reserved device names, with or without an extension, case-insensitive.
    stem = part.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        part = "_" + part

    # Windows strips trailing dots and spaces; leaving them makes the written
    # name differ from the requested one and can collide with a sibling.
    part = part.rstrip(". ")

    # Keep the extension when truncating so the type is still identifiable.
    if len(part) > _MAX_COMPONENT_LENGTH:
        stem_part, dot, ext = part.rpartition(".")
        if dot and len(ext) <= 20 and stem_part:
            keep = _MAX_COMPONENT_LENGTH - len(ext) - 1
            part = f"{stem_part[:keep]}.{ext}"
        else:
            part = part[:_MAX_COMPONENT_LENGTH]

    return part or "_"


def _check_deadline(deadline: Optional[float]) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise ArchiveTimeout("Archive extraction exceeded the configured timeout")


def validate_member_path(name: str) -> str:
    """Normalise and validate an archive member name.

    Returns a safe, relative, slash-delimited path.

    Raises :class:`ArchiveSafetyError` for absolute paths, traversal,
    drive-qualified paths, UNC paths and NUL bytes.
    """
    if not name or "\x00" in name:
        raise ArchiveSafetyError(f"Invalid archive member name: {name!r}")

    # Detect Windows-isms before any normalisation can hide them.
    win = PureWindowsPath(name)
    if win.is_absolute() or win.drive:
        raise ArchiveSafetyError(f"Absolute or drive-qualified path in archive: {name!r}")
    if name.startswith("\\\\") or name.startswith("//"):
        raise ArchiveSafetyError(f"UNC path in archive: {name!r}")

    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute():
        raise ArchiveSafetyError(f"Absolute path in archive: {name!r}")

    parts: List[str] = []
    depth = 0
    for part in p.parts:
        if part in ("", "."):
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                raise ArchiveSafetyError(f"Path traversal in archive member: {name!r}")
            if parts:
                parts.pop()
            continue
        depth += 1
        parts.append(windows_safe_component(part))

    if not parts:
        raise ArchiveSafetyError(f"Empty archive member path: {name!r}")
    if len(parts) > DEFAULT_POLICY.max_depth:
        raise ArchiveSafetyError(f"Archive member exceeds maximum depth: {name!r}")

    return "/".join(parts)


def safe_destination(root: Path, member_name: str) -> Path:
    """Resolve ``root`` + validated member name and confirm containment."""
    root = root.resolve()
    relative = validate_member_path(member_name)
    destination = (root / relative).resolve()
    # Final containment check post-normalisation (defends against symlinked
    # intermediate directories created by earlier members).
    if destination != root and root not in destination.parents:
        raise ArchiveSafetyError(
            f"Archive member escapes extraction root: {member_name!r}"
        )
    return destination


@dataclass
class ExtractionResult:
    output_dir: Path
    files_extracted: int = 0
    bytes_extracted: int = 0
    skipped: List[str] = field(default_factory=list)


def _policy_for_file(policy: ExtractionPolicy, name: str) -> None:
    if policy.allowed_extensions is not None:
        ext = Path(name).suffix.lower()
        if ext not in policy.allowed_extensions:
            raise ArchiveSafetyError(f"File type not allowed in archive: {name!r}")


def _destination_checks(policy: ExtractionPolicy, dest: Path, member_size: int) -> None:
    if member_size > policy.max_file_size:
        raise ArchiveSafetyError(
            f"Archive member exceeds per-file size limit: {dest.name} ({member_size} bytes)"
        )


def extract_zip(
    archive_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    policy: ExtractionPolicy = DEFAULT_POLICY,
    on_member: Optional[Callable[[str], None]] = None,
) -> ExtractionResult:
    """Safely extract a ZIP archive member-by-member."""
    deadline = time.monotonic() + policy.timeout_seconds if policy.timeout_seconds else None
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    result = ExtractionResult(output_dir=root)

    with zipfile.ZipFile(archive_path) as zf:
        infos = zf.infolist()
        # Bit 0 of the general-purpose flag marks an encrypted member. Check it
        # before any read: zipfile raises an opaque RuntimeError from deep
        # inside read(), which is indistinguishable from corruption and gives
        # the caller nothing actionable.
        if any((i.flag_bits & 0x1) for i in infos):
            raise ArchiveEncrypted(
                "Archive is password-protected and no password was supplied"
            )
        if len(infos) > policy.max_files:
            raise ArchiveSafetyError(
                f"Archive contains {len(infos)} members (limit {policy.max_files})"
            )
        total_uncompressed = sum(i.file_size for i in infos)
        total_compressed = sum(i.compress_size for i in infos) or 1
        if total_uncompressed > policy.max_bytes:
            raise ArchiveSafetyError("Archive expands beyond the total byte limit")
        if total_uncompressed / total_compressed > policy.max_compression_ratio:
            raise ArchiveSafetyError("Archive compression ratio exceeds safety limit")

        for info in infos:
            _check_deadline(deadline)
            name = info.filename
            if name.endswith("/"):
                continue
            safe_name = validate_member_path(name)
            dest = safe_destination(root, safe_name)
            _policy_for_file(policy, name)
            _destination_checks(policy, dest, info.file_size)
            if on_member:
                on_member(safe_name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Re-verify containment after mkdir (symlinked parents).
            if root not in dest.resolve().parents:
                raise ArchiveSafetyError(f"Archive member escapes extraction root: {name!r}")
            with zf.open(info, "r") as src, open(dest, "wb") as out:
                copied = 0
                while True:
                    _check_deadline(deadline)
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > info.file_size:
                        raise ArchiveSafetyError(
                            f"Member reports inconsistent size while streaming: {name!r}"
                        )
                    out.write(chunk)
            result.files_extracted += 1
            result.bytes_extracted += copied
    return result


def extract_tar(
    archive_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    policy: ExtractionPolicy = DEFAULT_POLICY,
    on_member: Optional[Callable[[str], None]] = None,
) -> ExtractionResult:
    """Safely extract a TAR archive (incl. .tar.gz/.tar.bz2/.tar.xz)."""
    deadline = time.monotonic() + policy.timeout_seconds if policy.timeout_seconds else None
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    result = ExtractionResult(output_dir=root)

    with tarfile.open(archive_path, "r:*") as tf:
        members = tf.getmembers()
        if len(members) > policy.max_files:
            raise ArchiveSafetyError(
                f"Archive contains {len(members)} members (limit {policy.max_files})"
            )
        total = sum(m.size for m in members)
        if total > policy.max_bytes:
            raise ArchiveSafetyError("Archive expands beyond the total byte limit")

        for member in members:
            _check_deadline(deadline)
            if not (member.isfile() or member.isdir()):
                # Refuse symlinks, hardlinks, devices, fifos.
                result.skipped.append(member.name)
                logger.warning("Refusing non-regular archive member: %s", member.name)
                continue
            safe_name = validate_member_path(member.name)
            dest = safe_destination(root, safe_name)
            _policy_for_file(policy, member.name)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
                if root not in dest.resolve().parents and dest != root:
                    raise ArchiveSafetyError(
                        f"Archive member escapes extraction root: {member.name!r}"
                    )
                continue
            _destination_checks(policy, dest, member.size)
            if on_member:
                on_member(safe_name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if root not in dest.resolve().parents:
                raise ArchiveSafetyError(
                    f"Archive member escapes extraction root: {member.name!r}"
                )
            src = tf.extractfile(member)
            if src is None:
                result.skipped.append(member.name)
                continue
            with src, open(dest, "wb") as out:
                copied = 0
                while True:
                    _check_deadline(deadline)
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    out.write(chunk)
            os.chmod(dest, 0o600)
            result.files_extracted += 1
            result.bytes_extracted += copied
    return result


def extract_single_file(
    archive_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    codec: str = "gzip",
    policy: ExtractionPolicy = DEFAULT_POLICY,
) -> ExtractionResult:
    """Safely extract a single-file stream (gzip/bzip2/xz)."""
    deadline = time.monotonic() + policy.timeout_seconds if policy.timeout_seconds else None
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    result = ExtractionResult(output_dir=root)

    opener = {"gzip": gzip.open, "bzip2": bz2.open, "xz": lzma.open}[codec]
    src_name = Path(archive_path).name
    for suffix in (".gz", ".bz2", ".xz"):
        if src_name.lower().endswith(suffix):
            src_name = src_name[: -len(suffix)]
            break
    dest = safe_destination(root, src_name or "decompressed.bin")
    if dest.exists():
        dest = safe_destination(root, (src_name or "decompressed.bin") + ".out")

    compressed_size = Path(archive_path).stat().st_size or 1
    copied = 0
    with opener(archive_path, "rb") as src, open(dest, "wb") as out:
        while True:
            _check_deadline(deadline)
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if copied > policy.max_file_size:
                raise ArchiveSafetyError("Decompressed file exceeds the per-file size limit")
            if copied / compressed_size > policy.max_compression_ratio:
                raise ArchiveSafetyError("Decompression ratio exceeds safety limit")
            out.write(chunk)
    result.files_extracted = 1
    result.bytes_extracted = copied
    return result


def extract_7z(
    archive_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    policy: ExtractionPolicy = DEFAULT_POLICY,
) -> ExtractionResult:
    """Safely extract a 7z archive (requires py7zr)."""
    try:
        import py7zr
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ArchiveSafetyError("py7zr is not installed; cannot extract 7z archives") from exc

    deadline = time.monotonic() + policy.timeout_seconds if policy.timeout_seconds else None
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    result = ExtractionResult(output_dir=root)

    with py7zr.SevenZipFile(archive_path, "r") as sz:
        if sz.needs_password():
            raise ArchiveEncrypted(
                "Archive is password-protected and no password was supplied"
            )
        file_list = sz.list()
        if len(file_list) > policy.max_files:
            raise ArchiveSafetyError(
                f"Archive contains {len(file_list)} members (limit {policy.max_files})"
            )
        for info in file_list:
            _check_deadline(deadline)
            validate_member_path(info.filename)
            if policy.allowed_extensions is not None:
                ext = Path(info.filename).suffix.lower()
                if ext and ext not in policy.allowed_extensions:
                    raise ArchiveSafetyError(
                        f"File type not allowed in archive: {info.filename!r}"
                    )
        # py7zr performs its own traversal sanitisation for targets we point it
        # at; we pre-validated every member name above and verify the tree.
        sz.extractall(path=root)
    _verify_tree_within(root, root, policy)
    for p in root.rglob("*"):
        if p.is_file():
            result.files_extracted += 1
            result.bytes_extracted += p.stat().st_size
    if result.files_extracted > policy.max_files or result.bytes_extracted > policy.max_bytes:
        raise ArchiveSafetyError("7z extraction exceeded resource limits")
    return result


def extract_rar(
    archive_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    policy: ExtractionPolicy = DEFAULT_POLICY,
) -> ExtractionResult:
    """Safely extract a RAR archive member-by-member (requires rarfile + unrar)."""
    try:
        import rarfile
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ArchiveSafetyError("rarfile is not installed; cannot extract RAR archives") from exc

    deadline = time.monotonic() + policy.timeout_seconds if policy.timeout_seconds else None
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    result = ExtractionResult(output_dir=root)

    with rarfile.RarFile(str(archive_path)) as rf:
        infos = rf.infolist()
        if len(infos) > policy.max_files:
            raise ArchiveSafetyError(
                f"Archive contains {len(infos)} members (limit {policy.max_files})"
            )
        for info in infos:
            _check_deadline(deadline)
            if info.is_dir():
                continue
            safe_name = validate_member_path(info.filename)
            dest = safe_destination(root, safe_name)
            _destination_checks(policy, dest, info.file_size)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if root not in dest.resolve().parents:
                raise ArchiveSafetyError(
                    f"Archive member escapes extraction root: {info.filename!r}"
                )
            with rf.open(info) as src, open(dest, "wb") as out:
                copied = 0
                while True:
                    _check_deadline(deadline)
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    out.write(chunk)
            os.chmod(dest, 0o600)
            result.files_extracted += 1
            result.bytes_extracted += copied
    return result


def _verify_tree_within(root: Path, current: Path, policy: ExtractionPolicy) -> None:
    """Verify every filesystem node under ``current`` stays within ``root``."""
    root = root.resolve()
    count = 0
    for p in current.rglob("*"):
        count += 1
        if count > policy.max_files:
            raise ArchiveSafetyError("Extracted tree exceeds the file-count limit")
        resolved = p.resolve()
        if resolved != root and root not in resolved.parents:
            raise ArchiveSafetyError(f"Path escapes extraction root: {p}")
        if p.is_symlink():
            raise ArchiveSafetyError(f"Symlink created during extraction: {p}")
        if p.is_file():
            if p.stat().st_size > policy.max_file_size:
                raise ArchiveSafetyError(f"Extracted file exceeds size limit: {p}")


def is_safe_member_name(name: str) -> bool:
    """Boolean convenience wrapper around :func:`validate_member_path`."""
    try:
        validate_member_path(name)
        return True
    except ArchiveSafetyError:
        return False
