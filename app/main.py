from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from .academic_ai_engine import enrich_review_with_academic_ai
from .ai_config import AIConfigurationError, HybridAIConfig
from .ai_providers import AIProviderError
from .annotated_exporter import build_annotated_docx
from .auth import (
    authenticate,
    create_bootstrap_admin,
    generate_recovery_pin,
    generate_temporary_password,
    hash_secret,
    normalize_username,
    suggest_username,
    unique_username,
    validate_password,
    verify_secret,
)
from .database import ReviewRecord, SessionLocal, User, get_db, init_db
from .report_exporter import build_docx_report
from .review_engine import analyse
from .storage import ensure_storage, load_annotated, load_review_json, save_annotated, save_review_json

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_CONTEXT_FILES = 5
MAX_TOTAL_CONTEXT_BYTES = 75 * 1024 * 1024
AI_JOB_MAX_SECONDS = max(900, int(os.getenv("AI_JOB_MAX_SECONDS", "5400")))
ALLOWED_EXTENSIONS = (".docx", ".pdf")
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-this-secret")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(
    title="ProjectReady AI Supervisor Assistant",
    version="1.1.0",
    description="Institutional supervisor portal for complete academic review of theses, dissertations, proposals and revisions.",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="supervisor_session",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=COOKIE_SECURE,
)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

REVIEW_CACHE: Dict[str, dict] = {}
ANNOTATED_CACHE: Dict[str, bytes] = {}
AI_USAGE_CACHE: Dict[str, dict] = {}
JOB_CACHE: Dict[str, Dict[str, Any]] = {}
BACKGROUND_TASKS: set[asyncio.Task] = set()
LOGIN_ATTEMPTS: Dict[str, Dict[str, Any]] = {}
CREDENTIAL_FLASH: Dict[str, Dict[str, str]] = {}


@app.on_event("startup")
def startup() -> None:
    init_db()
    ensure_storage()
    with SessionLocal() as db:
        generated = create_bootstrap_admin(db)
        if generated:
            logger.warning(
                "No administrator existed. A bootstrap administrator was created. Username=%s TemporaryPassword=%s. Change it immediately.",
                os.getenv("ADMIN_USERNAME", "admin"),
                generated,
            )


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


def _csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def _verify_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf_token")
    if not expected or not secrets.compare_digest(expected, token or ""):
        raise HTTPException(status_code=403, detail="Your session could not be verified. Refresh the page and try again.")


def _set_flash(request: Request, message: str, category: str = "info") -> None:
    request.session["flash"] = {"message": message, "category": category}


def _take_flash(request: Request) -> Optional[dict]:
    return request.session.pop("flash", None)


def _current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


def require_authenticated(request: Request, db: Session = Depends(get_db)) -> User:
    user = _current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    if user.must_change_password and request.url.path not in {"/account/password", "/logout"}:
        raise HTTPException(status_code=403, detail="Change your temporary password before continuing.")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = _current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return user


def _template_context(request: Request, user: Optional[User] = None, **extra: Any) -> dict:
    return {
        "request": request,
        "user": user,
        "csrf_token": _csrf_token(request),
        "flash": _take_flash(request),
        **extra,
    }


def _login_key(request: Request, username: str, role: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{role}:{normalize_username(username)}"


def _login_allowed(key: str) -> bool:
    state = LOGIN_ATTEMPTS.get(key)
    if not state:
        return True
    if state.get("locked_until", 0) <= time.time():
        LOGIN_ATTEMPTS.pop(key, None)
        return True
    return False


def _record_login_failure(key: str) -> None:
    state = LOGIN_ATTEMPTS.setdefault(key, {"count": 0, "locked_until": 0})
    state["count"] += 1
    if state["count"] >= 5:
        state["locked_until"] = time.time() + 15 * 60


def _clear_login_failures(key: str) -> None:
    LOGIN_ATTEMPTS.pop(key, None)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled application error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "The service encountered an unexpected error. Please try again."})


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/admin" if user.role == "admin" else "/portal", status_code=303)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "projectready-supervisor", "version": "1.3.1"}


