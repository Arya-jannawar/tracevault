"""Local authentication: PBKDF2 password hashing + HMAC-signed session cookies.

Deliberately simple (no enterprise identity platform): viewer/operator roles,
HttpOnly SameSite cookies, server-side secret. CSRF: the API requires the
`X-TraceVault-Session: csrf` header on cookie-authenticated mutations, which a
cross-site form cannot set (custom header => preflight => blocked by CORS).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import base64

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .errors import AuthFailed
from .models import User, utcnow

_PBKDF2_ITERATIONS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ sessions
def _sign(payload_b64: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()


def make_session_token(username: str, role: str) -> str:
    settings = get_settings()
    payload = {
        "u": username,
        "r": role,
        "exp": int(time.time()) + settings.session_ttl_minutes * 60,
        "n": secrets.token_urlsafe(8),
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64, settings.session_secret)}"


def read_session_token(token: str) -> dict:
    settings = get_settings()
    if not settings.session_secret:
        raise AuthFailed("Session secret is not configured; set SESSION_SECRET.")
    try:
        payload_b64, sig = token.rsplit(".", 1)
    except ValueError as exc:
        raise AuthFailed("Malformed session token.") from exc
    if not hmac.compare_digest(_sign(payload_b64, settings.session_secret), sig):
        raise AuthFailed("Invalid session token.")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except Exception as exc:  # noqa: BLE001 - malformed token is an auth failure
        raise AuthFailed("Malformed session token.") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthFailed("Session expired.")
    return payload


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthFailed("Invalid username or password.")
    return user


def ensure_admin(db: Session) -> User | None:
    """Bootstrap operator user. Returns the created user (with plaintext password)
    only on first creation so the CLI can print generated credentials once."""
    settings = get_settings()
    existing = db.scalar(select(User).where(User.username == settings.admin_username))
    if existing is not None:
        return None
    password = settings.admin_password or secrets.token_urlsafe(12)
    user = User(
        username=settings.admin_username,
        password_hash=hash_password(password),
        role="operator",
        created_at=utcnow(),
    )
    db.add(user)
    db.commit()
    if settings.admin_password:
        return None  # operator chose the password; do not echo it back
    user._generated_password = password  # type: ignore[attr-defined]
    return user
