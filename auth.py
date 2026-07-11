from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import string
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .database import User

PBKDF2_ITERATIONS = 310_000


def normalize_username(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", ".", (value or "").strip().lower())
    value = re.sub(r"\.+", ".", value).strip("._-")
    return value[:80]


def suggest_username(full_name: str) -> str:
    words = [re.sub(r"[^a-zA-Z0-9]", "", word).lower() for word in (full_name or "").split()]
    words = [word for word in words if word]
    if not words:
        return "lecturer"
    if len(words) == 1:
        return words[0]
    return f"{words[0]}.{words[-1]}"


def unique_username(db: Session, preferred: str) -> str:
    base = normalize_username(preferred) or "lecturer"
    candidate = base
    counter = 2
    while db.query(User.id).filter(User.username == candidate).first():
        suffix = str(counter)
        candidate = f"{base[: max(1, 80 - len(suffix))]}{suffix}"
        counter += 1
    return candidate


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_secret(secret: str, encoded: Optional[str]) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def validate_password(value: str) -> Optional[str]:
    if len(value or "") < 10:
        return "Use at least 10 characters."
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        return "Include both letters and numbers."
    return None


def generate_temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        if not validate_password(value):
            return value


def generate_recovery_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def authenticate(db: Session, username: str, password: str, required_role: Optional[str] = None) -> Optional[User]:
    user = db.query(User).filter(User.username == normalize_username(username)).first()
    if not user or not user.is_active or not verify_secret(password, user.password_hash):
        return None
    if required_role and user.role != required_role:
        return None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user


def create_bootstrap_admin(db: Session) -> Optional[str]:
    if db.query(User.id).filter(User.role == "admin").first():
        return None
    username = normalize_username(os.getenv("ADMIN_USERNAME", "admin")) or "admin"
    password = os.getenv("ADMIN_PASSWORD") or generate_temporary_password(18)
    admin = User(
        username=username,
        password_hash=hash_secret(password),
        role="admin",
        full_name=os.getenv("ADMIN_NAME", "System Administrator"),
        email=os.getenv("ADMIN_EMAIL") or None,
        department="Administration",
        is_active=True,
        must_change_password=True,
    )
    db.add(admin)
    db.commit()
    return password
