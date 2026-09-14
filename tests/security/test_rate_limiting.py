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
