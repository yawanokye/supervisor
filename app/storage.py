from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)

CONFIGURED_ROOT = Path(
    os.getenv("REVIEW_STORAGE_DIR", "/tmp/projectready-supervisor/reviews")
).expanduser()

FALLBACK_ROOT = Path(
    os.getenv("REVIEW_STORAGE_FALLBACK_DIR", "/tmp/projectready-supervisor/reviews")
).expanduser()

ROOT = CONFIGURED_ROOT
_STORAGE_READY = False


def _ensure_writable(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".storage-write-test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)


def ensure_storage() -> Path:
    """Resolve a writable review-storage directory.

    The configured persistent path is preferred. If it is unavailable or
    permission is denied, the service falls back to temporary storage rather
    than failing during application startup.
    """
    global ROOT, _STORAGE_READY

    if _STORAGE_READY:
        return ROOT

    candidates = []
    for candidate in (CONFIGURED_ROOT, FALLBACK_ROOT):
        if candidate not in candidates:
            candidates.append(candidate)

    failures = []
    for candidate in candidates:
        try:
            _ensure_writable(candidate)
            ROOT = candidate
            _STORAGE_READY = True

            if candidate == CONFIGURED_ROOT:
                logger.info("Review storage ready at %s", candidate)
            else:
                logger.warning(
                    "Configured review storage %s is unavailable. "
                    "Using temporary fallback storage %s. Files stored here "
                    "will not survive a Render restart or redeploy.",
                    CONFIGURED_ROOT,
                    candidate,
                )
            return ROOT
        except OSError as exc:
            failures.append(f"{candidate}: {exc}")
            logger.warning("Review storage path unavailable: %s (%s)", candidate, exc)

    raise RuntimeError(
        "No writable review-storage directory is available. "
        + " | ".join(failures)
    )


def storage_root() -> Path:
    return ensure_storage()


def _path(review_id: str, suffix: str) -> Path:
    root = ensure_storage()
    safe = "".join(ch for ch in review_id if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        raise ValueError("Invalid review identifier.")
    return root / f"{safe}{suffix}"


def save_review_json(review_id: str, review: Dict[str, Any]) -> None:
    target = _path(review_id, ".json")
    temp = target.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(review, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temp.replace(target)


def load_review_json(review_id: str) -> Optional[Dict[str, Any]]:
    target = _path(review_id, ".json")
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Could not load stored review %s", review_id)
        return None


def save_annotated(review_id: str, data: bytes) -> None:
    target = _path(review_id, "-annotated.docx")
    temp = target.with_suffix(".docx.tmp")
    temp.write_bytes(data)
    temp.replace(target)


def load_annotated(review_id: str) -> Optional[bytes]:
    target = _path(review_id, "-annotated.docx")
    return target.read_bytes() if target.exists() else None


def storage_status() -> Dict[str, Any]:
    root = ensure_storage()
    path_text = str(root)
    return {
        "path": path_text,
        "configured_path": str(CONFIGURED_ROOT),
        "using_fallback": root == FALLBACK_ROOT and CONFIGURED_ROOT != FALLBACK_ROOT,
        "persistent_hint": not path_text.startswith("/tmp/"),
    }
