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
    configured_password = os.getenv("ADMIN_PASSWORD")
    password = configured_password or generate_temporary_password(18)
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
    # Only a generated one-time credential may be returned for logging. Never
    # return or log a password supplied through the environment.
    return None if configured_password else password

def _env_truthy(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def initialise_admin_from_environment(db: Session) -> dict:
    """Create the first admin or perform an explicit one-time environment reset.

    ADMIN_PASSWORD remains bootstrap-only during normal startups. An existing
    PostgreSQL administrator is changed only when
    VPROF_RESET_ADMIN_PASSWORD_ON_STARTUP=true. This prevents an ordinary
    restart from silently overwriting a password chosen in the portal.
    """
    preferred_username = normalize_username(os.getenv("ADMIN_USERNAME", "admin")) or "admin"
    admin = (
        db.query(User)
        .filter(User.username == preferred_username, User.role == "admin")
        .first()
    )
    if admin is None:
        admin = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()

    if admin is None:
        generated = create_bootstrap_admin(db)
        created = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
        return {
            "created": True,
            "reset": False,
            "username": created.username if created else preferred_username,
            "generated_password": generated,
        }

    if not _env_truthy("VPROF_RESET_ADMIN_PASSWORD_ON_STARTUP", False):
        return {
            "created": False,
            "reset": False,
            "username": admin.username,
            "generated_password": None,
        }

    password = os.getenv("ADMIN_PASSWORD") or ""
    validation_error = validate_password(password)
    if validation_error:
        raise RuntimeError(
            "VPROF_RESET_ADMIN_PASSWORD_ON_STARTUP is enabled, but ADMIN_PASSWORD "
            f"is missing or invalid. {validation_error}"
        )

    if preferred_username != admin.username:
        conflict = db.query(User).filter(User.username == preferred_username).first()
        if conflict is not None and conflict.id != admin.id:
            raise RuntimeError(
                "ADMIN_USERNAME cannot be applied because that username already belongs "
                "to another account."
            )
        admin.username = preferred_username

    admin.password_hash = hash_secret(password)
    admin.is_active = True
    admin.must_change_password = _env_truthy(
        "VPROF_ADMIN_REQUIRE_PASSWORD_CHANGE_AFTER_RESET", False
    )
    db.commit()
    return {
        "created": False,
        "reset": True,
        "username": admin.username,
        "generated_password": None,
    }

