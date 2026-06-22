from __future__ import annotations

import os
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .annotated_exporter import build_annotated_docx
from .academic_ai_engine import enrich_review_with_academic_ai
from .ai_config import AIConfigurationError, HybridAIConfig
from .ai_providers import AIProviderError
from .hybrid_ai_engine import enrich_review_with_hybrid_ai
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
    version="0.6.1",
    description="Complete academic review for thesis chapters, proposals, revisions, and complete theses.",
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# MVP only. Replace with Redis or a database before commercial deployment.
REVIEW_CACHE: Dict[str, dict] = {}
ANNOTATED_CACHE: Dict[str, bytes] = {}
AI_USAGE_CACHE: Dict[str, dict] = {}


def _strip_internal_ai_metadata(review: dict) -> dict:
    """Remove provider metadata and the internal checklist guide from student-facing output."""
    review.pop("ai_review", None)
    review.pop("ai_document_map", None)
    review.pop("results", None)
    review.pop("chapter_scores", None)
    review.pop("critical_gates", None)
    summary = review.get("summary") or {}
    hidden_summary_keys = {
        "checklist_score", "rules_checked", "official_rules_checked", "meets", "partial",
        "missing", "manual", "not_applicable", "critical_gate_blocked", "critical_failed",
    }
    for key in list(summary):
        if key.startswith("ai_") or key in hidden_summary_keys:
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
    return {
        "status": "ok",
        "service": "projectready-supervisor",
        "version": "0.6.1",
    }


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
        raise HTTPException(status_code=413, detail=f"{label} exceeds the 25 MB file limit.")
    return data


@app.post("/api/review")
async def create_review(
    file: UploadFile = File(...),
    academic_level: str = Form(...),
    research_approach: str = Form(...),
    review_scope: str = Form("chapter"),
    selected_chapter: int = Form(0),
    document_type: str = Form("chapter_one"),
    submission_stage: str = Form("initial"),
    previous_files: Optional[List[UploadFile]] = File(None),
    supervisor_comment_files: Optional[List[UploadFile]] = File(None),
    supervisor_comments_text: str = Form(""),
    original_file: Optional[UploadFile] = File(None),
    ai_review_mode: str = Form("auto"),
):
    filename = file.filename or "uploaded-document"
    data = await _read_upload(file, "The chapter or thesis file")

    context_uploads = [item for item in (previous_files or []) if item and item.filename]
    if review_scope == "chapter" and selected_chapter >= 2 and not context_uploads:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Upload Chapters 1 to {selected_chapter - 1} for alignment. "
                "You may upload one composite file or several separate files."
            ),
        )
    if len(context_uploads) > MAX_CONTEXT_FILES:
        raise HTTPException(status_code=400, detail=f"Upload no more than {MAX_CONTEXT_FILES} previous-chapter files.")

    context_documents = []
    total_context_bytes = 0
    for index, upload in enumerate(context_uploads, start=1):
        context_data = await _read_upload(upload, f"Previous-chapter file {index}")
        total_context_bytes += len(context_data)
        if total_context_bytes > MAX_TOTAL_CONTEXT_BYTES:
            raise HTTPException(status_code=413, detail="The combined previous-chapter uploads exceed 75 MB.")
        context_documents.append({
            "filename": upload.filename or f"previous-chapter-{index}",
            "data": context_data,
        })

    comment_uploads = [item for item in (supervisor_comment_files or []) if item and item.filename]
    if submission_stage == "revised" and not comment_uploads and not supervisor_comments_text.strip():
        raise HTTPException(
            status_code=400,
            detail="For a revised chapter, upload the supervisor comments or paste them into the comments box.",
        )
    if len(comment_uploads) > MAX_CONTEXT_FILES:
        raise HTTPException(status_code=400, detail=f"Upload no more than {MAX_CONTEXT_FILES} supervisor-comment files.")

    supervisor_comment_documents = []
    total_comment_bytes = 0
    for index, upload in enumerate(comment_uploads, start=1):
        comment_data = await _read_upload(upload, f"Supervisor-comment file {index}")
        total_comment_bytes += len(comment_data)
        if total_comment_bytes > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="The combined supervisor-comment uploads exceed 50 MB.")
        supervisor_comment_documents.append({
            "filename": upload.filename or f"supervisor-comments-{index}",
            "data": comment_data,
        })

    original_document = None
    if original_file and original_file.filename:
        original_data = await _read_upload(original_file, "The original chapter file")
        original_document = {
            "filename": original_file.filename or "original-chapter",
            "data": original_data,
        }

    try:
        review = analyse(
            data,
            filename,
            academic_level=academic_level,
            research_approach=research_approach,
            selected_chapter=selected_chapter or None,
            review_scope=review_scope,
            document_type=document_type,
            context_documents=context_documents,
            submission_stage=submission_stage,
            supervisor_comment_documents=supervisor_comment_documents,
            supervisor_comments_text=supervisor_comments_text,
            original_document=original_document,
        )
        runtime_context = review.pop("_runtime_context", {})
        config = HybridAIConfig.from_env()
        # First refine cross-chapter alignment and revised-comment follow-up.
        review = await enrich_review_with_hybrid_ai(
            review,
            runtime_context,
            requested_mode=ai_review_mode,
            config=config,
        )
        # Then conduct a complete section-by-section academic review. The official checklist
        # is supplied only as hidden guidance and is never shown as the review itself.
        review = await enrich_review_with_academic_ai(
            review,
            runtime_context,
            requested_mode=ai_review_mode,
            config=config,
        )
        if review.get("ai_review"):
            AI_USAGE_CACHE[review["review_id"]] = dict(review["ai_review"])
        review = _strip_internal_ai_metadata(review)
    except (ValueError, AIConfigurationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIProviderError as exc:
        logger.exception("Expert review provider failure")
        raise HTTPException(
            status_code=503,
            detail=(
                "The expert review service could not complete the document review. "
                "Please try again. The server log now contains the exact provider error. "
                f"Technical detail: {str(exc)[:700]}"
            ),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected review failure")
        raise HTTPException(status_code=500, detail=f"Review failed: {exc}") from exc

    annotated_available = filename.lower().endswith(".docx")
    review["summary"]["annotated_document_available"] = annotated_available
    if annotated_available:
        try:
            ANNOTATED_CACHE[review["review_id"]] = build_annotated_docx(data, review)
        except Exception as exc:
            review["summary"]["annotated_document_available"] = False
            review["summary"]["annotation_warning"] = f"Annotated document could not be generated: {exc}"

    REVIEW_CACHE[review["review_id"]] = review
    return review


@app.get("/api/review/{review_id}")
async def get_review(review_id: str):
    review = REVIEW_CACHE.get(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or expired.")
    return review


@app.get("/api/review/{review_id}/annotated.docx")
async def export_annotated_document(review_id: str):
    review = REVIEW_CACHE.get(review_id)
    data = ANNOTATED_CACHE.get(review_id)
    if not review or data is None:
        raise HTTPException(status_code=404, detail="Annotated DOCX is not available for this review.")
    original = review.get("summary", {}).get("filename", "thesis.docx")
    stem = os.path.splitext(os.path.basename(original))[0]
    safe_name = f"{stem}-supervisor-reviewed.docx"
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@app.get("/api/review/{review_id}/export.docx")
async def export_review(review_id: str):
    review = REVIEW_CACHE.get(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or expired.")
    data = build_docx_report(review)
    safe_name = "supervisor-review-report.docx"
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )
