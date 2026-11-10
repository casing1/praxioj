"""Bounded operational accounting. Counters are policy records, not billing data."""
from datetime import datetime
from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, utcnow


class AdmissionGate(Base):
    __tablename__ = "admission_gates"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)


class QuotaBucket(Base):
    __tablename__ = "quota_buckets"
    __table_args__ = (Index("ix_quota_window", "window_start"),
        Index("ix_quota_subject", "scope", "subject"),
        CheckConstraint("model_calls >= 0 AND tool_calls >= 0 AND reserved_units >= 0", name="ck_quota_nonnegative"))
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str] = mapped_column(String(128), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reserved_units: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    uncertain_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ProviderReservation(Base):
    __tablename__ = "provider_reservations"
    call_id: Mapped[str] = mapped_column(ForeignKey("provider_calls.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    problem_id: Mapped[str] = mapped_column(String(128), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    units: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="reserved", nullable=False)


class TraceUsage(Base):
    __tablename__ = "trace_usage"
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="CASCADE"), primary_key=True)
    bytes_used: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    terminal_base_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    terminal_base_events: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkerRecord(Base):
    __tablename__ = "worker_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recovered_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_wait_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    total_run_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
