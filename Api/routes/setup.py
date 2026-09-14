"""
Web-based installation wizard routes.

The page at /setup renders a multi-step wizard (install_wizard.html).
Each step calls an API endpoint that delegates to the shared installer
services in core.installer — no business logic lives here.

Endpoints:
    GET  /setup                  → wizard page
    GET  /api/setup/system-check → prerequisite checks
    POST /api/setup/test-database→ DB connectivity test
    POST /api/setup/install      → execute full installation
    GET  /api/setup/check        → is the system initialized?
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
import logging
import threading

logger = logging.getLogger(__name__)

setup_bp = Blueprint("setup", __name__)

# Installation lock: prevents concurrent installation requests from
# racing.  Only one installation can execute at a time across all
# threads.  The second request receives a deterministic 409 response.
_install_lock = threading.Lock()


def _is_initialized():
    """Authoritative initialization-state check.

    The system is considered initialized when the filesystem marker exists
    AND the critical tables exist in the application database.  The
    filesystem marker is the fast-path; the table check is authoritative.

    Returns True if initialized, False if not, False on any error
    (fail-safe: an errored check should not block legitimate setup).
    """
    # Fast-path: filesystem marker (written at end of successful install)
    try:
        from core.initialization import is_system_initialized
        if not is_system_initialized():
            return False
        # Marker exists, but verify DB is actually ready too
    except Exception:
        return False

    # Authoritative check: do the critical tables exist?
    try:
        import psycopg2
        from database import get_db_config
        cfg = get_db_config()
        conn = psycopg2.connect(
            dbname=cfg.get("database", "analysis"),
            user=cfg.get("user", "postgres"),
            password=cfg.get("password", ""),
            host=cfg.get("host", "localhost"),
            port=cfg.get("port", 5432),
            connect_timeout=5,
        )
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='public' "
                "AND table_name IN ('words','paths','contents','users')")
            count = cur.fetchone()[0]
            cur.close()
            return count >= 4
        finally:
            conn.close()
    except Exception:
        # DB unreachable — if marker exists, trust it (partial recovery case)
        return True


def _reject_if_initialized():
    """Return an error response if the system is already initialized.

    Used as a guard on mutating setup endpoints.  Returns None if the
    system is NOT initialized (i.e., installation is allowed).
    """
    try:
        if _is_initialized():
            return jsonify({
                "ok": False,
                "error": "System is already initialized. "
                         "Re-installation is not permitted through this endpoint."
            }), 409  # 409 Conflict
    except Exception as e:
        # If we cannot determine state, block installation as a safety measure.
        # The admin can always use CLI for recovery.
        logger.error("Initialization check failed: %s", e)
        return jsonify({
            "ok": False,
            "error": "Cannot verify system state. "
                     "Installation blocked for safety. Use CLI for recovery."
        }), 503
    return None


# ── Page ──
@setup_bp.route("/setup", methods=["GET"])
def setup_page():
    if _is_initialized():
        return redirect(url_for("index"))
    return render_template("Setup/install_wizard.html")


# ── Step 1: System check ──
@setup_bp.route("/api/setup/system-check", methods=["GET"])
def system_check():
    from core.installer import check_system
    checks = check_system()
    all_ok = all(c.get("ok", False) for c in checks.values())
    return jsonify({"all_ok": all_ok, "checks": checks})


# ── Step 2: Test database ──
@setup_bp.route("/api/setup/test-database", methods=["POST"])
def test_database():
    from core.installer import test_database_connection
    data = request.get_json() or {}
    result = test_database_connection(
        host=data.get("host", "localhost"),
        port=int(data.get("port", 5432)),
        user=data.get("user", "postgres"),
        password=data.get("password", ""),
        database=data.get("database", "analysis"),
    )
    status = 200 if result.get("ok", True) else 400
    return jsonify(result), status


# ── Step 5: Full installation ──
@setup_bp.route("/api/setup/install", methods=["POST"])
def run_installation():
    # GUARD 1: reject if system is already initialized
    guard_response = _reject_if_initialized()
    if guard_response is not None:
        return guard_response

    # GUARD 2: serialize installation — only one request at a time.
    # Non-blocking acquire: if another request is already installing,
    # return 409 immediately rather than waiting or racing.
    acquired = _install_lock.acquire(blocking=False)
    if not acquired:
        return jsonify({
            "ok": False,
            "error": "Installation is already in progress. "
                     "Please wait for it to complete."
        }), 409

    try:
        from core.installer import run_installation as _run
        data = request.get_json() or {}

        # Validate required fields
        db_password = data.get("db_password", "")
        admin_username = data.get("admin_username", "admin").strip()
        admin_password = data.get("admin_password", "")
        pw_min = int(data.get("password_min_length", 12))

        if not db_password:
            return jsonify({"ok": False, "error": "Database password is required"}), 400
        if not admin_password or len(admin_password) < pw_min:
            return jsonify({"ok": False,
                            "error": f"Admin password must be at least {pw_min} characters"}), 400
        if not admin_username:
            return jsonify({"ok": False, "error": "Admin username is required"}), 400

        # Map frontend field names → .env key names
        config = {
            "DB_HOST": data.get("db_host", "localhost"),
            "DB_PORT": str(data.get("db_port", 5432)),
            "DB_USER": data.get("db_user", "postgres"),
            "DB_PASSWORD": db_password,
            "DB_NAME": data.get("db_name", "analysis"),
            "APP_ADMIN_USERNAME": admin_username,
            "APP_ADMIN_PASSWORD": admin_password,
            "FLASK_ENV": data.get("environment", "production"),
            "FLASK_PORT": str(data.get("flask_port", 5000)),
            "FLASK_HOST": data.get("flask_host", "0.0.0.0"),
            "MAX_WORKERS": str(data.get("max_workers", 8)),
            "LOG_LEVEL": data.get("log_level", "INFO"),
            "INGESTION_ROOTS": data.get("ingestion_roots", ""),
            "SECURITY_MAX_FAILED_LOGINS": str(data.get("max_failed_logins", 5)),
            "SECURITY_LOCKOUT_MINUTES": str(data.get("lockout_minutes", 15)),
            "SECURITY_SESSION_HOURS": str(data.get("session_hours", 12)),
            "SECURITY_SESSION_IDLE_HOURS": str(data.get("session_idle_hours", 6)),
            "PASSWORD_MIN_LENGTH": str(pw_min),
            "RATE_LIMIT_PER_MINUTE": str(data.get("rate_limit_per_minute", 60)),
            "RATE_LIMIT_PER_HOUR": str(data.get("rate_limit_per_hour", 600)),
            "FILE_PROCESSING_TIMEOUT": str(data.get("file_processing_timeout", 1200)),
        }

        result = _run(config)
        result["redirect"] = url_for("index")
        status = 200 if result.get("ok") else 500
        return jsonify(result), status
    finally:
        _install_lock.release()


# ── Status check ──
@setup_bp.route("/api/setup/check", methods=["GET"])
def check_setup_status():
    try:
        return jsonify({"initialized": _is_initialized()}), 200
    except Exception:
        return jsonify({"initialized": False}), 200


# ── Registration ──
def register_setup_routes(app):
    app.register_blueprint(setup_bp)

    @app.before_request
    def _check_database_setup():
        if request.endpoint in (
            "setup.setup_page", "setup.system_check",
            "setup.test_database", "setup.run_installation",
            "setup.check_setup_status", "static",
        ):
            return None
        if request.path.startswith("/api/setup/") or request.path.startswith("/static/"):
            return None
        if request.endpoint in ("_internal_error", "not_found", "favicon"):
            return None
        try:
            if _is_initialized():
                return None
        except Exception:
            pass
        if request.path != "/setup":
            return redirect(url_for("setup.setup_page"))
        return None
