"""Local cookie sessions; no default credentials and no exchange secrets."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request

from .db import now
from .hosting import secure_cookies

COOKIE_NAME = "kedr_session"
SESSION_SECONDS = 7 * 24 * 60 * 60


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str | None) -> bool:
    try:
        if not stored:
            # Comparable expensive work for an unknown account.
            hashlib.scrypt(password.encode("utf-8"), salt=b"kedr-local-dummy", n=16384, r=8, p=1, dklen=32)
            return False
        algorithm, n, r, p, salt, expected = stored.split("$")
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (16384, 8, 1):
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()


def public_user(user) -> dict:
    return {key: (bool(user[key]) if key == "is_demo" else user[key]) for key in ("id", "email", "name", "level", "locale", "timezone", "theme", "is_demo")}


def new_session(db, user_id: str, response) -> str:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (token_digest(token), user_id, csrf, int(time.time()) + SESSION_SECONDS, now()))
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True, secure=secure_cookies(), samesite="strict", path="/")
    return csrf


def current_identity(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 128:
        raise HTTPException(401, "Authentication required")
    with request.app.state.db.connection() as conn:
        row = conn.execute("SELECT users.*, sessions.csrf_token, sessions.token_hash FROM users JOIN sessions ON sessions.user_id=users.id WHERE sessions.token_hash=? AND sessions.expires_at>?", (token_digest(token), int(time.time()))).fetchone()
    if not row:
        raise HTTPException(401, "Session expired or unavailable")
    return dict(row)


def current_user(request: Request) -> dict:
    return public_user(current_identity(request))


def require_csrf(request: Request) -> dict:
    identity = current_identity(request)
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not hmac.compare_digest(supplied, identity["csrf_token"]):
        raise HTTPException(403, "CSRF token missing or invalid")
    return public_user(identity)
