from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Generator, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, create_engine, func, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "sqlite:///./supervisor.db").strip()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://") and "+psycopg" not in value:
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


DATABASE_URL = _database_url()
CONNECT_ARGS = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args=CONNECT_ARGS,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    recovery_pin_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), index=True, default="lecturer", nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    token_balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    token_reserved_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    token_allocated_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    token_used_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    reviews: Mapped[list["ReviewRecord"]] = relationship(back_populates="lecturer", cascade="all, delete-orphan")


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    review_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    lecturer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    academic_level: Mapped[str] = mapped_column(String(80), nullable=False)
    research_approach: Mapped[str] = mapped_column(String(80), nullable=False)
    review_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    selected_chapter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    review_depth: Mapped[str] = mapped_column(String(30), nullable=False)
    submission_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    workflow_type: Mapped[str] = mapped_column(String(40), default="supervisory_review", nullable=False)
    assessment_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    readiness_label: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    annotated_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    document_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    current_stage: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    checkpoint_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recoverable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    payload_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resume_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_estimate: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    token_reserved: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tokens_used: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    token_accounting_status: Mapped[str] = mapped_column(String(30), default="unmetered", nullable=False)

    lecturer: Mapped[User] = relationship(back_populates="reviews")


class TokenLedger(Base):
    __tablename__ = "token_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lecturer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    review_record_id: Mapped[Optional[int]] = mapped_column(ForeignKey("review_records.id", ondelete="SET NULL"), index=True, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)




class ReviewArtifact(Base):
    __tablename__ = "review_artifacts"
    __table_args__ = (
        UniqueConstraint("job_id", "artifact_key", name="uq_review_artifact_job_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    artifact_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream", nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ReviewCheckpoint(Base):
    __tablename__ = "review_checkpoints"
    __table_args__ = (
        UniqueConstraint("job_id", "stage_key", name="uq_review_checkpoint_job_stage"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    stage_key: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    input_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    result_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


def _ensure_user_token_columns() -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("users")}
    definitions = {
        "token_balance": "BIGINT DEFAULT 0",
        "token_reserved_total": "BIGINT DEFAULT 0",
        "token_allocated_total": "BIGINT DEFAULT 0",
        "token_used_total": "BIGINT DEFAULT 0",
    }
    statements = [
        f"ALTER TABLE users ADD COLUMN {name} {definition}"
        for name, definition in definitions.items()
        if name not in existing
    ]
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        for name in definitions:
            connection.execute(text(f"UPDATE users SET {name}=0 WHERE {name} IS NULL"))


def _ensure_review_record_columns() -> None:
    """Add workflow columns for existing SQLite or PostgreSQL deployments."""
    inspector = inspect(engine)
    if "review_records" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("review_records")}
    statements = []
    if "workflow_type" not in existing:
        statements.append(
            "ALTER TABLE review_records ADD COLUMN workflow_type VARCHAR(40) DEFAULT 'supervisory_review'"
        )
    if "assessment_stage" not in existing:
        statements.append(
            "ALTER TABLE review_records ADD COLUMN assessment_stage VARCHAR(50)"
        )
    migration_columns = {
        "document_hash": "VARCHAR(64)",
        "current_stage": "VARCHAR(180)",
        "checkpoint_count": "INTEGER DEFAULT 0",
        "recoverable": "BOOLEAN DEFAULT TRUE",
        "payload_available": "BOOLEAN DEFAULT FALSE",
        "resume_count": "INTEGER DEFAULT 0",
        "last_heartbeat_at": "TIMESTAMP",
        "lease_owner": "VARCHAR(160)",
        "lease_expires_at": "TIMESTAMP",
        "started_at": "TIMESTAMP",
        "estimated_pages": "INTEGER DEFAULT 0",
        "token_estimate": "BIGINT DEFAULT 0",
        "token_reserved": "BIGINT DEFAULT 0",
        "tokens_used": "BIGINT DEFAULT 0",
        "token_accounting_status": "VARCHAR(30) DEFAULT 'unmetered'",
    }
    for column_name, definition in migration_columns.items():
        if column_name not in existing:
            statements.append(
                f"ALTER TABLE review_records ADD COLUMN {column_name} {definition}"
            )
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text("UPDATE review_records SET workflow_type='supervisory_review' WHERE workflow_type IS NULL OR workflow_type=''")
        )
        connection.execute(
            text("UPDATE review_records SET checkpoint_count=0 WHERE checkpoint_count IS NULL")
        )
        connection.execute(
            text("UPDATE review_records SET resume_count=0 WHERE resume_count IS NULL")
        )
        connection.execute(
            text("UPDATE review_records SET recoverable=TRUE WHERE recoverable IS NULL")
        )
        connection.execute(
            text("UPDATE review_records SET payload_available=FALSE WHERE payload_available IS NULL")
        )
        connection.execute(text("UPDATE review_records SET estimated_pages=0 WHERE estimated_pages IS NULL"))
        connection.execute(text("UPDATE review_records SET token_estimate=0 WHERE token_estimate IS NULL"))
        connection.execute(text("UPDATE review_records SET token_reserved=0 WHERE token_reserved IS NULL"))
        connection.execute(text("UPDATE review_records SET tokens_used=0 WHERE tokens_used IS NULL"))
        connection.execute(text("UPDATE review_records SET token_accounting_status='unmetered' WHERE token_accounting_status IS NULL OR token_accounting_status=''"))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_user_token_columns()
    _ensure_review_record_columns()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def count_admins(db: Session) -> int:
    return int(db.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0)