@app.get("/login", response_class=HTMLResponse)
async def lecturer_login_page(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if user:
        return RedirectResponse("/admin" if user.role == "admin" else "/portal", status_code=303)
    return templates.TemplateResponse("login.html", _template_context(request, portal_type="lecturer"))


@app.post("/login")
async def lecturer_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    key = _login_key(request, username, "lecturer")
    if not _login_allowed(key):
        _set_flash(request, "Too many unsuccessful attempts. Try again in 15 minutes.", "error")
        return RedirectResponse("/login", status_code=303)
    user = authenticate(db, username, password, required_role="lecturer")
    if not user:
        _record_login_failure(key)
        _set_flash(request, "The username or password is incorrect.", "error")
        return RedirectResponse("/login", status_code=303)
    _clear_login_failures(key)
    request.session.clear()
    request.session["user_id"] = user.id
    _csrf_token(request)
    if user.must_change_password:
        _set_flash(request, "Create a private password before using the supervisor portal.", "warning")
        return RedirectResponse("/account/password", status_code=303)
    return RedirectResponse("/portal", status_code=303)


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if user and user.role == "admin":
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("login.html", _template_context(request, portal_type="admin"))


@app.post("/admin/login")
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    key = _login_key(request, username, "admin")
    if not _login_allowed(key):
        _set_flash(request, "Too many unsuccessful attempts. Try again in 15 minutes.", "error")
        return RedirectResponse("/admin/login", status_code=303)
    user = authenticate(db, username, password, required_role="admin")
    if not user:
        _record_login_failure(key)
        _set_flash(request, "The administrator username or password is incorrect.", "error")
        return RedirectResponse("/admin/login", status_code=303)
    _clear_login_failures(key)
    request.session.clear()
    request.session["user_id"] = user.id
    _csrf_token(request)
    if user.must_change_password:
        _set_flash(request, "Change the temporary administrator password before continuing.", "warning")
        return RedirectResponse("/account/password", status_code=303)
    return RedirectResponse("/admin", status_code=303)


@app.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", _template_context(request))


@app.post("/forgot-password")
async def forgot_password(
    request: Request,
    username: str = Form(...),
    recovery_pin: str = Form(...),
    new_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    key = _login_key(request, username, "recovery")
    if not _login_allowed(key):
        _set_flash(request, "Too many unsuccessful attempts. Try again in 15 minutes.", "error")
        return RedirectResponse("/forgot-password", status_code=303)
    error = validate_password(new_password)
    user = db.query(User).filter(User.username == normalize_username(username), User.role == "lecturer", User.is_active.is_(True)).first()
    if error:
        _set_flash(request, error, "error")
        return RedirectResponse("/forgot-password", status_code=303)
    if not user or not verify_secret(recovery_pin.strip(), user.recovery_pin_hash):
        _record_login_failure(key)
        _set_flash(request, "The username or recovery PIN is incorrect.", "error")
        return RedirectResponse("/forgot-password", status_code=303)
    _clear_login_failures(key)
    user.password_hash = hash_secret(new_password)
    user.must_change_password = False
    db.commit()
    _set_flash(request, "Your password has been reset. Sign in with the new password.", "success")
    return RedirectResponse("/login", status_code=303)


@app.get("/account/password", response_class=HTMLResponse)
async def change_password_page(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("change_password.html", _template_context(request, user=user))


@app.post("/account/password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not verify_secret(current_password, user.password_hash):
        _set_flash(request, "The current password is incorrect.", "error")
        return RedirectResponse("/account/password", status_code=303)
    if new_password != confirm_password:
        _set_flash(request, "The new passwords do not match.", "error")
        return RedirectResponse("/account/password", status_code=303)
    error = validate_password(new_password)
    if error:
        _set_flash(request, error, "error")
        return RedirectResponse("/account/password", status_code=303)
    user.password_hash = hash_secret(new_password)
    user.must_change_password = False
    db.commit()
    _set_flash(request, "Password updated successfully.", "success")
    return RedirectResponse("/admin" if user.role == "admin" else "/portal", status_code=303)


@app.get("/portal", response_class=HTMLResponse)
async def lecturer_portal(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role == "admin":
        return RedirectResponse("/admin", status_code=303)
    if user.must_change_password:
        return RedirectResponse("/account/password", status_code=303)
    reviews = db.query(ReviewRecord).filter(ReviewRecord.lecturer_id == user.id).order_by(ReviewRecord.created_at.desc()).limit(100).all()
    total = len(reviews)
    completed = sum(1 for row in reviews if row.status == "completed")
    processing = sum(1 for row in reviews if row.status in {"queued", "processing"})
    revised = sum(1 for row in reviews if row.submission_stage == "revised")
    return templates.TemplateResponse(
        "portal.html",
        _template_context(request, user=user, reviews=reviews, stats={"total": total, "completed": completed, "processing": processing, "revised": revised}),
    )


@app.get("/review", response_class=HTMLResponse)
async def review_workspace(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.must_change_password:
        return RedirectResponse("/account/password", status_code=303)
    return templates.TemplateResponse("index.html", _template_context(request, user=user))


@app.get("/reviews/{review_id}", response_class=HTMLResponse)
async def review_detail(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    record = db.query(ReviewRecord).filter(ReviewRecord.review_id == review_id).first()
    if not record or (user.role != "admin" and record.lecturer_id != user.id):
        raise HTTPException(status_code=404, detail="Review not found.")
    review = REVIEW_CACHE.get(review_id) or load_review_json(review_id)
    return templates.TemplateResponse("review_detail.html", _template_context(request, user=user, record=record, review=review))


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/admin/login", status_code=303)
    if user.must_change_password:
        return RedirectResponse("/account/password", status_code=303)
    lecturers = db.query(User).filter(User.role == "lecturer").order_by(User.created_at.desc()).all()
    review_counts = dict(db.query(ReviewRecord.lecturer_id, func.count(ReviewRecord.id)).group_by(ReviewRecord.lecturer_id).all())
    recent_reviews = db.query(ReviewRecord).options(joinedload(ReviewRecord.lecturer)).order_by(ReviewRecord.created_at.desc()).limit(20).all()
    stats = {
        "lecturers": len(lecturers),
        "active": sum(1 for item in lecturers if item.is_active),
        "reviews": int(db.query(func.count(ReviewRecord.id)).scalar() or 0),
        "processing": int(db.query(func.count(ReviewRecord.id)).filter(ReviewRecord.status.in_(["queued", "processing"])).scalar() or 0),
    }
    credential_token = request.session.pop("credential_token", None)
    credentials = CREDENTIAL_FLASH.pop(credential_token, None) if credential_token else None
    return templates.TemplateResponse(
        "admin_dashboard.html",
        _template_context(request, user=user, lecturers=lecturers, review_counts=review_counts, recent_reviews=recent_reviews, stats=stats, credentials=credentials),
    )


@app.post("/admin/lecturers")
async def create_lecturer(
    request: Request,
    full_name: str = Form(...),
    username: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    department: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    admin = _current_user(request, db)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    full_name = full_name.strip()
    if len(full_name) < 3:
        _set_flash(request, "Enter the supervisor’s full name.", "error")
        return RedirectResponse("/admin", status_code=303)
    preferred = username.strip() or suggest_username(full_name)
    final_username = unique_username(db, preferred)
    temporary_password = generate_temporary_password()
    recovery_pin = generate_recovery_pin()
    lecturer = User(
        username=final_username,
        password_hash=hash_secret(temporary_password),
        recovery_pin_hash=hash_secret(recovery_pin),
        role="lecturer",
        full_name=full_name,
        email=email.strip() or None,
        phone=phone.strip() or None,
        department=department.strip() or None,
        is_active=True,
        must_change_password=True,
    )
    db.add(lecturer)
    db.commit()
    token = secrets.token_urlsafe(24)
    CREDENTIAL_FLASH[token] = {
        "full_name": lecturer.full_name,
        "username": lecturer.username,
        "temporary_password": temporary_password,
        "recovery_pin": recovery_pin,
    }
    request.session["credential_token"] = token
    _set_flash(request, f"Account created for {lecturer.full_name}.", "success")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/lecturers/{lecturer_id}/toggle")
async def toggle_lecturer(
    lecturer_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    admin = _current_user(request, db)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    lecturer = db.get(User, lecturer_id)
    if not lecturer or lecturer.role != "lecturer":
        raise HTTPException(status_code=404, detail="Lecturer account not found.")
    lecturer.is_active = not lecturer.is_active
    db.commit()
    _set_flash(request, f"{lecturer.full_name} has been {'activated' if lecturer.is_active else 'suspended'}.", "success")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/lecturers/{lecturer_id}/reset")
async def reset_lecturer(
    lecturer_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    admin = _current_user(request, db)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    lecturer = db.get(User, lecturer_id)
    if not lecturer or lecturer.role != "lecturer":
        raise HTTPException(status_code=404, detail="Lecturer account not found.")
    temporary_password = generate_temporary_password()
    recovery_pin = generate_recovery_pin()
    lecturer.password_hash = hash_secret(temporary_password)
    lecturer.recovery_pin_hash = hash_secret(recovery_pin)
    lecturer.must_change_password = True
    lecturer.is_active = True
    db.commit()
    token = secrets.token_urlsafe(24)
    CREDENTIAL_FLASH[token] = {
        "full_name": lecturer.full_name,
        "username": lecturer.username,
        "temporary_password": temporary_password,
        "recovery_pin": recovery_pin,
    }
    request.session["credential_token"] = token
    _set_flash(request, f"New login details generated for {lecturer.full_name}.", "success")
    return RedirectResponse("/admin", status_code=303)


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


def _persist_job_update(job_id: str, **values: Any) -> None:
    try:
        with SessionLocal() as db:
            record = db.query(ReviewRecord).filter(ReviewRecord.job_id == job_id).first()
            if not record:
                return
            for key in ("status", "progress", "message", "error"):
                if key in values and hasattr(record, key):
                    setattr(record, key, values[key])
            if values.get("review_id"):
                record.review_id = values["review_id"]
            if values.get("status") == "completed":
                record.completed_at = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        logger.exception("Could not persist review job status")


def _job_update(job_id: str, *, status: Optional[str] = None, progress: Optional[int] = None, message: Optional[str] = None, **extra: Any) -> None:
    job = JOB_CACHE.setdefault(job_id, {})
    if status is not None:
        job["status"] = status
    if progress is not None:
        job["progress"] = max(0, min(100, int(progress)))
    if message is not None:
        job["message"] = message
    job.update(extra)
    job["updated_at"] = time.time()
    _persist_job_update(job_id, status=status, progress=progress, message=message, error=extra.get("error"), review_id=extra.get("review_id"))


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

        review = await asyncio.wait_for(
            enrich_review_with_academic_ai(
                review,
                runtime_context,
                requested_mode=payload["review_depth"],
                config=config,
                progress_callback=progress_callback,
            ),
            timeout=AI_JOB_MAX_SECONDS,
        )
        if review.get("ai_review"):
            AI_USAGE_CACHE[review["review_id"]] = dict(review["ai_review"])
        review = _strip_internal_ai_metadata(review)
        review["summary"]["annotated_document_available"] = payload["filename"].lower().endswith(".docx")

        annotated_data = None
        if review["summary"]["annotated_document_available"]:
            try:
                annotated_data = build_annotated_docx(payload["data"], review)
                ANNOTATED_CACHE[review["review_id"]] = annotated_data
                save_annotated(review["review_id"], annotated_data)
            except Exception:
                logger.exception("Annotated document generation failed")
                review["summary"]["annotated_document_available"] = False
                review["summary"]["annotation_warning"] = "The review completed, but the annotated document could not be generated."

        REVIEW_CACHE[review["review_id"]] = review
        save_review_json(review["review_id"], review)
        with SessionLocal() as db:
            record = db.query(ReviewRecord).filter(ReviewRecord.job_id == job_id).first()
            if record:
                summary = review.get("summary") or {}
                record.review_id = review["review_id"]
                record.status = "completed"
                record.progress = 100
                record.message = "Review complete"
                record.overall_score = float(summary.get("overall_score") or 0)
                record.readiness_label = summary.get("readiness_label")
                record.annotated_available = bool(summary.get("annotated_document_available"))
                record.completed_at = datetime.now(timezone.utc)
                db.commit()
        _job_update(
            job_id,
            status="completed",
            progress=100,
            message="Review complete",
            review_id=review["review_id"],
            result_url=f'/api/review/{review["review_id"]}',
        )
    except (ValueError, AIConfigurationError) as exc:
        _job_update(job_id, status="failed", progress=100, message="Review could not start", error=str(exc), retryable=False)
    except asyncio.TimeoutError:
        logger.exception("Background review exceeded the maximum processing time")
        _job_update(
            job_id,
            status="failed",
            progress=100,
            message="The review exceeded the maximum processing time",
            error="The review did not finish within the allowed processing window. Please retry with a smaller document or contact the administrator.",
            retryable=True,
        )
    except AIProviderError:
        logger.exception("Expert review provider failure")
        _job_update(job_id, status="failed", progress=100, message="The expert review service was temporarily unable to finish", error="The expert review could not be completed. Please retry in a few minutes.", retryable=True)
    except Exception:
        logger.exception("Unexpected background review failure")
        _job_update(job_id, status="failed", progress=100, message="Review failed", error="The review could not be completed. Please try again.", retryable=True)


@app.post("/api/review", status_code=202)
async def create_review(
    request: Request,
    file: UploadFile = File(...), academic_level: str = Form(...), research_approach: str = Form(...),
    review_scope: str = Form("chapter"), selected_chapter: int = Form(0), document_type: str = Form("chapter_one"),
    submission_stage: str = Form("initial"), review_depth: str = Form("standard"), csrf_token: str = Form(...),
    previous_files: Optional[List[UploadFile]] = File(None), supervisor_comment_files: Optional[List[UploadFile]] = File(None),
    supervisor_comments_text: str = Form(""), original_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    user = _current_user(request, db)
    if not user or user.role not in {"lecturer", "admin"}:
        raise HTTPException(status_code=401, detail="Sign in to submit a review.")
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Change your temporary password before submitting a review.")
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
    record = ReviewRecord(
        job_id=job_id,
        lecturer_id=user.id,
        filename=filename,
        academic_level=academic_level,
        research_approach=research_approach,
        review_scope=review_scope,
        selected_chapter=selected_chapter or None,
        review_depth=review_depth,
        submission_stage=submission_stage,
        status="queued",
        progress=2,
        message="Review queued",
    )
    db.add(record)
    db.commit()

    JOB_CACHE[job_id] = {"job_id": job_id, "user_id": user.id, "status": "queued", "progress": 2, "message": "Review queued", "created_at": time.time(), "updated_at": time.time()}
    payload = {
        "filename": filename, "data": data, "academic_level": academic_level, "research_approach": research_approach,
        "review_scope": review_scope, "selected_chapter": selected_chapter, "document_type": document_type,
        "submission_stage": submission_stage, "review_depth": review_depth, "context_documents": context_documents,
        "supervisor_comment_documents": supervisor_comment_documents, "supervisor_comments_text": supervisor_comments_text,
        "original_document": original_document, "user_id": user.id,
    }
    task = asyncio.create_task(_run_review_job(job_id, payload))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return {"job_id": job_id, "status": "queued", "progress": 2, "message": "Review queued", "poll_url": f"/api/review/jobs/{job_id}"}


@app.get("/api/review/jobs/{job_id}")
async def get_review_job(job_id: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    job = JOB_CACHE.get(job_id)
    record = db.query(ReviewRecord).filter(ReviewRecord.job_id == job_id).first()
    if not record or (user.role != "admin" and record.lecturer_id != user.id):
        raise HTTPException(status_code=404, detail="Review job not found or expired.")
    if job:
        response = dict(job)
        if response.get("status") == "completed" and response.get("review_id"):
            response.setdefault("result_url", f'/api/review/{response["review_id"]}')
        return response
    response = {
        "job_id": record.job_id,
        "status": record.status,
        "progress": record.progress,
        "message": record.message,
        "error": record.error,
        "review_id": record.review_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }
    if record.status == "completed" and record.review_id:
        response["result_url"] = f"/api/review/{record.review_id}"
    return response


@app.get("/api/review/{review_id}")
async def get_review(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    record = db.query(ReviewRecord).filter(ReviewRecord.review_id == review_id).first()
    if not record or (user.role != "admin" and record.lecturer_id != user.id):
        raise HTTPException(status_code=404, detail="Review not found.")
    review = REVIEW_CACHE.get(review_id) or load_review_json(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review result not found or expired.")
    REVIEW_CACHE[review_id] = review
    return review


def _authorised_review_record(db: Session, user: User, review_id: str) -> ReviewRecord:
    record = db.query(ReviewRecord).filter(ReviewRecord.review_id == review_id).first()
    if not record or (user.role != "admin" and record.lecturer_id != user.id):
        raise HTTPException(status_code=404, detail="Review not found.")
    return record


@app.get("/api/review/{review_id}/annotated.docx")
async def export_annotated_document(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    record = _authorised_review_record(db, user, review_id)
    review = REVIEW_CACHE.get(review_id) or load_review_json(review_id)
    data = ANNOTATED_CACHE.get(review_id) or load_annotated(review_id)
    if not review or data is None:
        raise HTTPException(status_code=404, detail="Annotated DOCX is not available for this review.")
    ANNOTATED_CACHE[review_id] = data
    stem = os.path.splitext(os.path.basename(record.filename or "thesis.docx"))[0]
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="{stem}-supervisor-reviewed.docx"'})


@app.get("/api/review/{review_id}/export.docx")
async def export_review(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    _authorised_review_record(db, user, review_id)
    review = REVIEW_CACHE.get(review_id) or load_review_json(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or expired.")
    return Response(content=build_docx_report(review), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="supervisor-review-report.docx"'})
