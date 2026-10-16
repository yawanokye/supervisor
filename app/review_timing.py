"""Queue-aware ready-time estimates, never deadlines or processing cutoffs."""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from .database import ReviewRecord


def utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _context(db):
    if db is None:
        return {}, []
    if "review_timing_context" in db.info:
        return db.info["review_timing_context"]
    history = db.query(ReviewRecord).filter(ReviewRecord.status == "completed", ReviewRecord.completed_at.is_not(None),
        ReviewRecord.started_at.is_not(None), ReviewRecord.estimated_pages > 0).order_by(ReviewRecord.completed_at.desc()).limit(80).all()
    rates = defaultdict(list)
    for row in history:
        # Human chapter pauses would inflate the observed processing rate.
        if row.guided_mode and row.review_delivery != "automatic":
            continue
        seconds = (utc(row.completed_at) - utc(row.started_at)).total_seconds()
        if seconds < 30:
            continue
        rate = seconds / max(1, int(row.estimated_pages or 1))
        if 2 <= rate <= 7200:
            rates[(row.workflow_type, row.review_depth, row.processing_mode)].append(rate)
    jobs = db.query(ReviewRecord).filter(ReviewRecord.status.in_(["queued", "processing"]),
        ReviewRecord.recoverable.is_(True), ReviewRecord.payload_available.is_(True)).order_by(ReviewRecord.created_at.asc()).all()
    context = ({key: median(values) for key, values in rates.items() if len(values) >= 3}, jobs)
    db.info["review_timing_context"] = context
    return context


def _remaining(record, rates, now):
    pages = max(1, int(getattr(record, "estimated_pages", 1) or 1))
    depth = getattr(record, "review_depth", "standard") or "standard"
    workflow = getattr(record, "workflow_type", "supervisory_review") or "supervisory_review"
    automatic = getattr(record, "review_delivery", "guided") == "automatic"
    units = max(1, int(getattr(record, "guided_total_units", 0) or 1)) if getattr(record, "guided_mode", False) else 1
    index = max(0, min(units - 1, int(getattr(record, "guided_current_index", 0) or 0)))
    raw = max(0, min(99, int(getattr(record, "progress", 0) or 0)))
    fraction = ((index + raw / 100) / units) if automatic else raw / 100
    # Guided estimates cover the current turn, automatic estimates cover all
    # remaining chapters and final consolidation.
    effective_pages = pages if automatic or units == 1 else max(1, pages / units)
    mode = getattr(record, "processing_mode", "standard") or "standard"
    historical = rates.get((workflow, depth, mode))
    default_rate = {"light": 30, "standard": 60, "advanced": 90}.get(depth, 60)
    if workflow == "external_assessment":
        default_rate = max(120, default_rate)
    rate = historical * 1.15 if historical else default_rate * (1.5 if mode == "flex" else 1)
    planned = max(300 * (units if automatic else 1), effective_pages * rate)
    remaining = max(30, planned * (1 - fraction))
    started = utc(getattr(record, "started_at", None))
    if started and fraction >= .08 and getattr(record, "status", "") == "processing" and (automatic or units == 1):
        elapsed = max(1, (now - started).total_seconds())
        remaining = max(remaining, elapsed * (1 - fraction) / fraction)
    final_chapter = not automatic or index == units - 1
    if final_chapter and (getattr(record, "current_stage", "") == "document-export" or raw >= 98):
        remaining = max(10, min(240, 20 + effective_pages * 2))
    if mode == "batch" and getattr(record, "current_stage", "") != "document-export":
        deadline = utc(getattr(record, "batch_deadline_at", None))
        remaining = max(remaining, max(0, (deadline - now).total_seconds()) + 900 if deadline else 86400 + 900)
    return int(math.ceil(remaining)), bool(historical)


def estimate_review(record, db=None, *, worker_slots=1, now=None):
    now = utc(now) or datetime.now(timezone.utc)
    status = str(getattr(record, "status", ""))
    if status in {"completed", "failed", "stopped", "awaiting_continue", "paused"}:
        return {"estimated_seconds_remaining": 0, "estimated_completion_at": None,
                "check_back_at": None, "estimate_is_approximate": True,
                "estimate_state": "ready" if status == "completed" else "needs_attention"}
    rates, jobs = _context(db)
    processing, learned = _remaining(record, rates, now)
    waiting = 0
    if status == "queued":
        loads = [0] * max(1, int(worker_slots))
        heapq.heapify(loads)
        ahead = [r for r in jobs if r.job_id != record.job_id and (r.status == "processing" or
            (utc(r.created_at) and utc(getattr(record, "created_at", None)) and utc(r.created_at) < utc(record.created_at)))]
        if int(worker_slots) > 1 and getattr(record, "processing_mode", "standard") != "batch":
            # The default worker reserves capacity for non-Batch work.
            # Queued overnight jobs must not inflate an urgent review's ETA.
            ahead = [r for r in ahead if r.status == "processing" or r.processing_mode != "batch"]
        ahead.sort(key=lambda r: (r.status != "processing", utc(r.created_at) or now))
        for job in ahead:
            available = heapq.heappop(loads)
            duration, _ = _remaining(job, rates, now)
            heapq.heappush(loads, available + duration)
        waiting = min(loads)
    remaining = max(30, waiting + processing)
    lower, upper = max(30, int(remaining * .7)), max(60, int(remaining * 1.5))
    # Round the suggested return time up, with room for normal variation.
    check_seconds = int(math.ceil(upper / 300) * 300)
    return {
        "estimated_seconds_remaining": remaining,
        "estimated_completion_at": (now + timedelta(seconds=remaining)).isoformat(),
        "estimated_ready_from": (now + timedelta(seconds=lower)).isoformat(),
        "estimated_ready_until": (now + timedelta(seconds=upper)).isoformat(),
        "check_back_at": (now + timedelta(seconds=check_seconds)).isoformat(),
        "estimated_queue_seconds": waiting, "estimate_is_approximate": True,
        "estimate_basis": "recent_reviews_and_progress" if learned else "document_size_depth_and_progress",
        "estimate_state": "waiting" if status == "queued" else "processing",
        "estimate_note": (
            "Each Batch submission has a 24-hour window. Follow-up stages can extend the whole review beyond this window."
            if getattr(record, "processing_mode", "standard") == "batch" else
            "An approximate range, updated as work progresses. Economy capacity and queue times can vary."
            if getattr(record, "processing_mode", "standard") == "flex" else
            "An approximate range, updated as work progresses and the queue changes."
        ),
        "batch_window_ends_at": utc(getattr(record, "batch_deadline_at", None)).isoformat() if getattr(record, "batch_deadline_at", None) else None,
    }
