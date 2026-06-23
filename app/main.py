from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .annotated_exporter import build_annotated_docx
from .academic_ai_engine import enrich_review_with_academic_ai
from .ai_config import AIConfigurationError, HybridAIConfig
from .ai_providers import AIProviderError
from .report_exporter import build_docx_report
from .review_engine import analyse

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_CONTEXT_FILES = 5
MAX_TOTAL_CONTEXT_BYTES = 75 * 1024 * 1024
ALLOWED_EXTENSIONS = (".docx", ".pdf")

app = FastAPI(
    title="ProjectReady AI Supervisor Assistant",
    version="1.0.0",
    description="Complete section-by-section Light, Standard and Advanced academic review for theses, dissertations, proposals and revisions.",
)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

REVIEW_CACHE: Dict[str, dict] = {}
ANNOTATED_CACHE: Dict[str, bytes] = {}
AI_USAGE_CACHE: Dict[str, dict] = {}
JOB_CACHE: Dict[str, Dict[str, Any]] = {}
BACKGROUND_TASKS: set[asyncio.Task] = set()


def _strip_internal_ai_metadata(review: dict) -> dict:
    review.pop("ai_review", None)
    review.pop("ai_document_map", None)
    review.pop("results", None)
    review.pop("chapter_scores", None)
    review.pop("critical_gates", None)
    summary = review.get("summary") or {}
    hidden = {"checklist_score", "rules_checked", "official_rules_checked", "meets", "partial", "missing", "manual", "not_applicable", "critical_gate_blocked", "critical_failed"}
    for key in list(summary):
        if key.startswith("ai_") or key in hidden:
            summary.pop(key, None)
    for collection_name in ("academic_findings", "alignment_results", "revision_results"):
        for row in review.get(collection_name) or []:
            row.pop("code", None)
            for key in list(row):
                if key.startswith("ai_") or key.startswith("local_"):
                    row.pop(key, None)
    for action in review.get("priority_actions") or []:
        action.pop("code", None)
    return review


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "projectready-supervisor", "version": "1.0.0"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled application error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "The review service encountered an unexpected error. Please try again."})


def _validate_filename(filename: str, label: str) -> None:
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail=f"{label} must be a DOCX or text-based PDF file.")


async def _read_upload(upload: UploadFile, label: str, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    filename = upload.filename or label
    _validate_filename(filename, label)
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"{label} is empty.")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{label} exceeds the file limit.")
    return data


def _job_update(job_id: str, *, status: Optional[str] = None, progress: Optional[int] = None, message: Optional[str] = None, **extra: Any) -> None:
    job = JOB_CACHE.setdefault(job_id, {})
    if status is not None: job["status"] = status
    if progress is not None: job["progress"] = max(0, min(100, int(progress)))
    if message is not None: job["message"] = message
    job.update(extra)
    job["updated_at"] = time.time()


async def _run_review_job(job_id: str, payload: Dict[str, Any]) -> None:
    try:
        _job_update(job_id, status="processing", progress=8, message="Reading and organising the uploaded documents")
        review = analyse(
            payload["data"], payload["filename"],
            academic_level=payload["academic_level"], research_approach=payload["research_approach"],
            selected_chapter=payload["selected_chapter"] or None, review_scope=payload["review_scope"],
            document_type=payload["document_type"], context_documents=payload["context_documents"],
            submission_stage=payload["submission_stage"], supervisor_comment_documents=payload["supervisor_comment_documents"],
            supervisor_comments_text=payload["supervisor_comments_text"], original_document=payload["original_document"],
        )
        runtime_context = review.pop("_runtime_context", {})
        _job_update(job_id, progress=22, message="Preparing the academic review")
        config = HybridAIConfig.from_env()

        async def progress_callback(value: int, message: str) -> None:
            _job_update(job_id, progress=value, message=message)

        review = await enrich_review_with_academic_ai(
            review, runtime_context, requested_mode=payload["review_depth"],
            config=config, progress_callback=progress_callback,
        )
        if review.get("ai_review"):
            AI_USAGE_CACHE[review["review_id"]] = dict(review["ai_review"])
        review = _strip_internal_ai_metadata(review)
        review["summary"]["annotated_document_available"] = payload["filename"].lower().endswith(".docx")

        if review["summary"]["annotated_document_available"]:
            try:
                ANNOTATED_CACHE[review["review_id"]] = build_annotated_docx(payload["data"], review)
            except Exception as exc:
                logger.exception("Annotated document generation failed")
                review["summary"]["annotated_document_available"] = False
                review["summary"]["annotation_warning"] = "The review completed, but the annotated document could not be generated."

        REVIEW_CACHE[review["review_id"]] = review
        _job_update(job_id, status="completed", progress=100, message="Review complete", review_id=review["review_id"], review=review)
    except (ValueError, AIConfigurationError) as exc:
        _job_update(job_id, status="failed", progress=100, message="Review could not start", error=str(exc), retryable=False)
    except AIProviderError as exc:
        logger.exception("Expert review provider failure")
        _job_update(job_id, status="failed", progress=100, message="The expert review service was temporarily unable to finish", error="The expert review could not be completed. Please retry in a few minutes.", retryable=True)
    except Exception:
        logger.exception("Unexpected background review failure")
        _job_update(job_id, status="failed", progress=100, message="Review failed", error="The review could not be completed. Please try again.", retryable=True)


