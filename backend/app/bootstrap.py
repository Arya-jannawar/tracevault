"""One-time local bootstrap CLI: creates the workspace and the operator user.

Generated credentials are printed once and written to backend/.local/
credentials.txt (gitignored). Run: `python -m app.bootstrap`
"""
from __future__ import annotations

import secrets
from pathlib import Path

from .config import get_settings
from .db import SessionLocal


def main() -> None:
    from .auth import ensure_admin
    from .fence import get_or_create_default_workspace

    settings = get_settings()
    if not settings.session_secret:
        print("[tracevault-bootstrap] WARNING: SESSION_SECRET is empty; set it "
              "in .env (see .env.example). Sessions will fail until it is set.")
    db = SessionLocal()
    try:
        ws = get_or_create_default_workspace(db, settings.workspace_name)
        user = ensure_admin(db)
        if user is not None:
            password = getattr(user, "_generated_password", None) or secrets.token_urlsafe(12)
            local_dir = Path(__file__).resolve().parent.parent / ".local"
            local_dir.mkdir(parents=True, exist_ok=True)
            cred_file = local_dir / "credentials.txt"
            cred_file.write_text(
                f"operator: {user.username}\npassword: {password}\n",
                encoding="utf-8",
            )
            print(f"[tracevault-bootstrap] workspace: {ws.name}")
            print(f"[tracevault-bootstrap] operator user created: {user.username}")
            print(f"[tracevault-bootstrap] password: {password}")
            print(f"[tracevault-bootstrap] (also written to {cred_file})")
        else:
            print(f"[tracevault-bootstrap] workspace: {ws.name}")
            print("[tracevault-bootstrap] operator user already exists; nothing "
                  "printed (set ADMIN_PASSWORD to control it explicitly).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
