"""Minimal shared-token auth for the web UI (Phase 4).

A single ``WEB_TOKEN`` gates ``/ui`` and every mutating route. Login sets a signed
cookie (stdlib HMAC over a constant, keyed by the token) so the cookie can't be forged
without the token. This is a localhost seatbelt, not a fortress.

If ``WEB_TOKEN`` is unset the UI runs in explicit dev-open mode (every request passes) and
a warning is printed once -- so a fresh clone is usable, but production must set the token.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import HTTPException, Request, Response

from app.config import WEB_TOKEN, WEB_COOKIE_NAME, WEB_COOKIE_MAX_AGE

_COOKIE_VALUE_PREFIX = "v1:"
_warned = False


def _token() -> str | None:
    # Re-read env each call so tests can set it after import.
    return os.environ.get("WEB_TOKEN", WEB_TOKEN)


def dev_open() -> bool:
    global _warned
    if _token() is None:
        if not _warned:
            print("[web] WARNING: WEB_TOKEN not set -- UI is OPEN (dev mode). "
                  "Set WEB_TOKEN before exposing this beyond localhost.")
            _warned = True
        return True
    return False


def _sign(token: str) -> str:
    mac = hmac.new(token.encode(), b"authenticated", hashlib.sha256).hexdigest()
    return _COOKIE_VALUE_PREFIX + mac


def cookie_value() -> str:
    tok = _token() or "dev"
    return _sign(tok)


def _cookie_valid(value: str | None) -> bool:
    tok = _token()
    if tok is None:
        return True
    if not value:
        return False
    return hmac.compare_digest(value, _sign(tok))


def check_password(submitted: str) -> bool:
    tok = _token()
    if tok is None:
        return True
    return hmac.compare_digest(submitted or "", tok)


def is_authenticated(request: Request) -> bool:
    if dev_open():
        return True
    # Cookie (browser) or X-Web-Token header (API clients / tests).
    if _cookie_valid(request.cookies.get(WEB_COOKIE_NAME)):
        return True
    header = request.headers.get("x-web-token")
    return bool(header) and check_password(header)


def set_login_cookie(response: Response) -> None:
    response.set_cookie(
        WEB_COOKIE_NAME, cookie_value(), max_age=WEB_COOKIE_MAX_AGE,
        httponly=True, samesite="lax",
    )


def clear_login_cookie(response: Response) -> None:
    response.delete_cookie(WEB_COOKIE_NAME)


def require_token(request: Request) -> None:
    """FastAPI dependency for mutating API routes: 401 if not authenticated."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="authentication required")
