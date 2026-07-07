from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from .academic_ai_engine import ReviewOutputValidationError, enrich_review_with_academic_ai
from .ai_config import AIConfigurationError, HybridAIConfig
from .ai_providers import AIProviderError
from .annotated_exporter import ANNOTATION_EXPORT_VERSION, build_annotated_docx, native_comment_count
from .inline_annotated_exporter import INLINE_ANNOTATION_EXPORT_VERSION, build_inline_annotated_docx
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
from .database import ReviewCheckpoint, ReviewRecord, SessionLocal, TokenLedger, User, get_db, init_db
from .checkpointing import (
    CheckpointManager,
    load_job_payload,
    payload_available,
    save_job_payload,
    stable_hash,
)
from .document_parser import clean_text
from .external_assessment import (
    ExternalAssessmentValidationError,
    enrich_with_external_assessment,
)
from .external_assessment_exporter import (
    build_confidential_recommendation,
    build_corrections_schedule,
    build_external_examination_report,
    build_oral_examination_questions,
)
from .report_exporter import build_docx_report
from .review_engine import analyse
from .storage import ensure_storage, load_annotated, load_review_json, save_annotated, save_review_json, storage_status
from .token_budget import (
    DEFAULT_SUPERVISOR_TOKENS,
    TOKEN_ACCOUNTING_ENABLED,
    TOKEN_QUOTA_ENFORCEMENT,
    TOKENS_PER_PAGE,
    RESERVED_TOKENS_PER_PAGE,
    adjust_allocation,
    allocation_to_tokens,
    estimate_document_pages,
    estimate_review_tokens,
    page_capacity,
    reserve_existing_review_tokens,
    reserve_review_tokens,
    release_review_reservation,
    settle_review_tokens,
    supervisor_capacity,
    usage_token_total,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_CONTEXT_FILES = 5
MAX_TOTAL_CONTEXT_BYTES = 75 * 1024 * 1024
AI_JOB_MAX_SECONDS = max(900, int(os.getenv("AI_JOB_MAX_SECONDS", "5400")))
JOB_HEARTBEAT_SECONDS = max(15, int(os.getenv("JOB_HEARTBEAT_SECONDS", "45")))
JOB_LEASE_SECONDS = max(
    JOB_HEARTBEAT_SECONDS * 3,
    int(os.getenv("JOB_LEASE_SECONDS", "240")),
)
JOB_STALE_AFTER_SECONDS = max(
    JOB_HEARTBEAT_SECONDS * 2,
    int(os.getenv("JOB_STALE_AFTER_SECONDS", "180")),
)
STAGE_STALE_AFTER_SECONDS = max(
    600,
    int(os.getenv("STAGE_STALE_AFTER_SECONDS", "1800")),
)
MAX_AUTO_RESUMES = max(1, int(os.getenv("MAX_AUTO_RESUMES", "4")))
AUTOMATIC_RETRY_DELAY_SECONDS = max(5, int(os.getenv("AUTOMATIC_RETRY_DELAY_SECONDS", "12")))
AUTOMATIC_RETRY_MAX_DELAY_SECONDS = max(30, int(os.getenv("AUTOMATIC_RETRY_MAX_DELAY_SECONDS", "90")))
AUTO_RESUME_JOBS = os.getenv("AUTO_RESUME_JOBS", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
WORKER_ID = f"{os.getenv('RENDER_INSTANCE_ID', 'local')}-{uuid.uuid4().hex[:10]}"
ALLOWED_EXTENSIONS = (".docx", ".pdf")
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-this-secret")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(
    title="ProjectReady AI Supervisor Assistant",
    version="1.9.8.6",
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
JOB_TASKS: Dict[str, asyncio.Task] = {}
RUNNING_JOB_IDS: set[str] = set()
SCHEDULED_JOB_IDS: set[str] = set()
LOGIN_ATTEMPTS: Dict[str, Dict[str, Any]] = {}
CREDENTIAL_FLASH: Dict[str, Dict[str, str]] = {}


@app.on_event("startup")
async def startup() -> None:
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
    if AUTO_RESUME_JOBS:
        await _resume_recoverable_jobs()


def _strip_internal_ai_metadata(review: dict) -> dict:
    review.pop("ai_review", None)
    review.pop("ai_document_map", None)
    review.pop("external_assessment_usage", None)
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
    return {
        "status": "ok",
        "service": "projectready-supervisor",
        "version": "1.9.2",
        "checkpoint_resume": True,
        "storage": storage_status(),
    }


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
    now = datetime.now(timezone.utc)
    for row in reviews:
        row.is_stalled = _is_stalled_record(db, row)
        last_activity = _stage_last_activity(db, row)
        row.stage_age_minutes = (
            int(max(0, (now - last_activity).total_seconds()) // 60)
            if last_activity
            else 0
        )
    total = len(reviews)
    completed = sum(1 for row in reviews if row.status == "completed")
    processing = sum(1 for row in reviews if row.status in {"queued", "processing", "paused"})
    revised = sum(1 for row in reviews if row.submission_stage == "revised")
    return templates.TemplateResponse(
        "portal.html",
        _template_context(
            request,
            user=user,
            reviews=reviews,
            stats={"total": total, "completed": completed, "processing": processing, "revised": revised},
            token_capacity=supervisor_capacity(user),
            token_accounting_enabled=TOKEN_ACCOUNTING_ENABLED,
        ),
    )


@app.get("/review", response_class=HTMLResponse)
async def review_workspace(request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.must_change_password:
        return RedirectResponse("/account/password", status_code=303)
    return templates.TemplateResponse("index.html", _template_context(request, user=user, token_capacity=supervisor_capacity(user), token_accounting_enabled=TOKEN_ACCOUNTING_ENABLED))


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
    token_capacities = {item.id: supervisor_capacity(item) for item in lecturers}
    token_ledger = (
        db.query(TokenLedger)
        .order_by(TokenLedger.created_at.desc())
        .limit(20)
        .all()
    )
    ledger_users = {
        item.id: item.full_name
        for item in db.query(User).filter(User.id.in_({row.lecturer_id for row in token_ledger} or {-1})).all()
    }
    recent_reviews = db.query(ReviewRecord).options(joinedload(ReviewRecord.lecturer)).order_by(ReviewRecord.created_at.desc()).limit(20).all()
    total_available_tokens = sum(int(item.token_balance or 0) for item in lecturers)
    total_reserved_tokens = sum(int(item.token_reserved_total or 0) for item in lecturers)
    total_used_tokens = sum(int(item.token_used_total or 0) for item in lecturers)
    stats = {
        "lecturers": len(lecturers),
        "active": sum(1 for item in lecturers if item.is_active),
        "reviews": int(db.query(func.count(ReviewRecord.id)).scalar() or 0),
        "processing": int(db.query(func.count(ReviewRecord.id)).filter(ReviewRecord.status.in_(["queued", "processing", "paused"])).scalar() or 0),
        "available_tokens": total_available_tokens,
        "reserved_tokens": total_reserved_tokens,
        "used_tokens": total_used_tokens,
        "standard_pages": page_capacity(total_available_tokens, "supervisory_standard"),
        "external_pages": page_capacity(total_available_tokens, "external_assessment"),
    }
    credential_token = request.session.pop("credential_token", None)
    credentials = CREDENTIAL_FLASH.pop(credential_token, None) if credential_token else None
    return templates.TemplateResponse(
        "admin_dashboard.html",
        _template_context(request, user=user, lecturers=lecturers, review_counts=review_counts, recent_reviews=recent_reviews, stats=stats, credentials=credentials, token_capacities=token_capacities, token_ledger=token_ledger, ledger_users=ledger_users, token_rates=TOKENS_PER_PAGE, token_capacity_rates=RESERVED_TOKENS_PER_PAGE, token_accounting_enabled=TOKEN_ACCOUNTING_ENABLED, token_quota_enforcement=TOKEN_QUOTA_ENFORCEMENT),
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
        token_balance=0,
        token_allocated_total=0,
    )
    db.add(lecturer)
    db.flush()
    if DEFAULT_SUPERVISOR_TOKENS > 0:
        adjust_allocation(
            db,
            user=lecturer,
            token_amount=DEFAULT_SUPERVISOR_TOKENS,
            mode="add",
            note="Default allocation for new supervisor account",
            created_by_user_id=admin.id,
        )
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


@app.post("/admin/lecturers/{lecturer_id}/tokens")
async def allocate_lecturer_tokens(
    lecturer_id: int,
    request: Request,
    amount: int = Form(...),
    unit: str = Form("tokens"),
    mode: str = Form("add"),
    note: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    admin = _current_user(request, db)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    lecturer = (
        db.query(User)
        .filter(User.id == lecturer_id, User.role == "lecturer")
        .with_for_update()
        .first()
    )
    if not lecturer:
        raise HTTPException(status_code=404, detail="Supervisor account not found.")
    try:
        token_amount = allocation_to_tokens(amount, unit)
        delta = adjust_allocation(
            db,
            user=lecturer,
            token_amount=token_amount,
            mode=mode,
            note=clean_text(note) or f"Administrator {mode} allocation",
            created_by_user_id=admin.id,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        _set_flash(request, str(exc), "error")
        return RedirectResponse("/admin#token-allocation", status_code=303)
    capacity = supervisor_capacity(lecturer)
    _set_flash(
        request,
        f"{lecturer.full_name}'s available balance changed by {delta:+,} tokens. "
        f"The current allocation supports about {capacity['standard_pages']:,} standard supervisory pages "
        f"or {capacity['external_pages']:,} external-examination pages.",
        "success",
    )
    return RedirectResponse("/admin#token-allocation", status_code=303)


@app.post("/admin/tokens/bulk")
async def bulk_allocate_tokens(
    request: Request,
    amount: int = Form(...),
    unit: str = Form("tokens"),
    mode: str = Form("add"),
    target: str = Form("active"),
    department: str = Form(""),
    note: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    admin = _current_user(request, db)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    query = db.query(User).filter(User.role == "lecturer")
    if target == "active":
        query = query.filter(User.is_active.is_(True))
    elif target == "department":
        department_value = clean_text(department)
        if not department_value:
            _set_flash(request, "Enter the department or school for the bulk allocation.", "error")
            return RedirectResponse("/admin#token-allocation", status_code=303)
        query = query.filter(func.lower(User.department) == department_value.lower())
    elif target != "all":
        _set_flash(request, "Choose active supervisors, all supervisors or one department.", "error")
        return RedirectResponse("/admin#token-allocation", status_code=303)
    lecturers = query.with_for_update().all()
    if not lecturers:
        _set_flash(request, "No supervisors matched the bulk-allocation target.", "error")
        return RedirectResponse("/admin#token-allocation", status_code=303)
    try:
        token_amount = allocation_to_tokens(amount, unit)
        for lecturer in lecturers:
            adjust_allocation(
                db,
                user=lecturer,
                token_amount=token_amount,
                mode=mode,
                note=clean_text(note) or f"Bulk {mode} allocation",
                created_by_user_id=admin.id,
            )
        db.commit()
    except ValueError as exc:
        db.rollback()
        _set_flash(request, str(exc), "error")
        return RedirectResponse("/admin#token-allocation", status_code=303)
    _set_flash(
        request,
        f"Token allocation updated for {len(lecturers)} supervisor account(s).",
        "success",
    )
    return RedirectResponse("/admin#token-allocation", status_code=303)


@app.post("/admin/reviews/{record_id}/release-token-reservation")
async def release_abandoned_review_tokens(
    record_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    admin = _current_user(request, db)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    record = (
        db.query(ReviewRecord)
        .filter(ReviewRecord.id == record_id)
        .with_for_update()
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Review record not found.")
    if record.status not in {"failed", "stopped"}:
        _set_flash(
            request,
            "Reserved tokens can be released only for a failed or stopped review.",
            "error",
        )
        return RedirectResponse("/admin#recent-reviews", status_code=303)
    lecturer = db.get(User, record.lecturer_id)
    if not lecturer or record.token_accounting_status != "reserved":
        _set_flash(request, "This review has no active token reservation.", "info")
        return RedirectResponse("/admin#recent-reviews", status_code=303)
    amount = int(record.token_reserved or 0)
    release_review_reservation(
        db,
        record=record,
        user=lecturer,
        note=f"Administrator released abandoned reservation for {record.filename}",
    )
    db.commit()
    _set_flash(
        request,
        f"Released {amount:,} tokens to {lecturer.full_name}'s available balance.",
        "success",
    )
    return RedirectResponse("/admin#recent-reviews", status_code=303)


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
            record = (
                db.query(ReviewRecord)
                .filter(ReviewRecord.job_id == job_id)
                .first()
            )
            if not record:
                return

            incoming_progress = values.get("progress")
            if incoming_progress is not None:
                incoming_progress = max(
                    0,
                    min(100, int(incoming_progress)),
                )
                record.progress = max(
                    int(record.progress or 0),
                    incoming_progress,
                )

            for key in (
                "status",
                "message",
                "error",
                "current_stage",
                "lease_owner",
            ):
                if (
                    key in values
                    and values[key] is not None
                    and hasattr(record, key)
                ):
                    setattr(record, key, values[key])

            for key in (
                "recoverable",
                "payload_available",
            ):
                if key in values and values[key] is not None:
                    setattr(record, key, bool(values[key]))

            for key in ("checkpoint_count", "resume_count"):
                if key in values and values[key] is not None:
                    setattr(record, key, int(values[key]))

            for key in (
                "last_heartbeat_at",
                "lease_expires_at",
                "started_at",
            ):
                if key in values and values[key] is not None:
                    setattr(record, key, values[key])

            if values.get("review_id"):
                record.review_id = values["review_id"]
            if values.get("status") == "completed":
                record.completed_at = datetime.now(timezone.utc)
                record.recoverable = False
                record.lease_owner = None
                record.lease_expires_at = None
            db.commit()
    except Exception:
        logger.exception("Could not persist review job status")


def _job_update(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    **extra: Any,
) -> None:
    job = JOB_CACHE.setdefault(job_id, {})
    current_progress = max(
        0,
        min(100, int(job.get("progress") or 0)),
    )
    effective_progress: Optional[int] = None
    accepted_message = message

    if status is not None:
        job["status"] = status

    if progress is not None:
        incoming_progress = max(0, min(100, int(progress)))
        effective_progress = max(current_progress, incoming_progress)
        job["progress"] = effective_progress

        if incoming_progress < current_progress:
            accepted_message = None

    if accepted_message is not None:
        job["message"] = accepted_message

    job.update(extra)
    job["updated_at"] = time.time()

    _persist_job_update(
        job_id,
        status=status,
        progress=effective_progress,
        message=accepted_message,
        error=extra.get("error"),
        review_id=extra.get("review_id"),
        current_stage=extra.get("current_stage"),
        recoverable=extra.get("recoverable"),
        payload_available=extra.get("payload_available"),
        checkpoint_count=extra.get("checkpoint_count"),
        resume_count=extra.get("resume_count"),
        last_heartbeat_at=extra.get("last_heartbeat_at"),
        lease_owner=extra.get("lease_owner"),
        lease_expires_at=extra.get("lease_expires_at"),
        started_at=extra.get("started_at"),
    )


def _normalise_db_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _claim_job(job_id: str, *, resumed: bool) -> bool:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        record = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.job_id == job_id)
            .with_for_update()
            .first()
        )
        if not record or record.status == "completed":
            return False
        lease_expires = _normalise_db_datetime(record.lease_expires_at)
        if (
            record.lease_owner
            and record.lease_owner != WORKER_ID
            and lease_expires
            and lease_expires > now
        ):
            return False
        record.lease_owner = WORKER_ID
        record.lease_expires_at = now + timedelta(seconds=JOB_LEASE_SECONDS)
        record.last_heartbeat_at = now
        record.started_at = record.started_at or now
        record.status = "processing"
        record.recoverable = True
        if resumed:
            record.resume_count = int(record.resume_count or 0) + 1
        db.commit()
        JOB_CACHE[job_id] = {
            "job_id": job_id,
            "user_id": record.lecturer_id,
            "status": "processing",
            "progress": int(record.progress or 2),
            "message": record.message or "Resuming saved review",
            "current_stage": record.current_stage,
            "checkpoint_count": int(record.checkpoint_count or 0),
            "resume_count": int(record.resume_count or 0),
            "recoverable": True,
            "created_at": record.created_at.timestamp() if record.created_at else time.time(),
            "updated_at": time.time(),
        }
    return True




def _stage_last_activity(db: Session, record: ReviewRecord) -> Optional[datetime]:
    if not record.current_stage:
        return _normalise_db_datetime(record.started_at or record.created_at)
    checkpoint = (
        db.query(ReviewCheckpoint)
        .filter(
            ReviewCheckpoint.job_id == record.job_id,
            ReviewCheckpoint.stage_key == record.current_stage,
        )
        .first()
    )
    value = checkpoint.updated_at if checkpoint else (record.started_at or record.created_at)
    return _normalise_db_datetime(value)


def _is_stalled_record(db: Session, record: ReviewRecord) -> bool:
    if record.status != "processing":
        return False
    last_activity = _stage_last_activity(db, record)
    if not last_activity:
        return False
    return (datetime.now(timezone.utc) - last_activity).total_seconds() >= STAGE_STALE_AFTER_SECONDS


def _assert_job_lease(job_id: str) -> None:
    with SessionLocal() as db:
        record = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.job_id == job_id)
            .first()
        )
        if (
            not record
            or record.status != "processing"
            or record.lease_owner != WORKER_ID
        ):
            raise asyncio.CancelledError()


def _release_job_lease(job_id: str) -> None:
    with SessionLocal() as db:
        record = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.job_id == job_id)
            .first()
        )
        if record and record.lease_owner == WORKER_ID:
            record.lease_owner = None
            record.lease_expires_at = None
            db.commit()


def _heartbeat_job(job_id: str) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        record = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.job_id == job_id)
            .first()
        )
        if not record or record.status != "processing":
            return
        if record.lease_owner not in {None, WORKER_ID}:
            return
        record.lease_owner = WORKER_ID
        record.last_heartbeat_at = now
        record.lease_expires_at = now + timedelta(seconds=JOB_LEASE_SECONDS)
        db.commit()
    _job_update(
        job_id,
        last_heartbeat_at=now,
        lease_owner=WORKER_ID,
        lease_expires_at=now + timedelta(seconds=JOB_LEASE_SECONDS),
    )


async def _heartbeat_loop(job_id: str) -> None:
    while job_id in RUNNING_JOB_IDS:
        await asyncio.sleep(JOB_HEARTBEAT_SECONDS)
        try:
            _heartbeat_job(job_id)
        except Exception:
            logger.exception("Could not update heartbeat for review job %s", job_id)


def _schedule_review_job(
    job_id: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    resumed: bool,
) -> bool:
    if job_id in RUNNING_JOB_IDS or job_id in SCHEDULED_JOB_IDS:
        return False
    if payload is None:
        try:
            payload = load_job_payload(job_id)
        except Exception:
            logger.exception("Could not load the saved payload for job %s", job_id)
            payload = None
    if not payload:
        _job_update(
            job_id,
            status="failed",
            message="The saved review files are unavailable",
            error=(
                "The review cannot resume because its uploaded files are not "
                "available in persistent storage. Submit the document again."
            ),
            recoverable=False,
        )
        return False

    SCHEDULED_JOB_IDS.add(job_id)
    task = asyncio.create_task(
        _run_review_job(job_id, payload, resumed=resumed)
    )
    JOB_TASKS[job_id] = task
    BACKGROUND_TASKS.add(task)

    def _cleanup(completed: asyncio.Task) -> None:
        SCHEDULED_JOB_IDS.discard(job_id)
        JOB_TASKS.pop(job_id, None)
        BACKGROUND_TASKS.discard(completed)

    task.add_done_callback(_cleanup)
    return True


async def _resume_after_lease(job_id: str, delay_seconds: float) -> None:
    await asyncio.sleep(max(1.0, delay_seconds))
    _schedule_review_job(job_id, resumed=True)


async def _resume_recoverable_jobs() -> None:
    with SessionLocal() as db:
        records = (
            db.query(ReviewRecord)
            .filter(
                ReviewRecord.status.in_(["queued", "processing", "paused"]),
                ReviewRecord.recoverable.is_(True),
                ReviewRecord.payload_available.is_(True),
                ReviewRecord.resume_count < MAX_AUTO_RESUMES,
            )
            .order_by(ReviewRecord.created_at.asc())
            .limit(100)
            .all()
        )
        job_ids = [record.job_id for record in records]
    now = datetime.now(timezone.utc)
    for job_id in job_ids:
        if not payload_available(job_id):
            continue
        with SessionLocal() as db:
            record = (
                db.query(ReviewRecord)
                .filter(ReviewRecord.job_id == job_id)
                .first()
            )
            lease_expires = _normalise_db_datetime(
                record.lease_expires_at if record else None
            )
        if lease_expires and lease_expires > now:
            delay = (lease_expires - now).total_seconds() + 1
            task = asyncio.create_task(
                _resume_after_lease(job_id, delay)
            )
            BACKGROUND_TASKS.add(task)
            task.add_done_callback(BACKGROUND_TASKS.discard)
        else:
            _schedule_review_job(job_id, resumed=True)


async def _delayed_auto_resume(job_id: str) -> None:
    """Retry a recoverable job without exposing an automatic Paused state.

    Transient provider, timeout and validation failures are queued and retried
    from durable checkpoints. Only an explicit user stop creates a Stopped job.
    Exhausted automatic retries become Failed with a manual Recover action.
    """
    with SessionLocal() as db:
        record = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.job_id == job_id)
            .first()
        )
        attempt = int(record.resume_count or 0) if record else 0
    delay = min(
        AUTOMATIC_RETRY_MAX_DELAY_SECONDS,
        AUTOMATIC_RETRY_DELAY_SECONDS * (2 ** min(attempt, 3)),
    )
    await asyncio.sleep(delay)
    with SessionLocal() as db:
        record = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.job_id == job_id)
            .first()
        )
        if (
            not record
            or record.status != "queued"
            or not record.recoverable
            or int(record.resume_count or 0) >= MAX_AUTO_RESUMES
        ):
            return
    _schedule_review_job(job_id, resumed=True)


