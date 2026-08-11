"""Optional S3-compatible durable storage for review payloads and artifacts.

PostgreSQL remains the compatibility fallback. When an S3 bucket is configured,
large source files, checkpoints and generated DOCX files bypass database BLOB
storage while job state and checkpoint metadata remain in PostgreSQL.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Optional


logger = logging.getLogger(__name__)


def _clean_key(value: str) -> str:
    parts = []
    for part in str(value or "").replace("\\", "/").split("/"):
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", part).strip("-.")
        if cleaned:
            parts.append(cleaned[:180])
    if not parts:
        raise ValueError("A durable artifact key is required.")
    return "/".join(parts)


def configured() -> bool:
    backend = os.getenv("VPROF_ARTIFACT_STORAGE_BACKEND", "auto").strip().lower()
    if backend == "db":
        return False
    return bool(os.getenv("S3_BUCKET", "").strip()) and backend in {"auto", "s3"}


def backend_name() -> str:
    return "s3" if configured() else "database"


@lru_cache(maxsize=1)
def _client():
    if not configured():
        return None
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "S3 artifact storage is configured but boto3 is not installed."
        ) from exc

    kwargs = {}
    endpoint = os.getenv("S3_ENDPOINT_URL", "").strip()
    region = os.getenv("S3_REGION", "").strip()
    access_key = os.getenv("S3_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if region:
        kwargs["region_name"] = region
    if access_key:
        kwargs["aws_access_key_id"] = access_key
    if secret_key:
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


def _object_key(namespace: str, artifact_key: str) -> str:
    prefix = _clean_key(os.getenv("S3_PREFIX", "vprofessor"))
    return f"{prefix}/{_clean_key(namespace)}/{_clean_key(artifact_key)}"


def put(
    namespace: str,
    artifact_key: str,
    data: bytes,
    *,
    content_type: str = "application/octet-stream",
) -> bool:
    client = _client()
    if client is None:
        return False
    kwargs = {
        "Bucket": os.environ["S3_BUCKET"].strip(),
        "Key": _object_key(namespace, artifact_key),
        "Body": bytes(data or b""),
        "ContentType": content_type or "application/octet-stream",
    }
    encryption = os.getenv("S3_SERVER_SIDE_ENCRYPTION", "AES256").strip()
    if encryption:
        kwargs["ServerSideEncryption"] = encryption
    client.put_object(**kwargs)
    return True


def get(namespace: str, artifact_key: str) -> Optional[bytes]:
    client = _client()
    if client is None:
        return None
    try:
        response = client.get_object(
            Bucket=os.environ["S3_BUCKET"].strip(),
            Key=_object_key(namespace, artifact_key),
        )
    except Exception as exc:
        error = getattr(exc, "response", {}).get("Error", {})
        if str(error.get("Code") or "") in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise
    body = response.get("Body")
    return bytes(body.read()) if body is not None else None

