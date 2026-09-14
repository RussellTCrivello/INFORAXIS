"""Shared pytest fixtures.

Provides:
* ``pg_db``      - a disposable PostgreSQL server + fresh application database
                   (per-session) with the full migration bootstrap applied.
* ``app``        - the real Flask application wired to the disposable database.
* ``client``     - Flask test client.
* ``admin_session`` - an authenticated admin client session.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Isolated application data root for tests (Phase 19).
os.environ.setdefault("APP_DATA_DIR", str(PROJECT_ROOT / ".test_runtime"))
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-not-for-production-0123456789")
os.environ.setdefault("FLASK_ENV", "development")


@pytest.fixture(scope="session")
def pg_server(tmp_path_factory):
    """Start a disposable PostgreSQL server (pgserver bundles the binaries)."""
    pgserver = pytest.importorskip("pgserver")
    data_dir = tmp_path_factory.mktemp("pgdata")
    server = pgserver.get_server(str(data_dir))
    yield server
    # Server cleanup handled by pgserver/tmp lifetime.


@pytest.fixture(scope="session")
def pg_db(pg_server, tmp_path_factory):
    """Create a fresh application database and run the migration bootstrap."""
    import urllib.parse

    db_name = f"file_analysis_test_{os.getpid()}"
    uri = pg_server.get_uri()
    # pgserver URI shape: postgresql://postgres:@/postgres?host=/path/to/socket
    parsed = urllib.parse.urlparse(uri)
    query = urllib.parse.parse_qs(parsed.query)
    host_dir = query.get("host", [parsed.path])[0]
    os.environ["DB_HOST"] = host_dir
    os.environ["DB_PORT"] = "5432"
    os.environ["DB_USER"] = "postgres"
    os.environ["DB_PASSWORD"] = ""
    os.environ["DB_NAME"] = db_name

    # Reset ALL cached settings/config singletons from any earlier import.
    # NOTE: settings_adapter caches an adapter under `_interface_manager`
    # which wraps the manager; it must be cleared too, otherwise a stale
    # manager built before DB_* env vars were set keeps serving localhost.
    import settings.settings_manager as _sm
    import settings.settings_adapter as _sa
    import settings.config as _sc
    for mod, attrs in (
        (_sm, ("_settings_manager",)),
        (_sa, ("_interface_manager",)),
        (_sc, ("_config",)),
    ):
        for attr in attrs:
            if hasattr(mod, attr):
                try:
                    setattr(mod, attr, None)
                except Exception:
                    pass

    from database.bootstrap import bootstrap_database

    cfg = {
        "host": host_dir,
        "port": 5432,
        "user": "postgres",
        "password": "",
        "database": db_name,
    }
    report = bootstrap_database(cfg)
    assert report["database_created"] is True
    assert len(report["applied_migrations"]) >= 4

    yield cfg


@pytest.fixture(scope="session")
def app(pg_db):
    """The real Flask application against the disposable database."""
    from apps.web.app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False  # API-level tests fetch tokens explicitly

    # The setup gate in Api/routes/setup.py redirects EVERY request to /setup
    # unless a filesystem marker exists and the critical tables are present.
    # pg_db bootstraps the tables, so only the marker is missing - which made
    # every authenticated fixture fail with 302 and blocked the API surface
    # from being tested at all. Mark it for the duration of the session and
    # remove it afterwards so no state leaks into the repository.
    from core.initialization import INIT_MARKER_FILE, mark_system_initialized

    marker_existed = INIT_MARKER_FILE.exists()
    if not marker_existed:
        mark_system_initialized()

    # API-01: per-route limits would trip the ~30 login fixtures; individual
    # rate-limit tests re-enable the limiter explicitly.
    from core.security.rate_limit import limiter as _limiter
    _limiter.enabled = False

    # Pre-register test-only routes (must happen before the first request).
    if "_test/sec08/boom" not in {r.rule for r in flask_app.url_map.iter_rules()}:
        def _boom():
            raise RuntimeError("SECRET postgresql://user:pass@host/db leaked")
        flask_app.add_url_rule("/_test/sec08/boom", view_func=_boom, endpoint="_sec08_boom")

    yield flask_app

    if not marker_existed and INIT_MARKER_FILE.exists():
        INIT_MARKER_FILE.unlink()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def admin_credentials(pg_db):
    """Ensure an initial admin exists; return (username, password)."""
    from core.security.service import get_auth_service

    auth = get_auth_service()
    username = "testadmin"
    password = "test-admin-password-123"
    if auth.get_user_by_username(username) is None:
        auth.create_user(username, password, role="admin")
    return username, password


@pytest.fixture()
def admin_client(app, client, admin_credentials):
    """A test client authenticated as administrator."""
    username, password = admin_credentials
    resp = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return client


@pytest.fixture()
def viewer_client(app, admin_credentials):
    """A test client authenticated as a read-only user.

    Uses its OWN client instance: sharing one client across roles would let
    the later login overwrite the session cookie.
    """
    from core.security.service import get_auth_service

    auth = get_auth_service()
    username = "testviewer"
    password = "test-viewer-password-123"
    if auth.get_user_by_username(username) is None:
        auth.create_user(username, password, role="viewer")
    c = app.test_client()
    resp = c.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return c


@pytest.fixture()
def client_factory(app, client, admin_credentials):
    """Factory for clients authenticated with an arbitrary role."""
    from core.security.service import get_auth_service

    def _make(role: str):
        auth = get_auth_service()
        username = f"testrole_{role}"
        password = f"test-{role}-password-123"
        if auth.get_user_by_username(username) is None:
            auth.create_user(username, password, role=role)
        c = app.test_client()
        resp = c.post("/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200
        return c

    return _make