def _queue_automatic_retry(
    job_id: str,
    *,
    message: str,
    error: str,
    current_stage: str,
    checkpoint_count: int,
) -> bool:
    """Queue a transient failure for automatic checkpoint recovery.

    Returns True when an automatic retry was scheduled. If the retry budget is
    exhausted, the job is marked Failed rather than Paused so the user is never
    trapped in an automatic pause/resume loop.
    """
    with SessionLocal() as db:
        record = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.job_id == job_id)
            .first()
        )
        attempts = int(record.resume_count or 0) if record else 0
    saved_payload_available = payload_available(job_id)
    can_retry = (
        AUTO_RESUME_JOBS
        and saved_payload_available
        and attempts < MAX_AUTO_RESUMES
    )
    if can_retry:
        _job_update(
            job_id,
            status="queued",
            message=message,
            error=error,
            current_stage=current_stage,
            checkpoint_count=checkpoint_count,
            retryable=True,
            recoverable=True,
            payload_available=True,
            resume_url=f"/api/review/jobs/{job_id}/resume",
        )
        asyncio.create_task(_delayed_auto_resume(job_id))
        return True

    _job_update(
        job_id,
        status="failed",
        message="Automatic recovery could not complete the review",
        error=(
            error
            + " The upload and completed checkpoints remain available. "
              "Select Recover once after checking the API key, quota and model access."
        ),
        current_stage=current_stage,
        checkpoint_count=checkpoint_count,
        retryable=saved_payload_available,
        recoverable=saved_payload_available,
        payload_available=saved_payload_available,
        resume_url=(
            f"/api/review/jobs/{job_id}/resume"
            if saved_payload_available else None
        ),
    )
    return False


