from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .ai_schemas import AIUsageRecord
from .database import ReviewArtifact, ReviewCheckpoint, ReviewRecord, SessionLocal
from .ai_providers import ProviderResult
from .storage import storage_root

logger = logging.getLogger(__name__)



def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _db_artifact_storage_enabled() -> bool:
    return _env_bool("VPROF_DB_ARTIFACT_STORAGE", False)


def _save_db_artifact(
    job_id: str,
    artifact_key: str,
    data: bytes,
    *,
    filename: str = "",
    content_type: str = "application/octet-stream",
) -> None:
    if not _db_artifact_storage_enabled():
        return
    value = bytes(data or b"")
    with SessionLocal() as db:
        row = (
            db.query(ReviewArtifact)
            .filter(
                ReviewArtifact.job_id == job_id,
                ReviewArtifact.artifact_key == artifact_key,
            )
            .first()
        )
        if not row:
            row = ReviewArtifact(job_id=job_id, artifact_key=artifact_key)
            db.add(row)
        row.filename = filename or row.filename or artifact_key
        row.content_type = content_type
        row.sha256 = bytes_hash(value)
        row.size_bytes = len(value)
        row.data = value
        row.updated_at = utcnow()
        db.commit()


def _load_db_artifact(job_id: str, artifact_key: str) -> Optional[bytes]:
    if not _db_artifact_storage_enabled():
        return None
    with SessionLocal() as db:
        row = (
            db.query(ReviewArtifact)
            .filter(
                ReviewArtifact.job_id == job_id,
                ReviewArtifact.artifact_key == artifact_key,
            )
            .first()
        )
        return bytes(row.data) if row and row.data is not None else None


def _load_json_from_db(job_id: str, artifact_key: str) -> Optional[Dict[str, Any]]:
    data = _load_db_artifact(job_id, artifact_key)
    if not data:
        return None
    try:
        value = json.loads(data.decode("utf-8"))
    except Exception:
        logger.exception("Could not load database artifact %s for job %s", artifact_key, job_id)
        return None
    return value if isinstance(value, dict) else None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-.")
    if not cleaned:
        raise ValueError("A safe storage identifier is required.")
    return cleaned[:180]


