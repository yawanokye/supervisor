from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Generator, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func, inspect, text
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    lecturer: Mapped[User] = relationship(back_populates="reviews")


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
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text("UPDATE review_records SET workflow_type='supervisory_review' WHERE workflow_type IS NULL OR workflow_type=''")
        )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_review_record_columns()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def count_admins(db: Session) -> int:
    return int(db.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0)