def _assessment_review_depth(academic_level: str) -> str:
    value = clean_text(academic_level).lower()
    if value in {"phd", "professional doctorate"} or "doctor" in value:
        return "advanced"
    if "research masters" in value or "mphil" in value:
        return "standard"
    return "light"


async def _run_review_job(
    job_id: str,
    payload: Dict[str, Any],
    *,
    resumed: bool = False,
) -> None:
    SCHEDULED_JOB_IDS.discard(job_id)
    if job_id in RUNNING_JOB_IDS:
        return
    if not _claim_job(job_id, resumed=resumed):
        return

    RUNNING_JOB_IDS.add(job_id)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(job_id))
    document_hash = str(payload.get("document_hash") or "")
    payload_hash = str(
        payload.get("payload_hash")
        or stable_hash({
            "document_hash": document_hash,
            "filename": payload.get("filename"),
            "academic_level": payload.get("academic_level"),
            "research_approach": payload.get("research_approach"),
            "workflow_type": payload.get("workflow_type"),
            "review_scope": payload.get("review_scope"),
            "selected_chapter": payload.get("selected_chapter"),
            "combined_chapter_end": payload.get("combined_chapter_end"),
            "submission_stage": payload.get("submission_stage"),
            "review_depth": payload.get("review_depth"),
        })
    )
    checkpoints = CheckpointManager(job_id, document_hash)
    current_stage = "pipeline-start"

    try:
        usage_snapshot: Dict[str, Any] = {}
        _job_update(
            job_id,
            status="processing",
            progress=(
                max(8, int(JOB_CACHE.get(job_id, {}).get("progress") or 0))
                if resumed else 8
            ),
            message=(
                "Resuming the review from its last saved checkpoint"
                if resumed
                else "Reading and organising the uploaded documents"
            ),
            current_stage=current_stage,
            recoverable=True,
            payload_available=True,
            started_at=datetime.now(timezone.utc),
        )

        final_hash = stable_hash({
            "pipeline": "review-pipeline-v1.9.8.6-final-degree-quality-gate",
            "payload_hash": payload_hash,
            "workflow_type": payload.get("workflow_type"),
            "assessment_metadata": payload.get("assessment_metadata") or {},
        })
        reviewer_name = clean_text(
            (payload.get("assessment_metadata") or {}).get("examiner_name")
        )
        final_checkpoint = checkpoints.load(
            "pipeline-final",
            expected_input_hash=final_hash,
        )

        if final_checkpoint:
            review = dict(final_checkpoint["review"])
            usage_snapshot = dict(final_checkpoint.get("usage_snapshot") or {})
            runtime_context: Dict[str, Any] = {}
            _job_update(
                job_id,
                progress=97,
                message="Restored the completed review from its saved checkpoint",
                current_stage="pipeline-final",
                checkpoint_count=checkpoints.completed_count(),
            )
        else:
            analysis_hash = stable_hash({
                "pipeline": "document-analysis-v1.9.1-tiered-openai",
                "payload_hash": payload_hash,
            })
            current_stage = "document-analysis"
            analysis_checkpoint = checkpoints.load(
                current_stage,
                expected_input_hash=analysis_hash,
            )
            if analysis_checkpoint:
                review = dict(analysis_checkpoint["review"])
                runtime_context = dict(
                    analysis_checkpoint.get("runtime_context") or {}
                )
                _job_update(
                    job_id,
                    progress=22,
                    message="Restored document extraction and structural analysis",
                    current_stage=current_stage,
                    checkpoint_count=checkpoints.completed_count(),
                )
            else:
                checkpoints.mark_running(
                    current_stage,
                    input_hash=analysis_hash,
                    progress=8,
                    message="Extracting the document and building the thesis map",
                )
                review = await asyncio.to_thread(
                    analyse,
                    payload["data"],
                    payload["filename"],
                    academic_level=payload["academic_level"],
                    research_approach=payload["research_approach"],
                    selected_chapter=payload["selected_chapter"] or None,
                    combined_chapter_end=(
                        payload.get("combined_chapter_end") or None
                    ),
                    review_scope=payload["review_scope"],
                    document_type=payload["document_type"],
                    context_documents=payload["context_documents"],
                    submission_stage=payload["submission_stage"],
                    supervisor_comment_documents=payload[
                        "supervisor_comment_documents"
                    ],
                    supervisor_comments_text=payload[
                        "supervisor_comments_text"
                    ],
                    original_document=payload["original_document"],
                )
                runtime_context = review.pop("_runtime_context", {})
                checkpoints.save(
                    current_stage,
                    {
                        "review": review,
                        "runtime_context": runtime_context,
                    },
                    input_hash=analysis_hash,
                    progress=22,
                    message="Document extraction and thesis map completed",
                )
                _job_update(
                    job_id,
                    progress=22,
                    message="Preparing the academic review",
                    current_stage=current_stage,
                    checkpoint_count=checkpoints.completed_count(),
                )

            config = HybridAIConfig.from_env()

            async def progress_callback(value: int, message: str) -> None:
                _assert_job_lease(job_id)
                # On an automatic retry, retain the highest displayed progress
                # while still showing the live stage message. This prevents the
                # portal from appearing frozen at the previous percentage.
                display_value = max(
                    int(value),
                    int(JOB_CACHE.get(job_id, {}).get("progress") or 0),
                )
                _job_update(
                    job_id,
                    progress=display_value,
                    message=message,
                    current_stage=current_stage,
                    checkpoint_count=checkpoints.completed_count(),
                )

            academic_hash = stable_hash({
                "pipeline": "academic-review-complete-v1.9.8.6-final-degree-quality-gate",
                "analysis_hash": analysis_hash,
                "review_depth": payload["review_depth"],
                "chapter_model": config.openai_chapter_model,
                "expert_model": config.openai_expert_model,
                "final_audit_model": config.openai_final_audit_model,
                "chapter_reasoning_effort": config.openai_chapter_reasoning_effort,
                "expert_reasoning_effort": config.openai_expert_reasoning_effort,
                "final_audit_reasoning_effort": config.openai_final_audit_reasoning_effort,
                "quality_control": config.advanced_quality_control,
            })
            current_stage = "academic-review-complete"
            academic_checkpoint = checkpoints.load(
                current_stage,
                expected_input_hash=academic_hash,
            )
            if academic_checkpoint:
                review = dict(academic_checkpoint["review"])
                _job_update(
                    job_id,
                    progress=86,
                    message="Restored the completed academic review",
                    current_stage=current_stage,
                    checkpoint_count=checkpoints.completed_count(),
                )
            else:
                checkpoints.mark_running(
                    current_stage,
                    input_hash=academic_hash,
                    progress=22,
                    message="Running the section-level academic review",
                )
                review = await asyncio.wait_for(
                    enrich_review_with_academic_ai(
                        review,
                        runtime_context,
                        requested_mode=payload["review_depth"],
                        config=config,
                        progress_callback=progress_callback,
                        checkpoint_manager=checkpoints,
                        retry_generation=int(JOB_CACHE.get(job_id, {}).get("resume_count") or 0),
                    ),
                    timeout=AI_JOB_MAX_SECONDS,
                )
                checkpoints.save(
                    current_stage,
                    {"review": review},
                    input_hash=academic_hash,
                    progress=86,
                    message="Academic review completed",
                )

            if payload.get("workflow_type") == "external_assessment":
                external_hash = stable_hash({
                    "pipeline": "external-assessment-complete-v1.9.6-three-examiners-one-adjudicator",
                    "academic_hash": academic_hash,
                    "assessment_metadata": payload.get(
                        "assessment_metadata"
                    ) or {},
                    "assessment_stage": payload.get("assessment_stage"),
                })
                current_stage = "external-assessment-complete"
                external_checkpoint = checkpoints.load(
                    current_stage,
                    expected_input_hash=external_hash,
                )
                if external_checkpoint:
                    review = dict(external_checkpoint["review"])
                    _job_update(
                        job_id,
                        progress=97,
                        message="Restored the completed external assessment",
                        current_stage=current_stage,
                        checkpoint_count=checkpoints.completed_count(),
                    )
                else:
                    checkpoints.mark_running(
                        current_stage,
                        input_hash=external_hash,
                        progress=86,
                        message="Preparing the external examination judgement",
                    )
                    review = await asyncio.wait_for(
                        enrich_with_external_assessment(
                            review,
                            runtime_context,
                            metadata=(
                                payload.get("assessment_metadata") or {}
                            ),
                            config=config,
                            progress_callback=progress_callback,
                            checkpoint_manager=checkpoints,
                            retry_generation=int(JOB_CACHE.get(job_id, {}).get("resume_count") or 0),
                        ),
                        timeout=AI_JOB_MAX_SECONDS,
                    )
                    checkpoints.save(
                        current_stage,
                        {"review": review},
                        input_hash=external_hash,
                        progress=97,
                        message="External assessment completed",
                    )
            else:
                review.setdefault("summary", {}).update({
                    "workflow_type": "supervisory_review",
                    "workflow_label": "Supervisory Review",
                    "external_assessment_available": False,
                })

            usage_snapshot = dict(review.get("ai_review") or {})
            if usage_snapshot:
                AI_USAGE_CACHE[review["review_id"]] = usage_snapshot
            review = _strip_internal_ai_metadata(review)
            if reviewer_name:
                review.setdefault("summary", {})["reviewer_name"] = reviewer_name
            is_external = (
                payload.get("workflow_type") == "external_assessment"
            )
            actionable_findings = [
                row for row in review.get("academic_findings") or []
                if row.get("status") in {
                    "partly_meets_requirement",
                    "does_not_meet_requirement",
                    "manual_review_required",
                }
                and row.get("annotation_eligible") is not False
            ]
            review["summary"]["annotated_document_available"] = (
                not is_external
                and payload["filename"].lower().endswith(".docx")
                and bool(actionable_findings)
            )
            if not is_external and not actionable_findings:
                review["summary"]["annotation_warning"] = (
                    "No grounded actionable comments were available for annotation. "
                    "The review must be rebuilt rather than downloading an empty annotated document."
                )
                review["summary"]["review_rebuild_recommended"] = True
            review["summary"].update({
                "checkpoint_resume_enabled": True,
                "checkpoint_count": checkpoints.completed_count(),
                "resumed_job": resumed,
                "partial_report_generated": False,
            })
            checkpoints.save(
                "pipeline-final",
                {"review": review, "usage_snapshot": usage_snapshot},
                input_hash=final_hash,
                progress=97,
                message="Final review data assembled",
            )

        if reviewer_name:
            review.setdefault("summary", {})["reviewer_name"] = reviewer_name

        current_stage = "document-export"
        _job_update(
            job_id,
            progress=98,
            message="Generating and saving the final review documents",
            current_stage=current_stage,
            checkpoint_count=checkpoints.completed_count(),
        )

        if review["summary"].get("annotated_document_available"):
            annotation_is_current = (
                review["summary"].get("annotation_export_version")
                == ANNOTATION_EXPORT_VERSION
            )
            annotated_data = (
                load_annotated(review["review_id"])
                if annotation_is_current
                else None
            )
            if annotated_data is None:
                try:
                    annotated_data = await asyncio.to_thread(
                        build_annotated_docx,
                        payload["data"],
                        review,
                        reviewer_name or None,
                    )
                    if native_comment_count(annotated_data) < 1:
                        raise RuntimeError(
                            "The annotated DOCX was generated without native Word comments."
                        )
                    ANNOTATED_CACHE[review["review_id"]] = annotated_data
                    save_annotated(review["review_id"], annotated_data)
                    review["summary"].update({
                        "annotation_export_version": ANNOTATION_EXPORT_VERSION,
                        "annotation_mode": "native_word_comments",
                    })
                    review["summary"].pop("annotation_warning", None)
                except Exception:
                    logger.exception("Annotated document generation failed")
                    review["summary"][
                        "annotated_document_available"
                    ] = False
                    review["summary"]["annotation_warning"] = (
                        "The review completed, but the native-comment "
                        "annotated document could not be generated."
                    )
            else:
                ANNOTATED_CACHE[review["review_id"]] = annotated_data

        _assert_job_lease(job_id)
        REVIEW_CACHE[review["review_id"]] = review
        await asyncio.to_thread(
            save_review_json,
            review["review_id"],
            review,
        )

        with SessionLocal() as db:
            record = (
                db.query(ReviewRecord)
                .filter(ReviewRecord.job_id == job_id)
                .first()
            )
            if record:
                summary = review.get("summary") or {}
                record.review_id = review["review_id"]
                record.status = "completed"
                record.progress = 100
                record.message = (
                    "External assessment complete"
                    if payload.get("workflow_type")
                    == "external_assessment"
                    else "Review complete"
                )
                record.current_stage = "completed"
                record.checkpoint_count = checkpoints.completed_count()
                record.recoverable = bool(
                    summary.get("review_rebuild_recommended")
                    and payload_available(job_id)
                )
                record.overall_score = float(
                    summary.get("overall_score") or 0
                )
                record.readiness_label = summary.get("readiness_label")
                record.annotated_available = bool(
                    summary.get("annotated_document_available")
                )
                record.completed_at = datetime.now(timezone.utc)
                record.lease_owner = None
                record.lease_expires_at = None
                accounting_user = db.get(User, record.lecturer_id)
                if accounting_user:
                    effective_usage = usage_snapshot or AI_USAGE_CACHE.get(review["review_id"]) or {}
                    settle_review_tokens(
                        db,
                        record=record,
                        user=accounting_user,
                        actual_tokens=usage_token_total(effective_usage),
                    )
                db.commit()

        _job_update(
            job_id,
            status="completed",
            progress=100,
            message=(
                "External assessment complete"
                if payload.get("workflow_type") == "external_assessment"
                else "Review complete"
            ),
            current_stage="completed",
            checkpoint_count=checkpoints.completed_count(),
            recoverable=bool(
                review.get("summary", {}).get("review_rebuild_recommended")
                and payload_available(job_id)
            ),
            review_id=review["review_id"],
            result_url=f'/api/review/{review["review_id"]}',
        )

    except asyncio.CancelledError:
        # A user-triggered stop writes the durable ``stopped`` status before
        # cancelling this task. Service shutdowns leave the job recoverable.
        with SessionLocal() as db:
            record = (
                db.query(ReviewRecord)
                .filter(ReviewRecord.job_id == job_id)
                .first()
            )
            if record and record.status != "stopped":
                record.status = "queued"
                record.message = "Review interrupted safely and queued for automatic recovery"
                record.recoverable = bool(payload_available(job_id))
                record.lease_owner = None
                record.lease_expires_at = None
                db.commit()
        raise
    except ExternalAssessmentValidationError as exc:
        detail = clean_text(str(exc))
        checkpoints.mark_failed(current_stage, detail)
        _queue_automatic_retry(
            job_id,
            message="Rechecking external-assessment evidence automatically",
            error=(
                detail
                + " The current examiner stage will be regenerated from the saved evidence packet."
            ),
            current_stage=current_stage,
            checkpoint_count=checkpoints.completed_count(),
        )
    except ReviewOutputValidationError as exc:
        detail = clean_text(str(exc))
        checkpoints.mark_failed(current_stage, detail)
        _queue_automatic_retry(
            job_id,
            message="Rebuilding grounded review comments automatically",
            error=(
                detail
                + " A fresh expert pass will run using the saved document map and exact evidence anchors."
            ),
            current_stage=current_stage,
            checkpoint_count=checkpoints.completed_count(),
        )
    except (ValueError, AIConfigurationError) as exc:
        checkpoints.mark_failed(current_stage, str(exc))
        _job_update(
            job_id,
            status="failed",
            message="Review could not start",
            error=str(exc),
            current_stage=current_stage,
            checkpoint_count=checkpoints.completed_count(),
            retryable=False,
            recoverable=False,
        )
    except asyncio.TimeoutError as exc:
        logger.exception("Background review exceeded the maximum processing time")
        checkpoints.mark_failed(current_stage, str(exc))
        _queue_automatic_retry(
            job_id,
            message="The slow stage timed out and is retrying automatically",
            error=(
                "The current stage exceeded its processing window. Completed stages "
                "remain saved and only the interrupted stage will be regenerated."
            ),
            current_stage=current_stage,
            checkpoint_count=checkpoints.completed_count(),
        )
    except AIProviderError as exc:
        logger.exception("Expert review provider failure")
        detail = clean_text(str(exc))
        safe_detail = (
            detail
            if detail and len(detail) <= 700
            else "The expert review provider interrupted the current stage."
        )
        checkpoints.mark_failed(current_stage, safe_detail)
        _queue_automatic_retry(
            job_id,
            message="The expert review request is retrying automatically",
            error=(
                safe_detail
                + " Completed chapter and evidence checkpoints have been retained."
            ),
            current_stage=current_stage,
            checkpoint_count=checkpoints.completed_count(),
        )
    except Exception as exc:
        logger.exception("Unexpected background review failure")
        detail = clean_text(str(exc)) or "The current review stage was interrupted."
        checkpoints.mark_failed(current_stage, detail)
        _queue_automatic_retry(
            job_id,
            message="The interrupted stage is recovering automatically",
            error=(
                "The current stage was interrupted. Completed stages remain saved "
                "and only the interrupted stage will run again."
            ),
            current_stage=current_stage,
            checkpoint_count=checkpoints.completed_count(),
        )
    finally:
        RUNNING_JOB_IDS.discard(job_id)
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        _release_job_lease(job_id)


