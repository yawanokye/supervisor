from __future__ import annotations

import os
from typing import Dict

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .annotated_exporter import build_annotated_docx
from .report_exporter import build_docx_report
from .review_engine import analyse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(
    title="ProjectReady AI Supervisor Assistant",
    version="0.2.0",
    description="Evidence-linked expert review for thesis chapters and full theses.",
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# MVP only. Replace with Redis or a database before commercial deployment.
REVIEW_CACHE: Dict[str, dict] = {}
ANNOTATED_CACHE: Dict[str, bytes] = {}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "ok", "service": "projectready-supervisor"}

@app.post("/api/review")
async def create_review(
    file: UploadFile = File(...),
    academic_level: str = Form(...),
    research_approach: str = Form(...),
    review_scope: str = Form("chapter"),
    selected_chapter: int = Form(0),
):
    filename = file.filename or "uploaded-document"
    if not filename.lower().endswith((".docx", ".pdf")):
        raise HTTPException(status_code=400, detail="Upload a DOCX or PDF file.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The MVP file limit is 25 MB.")

    try:
        review = analyse(
            data,
            filename,
            academic_level=academic_level,
            research_approach=research_approach,
            selected_chapter=selected_chapter or None,
            review_scope=review_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
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
