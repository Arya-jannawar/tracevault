"""Auth routes: login/logout/me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..auth import authenticate, make_session_token
from ..db import get_db
from ..deps import SESSION_COOKIE, get_current_user
from ..schemas import LoginRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response,
          db: Session = Depends(get_db)):
    user = authenticate(db, body.username, body.password)
    token = make_session_token(user.username, user.role)
    secure = request.url.hostname not in ("127.0.0.1", "localhost", "testserver")
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax", secure=secure,
        max_age=720 * 60, path="/",
    )
    return UserOut(username=user.username, role=user.role)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)):
    return UserOut(username=user.username, role=user.role)