@app.post("/api/review", status_code=202)
async def create_review(
    request: Request,
    file: UploadFile = File(...), academic_level: str = Form(...), research_approach: str = Form(...),
    workflow_type: str = Form("supervisory_review"),
    assessment_stage: str = Form("initial_examination"),
    candidate_name: str = Form(""),
    candidate_number: str = Form(""),
    degree_programme: str = Form(""),
    candidate_department: str = Form(""),
    institution: str = Form("University of Cape Coast"),
    thesis_title: str = Form(""),
    review_scope: str = Form("chapter"),
    selected_chapter: int = Form(0),
    combined_chapter_end: int = Form(0),
    document_type: str = Form("chapter_one"),
    submission_stage: str = Form("initial"), review_depth: str = Form("standard"), csrf_token: str = Form(...),
    previous_files: Optional[List[UploadFile]] = File(None), supervisor_comment_files: Optional[List[UploadFile]] = File(None),
    supervisor_comments_text: str = Form(""), original_file: Optional[UploadFile] = File(None),
    prior_examiner_files: Optional[List[UploadFile]] = File(None),
    prior_examiner_comments_text: str = Form(""),
    prior_version_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    user = _current_user(request, db)
    if not user or user.role not in {"lecturer", "admin"}:
        raise HTTPException(status_code=401, detail="Sign in to submit a review.")
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Change your temporary password before submitting a review.")
    if workflow_type not in {"supervisory_review", "external_assessment"}:
        raise HTTPException(
            status_code=400,
            detail="Choose Supervisory Review or External Assessment.",
        )
    if workflow_type == "external_assessment":
        if assessment_stage not in {
            "initial_examination",
            "re_examination",
            "corrected_thesis_verification",
        }:
            raise HTTPException(
                status_code=400,
                detail="Choose Initial Examination, Re-examination or Corrected Thesis Verification.",
            )
        if not clean_text(thesis_title):
            raise HTTPException(
                status_code=400,
                detail="Enter the thesis or dissertation title for the external examination report.",
            )
        if not clean_text(degree_programme):
            raise HTTPException(
                status_code=400,
                detail="Enter the degree programme for the external examination report.",
            )
        review_scope = "full_thesis"
        selected_chapter = 0
        combined_chapter_end = 0
        document_type = "full_thesis"
        submission_stage = (
            "initial"
            if assessment_stage == "initial_examination"
            else "revised"
        )
        review_depth = _assessment_review_depth(academic_level)
        previous_files = None
        if submission_stage == "revised":
            supervisor_comment_files = prior_examiner_files
            supervisor_comments_text = prior_examiner_comments_text
            original_file = prior_version_file
        else:
            supervisor_comment_files = None
            supervisor_comments_text = ""
            original_file = None
    if review_depth not in {"light", "standard", "advanced"}:
        raise HTTPException(status_code=400, detail="Choose Light Review, Standard Review or Advanced Review.")
    if review_scope not in {"chapter", "chapter_range", "full_thesis"}:
        raise HTTPException(status_code=400, detail="Choose Single chapter, Combined chapters or Complete thesis.")
    if review_scope == "chapter_range" and combined_chapter_end not in {2, 3, 4, 5}:
        raise HTTPException(
            status_code=400,
            detail="Choose Chapters 1–2, 1–3, 1–4 or 1–5.",
        )
    filename = file.filename or "uploaded-document"
    data = await _read_upload(file, "The chapter or thesis file")

    context_uploads = [
        item for item in (previous_files or [])
        if item and item.filename
    ]
    # The main upload may be a composite containing both the selected chapter
    # and alignment chapters. The parsed document determines whether extra
    # context uploads are required.
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
        detail = (
            "For re-examination or corrected-thesis verification, upload the earlier examiner report or paste the correction schedule."
            if workflow_type == "external_assessment"
            else "For a revised chapter, upload or paste the supervisor comments."
        )
        raise HTTPException(status_code=400, detail=detail)
    supervisor_comment_documents = []
    total_comments = 0
    for index, upload in enumerate(comment_uploads, start=1):
        value = await _read_upload(
            upload,
            f"Earlier examiner file {index}"
            if workflow_type == "external_assessment"
            else f"Supervisor-comment file {index}",
        )
        total_comments += len(value)
        if total_comments > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="The combined supervisor-comment uploads exceed 50 MB.")
        supervisor_comment_documents.append({"filename": upload.filename or (
            f"earlier-examiner-report-{index}"
            if workflow_type == "external_assessment"
            else f"supervisor-comments-{index}"
        ), "data": value})

    original_document = None
    if original_file and original_file.filename:
        original_document = {
            "filename": original_file.filename,
            "data": await _read_upload(
                original_file,
                "The earlier thesis version"
                if workflow_type == "external_assessment"
                else "The original chapter file",
            ),
        }

    job_id = uuid.uuid4().hex
    estimated_pages = estimate_document_pages(data, filename)
    token_plan = estimate_review_tokens(
        estimated_pages,
        workflow_type,
        review_depth,
    )
    token_reserved = False
    try:
        token_reserved = reserve_review_tokens(
            db,
            user=user,
            token_amount=token_plan.reserved_tokens,
            pages=estimated_pages,
            workflow_label=(
                "external assessment"
                if workflow_type == "external_assessment"
                else "supervisory review"
            ),
            job_id=job_id,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    payload = {
        "filename": filename,
        "data": data,
        "academic_level": academic_level,
        "research_approach": research_approach,
        "workflow_type": workflow_type,
        "assessment_stage": assessment_stage,
        "assessment_metadata": {
            "candidate_name": candidate_name,
            "candidate_number": candidate_number,
            "degree_programme": degree_programme,
            "candidate_department": candidate_department,
            "institution": institution,
            "thesis_title": thesis_title,
            "assessment_stage": assessment_stage,
            "examiner_name": user.full_name,
            "examiner_department": user.department or "",
        },
        "review_scope": review_scope,
        "selected_chapter": selected_chapter,
        "combined_chapter_end": combined_chapter_end,
        "document_type": document_type,
        "submission_stage": submission_stage,
        "review_depth": review_depth,
        "context_documents": context_documents,
        "supervisor_comment_documents": supervisor_comment_documents,
        "supervisor_comments_text": supervisor_comments_text,
        "original_document": original_document,
        "user_id": user.id,
        "estimated_pages": estimated_pages,
        "token_estimate": token_plan.reserved_tokens,
        "token_reserved": token_reserved,
    }
    try:
        manifest = save_job_payload(job_id, payload)
    except Exception as exc:
        logger.exception("Could not persist the review submission")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "The uploaded documents could not be saved for reliable "
                "processing. Check the persistent storage configuration."
            ),
        ) from exc

    payload["document_hash"] = manifest["document_hash"]
    payload["payload_hash"] = manifest["payload_hash"]

    record = ReviewRecord(
        job_id=job_id,
        lecturer_id=user.id,
        filename=filename,
        academic_level=academic_level,
        research_approach=research_approach,
        review_scope=review_scope,
        selected_chapter=(
            combined_chapter_end
            if review_scope == "chapter_range"
            else selected_chapter or None
        ),
        review_depth=review_depth,
        submission_stage=submission_stage,
        workflow_type=workflow_type,
        assessment_stage=(
            assessment_stage
            if workflow_type == "external_assessment"
            else None
        ),
        status="queued",
        progress=2,
        message="Review queued and safely saved",
        document_hash=manifest["document_hash"],
        current_stage="queued",
        checkpoint_count=0,
        recoverable=True,
        payload_available=True,
        estimated_pages=estimated_pages,
        token_estimate=token_plan.reserved_tokens,
        token_reserved=(token_plan.reserved_tokens if token_reserved else 0),
        token_accounting_status=("reserved" if token_reserved else "unmetered"),
    )
    db.add(record)
    db.commit()

    JOB_CACHE[job_id] = {
        "job_id": job_id,
        "user_id": user.id,
        "status": "queued",
        "progress": 2,
        "message": "Review queued and safely saved",
        "current_stage": "queued",
        "checkpoint_count": 0,
        "recoverable": True,
        "created_at": time.time(),
        "updated_at": time.time(),
        "resume_url": f"/api/review/jobs/{job_id}/resume",
    }
    _schedule_review_job(job_id, payload, resumed=False)
    return {
        "job_id": job_id,
        "status": "queued",
        "progress": 2,
        "message": "Review queued and safely saved",
        "poll_url": f"/api/review/jobs/{job_id}",
        "resume_url": f"/api/review/jobs/{job_id}/resume",
        "stop_url": f"/api/review/jobs/{job_id}/stop",
        "estimated_pages": estimated_pages,
        "reserved_tokens": token_plan.reserved_tokens if token_reserved else 0,
    }


