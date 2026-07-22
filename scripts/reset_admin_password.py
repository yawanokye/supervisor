"""Reset the stored administrator credential from ADMIN_USERNAME/ADMIN_PASSWORD.

Run only from a trusted Render Shell. The secret is read from the environment and
is never printed. This command performs one explicit reset and does not require
the startup reset flag.
"""
from __future__ import annotations

import os

from app.auth import hash_secret, normalize_username, validate_password
from app.database import SessionLocal, User, init_db


def main() -> int:
    init_db()
    username = normalize_username(os.getenv("ADMIN_USERNAME", "admin")) or "admin"
    password = os.getenv("ADMIN_PASSWORD") or ""
    error = validate_password(password)
    if error:
        raise SystemExit(f"ADMIN_PASSWORD is missing or invalid. {error}")

    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == username, User.role == "admin").first()
        if admin is None:
            admin = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
        if admin is None:
            raise SystemExit("No administrator exists. Restart the web service to bootstrap one.")

        conflict = db.query(User).filter(User.username == username, User.id != admin.id).first()
        if conflict is not None:
            raise SystemExit("ADMIN_USERNAME already belongs to another account.")

        admin.username = username
        admin.password_hash = hash_secret(password)
        admin.is_active = True
        admin.must_change_password = False
        db.commit()
        print(f"Administrator password reset successfully for username: {admin.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
