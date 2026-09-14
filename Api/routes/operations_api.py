"""Unified operations API (spec section 24).

Endpoints for the frontend control surface: file input/ingestion, the
Import Center, and the shared Jobs/Operations system.

Security model (server-side enforced):
* authentication  - middleware default-deny (core.security.flask_ext);
* authorization   - viewers read; analysts/admins start/pause/resume/cancel
                    ingestion and batch-import jobs; backup-import jobs and
                    job deletion are admin-only;
* CSRF            - global flask-wtf protection (no exemptions);
* validation      - every payload validated server-side (services raise
                    IngestionValidationError/... -> HTTP 400 structured error);
* rate limiting   - strict per-route limits on job creation.
"""
import json
import logging
import os
import shutil
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from core.path_safety import configured_ingestion_roots
from core.security.flask_ext import admin_required, current_user
from core.security.rate_limit import limiter
from services.importing.backup_import_service import (
    BackupImportService, BatchImportService,
)
from services.ingesting.options import IngestionOptions
from services.ingesting.service import (
    IngestionRequest, IngestionService, IngestionValidationError,
)
from services.jobs import job_state
from services.jobs.manager import JobManager
from services.jobs.models import job_to_api
from services.sources import (
    SourceSideError, create_side_svc, create_source_svc,
    list_sides_svc, list_sources_svc, search_sides_svc, search_sources_svc,
)

logger = logging.getLogger(__name__)

operations_bp = Blueprint("operations_api", __name__)


def _manager() -> JobManager:
    return JobManager.get_instance()


def _error(code: str, message: str, status: int, details=None):
    """Structured error envelope (spec section 23)."""
    body = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "request_id": uuid.uuid4().hex[:12],
        },
    }
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def _validation_error(exc: Exception):
    return _error("VALIDATION_FAILED", str(exc), 400)


def _username() -> str:
    user = current_user()
    return getattr(user, "username", None) or "system"


def _job_or_404(job_id):
    try:
        job = _manager().get(job_id)
    except KeyError:
        job = None
    if job is None:
        return None, _error("JOB_NOT_FOUND", "Job not found", 404)
    return job, None


MAX_UPLOAD_BYTES = int(os.environ.get("OPERATIONS_MAX_UPLOAD_MB", "2048")) * 1024 * 1024
UPLOAD_SUBDIR = "uploads"


def _staged_uploads_dir() -> Path:
    from core.app_paths import get_data_root

    d = Path(get_data_root()) / UPLOAD_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# ===========================================================================
# Sources & sides (Input page selects)
# ===========================================================================
@operations_bp.route("/api/input/options-info", methods=["GET"])
def api_input_options_info():
    """Capability info for the Input page (real backend facts only)."""
    try:
        roots = bool(configured_ingestion_roots())
    except Exception:
        roots = False
    return jsonify({
        "success": True,
        "ingestion_roots_configured": roots,
        "server_path_import_available": roots,
        "upload_available": True,
        "hashing": "sha256-streamed (always on)",
        "deduplication": "identity=(hash,source,side) (always on)",
        "archive_safety": "core.archive_safety (always on)",
    })


@operations_bp.route("/api/input/sources", methods=["GET"])
def api_input_sources():
    q = (request.args.get("q") or "").strip()
    rows = search_sources_svc(q) if q else list_sources_svc()
    return jsonify({"success": True, "sources": rows})


@operations_bp.route("/api/input/sides", methods=["GET"])
def api_input_sides():
    q = (request.args.get("q") or "").strip()
    rows = search_sides_svc(q) if q else list_sides_svc()
    return jsonify({"success": True, "sides": rows})


@operations_bp.route("/api/input/sources", methods=["POST"])
@limiter.limit("20 per minute")
def api_input_create_source():
    payload = request.get_json(silent=True) or {}
    try:
        created = create_source_svc(payload)
        return jsonify({"success": True, **created}), 201
    except SourceSideError as exc:
        return _validation_error(exc)
    except Exception:
        logger.exception("create source failed")
        return _error("SOURCE_CREATE_FAILED", "Source could not be created", 500)


