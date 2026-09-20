"""API-01 regression: login brute force is rate limited (429)."""
import pytest


@pytest.fixture()
def rate_limited_app(app):
    from core.security.rate_limit import limiter

    prev_enabled = limiter.enabled
    limiter.enabled = True
    try:
        limiter.reset()
    except Exception:
        pass
    try:
        yield app
    finally:
        limiter.enabled = prev_enabled
        try:
            limiter.reset()
        except Exception:
            pass


@pytest.mark.usefixtures("rate_limited_app")
def test_login_brute_force_rate_limited(client, admin_credentials):
    username, password = admin_credentials
    codes = []
    for _ in range(12):
        resp = client.post(
            "/auth/login",
            json={"username": "nobody", "password": "wrong-password"},
        )
        codes.append(resp.status_code)
    assert 429 in codes, f"expected a 429 among {codes}"
    # Before the limit tripped, invalid credentials must have been 401s.
    assert codes[0] == 401


@pytest.mark.usefixtures("rate_limited_app")
def test_job_progress_polling_is_not_throttled_during_a_run(admin_client):
    """The panel that explains a failure must survive the run it reports on.

    The Jobs page polls the job's status and error endpoints while a run is in
    progress. Under the default 60/minute limit every poll of the error
    endpoint answered 429 for the whole duration of a production ingest (the
    log shows one 429 per poll), so the operator could not see *why* files
    failed - including the archive that reported no decoder.

    These read-only endpoints therefore carry their own, higher limit. This
    test polls them past the default budget and asserts none is refused.
    """
    for _ in range(75):
        assert admin_client.get("/api/jobs/NOPE/errors").status_code == 404
        assert admin_client.get("/api/jobs/NOPE").status_code == 404


@pytest.mark.usefixtures("rate_limited_app")
def test_the_default_limit_still_applies_to_other_endpoints(admin_client):
    """Polling endpoints are the exception, not the rule."""
    codes = [admin_client.get("/api/jobs").status_code for _ in range(75)]
    assert 429 in codes, f"expected the default limit to still apply: {set(codes)}"
