from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from .checkpointing import load_job_payload, payload_available
from .database import ReviewRecord, SessionLocal, init_db
from .main import JOB_LEASE_SECONDS, _normalise_db_datetime, _run_review_job
from .storage import ensure_storage

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

WORKER_CONCURRENCY = max(1, int(os.getenv("VPROF_WORKER_CONCURRENCY", "1")))
POLL_SECONDS = max(2, int(os.getenv("VPROF_WORKER_POLL_SECONDS", "8")))
CLAIM_LIMIT = max(1, int(os.getenv("VPROF_WORKER_CLAIM_LIMIT", str(WORKER_CONCURRENCY))))


def _next_job_id() -> Optional[tuple[str, bool]]:
    """Return the next queued/recoverable job for this worker.

    The durable lease is still acquired inside app.main._run_review_job through
    _claim_job. This function only chooses a candidate and normalises expired
    processing rows back to queued so they can be recovered by any worker.
    """
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        records = (
            db.query(ReviewRecord)
            .filter(
                ReviewRecord.status.in_(["queued", "processing", "paused"]),
                ReviewRecord.recoverable.is_(True),
                ReviewRecord.payload_available.is_(True),
            )
            .order_by(ReviewRecord.created_at.asc())
            .limit(50)
            .all()
        )
        for record in records:
            lease_expires = _normalise_db_datetime(record.lease_expires_at)
            if record.status == "processing" and lease_expires and lease_expires > now:
                continue
            if record.status in {"processing", "paused"}:
                record.status = "queued"
                record.lease_owner = None
                record.lease_expires_at = None
                record.message = record.message or "Recovered by the background worker"
                db.commit()
            if not payload_available(record.job_id):
                record.payload_available = False
                record.recoverable = False
                record.status = "failed"
                record.error = "The saved upload is unavailable to the worker. Submit the document again."
                db.commit()
                continue
            resumed = bool(
                int(record.resume_count or 0) > 0
                or int(record.checkpoint_count or 0) > 0
                or record.started_at is not None
                or (record.current_stage and record.current_stage != "queued")
            )
            return record.job_id, resumed
    return None


async def _run_candidate(job_id: str, resumed: bool) -> None:
    payload = load_job_payload(job_id)
    if not payload:
        logger.error("Worker could not load payload for job %s", job_id)
        with SessionLocal() as db:
            record = db.query(ReviewRecord).filter(ReviewRecord.job_id == job_id).first()
            if record:
                record.status = "failed"
                record.recoverable = False
                record.payload_available = False
                record.error = "The saved upload is unavailable to the worker. Submit the document again."
                db.commit()
        return
    await _run_review_job(job_id, payload, resumed=resumed)


async def worker_loop() -> None:
    init_db()
    ensure_storage()
    logger.info(
        "VProfessor worker started. concurrency=%s poll_seconds=%s lease_seconds=%s",
        WORKER_CONCURRENCY,
        POLL_SECONDS,
        JOB_LEASE_SECONDS,
    )
    running: set[asyncio.Task] = set()
    while True:
        running = {task for task in running if not task.done()}
        while len(running) < WORKER_CONCURRENCY:
            candidate = _next_job_id()
            if not candidate:
                break
            job_id, resumed = candidate
            if any(getattr(task, "_vprof_job_id", None) == job_id for task in running):
                break
            task = asyncio.create_task(_run_candidate(job_id, resumed))
            setattr(task, "_vprof_job_id", job_id)
            running.add(task)
            logger.info("Worker accepted job %s resumed=%s", job_id, resumed)
        if running:
            done, pending = await asyncio.wait(
                running,
                timeout=POLL_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                try:
                    task.result()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Worker task failed unexpectedly")
            running = pending
        else:
            await asyncio.sleep(POLL_SECONDS)


def main() -> None:
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
