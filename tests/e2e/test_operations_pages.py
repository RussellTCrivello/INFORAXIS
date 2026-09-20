"""Frontend pages render for authenticated users (Operations UI)."""


def test_operations_pages_render(app, admin_client):
    for url, marker in (
        ("/operations/input", "Start Analysis"),
        ("/operations/import", "Import Center"),
        ("/operations/jobs", "Jobs"),
    ):
        resp = admin_client.get(url)
        assert resp.status_code == 200, url
        assert marker.encode() in resp.data, url

    # job detail page renders for any id (loads data via API)
    resp = admin_client.get("/operations/jobs/XYZ123")
    assert resp.status_code == 200


def test_dashboard_has_operations_widget(app, admin_client):
    resp = admin_client.get("/")
    assert resp.status_code == 200
    assert b"operations" in resp.data.lower() or b"Operations" in resp.data


def test_input_options_info_endpoint(app, admin_client, monkeypatch):
    """Regression: the Input page fetches /api/input/options-info on load.

    The route was missing in production (404 on page open). It must return
    real capability facts the page renders.
    """
    monkeypatch.delenv("INGESTION_ROOTS", raising=False)
    resp = admin_client.get("/api/input/options-info")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    assert body["ingestion_roots_configured"] is False
    assert body["server_path_import_available"] is False
    assert body["upload_available"] is True

    monkeypatch.setenv("INGESTION_ROOTS", "/tmp/anything")
    body = admin_client.get("/api/input/options-info").get_json()
    assert body["ingestion_roots_configured"] is True
    assert body["server_path_import_available"] is True


def test_upload_url_redirects_to_the_single_ingestion_page(app, admin_client):
    """One interface: the old /upload URL still resolves, to the same page.

    The interface toggle that used to gate /upload still applies - the alias
    either lands on the ingestion page or (when the interface is switched off)
    on the dashboard, exactly as before the merge.
    """
    from settings import get_interface_manager

    response = admin_client.get("/upload", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["Location"]

    followed = admin_client.get("/upload", follow_redirects=True)
    assert followed.status_code == 200

    if get_interface_manager().is_interface_enabled("upload_files"):
        assert location.endswith("/operations/input")
        assert b"Start Analysis" in followed.data
    else:
        # Switched off: the gate sends the alias to the dashboard, as before.
        assert "/upload" not in location
        assert b"Start Analysis" not in followed.data


def test_the_ingestion_page_ships_the_single_interface(app, admin_client):
    """The page loads its own controller, stylesheet and endpoint map."""
    html = admin_client.get("/operations/input").get_data(as_text=True)
    assert "js/pages/ingestion-studio-page.js" in html
    assert "css/ingestion.css" in html
    assert "ingestionPageData" in html
    # Both input modes are named on the page, not hidden behind tabs.
    assert "This computer" in html
    assert "Server path" in html
    # The pipeline the engine runs is stated, not offered as dead checkboxes.
    assert "What this pipeline always does" in html


def test_the_removed_interface_is_gone_and_the_task_api_is_not(app, admin_client):
    """The duplicated page went; the task-manager API it shared a prefix with did not.

    ``/upload/process-path`` was the deleted page's own ingestion entry point
    (a second, differently-shaped pipeline). ``/upload/active-tasks`` belongs to
    Api/task_manager.py, whose tasks the import flows create and the dashboard
    polls - removing it would break live progress, so it must keep answering.
    """
    assert admin_client.post("/upload/process-path", json={}).status_code == 404

    active = admin_client.get("/upload/active-tasks")
    assert active.status_code == 200
    assert active.get_json()["success"] is True
