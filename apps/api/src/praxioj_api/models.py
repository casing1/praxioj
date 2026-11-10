"""Platform persistence. Framework models never import these ORM classes."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('administrator', 'author', 'participant')", name="ck_user_role"),
                      Index("uq_users_username", "username", unique=True))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    identity_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(24), default="participant", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Problem(Base):
    __tablename__ = "problems"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class ProblemVersion(Base):
    __tablename__ = "problem_versions"
    __table_args__ = (UniqueConstraint("problem_id", "version", name="uq_problem_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id", ondelete="RESTRICT"), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SolveSession(Base):
    __tablename__ = "solve_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'submitted', 'ended')", name="ck_session_status"),
        CheckConstraint("next_sequence_number >= 1", name="ck_next_sequence"),
        CheckConstraint("user_message_count >= 0", name="ck_message_count"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    problem_version_id: Mapped[str] = mapped_column(ForeignKey("problem_versions.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    next_sequence_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trace_head_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    trace_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=lambda: utcnow() + timedelta(days=30), nullable=True)
    trace_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    runtime_profile: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    profile_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    draft: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_message_position"),
        CheckConstraint("role IN ('user', 'assistant', 'tool')", name="ck_message_role"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="RESTRICT"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TraceEvent(Base):
    __tablename__ = "trace_events"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_number", name="uq_trace_session_sequence"),
        CheckConstraint("sequence_number >= 1", name="ck_trace_sequence"),
    )
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="RESTRICT"), index=True, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    envelope: Mapped[dict] = mapped_column(JSON, nullable=False)


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="RESTRICT"), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifacts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="RESTRICT"), unique=True, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WorkspaceRun(Base):
    __tablename__ = "workspace_runs"
    __table_args__ = (
        UniqueConstraint("session_id", "request_id", name="uq_run_request"),
        CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name="ck_run_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="RESTRICT"), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderCall(Base):
    __tablename__ = "provider_calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="RESTRICT"), index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("workspace_runs.id", ondelete="RESTRICT"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="started", nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkspaceFile(Base):
    __tablename__ = "workspace_files"
    __table_args__ = (UniqueConstraint("session_id", "path", name="uq_workspace_path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("solve_sessions.id", ondelete="RESTRICT"), index=True, nullable=False)
    path: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
