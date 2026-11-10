"""Durable execution metadata; no provider inputs or credentials live here."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, utcnow


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("state IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')", name="ck_job_state"),
        CheckConstraint("fence >= 0 AND attempt >= 0", name="ck_job_generation"),
        CheckConstraint("max_seconds > 0", name="ck_job_timeout"),
        Index("ix_job_schedule", "state", "available_at"),
        Index("ix_job_lease", "state", "lease_expires_at"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("workspace_runs.id", ondelete="RESTRICT"), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="RESTRICT"), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recovery_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_effect_uncertain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


def job_public(job: Job | None) -> dict | None:
    """Do not expose worker ownership tokens or internal host/process identifiers."""
    if job is None:
        return None
    return {"state": job.state, "attempt": job.attempt, "recovery_reason": job.recovery_reason,
            "external_effect_uncertain": job.external_effect_uncertain,
            "started_at": job.started_at, "finished_at": job.finished_at}
