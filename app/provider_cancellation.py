"""Cancel retained background work only after an explicit user stop."""
from __future__ import annotations

from sqlalchemy import or_
from .ai_providers import _post_json_with_retry
from .checkpointing import CheckpointManager
from .database import ReviewCheckpoint, SessionLocal


async def cancel_retained_background_responses(job_id: str, config) -> dict:
    if not config.openai_configured:
        return {'cancelled':0,'failed':0}
    with SessionLocal() as db:
        records = [(r.job_id,r.stage_key) for r in db.query(ReviewCheckpoint).filter(
            or_(ReviewCheckpoint.job_id == job_id, ReviewCheckpoint.job_id.startswith(job_id+'-chapter-',autoescape=True)),
            ReviewCheckpoint.stage_key.startswith('provider-inflight-',autoescape=True)).all()]
    cancelled = 0; failed = 0
    for checkpoint_job,key in records:
        manager = CheckpointManager(checkpoint_job)
        saved = manager.load(key) or {}
        payload = saved.get('payload') or {}
        if payload.get('status') not in {'queued','in_progress'} or not payload.get('id'): continue
        try:
            result, request_id = await _post_json_with_retry(
                url=f"{config.openai_base_url}/responses/{payload['id']}/cancel",
                headers={'Authorization':f'Bearer {config.openai_api_key}','Content-Type':'application/json'},
                payload={},timeout_seconds=10,max_retries=0)
            manager.save(key,{**saved,'payload':result,'request_id':request_id or saved.get('request_id')},
                message='Background cancellation requested by user')
            cancelled += int(result.get('status') == 'cancelled')
        except Exception:
            failed += 1
    return {'cancelled':cancelled,'failed':failed}