def job_directory(job_id: str) -> Path:
    root = storage_root() / "jobs" / _safe(job_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temp.replace(path)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Could not load checkpoint file %s", path)
        return None
    return value if isinstance(value, dict) else None


def _write_blob(path: Path, value: bytes) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(value)
    temp.replace(path)
    return {
        "path": str(path.relative_to(path.parents[1])),
        "size": len(value),
        "sha256": bytes_hash(value),
    }


def save_job_payload(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a review submission so a worker can resume it after interruption."""
    root = job_directory(job_id)
    files_root = root / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    metadata = {
        key: value
        for key, value in payload.items()
        if key not in {
            "data",
            "context_documents",
            "supervisor_comment_documents",
            "original_document",
        }
    }

    source_data = bytes(payload.get("data") or b"")
    if not source_data:
        raise ValueError("The review payload has no source document data.")
    source_info = _write_blob(files_root / "source.bin", source_data)
    source_info["filename"] = str(payload.get("filename") or "uploaded-document")

    def persist_documents(
        documents: Iterable[Dict[str, Any]],
        prefix: str,
    ) -> list[Dict[str, Any]]:
        output: list[Dict[str, Any]] = []
        for index, document in enumerate(documents or [], start=1):
            value = bytes(document.get("data") or b"")
            if not value:
                continue
            info = _write_blob(
                files_root / f"{prefix}-{index}.bin",
                value,
            )
            info["filename"] = str(
                document.get("filename") or f"{prefix}-{index}"
            )
            output.append(info)
        return output

    context_files = persist_documents(
        payload.get("context_documents") or [],
        "context",
    )
    comment_files = persist_documents(
        payload.get("supervisor_comment_documents") or [],
        "comments",
    )

    original_info = None
    original = payload.get("original_document")
    if isinstance(original, dict) and original.get("data"):
        original_info = _write_blob(
            files_root / "original.bin",
            bytes(original["data"]),
        )
        original_info["filename"] = str(
            original.get("filename") or "original-document"
        )

    manifest = {
        "version": 1,
        "job_id": job_id,
        "saved_at": utcnow().isoformat(),
        "document_hash": source_info["sha256"],
        "metadata": metadata,
        "source": source_info,
        "context_documents": context_files,
        "supervisor_comment_documents": comment_files,
        "original_document": original_info,
    }
    manifest["payload_hash"] = stable_hash({
        "version": manifest["version"],
        "document_hash": manifest["document_hash"],
        "metadata": metadata,
        "context_hashes": [item["sha256"] for item in context_files],
        "comment_hashes": [item["sha256"] for item in comment_files],
        "original_hash": (original_info or {}).get("sha256"),
    })
    _atomic_json(root / "payload.json", manifest)
    if _db_artifact_storage_enabled():
        _save_db_artifact(
            job_id,
            "payload.json",
            json.dumps(manifest, ensure_ascii=False, default=str).encode("utf-8"),
            filename="payload.json",
            content_type="application/json",
        )
        _save_db_artifact(
            job_id,
            source_info["path"],
            source_data,
            filename=source_info.get("filename") or "source.bin",
        )
        for index, info in enumerate(context_files, start=1):
            original = (payload.get("context_documents") or [])[index - 1]
            _save_db_artifact(
                job_id,
                info["path"],
                bytes(original.get("data") or b""),
                filename=info.get("filename") or f"context-{index}",
            )
        for index, info in enumerate(comment_files, start=1):
            original = (payload.get("supervisor_comment_documents") or [])[index - 1]
            _save_db_artifact(
                job_id,
                info["path"],
                bytes(original.get("data") or b""),
                filename=info.get("filename") or f"comments-{index}",
            )
        if original_info and isinstance(original, dict):
            _save_db_artifact(
                job_id,
                original_info["path"],
                bytes(original.get("data") or b""),
                filename=original_info.get("filename") or "original-document",
            )
    return manifest


def _read_manifest_blob(root: Path, info: Dict[str, Any]) -> bytes:
    path_value = str(info.get("path") or "")
    if not path_value:
        raise FileNotFoundError("Stored review file path is missing.")
    path = root / path_value
    if path.exists():
        data = path.read_bytes()
    else:
        data = _load_db_artifact(root.name, path_value)
        if data is None:
            raise FileNotFoundError(f"Stored review file is unavailable: {path_value}")
    expected = str(info.get("sha256") or "")
    if expected and bytes_hash(data) != expected:
        raise ValueError(f"Stored review file failed integrity checking: {path.name}")
    return data


def load_job_payload(job_id: str) -> Optional[Dict[str, Any]]:
    root = job_directory(job_id)
    manifest = _load_json(root / "payload.json") or _load_json_from_db(job_id, "payload.json")
    if not manifest:
        return None

    payload = dict(manifest.get("metadata") or {})
    source = manifest.get("source") or {}
    payload["filename"] = source.get("filename") or payload.get("filename")
    payload["data"] = _read_manifest_blob(root, source)

    def restore_documents(values: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
        output = []
        for info in values or []:
            output.append({
                "filename": info.get("filename") or "stored-document",
                "data": _read_manifest_blob(root, info),
            })
        return output

    payload["context_documents"] = restore_documents(
        manifest.get("context_documents") or []
    )
    payload["supervisor_comment_documents"] = restore_documents(
        manifest.get("supervisor_comment_documents") or []
    )

    original = manifest.get("original_document")
    payload["original_document"] = (
        {
            "filename": original.get("filename") or "original-document",
            "data": _read_manifest_blob(root, original),
        }
        if isinstance(original, dict)
        else None
    )
    payload["document_hash"] = manifest.get("document_hash")
    payload["payload_hash"] = manifest.get("payload_hash")
    return payload


def payload_available(job_id: str) -> bool:
    try:
        root = job_directory(job_id)
        manifest = _load_json(root / "payload.json") or _load_json_from_db(job_id, "payload.json")
        if not manifest:
            return False
        source = manifest.get("source") or {}
        key = str(source.get("path") or "")
        if not key:
            return False
        return bool((root / key).exists() or _load_db_artifact(job_id, key) is not None)
    except Exception:
        return False


class CheckpointManager:
    """Durable JSON checkpoint storage backed by storage and database metadata."""

    def __init__(self, job_id: str, document_hash: str = "") -> None:
        self.job_id = job_id
        self.document_hash = document_hash
        self.root = job_directory(job_id) / "checkpoints"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, stage_key: str) -> Path:
        return self.root / f"{_safe(stage_key)}.json"

    def load(
        self,
        stage_key: str,
        *,
        expected_input_hash: str = "",
    ) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            record = (
                db.query(ReviewCheckpoint)
                .filter(
                    ReviewCheckpoint.job_id == self.job_id,
                    ReviewCheckpoint.stage_key == stage_key,
                )
                .first()
            )
            if record and record.status != "completed":
                return None
            if (
                record
                and expected_input_hash
                and record.input_hash
                and record.input_hash != expected_input_hash
            ):
                return None
            path = Path(record.result_path) if record and record.result_path else self._path(stage_key)

        value = _load_json(path)
        if not value:
            value = _load_json_from_db(self.job_id, f"checkpoints/{_safe(stage_key)}.json")
        if not value:
            return None
        stored_hash = str(value.get("input_hash") or "")
        if expected_input_hash and stored_hash and stored_hash != expected_input_hash:
            return None
        data = value.get("data")
        return data if isinstance(data, dict) else None

    def mark_running(
        self,
        stage_key: str,
        *,
        input_hash: str = "",
        progress: int = 0,
        message: str = "",
    ) -> None:
        now = utcnow()
        with SessionLocal() as db:
            record = (
                db.query(ReviewCheckpoint)
                .filter(
                    ReviewCheckpoint.job_id == self.job_id,
                    ReviewCheckpoint.stage_key == stage_key,
                )
                .first()
            )
            if not record:
                record = ReviewCheckpoint(
                    job_id=self.job_id,
                    stage_key=stage_key,
                    created_at=now,
                )
                db.add(record)
            record.status = "running"
            record.input_hash = input_hash or record.input_hash
            record.progress = max(int(record.progress or 0), int(progress or 0))
            record.message = message or record.message
            record.attempt_count = int(record.attempt_count or 0) + 1
            record.updated_at = now
            record.error = None

            job = (
                db.query(ReviewRecord)
                .filter(ReviewRecord.job_id == self.job_id)
                .first()
            )
            if job:
                job.current_stage = stage_key
                job.last_heartbeat_at = now
            db.commit()

    def save(
        self,
        stage_key: str,
        data: Dict[str, Any],
        *,
        input_hash: str = "",
        progress: int = 0,
        message: str = "",
    ) -> None:
        now = utcnow()
        path = self._path(stage_key)
        checkpoint_value = {
            "version": 1,
            "job_id": self.job_id,
            "stage_key": stage_key,
            "input_hash": input_hash,
            "saved_at": now.isoformat(),
            "data": data,
        }
        _atomic_json(path, checkpoint_value)
        _save_db_artifact(
            self.job_id,
            f"checkpoints/{_safe(stage_key)}.json",
            json.dumps(checkpoint_value, ensure_ascii=False, default=str).encode("utf-8"),
            filename=f"{_safe(stage_key)}.json",
            content_type="application/json",
        )

        with SessionLocal() as db:
            record = (
                db.query(ReviewCheckpoint)
                .filter(
                    ReviewCheckpoint.job_id == self.job_id,
                    ReviewCheckpoint.stage_key == stage_key,
                )
                .first()
            )
            if not record:
                record = ReviewCheckpoint(
                    job_id=self.job_id,
                    stage_key=stage_key,
                    created_at=now,
                    attempt_count=1,
                )
                db.add(record)
            record.status = "completed"
            record.input_hash = input_hash or record.input_hash
            record.progress = max(int(record.progress or 0), int(progress or 0))
            record.message = message or record.message
            record.result_path = str(path)
            record.updated_at = now
            record.completed_at = now
            record.error = None

            db.flush()
            job = (
                db.query(ReviewRecord)
                .filter(ReviewRecord.job_id == self.job_id)
                .first()
            )
            if job:
                job.current_stage = stage_key
                job.last_heartbeat_at = now
                job.checkpoint_count = int(
                    db.query(ReviewCheckpoint)
                    .filter(
                        ReviewCheckpoint.job_id == self.job_id,
                        ReviewCheckpoint.status == "completed",
                    )
                    .count()
                )
            db.commit()

    def mark_failed(self, stage_key: str, error: str) -> None:
        now = utcnow()
        with SessionLocal() as db:
            record = (
                db.query(ReviewCheckpoint)
                .filter(
                    ReviewCheckpoint.job_id == self.job_id,
                    ReviewCheckpoint.stage_key == stage_key,
                )
                .first()
            )
            if not record:
                record = ReviewCheckpoint(
                    job_id=self.job_id,
                    stage_key=stage_key,
                    created_at=now,
                )
                db.add(record)
            record.status = "retryable"
            record.error = str(error or "")[:4000]
            record.updated_at = now
            db.commit()

    def completed_count(self) -> int:
        with SessionLocal() as db:
            return int(
                db.query(ReviewCheckpoint)
                .filter(
                    ReviewCheckpoint.job_id == self.job_id,
                    ReviewCheckpoint.status == "completed",
                )
                .count()
            )

    def completed_stage_keys(self) -> list[str]:
        with SessionLocal() as db:
            rows = (
                db.query(ReviewCheckpoint.stage_key)
                .filter(
                    ReviewCheckpoint.job_id == self.job_id,
                    ReviewCheckpoint.status == "completed",
                )
                .order_by(ReviewCheckpoint.id.asc())
                .all()
            )
        return [row[0] for row in rows]

    def load_provider_result(
        self,
        stage_key: str,
        *,
        expected_input_hash: str,
    ) -> Optional[ProviderResult]:
        value = self.load(
            stage_key,
            expected_input_hash=expected_input_hash,
        )
        if not value:
            return None
        try:
            return ProviderResult(
                data=dict(value["data"]),
                usage=AIUsageRecord.model_validate(value["usage"]),
            )
        except Exception:
            logger.exception(
                "Could not reconstruct provider checkpoint %s for job %s",
                stage_key,
                self.job_id,
            )
            return None

    def save_provider_result(
        self,
        stage_key: str,
        result: ProviderResult,
        *,
        input_hash: str,
        progress: int = 0,
        message: str = "",
    ) -> None:
        self.save(
            stage_key,
            {
                "data": result.data,
                "usage": result.usage.model_dump(),
            },
            input_hash=input_hash,
            progress=progress,
            message=message,
        )
