"""Shared FastAPI dependencies: DB session, current user, roles, workspace."""
from __future__ import annotations

from fastapi import Depends, Request

from .auth import read_session_token
from .config import get_settings
from .db import get_db
from .errors import AuthFailed, Forbidden
from .fence import get_or_create_default_workspace
from .models import User
from .schemas import UserOut  # noqa: F401  (re-export convenience)

SESSION_COOKIE = "tv_session"
CSRF_HEADER = "x-tracevault-session"


def get_current_user(request: Request, db=Depends(get_db)) -> User:
    """Authenticated user (viewer or operator) from the signed session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthFailed("Sign in required.")
    payload = read_session_token(token)
    user = db.query(User).filter_by(username=payload.get("u")).one_or_none()
    if user is None:
        raise AuthFailed("Unknown user.")
    return user


def require_operator(user: User = Depends(get_current_user)) -> User:
    if user.role != "operator":
        raise Forbidden("Operator role required for this action.")
    return user


def get_workspace(db=Depends(get_db)):
    """Single default workspace for the local prototype (documented choice)."""
    settings = get_settings()
    return get_or_create_default_workspace(db, settings.workspace_name)
