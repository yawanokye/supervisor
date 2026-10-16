"""Collect independent academic packets into durable OpenAI Batch submissions."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone

import httpx

from .database import ReviewRecord, SessionLocal


class BatchTransportError(RuntimeError):
    pass


class BatchSession:
    def __init__(self, config, checkpoints, job_id, *, poll_seconds=30, flush_seconds=.2):
        self.config, self.checkpoints, self.job_id = config, checkpoints, job_id
        self.poll_seconds, self.flush_seconds = poll_seconds, flush_seconds
        self.pending, self.futures, self.tasks = {}, {}, set()
        self.flush_task = None
        self.batch_tasks = {}

    async def http(self, method, path, *, data=None, files=None, payload=None, text=False):
        headers = {"Authorization": f"Bearer {self.config.openai_api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(method, self.config.openai_base_url + path,
                headers=headers, data=data, files=files, json=payload)
        if response.status_code >= 400:
            raise BatchTransportError(f"Batch API HTTP {response.status_code}: {response.text[:500]}")
        return response.text if text else response.json()

    def track(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def request(self, body):
        body = {k:v for k,v in body.items() if k not in {"background", "service_tier", "stream"}}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if digest not in self.futures:
            future = asyncio.get_running_loop().create_future()
            self.futures[digest] = future
            saved = self.checkpoints.load("batch-request-" + digest[:32]) or {}
            if saved.get("batch_id"):
                output = self.checkpoints.load("batch-output-" + saved["batch_id"])
                if output is not None:
                    item = (output.get("results") or {}).get(digest) or {}
                    if item.get("error") or (item.get("response") or {}).get("status_code") != 200:
                        # Retry only a failed/missing packet. Successful work
                        # keeps its original batch mapping and is never charged twice.
                        saved = {}
            if saved.get("batch_id"):
                self.track(self.deliver(saved["batch_id"], digest, future))
            else:
                self.pending[digest] = body
                if self.flush_task is None or self.flush_task.done():
                    self.flush_task = self.track(self.flush())
        return await asyncio.shield(self.futures[digest])

    async def flush(self):
        await asyncio.sleep(self.flush_seconds)
        pending, self.pending = self.pending, {}
        # Models must not be mixed in one JSONL input file.
        groups = {}
        for digest, body in pending.items():
            groups.setdefault(body["model"], {})[digest] = body
        for model, entries in groups.items():
            try:
                batch_id = await self.submit(entries)
                for digest in entries:
                    self.checkpoints.save("batch-request-" + digest[:32], {"batch_id":batch_id, "custom_id":digest})
                    self.track(self.deliver(batch_id, digest, self.futures[digest]))
            except Exception as error:
                for digest in entries:
                    if not self.futures[digest].done():
                        self.futures[digest].set_exception(error)
        if self.pending:
            self.flush_task = self.track(self.flush())

    async def submit(self, entries):
        content = "\n".join(json.dumps({"custom_id":digest,"method":"POST","url":"/v1/responses","body":body},
            ensure_ascii=False) for digest,body in sorted(entries.items())) + "\n"
        value = content.encode()
        if len(entries) > 50000 or len(value) > 190_000_000:
            raise BatchTransportError("The review packet exceeds the supported Batch file size. Use a smaller submission.")
        failed_batches = set()
        for digest in entries:
            previous = self.checkpoints.load("batch-request-" + digest[:32]) or {}
            if previous.get("batch_id") and self.checkpoints.load("batch-output-" + previous["batch_id"]) is not None:
                failed_batches.add(previous["batch_id"])
        group_hash = hashlib.sha256(value + "|".join(sorted(failed_batches)).encode()).hexdigest()
        key = "batch-group-" + group_hash[:32]
        state = self.checkpoints.load(key) or {}
        if state.get("batch_id"):
            return state["batch_id"]
        # If a prior POST acknowledgement was lost, find the exact existing
        # submission by metadata. Never blindly submit the same paid work twice.
        if state.get("submission_started"):
            after = ""
            for _ in range(50):
                listing = await self.http("GET", "/batches?limit=100" + ("&after=" + after if after else ""))
                for batch in listing.get("data", []):
                    metadata = batch.get("metadata") or {}
                    if metadata.get("vprof_job") == self.job_id and metadata.get("group_hash") == group_hash:
                        state["batch_id"] = batch["id"]
                        self.checkpoints.save(key, state)
                        return batch["id"]
                if not listing.get("has_more"):
                    break
                after = listing.get("last_id") or ""
                if not after:
                    break
            raise BatchTransportError("The earlier Batch submission could not be confirmed. Saved work was retained and was not submitted twice.")
        if not state.get("input_file_id"):
            uploaded = await self.http("POST", "/files", data={"purpose":"batch"},
                files={"file":("review-packets.jsonl",value,"application/jsonl")})
            state["input_file_id"] = uploaded["id"]
            self.checkpoints.save(key, state)
        state["submission_started"] = True
        self.checkpoints.save(key, state)
        batch = await self.http("POST", "/batches", payload={"input_file_id":state["input_file_id"],
            "endpoint":"/v1/responses", "completion_window":"24h",
            "metadata":{"vprof_job":self.job_id,"group_hash":group_hash}})
        state.update(batch_id=batch["id"], status=batch.get("status"))
        self.checkpoints.save(key, state)
        return batch["id"]

    async def collect(self, batch_id):
        key = "batch-output-" + batch_id
        saved = self.checkpoints.load(key)
        if saved is not None:
            return saved
        while True:
            batch = await self.http("GET", "/batches/" + batch_id)
            with SessionLocal() as db:
                record = db.query(ReviewRecord).filter(ReviewRecord.job_id == self.job_id).first()
                if record and record.status == "stopped":
                    raise asyncio.CancelledError()
                if record and record.status == "processing":
                    deadline = batch.get("expires_at") or ((batch.get("created_at") or datetime.now(timezone.utc).timestamp()) + 86400)
                    record.batch_deadline_at = datetime.fromtimestamp(deadline, timezone.utc)
                    record.current_stage = "openai-batch-wait"
                    counts = batch.get("request_counts") or {}
                    record.message = f"Overnight Batch review: {counts.get('completed',0)} of {counts.get('total',0)} packets returned. You may close the browser."
                    db.commit()
            if batch.get("status") in {"completed","failed","expired","cancelled"}:
                results = {}
                for field in ("output_file_id", "error_file_id"):
                    if batch.get(field):
                        output = await self.http("GET", "/files/" + batch[field] + "/content", text=True)
                        for line in output.splitlines():
                            if line.strip():
                                item = json.loads(line)
                                custom = item.get("custom_id")
                                if custom in results:
                                    raise BatchTransportError("The Batch returned duplicate request identifiers.")
                                results[custom] = item
                saved = {"status":batch["status"],"results":results}
                self.checkpoints.save(key, saved)
                return saved
            await asyncio.sleep(self.poll_seconds)

    async def deliver(self, batch_id, digest, future):
        try:
            if batch_id not in self.batch_tasks:
                self.batch_tasks[batch_id] = self.track(self.collect(batch_id))
            result = await self.batch_tasks[batch_id]
            item = result["results"].get(digest) or {}
            response = item.get("response") or {}
            if item.get("error") or response.get("status_code") != 200 or not response.get("body"):
                raise BatchTransportError(f"A Batch review packet did not complete successfully ({result.get('status')}). Successful packets remain saved for recovery.")
            body = {**response["body"], "_vprof_service_tier":"batch"}
            if not future.done():
                future.set_result((body, response.get("request_id") or batch_id + ":" + digest))
        except asyncio.CancelledError:
            if not future.done():
                future.cancel()
            raise
        except Exception as error:
            if not future.done():
                future.set_exception(error)

    async def close(self):
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
        for future in self.futures.values():
            if not future.done():
                future.cancel()


async def cancel_batches(job_id, config):
    from .checkpointing import CheckpointManager
    from .database import ReviewCheckpoint
    if not config.openai_configured:
        return {"cancelled":0,"failed":0}
    manager = CheckpointManager(job_id)
    session = BatchSession(config, manager, job_id)
    with SessionLocal() as db:
        keys = [r.stage_key for r in db.query(ReviewCheckpoint).filter(ReviewCheckpoint.job_id == job_id,
            ReviewCheckpoint.stage_key.startswith("batch-group-",autoescape=True)).all()]
    seen=set();cancelled=failed=0
    for key in keys:
        state=manager.load(key) or {};bid=state.get("batch_id")
        if not bid or bid in seen:
            continue
        seen.add(bid)
        try:
            batch=await session.http("GET","/batches/"+bid)
            if batch.get("status") not in {"completed","failed","expired","cancelled"}:
                await session.http("POST","/batches/"+bid+"/cancel",payload={})
                cancelled+=1
        except Exception:
            failed+=1
    return {"cancelled":cancelled,"failed":failed}
