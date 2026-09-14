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
