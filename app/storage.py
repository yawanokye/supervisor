from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(os.getenv("REVIEW_STORAGE_DIR", "/tmp/projectready-supervisor/reviews"))


def ensure_storage() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)


def _path(review_id: str, suffix: str) -> Path:
    safe = "".join(ch for ch in review_id if ch.isalnum() or ch in {"-", "_"})
    return ROOT / f"{safe}{suffix}"


def save_review_json(review_id: str, review: Dict[str, Any]) -> None:
    ensure_storage()
    target = _path(review_id, ".json")
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(review, ensure_ascii=False, default=str), encoding="utf-8")
    temp.replace(target)


def load_review_json(review_id: str) -> Optional[Dict[str, Any]]:
    target = _path(review_id, ".json")
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_annotated(review_id: str, data: bytes) -> None:
    ensure_storage()
    target = _path(review_id, "-annotated.docx")
    temp = target.with_suffix(".docx.tmp")
    temp.write_bytes(data)
    temp.replace(target)


def load_annotated(review_id: str) -> Optional[bytes]:
    target = _path(review_id, "-annotated.docx")
    return target.read_bytes() if target.exists() else None
