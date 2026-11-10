"""Synthetic Judge coordination is separate from AI runtime jobs and evaluation."""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, uid, utcnow


class JudgeJob(Base):
    __tablename__ = "judge_jobs"
    __table_args__ = (
        UniqueConstraint("owner_id", "request_id", name="uq_judge_owner_request"),
        CheckConstraint("state IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')", name="ck_judge_job_state"),
        CheckConstraint("fence >= 0 AND reserved_output_bytes >= 0", name="ck_judge_job_budget"),
        Index("ix_judge_schedule", "state", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    spec_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    fence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_output_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reservation_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JudgeAttempt(Base):
    __tablename__ = "judge_attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "fence", name="uq_judge_attempt_fence"),
        CheckConstraint("fence > 0", name="ck_judge_attempt_fence"),
        Index("ix_judge_attempt_lease", "lease_expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("judge_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    fence: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    audience: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def judge_public(job: JudgeJob) -> dict:
    """A synthetic result is never a participant's independent execution evidence."""
    return {"id": job.id, "session_id": job.session_id, "submission_id": job.submission_id,
        "request_id": job.request_id, "state": job.state, "fixture_id": job.fixture_id,
        "provenance": "synthetic_mock", "error_code": job.error_code,
        "result": job.result, "assessment": job.assessment,
        "created_at": job.created_at, "deadline_at": job.deadline_at, "finished_at": job.finished_at}