@operations_bp.route("/api/input/sides", methods=["POST"])
@limiter.limit("20 per minute")
def api_input_create_side():
    payload = request.get_json(silent=True) or {}
    try:
        created = create_side_svc(payload)
        return jsonify({"success": True, **created}), 201
    except SourceSideError as exc:
        return _validation_error(exc)
    except Exception:
        logger.exception("create side failed")
        return _error("SIDE_CREATE_FAILED", "Side could not be created", 500)


# ===========================================================================
# Input: staged uploads + ingestion jobs
# ===========================================================================
@operations_bp.route("/api/input/uploads", methods=["POST"])
@limiter.limit("30 per minute")
def api_input_upload():
    """Stream uploaded files to server-side staging; returns staged paths.

    The browser cannot reference arbitrary server filesystem paths; uploads
    are staged under the application data root and can then be ingested.
    Archive/path safety applies later, at processing time, to staged files
    exactly as to any other input.
    """
    files = request.files.getlist("files") or (
        [request.files["file"]] if "file" in request.files else []
    )
    if not files:
        return _error("NO_FILES", "No files provided", 400)
    staged_dir = _staged_uploads_dir() / uuid.uuid4().hex[:12]
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    total = 0
    for fs in files:
        name = Path(fs.filename or "upload.bin").name  # never trust filenames
        if not name or name in {".", ".."}:
            continue
        dest = staged_dir / name
        written = 0
        try:
            with open(dest, "wb") as out:
                while True:
                    chunk = fs.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise ValueError("size")
                    out.write(chunk)
        except ValueError:
            shutil.rmtree(staged_dir, ignore_errors=True)
            return _error("UPLOAD_TOO_LARGE", "Upload exceeds the size limit", 413)
        except Exception:
            shutil.rmtree(staged_dir, ignore_errors=True)
            logger.exception("upload staging failed")
            return _error("UPLOAD_FAILED", "Upload could not be stored", 500)
        staged.append(str(dest))
    if not staged:
        shutil.rmtree(staged_dir, ignore_errors=True)
        return _error("NO_FILES", "No valid files provided", 400)
    return jsonify({
        "success": True,
        "staged_paths": staged,
        "bytes": total,
        "expires_note": "Staged files are plain files; ingest or delete them.",
    }), 201