@app.post("/api/review", status_code=202)
async def create_review(
    file: UploadFile = File(...), academic_level: str = Form(...), research_approach: str = Form(...),
    review_scope: str = Form("chapter"), selected_chapter: int = Form(0), document_type: str = Form("chapter_one"),
    submission_stage: str = Form("initial"), review_depth: str = Form("standard"),
    previous_files: Optional[List[UploadFile]] = File(None), supervisor_comment_files: Optional[List[UploadFile]] = File(None),
    supervisor_comments_text: str = Form(""), original_file: Optional[UploadFile] = File(None),
):
    if review_depth not in {"light", "standard", "advanced"}:
        raise HTTPException(status_code=400, detail="Choose Light Review, Standard Review or Advanced Review.")
    filename = file.filename or "uploaded-document"
    data = await _read_upload(file, "The chapter or thesis file")

    context_uploads = [item for item in (previous_files or []) if item and item.filename]
    if review_scope == "chapter" and selected_chapter >= 2 and not context_uploads:
        raise HTTPException(status_code=400, detail=f"Upload Chapters 1 to {selected_chapter - 1} for alignment.")
    if len(context_uploads) > MAX_CONTEXT_FILES:
        raise HTTPException(status_code=400, detail=f"Upload no more than {MAX_CONTEXT_FILES} previous-chapter files.")
    context_documents = []
    total_context = 0
    for index, upload in enumerate(context_uploads, start=1):
        value = await _read_upload(upload, f"Previous-chapter file {index}")
        total_context += len(value)
        if total_context > MAX_TOTAL_CONTEXT_BYTES:
            raise HTTPException(status_code=413, detail="The combined previous-chapter uploads exceed 75 MB.")
        context_documents.append({"filename": upload.filename or f"previous-chapter-{index}", "data": value})

    comment_uploads = [item for item in (supervisor_comment_files or []) if item and item.filename]
    if submission_stage == "revised" and not comment_uploads and not supervisor_comments_text.strip():
        raise HTTPException(status_code=400, detail="For a revised chapter, upload or paste the supervisor comments.")
    supervisor_comment_documents = []
    total_comments = 0
    for index, upload in enumerate(comment_uploads, start=1):
        value = await _read_upload(upload, f"Supervisor-comment file {index}")
        total_comments += len(value)
        if total_comments > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="The combined supervisor-comment uploads exceed 50 MB.")
        supervisor_comment_documents.append({"filename": upload.filename or f"supervisor-comments-{index}", "data": value})

    original_document = None
    if original_file and original_file.filename:
        original_document = {"filename": original_file.filename, "data": await _read_upload(original_file, "The original chapter file")}

    job_id = uuid.uuid4().hex
    JOB_CACHE[job_id] = {"job_id": job_id, "status": "queued", "progress": 2, "message": "Review queued", "created_at": time.time(), "updated_at": time.time()}
    payload = {
        "filename": filename, "data": data, "academic_level": academic_level, "research_approach": research_approach,
        "review_scope": review_scope, "selected_chapter": selected_chapter, "document_type": document_type,
        "submission_stage": submission_stage, "review_depth": review_depth, "context_documents": context_documents,
        "supervisor_comment_documents": supervisor_comment_documents, "supervisor_comments_text": supervisor_comments_text,
        "original_document": original_document,
    }
    task = asyncio.create_task(_run_review_job(job_id, payload))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return {"job_id": job_id, "status": "queued", "progress": 2, "message": "Review queued", "poll_url": f"/api/review/jobs/{job_id}"}


@app.get("/api/review/jobs/{job_id}")
async def get_review_job(job_id: str):
    job = JOB_CACHE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Review job not found or expired.")
    return job


@app.get("/api/review/{review_id}")
async def get_review(review_id: str):
    review = REVIEW_CACHE.get(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or expired.")
    return review


@app.get("/api/review/{review_id}/annotated.docx")
async def export_annotated_document(review_id: str):
    review = REVIEW_CACHE.get(review_id); data = ANNOTATED_CACHE.get(review_id)
    if not review or data is None:
        raise HTTPException(status_code=404, detail="Annotated DOCX is not available for this review.")
    stem = os.path.splitext(os.path.basename(review.get("summary", {}).get("filename", "thesis.docx")))[0]
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="{stem}-supervisor-reviewed.docx"'})


@app.get("/api/review/{review_id}/export.docx")
async def export_review(review_id: str):
    review = REVIEW_CACHE.get(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or expired.")
    return Response(content=build_docx_report(review), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="supervisor-review-report.docx"'})
