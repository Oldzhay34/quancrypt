"""Quancrypt overrides for Superset 6.1.0 (P7.5, D-344i). Imported by the image's superset/config.py from PYTHONPATH.

Every setting below was read from the image's own superset/config.py (apache/superset:6.1.0):
- SECRET_KEY: config.py falls back to a published default when SUPERSET_SECRET_KEY is empty; here start-up fails instead.
- The metadata database stays the image's default (SQLite in DATA_DIR = SUPERSET_HOME, the `superset-home` volume).
- Locality (NFR-03): the navbar always renders a Scarf analytics pixel (an <img> to apachesuperset.gateway.scarf.sh,
  rendered without any condition in the frontend bundle) and the default CSP allows it, Mapbox, OpenStreetMap, Carto and
  font CDNs. The CSP below allows the server's own origin only, so the browser loads none of them. Map charts are not used.
- Feature flags that would send mail, take screenshots or embed (ALERT_REPORTS, THUMBNAILS, EMBEDDED_SUPERSET) are off
  by default in 6.1.0 and stay off; SMTP is never configured.
"""

from __future__ import annotations

import os

_MIN_SECRET_CHARS = 32


def _secret_key() -> str:
    value = os.environ.get("SUPERSET_SECRET_KEY", "")
    if len(value) < _MIN_SECRET_CHARS or "CHANGE_ME" in value:
        # The value itself is never printed.
        raise RuntimeError(
            f"SUPERSET_SECRET_KEY must be set in .env: at least {_MIN_SECRET_CHARS} characters, no CHANGE_ME placeholder"
        )
    return value


SECRET_KEY = _secret_key()

# Local-only content security policy: the server's own origin, inline styles (the UI needs them) and data/blob images.
TALISMAN_ENABLED = True
TALISMAN_CONFIG = {
    "content_security_policy": {
        "base-uri": ["'self'"],
        "default-src": ["'self'"],
        "img-src": ["'self'", "blob:", "data:"],
        "worker-src": ["'self'", "blob:"],
        "connect-src": ["'self'"],
        "object-src": "'none'",
        "style-src": ["'self'", "'unsafe-inline'"],
        "font-src": ["'self'"],
        "script-src": ["'self'", "'strict-dynamic'"],
        "frame-ancestors": ["'self'"],
    },
    "content_security_policy_nonce_in": ["script-src"],
    "force_https": False,
    "session_cookie_secure": False,
}
# FLASK_DEBUG switches Superset to TALISMAN_DEV_CONFIG, whose image default allows Scarf and CDNs: it is the same here.
TALISMAN_DEV_CONFIG = TALISMAN_CONFIG
CONTENT_SECURITY_POLICY_WARNING = False

# No external fonts, map tiles or tokens.
THEME_FONT_URL_ALLOWED_DOMAINS: list[str] = []
MAPBOX_API_KEY = ""

# Only the warehouse connection made by `make superset-import`; SQLite and other unsafe URIs stay refused (6.1.0 default).
PREVENT_UNSAFE_DB_CONNECTIONS = True
