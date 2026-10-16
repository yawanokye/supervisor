"""Durable chapter completion that does not depend on a connected browser."""
from __future__ import annotations

import json
import re

from .database import ReviewRecord, SessionLocal
from .guided_review import parse_review_id_map, remember_chapter_review


def is_fresh_chapter_queue(record) -> bool:
    return record.status == "queued" and bool(re.fullmatch(r"chapter-\d+-queued", record.current_stage or ""))


def finish_chapter_turn(job_id: str, *, worker_id: str, current_index: int,
                        units: list[int], review_id: str, usage_tokens: int,
                        checkpoint_count: int, summary: dict) -> dict | None:
    """Save the chapter and its next state in one locked transaction.

    Automatic work immediately becomes durable queued work for the next
    chapter. A stop or competing lease cannot be overwritten by a late result.
    """
    if current_index + 1 >= len(units):
        raise ValueError("Only an intermediate chapter can queue another chapter.")
    with SessionLocal() as db:
        record = db.query(ReviewRecord).filter(ReviewRecord.job_id == job_id).with_for_update().first()
        if (not record or record.status != "processing" or record.lease_owner != worker_id
                or int(record.guided_current_index or 0) != current_index):
            return None
        current_chapter, next_chapter = units[current_index], units[current_index + 1]
        mapping = parse_review_id_map(record.guided_review_ids_json)
        if str(current_chapter) not in mapping:
            record.guided_tokens_used = int(record.guided_tokens_used or 0) + int(usage_tokens or 0)
        record.guided_review_ids_json = json.dumps(remember_chapter_review(mapping, chapter=current_chapter, review_id=review_id))
        record.tokens_used = int(record.guided_tokens_used or 0)
        record.review_id = review_id
        record.checkpoint_count = checkpoint_count
        record.recoverable = True
        record.overall_score = float(summary.get("overall_score") or 0)
        record.readiness_label = summary.get("readiness_label")
        record.annotated_available = bool(summary.get("annotated_document_available"))
        record.completed_at = None
        record.lease_owner = None
        record.lease_expires_at = None
        automatic = record.review_delivery == "automatic"
        if automatic:
            record.guided_current_index = current_index + 1
            record.status = "queued"
            record.progress = 2
            record.current_stage = f"chapter-{next_chapter}-queued"
            record.resume_count = 0
            record.message = f"Chapter {current_chapter} saved. Chapter {next_chapter} queued automatically."
        else:
            record.status = "awaiting_continue"
            record.progress = 100
            record.current_stage = "awaiting-user"
            record.message = f"Chapter {current_chapter} review complete. Continue to Chapter {next_chapter}."
        record.error = None
        db.commit()
        return {"status": record.status, "progress": record.progress, "message": record.message,
                "current_stage": record.current_stage, "review_delivery": record.review_delivery,
                "guided_current_index": record.guided_current_index,
                "guided_current_chapter": next_chapter if automatic else current_chapter,
                "guided_next_chapter": next_chapter}


def public_job_progress(response: dict, record) -> dict:
    """Expose whole-review progress while the internal checkpoints stay chapter scoped."""
    delivery = getattr(record, "review_delivery", "guided") or "guided"
    response["review_delivery"] = delivery
    response["processing_mode"] = getattr(record, "processing_mode", "standard") or "standard"
    response["background_processing"] = True
    if delivery == "automatic" and record.guided_mode and int(record.guided_total_units or 0) > 1:
        raw = max(0, min(100, int(record.progress or 0)))
        total = int(record.guided_total_units)
        index = max(0, min(total - 1, int(record.guided_current_index or 0)))
        response["chapter_progress"] = raw
        response["progress"] = 100 if record.status == "completed" else min(99, int((index * 100 + raw) / total))
    return response