def _as_bool(value, default: bool) -> bool:
    """Boolean coercion for multipart form fields (string "false" → False)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_ingestion_payload() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    # multipart: staged upload followed by job creation in one request
    data = request.form.to_dict()
    paths = data.pop("file_paths", "[]")
    try:
        data["file_paths"] = json.loads(paths) if paths else []
    except (TypeError, ValueError):
        raise IngestionValidationError("file_paths must be a JSON array")
    if request.files:
        staged_dir = _staged_uploads_dir() / uuid.uuid4().hex[:12]
        staged_dir.mkdir(parents=True, exist_ok=True)
        staged = []
        for fs in request.files.getlist("files"):
            name = Path(fs.filename or "upload.bin").name
            dest = staged_dir / name
            fs.save(dest)
            staged.append(str(dest))
        data["file_paths"] = (data.get("file_paths") or []) + staged
    return data


@operations_bp.route("/api/input/jobs", methods=["POST"])
@limiter.limit("10 per minute")
def api_create_input_job():
    """Create an ingestion job (dry_run supported)."""
    try:
        data = _parse_ingestion_payload()
    except IngestionValidationError as exc:
        return _validation_error(exc)

    processing = data.get("processing") or {}
    if not isinstance(processing, dict):
        return _validation_error(IngestionValidationError("processing must be an object"))
    try:
        options = IngestionOptions(**{
            k: processing[k] for k in
            ("max_workers", "checkpoint", "enable_monitoring")
            if k in processing
        })
    except (TypeError, ValueError):
        return _validation_error(IngestionValidationError("Invalid processing options"))

    request_payload = {
        "path": data.get("path"),
        "file_paths": data.get("file_paths") or [],
        "source": data.get("source") or "",
        "side": data.get("side") or "",
        "recursive": bool(data.get("recursive", True)),
        "dry_run": bool(data.get("dry_run", False)),
        "processing": options.to_dict(),
    }
    # Validate BEFORE persisting the job (fail fast, no doomed job rows).
    probe = IngestionService()
    req = IngestionRequest(
        path=request_payload["path"],
        file_paths=request_payload["file_paths"],
        source=request_payload["source"],
        side=request_payload["side"],
        recursive=request_payload["recursive"],
        options=options,
        dry_run=request_payload["dry_run"],
        created_by=_username(),
    )
    try:
        probe.validate(req)
    except IngestionValidationError as exc:
        return _validation_error(exc)

    if request_payload["dry_run"]:
        # Dry runs are quick; answer synchronously (still no DB writes).
        try:
            return jsonify({
                "success": True, "dry_run": True,
                "preview": probe.discover(req),
            })
        except IngestionValidationError as exc:
            return _validation_error(exc)

    try:
        job = _manager().create_job(
            "ingestion",
            source=req.path or f"{len(req.file_paths)} files",
            options={
                "path": req.path,
                "file_paths": req.file_paths,
                "source": req.source,
                "side": req.side,
                "recursive": req.recursive,
                "processing": options.to_dict(),
            },
            created_by=_username(),
        )
    except Exception:
        logger.exception("job creation failed")
        return _error("JOB_CREATE_FAILED", "Job could not be created", 500)
    return jsonify({"success": True, "job": job_to_api(job)}), 202


@operations_bp.route("/api/input/jobs", methods=["GET"])
def api_list_input_jobs():
    jobs = _manager().list(job_type="ingestion",
                           limit=min(int(request.args.get("limit", 50)), 200))
    return jsonify({"success": True, "jobs": [job_to_api(j) for j in jobs]})


# ===========================================================================
# Import Center
# ===========================================================================
IMPORT_TYPES = ("domain_import", "backup_import", "batch_import")


@operations_bp.route("/api/import/validate", methods=["POST"])
@limiter.limit("20 per minute")
def api_import_validate():
    """Validate an import source without committing anything."""
    data = request.get_json(silent=True) or {}
    itype = data.get("type")
    try:
        if itype == "batch_import":
            preview = BatchImportService().preview(data.get("file_paths") or [])
            return jsonify({"success": True, "preview": preview})
        if itype == "backup_import":
            svc = BackupImportService()
            path = data.get("backup_path")
            if not path:
                return _error("VALIDATION_FAILED", "No backup file provided", 400)
            return jsonify({"success": True, "preview": svc.validate_backup(path)})
        if itype == "domain_import":
            from services.importing.domain_import_service import (
                DomainImportRequest, DomainImportService,
            )

            svc = DomainImportService()
            req = svc.validate(DomainImportRequest(data_file=data.get("data_file")))
            return jsonify({"success": True, "preview": {
                "data_file": req.data_file or "(default)",
                "note": "Use preview=true on the job to parse without writing.",
            }})
    except Exception as exc:
        return _validation_error(exc)
    return _error("VALIDATION_FAILED", f"Unknown import type: {itype}", 400)


@operations_bp.route("/api/import/preview", methods=["POST"])
@limiter.limit("10 per minute")
def api_import_preview():
    """Dry-run preview of a full import job (no destructive changes)."""
    data = request.get_json(silent=True) or {}
    itype = data.get("type")
    if itype not in IMPORT_TYPES:
        return _error("VALIDATION_FAILED", f"Unknown import type: {itype}", 400)
    try:
        job = _manager().create_job(
            itype,
            source=data.get("source") or data.get("data_file") or "preview",
            options={**data, "dry_run": True},
            created_by=_username(),
            starter=None if itype != "backup_import" else None,
        )
    except Exception:
        logger.exception("preview job failed")
        return _error("JOB_CREATE_FAILED", "Preview job could not be created", 500)
    if _manager().synchronous:
        job = _manager().get(job["job_id"])
        return jsonify({"success": True, "job": job_to_api(job),
                        "stats": job.get("stats")})
    return jsonify({"success": True, "job": job_to_api(job)}), 202


@operations_bp.route("/api/import/jobs", methods=["POST"])
@limiter.limit("10 per minute")
def api_create_import_job():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    itype = data.get("type")
    if itype not in IMPORT_TYPES:
        return _validation_error(
            Exception(f"type must be one of: {', '.join(IMPORT_TYPES)}"))
    if itype == "backup_import":
        # Admin-only regardless of button visibility (spec section 17).
        user = current_user()
        if getattr(user, "role", None) != "admin":
            return _error("FORBIDDEN", "Administrator role required", 403)
        # staged upload support
        fs = request.files.get("file")
        if fs is not None:
            staged_dir = _staged_uploads_dir() / uuid.uuid4().hex[:12]
            staged_dir.mkdir(parents=True, exist_ok=True)
            name = Path(fs.filename or "backup.zip").name
            dest = staged_dir / name
            fs.save(dest)
            data["backup_path"] = str(dest)
        if not data.get("backup_path"):
            # Fail fast: no doomed job rows (same contract as the
            # /api/import/validate endpoint).
            return _validation_error(Exception("No backup file provided"))
    if itype == "domain_import" and not data.get("data_file"):
        return _validation_error(Exception("No data_file provided"))
    if itype == "batch_import":
        # accept staged uploads too
        fs_list = request.files.getlist("files")
        if fs_list:
            staged_dir = _staged_uploads_dir() / uuid.uuid4().hex[:12]
            staged_dir.mkdir(parents=True, exist_ok=True)
            staged = []
            for fs in fs_list:
                name = Path(fs.filename or "upload.bin").name
                dest = staged_dir / name
                fs.save(dest)
                staged.append(str(dest))
            data["file_paths"] = (data.get("file_paths") or []) + staged
        if not data.get("source") or not data.get("side"):
            return _validation_error(Exception("source and side are required"))
    try:
        options = {k: v for k, v in data.items()
                   if k in ("file_paths", "source", "side", "data_file",
                            "backup_path", "backup_name", "processing")}
        job = _manager().create_job(itype, source=str(data.get("source") or itype),
                                    options=options, created_by=_username())
    except Exception:
        logger.exception("import job failed to start")
        return _error("JOB_CREATE_FAILED", "Import job could not be created", 500)
    return jsonify({"success": True, "job": job_to_api(job)}), 202


@operations_bp.route("/api/import/jobs", methods=["GET"])
def api_list_import_jobs():
    jobs = _manager().list(
        job_type=request.args.get("type") or None,
        limit=min(int(request.args.get("limit", 50)), 200),
    )
    return jsonify({"success": True, "jobs": [job_to_api(j) for j in jobs]})


# ===========================================================================
# Jobs / Operations Center (shared across job types)
# ===========================================================================
@operations_bp.route("/api/jobs", methods=["GET"])
def api_list_jobs():
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return _error("VALIDATION_FAILED", "limit/offset must be integers", 400)
    jobs = _manager().list(
        job_type=request.args.get("type") or None,
        status=request.args.get("status") or None,
        created_by=request.args.get("user") or None,
        limit=limit, offset=offset,
    )
    return jsonify({"success": True, "jobs": [job_to_api(j) for j in jobs]})


@operations_bp.route("/api/jobs/<job_id>", methods=["GET"])
def api_get_job(job_id):
    job, err = _job_or_404(job_id)
    if err:
        return err
    return jsonify({"success": True, "job": job_to_api(job),
                    "stats": job.get("stats")})


@operations_bp.route("/api/jobs/<job_id>/events", methods=["GET"])
def api_job_events(job_id):
    job, err = _job_or_404(job_id)
    if err:
        return err
    try:
        after = int(request.args.get("after_id", 0))
        limit = min(max(int(request.args.get("limit", 200)), 1), 1000)
    except (TypeError, ValueError):
        return _error("VALIDATION_FAILED", "after_id/limit must be integers", 400)
    events = _manager().events(job_id, limit=limit, after_id=after)
    return jsonify({"success": True, "events": events})


@operations_bp.route("/api/jobs/<job_id>/errors", methods=["GET"])
def api_job_errors(job_id):
    job, err = _job_or_404(job_id)
    if err:
        return err
    return jsonify({"success": True,
                    "errors": (job.get("errors") or [])[:500],
                    "warnings": (job.get("warnings") or [])[:500]})


@operations_bp.route("/api/jobs/<job_id>/results", methods=["GET"])
def api_job_results(job_id):
    job, err = _job_or_404(job_id)
    if err:
        return err
    return jsonify({
        "success": True,
        "status": job.get("status"),
        "result_summary": job.get("result_summary"),
        "stats": job.get("stats"),
    })


def _control(job_id, action):
    try:
        result = getattr(_manager(), action)(job_id)
    except KeyError:
        return _error("JOB_NOT_FOUND", "Job not found", 404)
    except ValueError as exc:
        return _error("INVALID_STATE", str(exc), 409)
    except Exception:
        logger.exception("job %s failed", action)
        return _error("CONTROL_FAILED", f"Job {action} failed", 500)
    return jsonify({"success": True, "job": job_to_api(result)})


@operations_bp.route("/api/jobs/<job_id>/cancel", methods=["POST"])
@limiter.limit("30 per minute")
def api_cancel_job(job_id):
    return _control(job_id, "cancel")


@operations_bp.route("/api/jobs/<job_id>/pause", methods=["POST"])
@limiter.limit("30 per minute")
def api_pause_job(job_id):
    return _control(job_id, "pause")


@operations_bp.route("/api/jobs/<job_id>/resume", methods=["POST"])
@limiter.limit("30 per minute")
def api_resume_job(job_id):
    try:
        job = _manager().resume(job_id, created_by=_username())
    except KeyError:
        return _error("JOB_NOT_FOUND", "Job not found", 404)
    except ValueError as exc:
        return _error("INVALID_STATE", str(exc), 409)
    return jsonify({"success": True, "job": job_to_api(job)}), 202


@operations_bp.route("/api/jobs/<job_id>/retry", methods=["POST"])
@limiter.limit("10 per minute")
def api_retry_job(job_id):
    try:
        job = _manager().retry(job_id, created_by=_username())
    except KeyError:
        return _error("JOB_NOT_FOUND", "Job not found", 404)
    except ValueError as exc:
        return _error("INVALID_STATE", str(exc), 409)
    return jsonify({"success": True, "job": job_to_api(job)}), 202


@operations_bp.route("/api/jobs/<job_id>", methods=["DELETE"])
@admin_required
def api_delete_job(job_id):
    try:
        deleted = _manager().delete(job_id)
    except KeyError:
        return _error("JOB_NOT_FOUND", "Job not found", 404)
    except ValueError as exc:
        return _error("INVALID_STATE", str(exc), 409)
    return jsonify({"success": deleted})


@operations_bp.route("/api/jobs/stream", methods=["GET"])
def api_job_stream():
    """SSE stream of job events (single-process deployments).

    Multi-process deployments should use the polling fallback built into
    the Operations UI (events endpoint, ~2s). This endpoint degrades to a
    heartbeat-only stream when no events arrive.
    """
    from queue import Queue, Empty

    q = Queue(maxsize=200)
    mgr = _manager()
    mgr.subscribe(q)

    def generate():
        try:
            yield ": connected\n\n"
            import time as _time

            last = _time.time()
            while True:
                try:
                    evt = q.get(timeout=5)
                    yield (f"event: {evt['event_type']}\n"
                           f"data: {json.dumps(evt)}\n\n")
                    last = _time.time()
                except Empty:
                    yield ": keep-alive\n\n"
                    if _time.time() - last > 300:
                        return
        finally:
            mgr.unsubscribe(q)

    resp = current_app.response_class(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@operations_bp.route("/api/jobs/summary", methods=["GET"])
def api_jobs_summary():
    counts = _manager().repo.count_by_status()
    active = counts.get(job_state.RUNNING, 0) + counts.get(job_state.QUEUED, 0)
    return jsonify({"success": True,
                    "counts": counts,
                    "active": active})
