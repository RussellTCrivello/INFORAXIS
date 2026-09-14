"""API-01: Shared Flask-Limiter instance.

Created here (not in the app factory) so blueprints can decorate routes with
``@limiter.limit`` at import time without circular imports; the app factory
calls ``limiter.init_app(app)``. Default limits apply to every route; stricter
per-route limits are declared on login, search, import/export and admin
mutations. In multi-process deployments set RATELIMIT_STORAGE_URI (e.g.
redis://...) so counters are shared.

Rate limits are read from environment at init_app time (not import time)
so that .env values are always used.
"""
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _get_rate_limits():
    """Read rate limits from environment at call time, not import time."""
    per_minute = os.environ.get("RATE_LIMIT_PER_MINUTE", "60")
    per_hour = os.environ.get("RATE_LIMIT_PER_HOUR", "600")
    return [f"{per_hour} per hour", f"{per_minute} per minute"]


limiter = Limiter(
    get_remote_address,
    default_limits=_get_rate_limits(),  # evaluated at import (before .env)
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)


def refresh_limits():
    """Re-read rate limits from environment.  Called after .env is loaded."""
    try:
        limiter._default_limits = _get_rate_limits()
    except Exception:
        pass