@app.post("/api/review/jobs/{job_id}/stop", status_code=202)
async def stop_review_job(
    job_id: str,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Stop an active review while retaining its upload and checkpoints.

    A user-stopped job is deliberately excluded from automatic recovery. It may
    be resumed manually later from the portal.
    """
    _verify_csrf(request, csrf_token)
    user = _current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")

    record = (
        db.query(ReviewRecord)
        .filter(ReviewRecord.job_id == job_id)
        .first()
    )
    if not record or (
        user.role != "admin" and record.lecturer_id != user.id
    ):
        raise HTTPException(status_code=404, detail="Review job not found.")
    if record.status == "completed":
        raise HTTPException(
            status_code=409,
            detail="This review is already complete and cannot be stopped.",
        )
    if record.status == "stopped":
        response = {
            "job_id": job_id,
            "status": "stopped",
            "progress": int(record.progress or 0),
            "message": record.message or "Review stopped by the user",
            "resume_url": f"/api/review/jobs/{job_id}/resume",
        }
        if "text/html" in request.headers.get("accept", ""):
            _set_flash(
                request,
                "The review is already stopped. Completed checkpoints remain available.",
                "info",
            )
            return RedirectResponse("/portal", status_code=303)
        return response

    saved_payload_available = payload_available(job_id)
    record.status = "stopped"
    record.message = "Review stopped by the user. Completed checkpoints were retained."
    record.error = None
    record.recoverable = bool(saved_payload_available)
    record.payload_available = bool(saved_payload_available)
    record.lease_owner = None
    record.lease_expires_at = None
    db.commit()

    # Remove the job from automatic execution before cancelling its task.
    SCHEDULED_JOB_IDS.discard(job_id)
    RUNNING_JOB_IDS.discard(job_id)
    task = JOB_TASKS.get(job_id)
    if task and not task.done():
        task.cancel()

    _job_update(
        job_id,
        status="stopped",
        progress=int(record.progress or 0),
        message="Review stopped by the user. Completed checkpoints were retained.",
        current_stage=record.current_stage,
        checkpoint_count=int(record.checkpoint_count or 0),
        recoverable=bool(saved_payload_available),
        payload_available=bool(saved_payload_available),
        lease_owner=None,
        lease_expires_at=None,
    )

    response = {
        "job_id": job_id,
        "status": "stopped",
        "progress": int(record.progress or 0),
        "message": "Review stopped. You may resume later from the saved checkpoints.",
        "checkpoint_count": int(record.checkpoint_count or 0),
        "recoverable": bool(saved_payload_available),
        "resume_url": (
            f"/api/review/jobs/{job_id}/resume"
            if saved_payload_available
            else None
        ),
    }
    if "text/html" in request.headers.get("accept", ""):
        _set_flash(
            request,
            "Review stopped. Completed checkpoints were retained and can be resumed later.",
            "success",
        )
        return RedirectResponse("/portal", status_code=303)
    return response


@app.post("/api/review/jobs/{job_id}/resume", status_code=202)
async def resume_review_job(
    job_id: str,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)
    user = _current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    record = (
        db.query(ReviewRecord)
        .filter(ReviewRecord.job_id == job_id)
        .first()
    )
    if not record or (
        user.role != "admin" and record.lecturer_id != user.id
    ):
        raise HTTPException(status_code=404, detail="Review job not found.")
    if record.status == "completed":
        completed_review = (
            REVIEW_CACHE.get(record.review_id)
            or (load_review_json(record.review_id) if record.review_id else None)
            or {}
        )
        completed_summary = completed_review.get("summary") or {}
        limited_output = bool(
            completed_summary.get("review_rebuild_recommended")
            or completed_summary.get("readiness_label") in {
                "Review completed with a limitation",
                "Review requires regeneration",
            }
            or (
                float(completed_summary.get("overall_score") or 0.0) < 85.0
                and not (completed_review.get("academic_findings") or [])
            )
        )
        if not (limited_output and payload_available(job_id)):
            return {
                "job_id": job_id,
                "status": "completed",
                "review_id": record.review_id,
                "result_url": (
                    f"/api/review/{record.review_id}"
                    if record.review_id
                    else None
                ),
            }
        accounting_user = db.get(User, record.lecturer_id)
        if accounting_user:
            try:
                reserve_existing_review_tokens(db, record, accounting_user)
            except ValueError as exc:
                db.rollback()
                if "text/html" in request.headers.get("accept", ""):
                    _set_flash(request, str(exc), "error")
                    return RedirectResponse("/portal", status_code=303)
                raise HTTPException(status_code=402, detail=str(exc)) from exc
        record.status = "queued"
        record.message = "Rebuild requested for the limited review output"
        record.error = None
        record.recoverable = True
        record.completed_at = None
        db.commit()
        JOB_CACHE.pop(job_id, None)
        scheduled = _schedule_review_job(job_id, resumed=True)
        if "text/html" in request.headers.get("accept", ""):
            _set_flash(
                request,
                "The limited review is being rebuilt from the saved document extraction.",
                "success",
            )
            return RedirectResponse("/portal", status_code=303)
        return {
            "job_id": job_id,
            "status": "queued" if scheduled else record.status,
            "progress": int(record.progress or 2),
            "message": record.message,
            "poll_url": f"/api/review/jobs/{job_id}",
        }
    if record.status in {"queued", "processing"} or job_id in RUNNING_JOB_IDS:
        return {
            "job_id": job_id,
            "status": record.status,
            "progress": int(record.progress or 2),
            "message": "The review is already running.",
            "poll_url": f"/api/review/jobs/{job_id}",
        }
    saved_payload_available = payload_available(job_id)
    can_recover_failed_job = (
        record.status == "failed" and saved_payload_available
    )
    if (not record.recoverable and not can_recover_failed_job) or not saved_payload_available:
        raise HTTPException(
            status_code=409,
            detail=(
                "This job cannot be resumed because its saved upload is "
                "unavailable. Submit the document again."
            ),
        )

    accounting_user = db.get(User, record.lecturer_id)
    if accounting_user:
        try:
            reserve_existing_review_tokens(db, record, accounting_user)
        except ValueError as exc:
            db.rollback()
            if "text/html" in request.headers.get("accept", ""):
                _set_flash(request, str(exc), "error")
                return RedirectResponse("/portal", status_code=303)
            raise HTTPException(status_code=402, detail=str(exc)) from exc
    record.status = "queued"
    record.message = "Resume requested from the last completed checkpoint"
    record.error = None
    record.recoverable = True
    db.commit()
    JOB_CACHE.pop(job_id, None)
    scheduled = _schedule_review_job(job_id, resumed=True)
    response = {
        "job_id": job_id,
        "status": "queued" if scheduled else record.status,
        "progress": int(record.progress or 2),
        "message": (
            "Resume requested from the last completed checkpoint"
            if scheduled
            else "The review is already running"
        ),
        "poll_url": f"/api/review/jobs/{job_id}",
    }
    if "text/html" in request.headers.get("accept", ""):
        _set_flash(
            request,
            "The review will continue from its last completed checkpoint.",
            "success",
        )
        return RedirectResponse("/portal", status_code=303)
    return response


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
        response.update({
            "status": record.status,
            "progress": max(
                int(response.get("progress") or 0),
                int(record.progress or 0),
            ),
            "message": record.message or response.get("message"),
            "error": record.error,
            "current_stage": record.current_stage,
            "checkpoint_count": int(record.checkpoint_count or 0),
            "completed_units": int(record.checkpoint_count or 0),
            "recoverable": bool(record.recoverable),
            "payload_available": bool(record.payload_available),
            "resume_count": int(record.resume_count or 0),
            "auto_resume_allowed": bool(
                AUTO_RESUME_JOBS
                and int(record.resume_count or 0) < MAX_AUTO_RESUMES
            ),
            "last_heartbeat_at": (
                record.last_heartbeat_at.isoformat()
                if record.last_heartbeat_at
                else None
            ),
        })
        if response.get("status") == "completed" and response.get("review_id"):
            response.setdefault(
                "result_url",
                f'/api/review/{response["review_id"]}',
            )
        elif (
            (record.recoverable and record.status in {"paused", "queued", "stopped"})
            or (record.status == "failed" and bool(record.payload_available))
        ):
            response["resume_url"] = f"/api/review/jobs/{job_id}/resume"
        if record.status in {"queued", "processing"}:
            response["stop_url"] = f"/api/review/jobs/{job_id}/stop"
        return response
    response = {
        "job_id": record.job_id,
        "status": record.status,
        "progress": record.progress,
        "message": record.message,
        "error": record.error,
        "review_id": record.review_id,
        "current_stage": record.current_stage,
        "checkpoint_count": int(record.checkpoint_count or 0),
        "completed_units": int(record.checkpoint_count or 0),
        "recoverable": bool(record.recoverable),
        "payload_available": bool(record.payload_available),
        "resume_count": int(record.resume_count or 0),
        "auto_resume_allowed": bool(
            AUTO_RESUME_JOBS
            and int(record.resume_count or 0) < MAX_AUTO_RESUMES
        ),
        "last_heartbeat_at": (
            record.last_heartbeat_at.isoformat()
            if record.last_heartbeat_at
            else None
        ),
        "created_at": (
            record.created_at.isoformat() if record.created_at else None
        ),
        "completed_at": (
            record.completed_at.isoformat() if record.completed_at else None
        ),
    }
    if record.status == "completed" and record.review_id:
        response["result_url"] = f"/api/review/{record.review_id}"
    elif (
        (record.recoverable and record.status in {"paused", "queued", "stopped"})
        or (record.status == "failed" and bool(record.payload_available))
    ):
        response["resume_url"] = f"/api/review/jobs/{job_id}/resume"
    if record.status in {"queued", "processing"}:
        response["stop_url"] = f"/api/review/jobs/{job_id}/stop"
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
    if not review:
        raise HTTPException(status_code=404, detail="Review result is not available.")

    summary = review.setdefault("summary", {})
    annotation_is_current = (
        summary.get("annotation_export_version") == ANNOTATION_EXPORT_VERSION
    )
    data = (
        ANNOTATED_CACHE.get(review_id) or load_annotated(review_id)
        if annotation_is_current
        else None
    )

    # Completed reviews created by an earlier exporter can be upgraded at
    # download time without rerunning the academic review, provided the saved
    # source upload is still available on persistent storage.
    if data is None and record.job_id and payload_available(record.job_id):
        try:
            payload = await asyncio.to_thread(load_job_payload, record.job_id)
            source_data = bytes((payload or {}).get("data") or b"")
            source_name = str((payload or {}).get("filename") or record.filename or "")
            if not source_data or not source_name.lower().endswith(".docx"):
                raise ValueError("The saved source is not an annotatable DOCX file.")
            comment_author = clean_text(
                (record.lecturer.full_name if record.lecturer else "")
                or summary.get("reviewer_name")
                or user.full_name
            )
            data = await asyncio.to_thread(
                build_annotated_docx,
                source_data,
                review,
                comment_author or None,
            )
            ANNOTATED_CACHE[review_id] = data
            await asyncio.to_thread(save_annotated, review_id, data)
            summary.update({
                "annotated_document_available": True,
                "annotation_export_version": ANNOTATION_EXPORT_VERSION,
                "annotation_mode": "native_word_comments",
            })
            summary.pop("annotation_warning", None)
            REVIEW_CACHE[review_id] = review
            await asyncio.to_thread(save_review_json, review_id, review)
        except Exception as exc:
            logger.exception("Could not regenerate native-comment annotated document")
            raise HTTPException(
                status_code=409,
                detail=(
                    "The annotated document could not be upgraded to native Word "
                    "comments. Submit a fresh review or confirm that the original "
                    "DOCX remains on persistent storage."
                ),
            ) from exc

    if data is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This review predates native Word comments and the saved source "
                "document is unavailable. Submit a fresh review to generate a "
                "comment-box annotated document."
            ),
        )

    ANNOTATED_CACHE[review_id] = data
    stem = os.path.splitext(os.path.basename(record.filename or "thesis.docx"))[0]
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{stem}-supervisor-reviewed.docx"'
            )
        },
    )


@app.get("/api/review/{review_id}/annotated-inline.docx")
async def export_inline_annotated_document(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    record = _authorised_review_record(db, user, review_id)
    review = REVIEW_CACHE.get(review_id) or load_review_json(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review result is not available.")
    if not record.job_id or not payload_available(record.job_id):
        raise HTTPException(
            status_code=409,
            detail=(
                "The inline annotated document requires the saved source DOCX. "
                "Submit a fresh review if the original upload is no longer available."
            ),
        )
    try:
        payload = await asyncio.to_thread(load_job_payload, record.job_id)
        source_data = bytes((payload or {}).get("data") or b"")
        source_name = str((payload or {}).get("filename") or record.filename or "")
        if not source_data or not source_name.lower().endswith(".docx"):
            raise ValueError("The saved source is not an annotatable DOCX file.")
        comment_author = clean_text(
            (record.lecturer.full_name if record.lecturer else "")
            or (review.get("summary") or {}).get("reviewer_name")
            or user.full_name
        )
        data = await asyncio.to_thread(
            build_inline_annotated_docx,
            source_data,
            review,
            comment_author or None,
        )
    except Exception as exc:
        logger.exception("Could not generate inline annotated document")
        raise HTTPException(
            status_code=409,
            detail="The inline annotated document could not be generated. Submit a fresh review and try again.",
        ) from exc

    stem = os.path.splitext(os.path.basename(record.filename or "thesis.docx"))[0]
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{stem}-inline-annotated.docx"'
            )
        },
    )


@app.get("/api/review/{review_id}/export.docx")
async def export_review(review_id: str, request: Request, db: Session = Depends(get_db)):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    _authorised_review_record(db, user, review_id)
    review = REVIEW_CACHE.get(review_id) or load_review_json(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or expired.")
    if review.get("external_assessment"):
        content = build_external_examination_report(review)
        filename = "external-examination-report.docx"
    else:
        content = build_docx_report(review)
        filename = "supervisor-review-report.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _external_review_or_404(
    db: Session,
    user: User,
    review_id: str,
) -> dict:
    _authorised_review_record(db, user, review_id)
    review = REVIEW_CACHE.get(review_id) or load_review_json(review_id)
    if not review or not review.get("external_assessment"):
        raise HTTPException(
            status_code=404,
            detail="External assessment output is not available for this review.",
        )
    return review


@app.get("/api/review/{review_id}/external-report.docx")
async def export_external_report(
    review_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    review = _external_review_or_404(db, user, review_id)
    return Response(
        content=build_external_examination_report(review),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="external-examination-report.docx"'},
    )


@app.get("/api/review/{review_id}/corrections-schedule.docx")
async def export_corrections_schedule(
    review_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    review = _external_review_or_404(db, user, review_id)
    return Response(
        content=build_corrections_schedule(review),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="external-examination-corrections-schedule.docx"'},
    )


@app.get("/api/review/{review_id}/confidential-recommendation.docx")
async def export_confidential_recommendation(
    review_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    review = _external_review_or_404(db, user, review_id)
    return Response(
        content=build_confidential_recommendation(review),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="confidential-examiner-recommendation.docx"'},
    )


@app.get("/api/review/{review_id}/oral-questions.docx")
async def export_oral_questions(
    review_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    review = _external_review_or_404(db, user, review_id)
    return Response(
        content=build_oral_examination_questions(review),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="oral-examination-question-bank.docx"'},
    )
