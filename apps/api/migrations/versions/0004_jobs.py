"""Durable worker jobs; unauthenticated legacy runs are not replayed.

Revision ID: 0004_jobs
Revises: 0003_authentication
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import uuid4

revision = "0004_jobs"
down_revision = "0003_authentication"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("jobs",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("workspace_runs.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("solve_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("claim_token", sa.String(64), nullable=True),
        sa.Column("fence", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_seconds", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_reason", sa.String(64), nullable=True),
        sa.Column("external_effect_uncertain", sa.Boolean(), nullable=False),
        sa.CheckConstraint("state IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')", name="ck_job_state"),
        sa.CheckConstraint("fence >= 0 AND attempt >= 0", name="ck_job_generation"),
        sa.CheckConstraint("max_seconds > 0", name="ck_job_timeout"),
    )
    op.create_index("ix_jobs_session_id", "jobs", ["session_id"])
    op.create_index("ix_job_schedule", "jobs", ["state", "available_at"])
    op.create_index("ix_job_lease", "jobs", ["state", "lease_expires_at"])
    # Retain historical runs, without granting their browser identities account
    # authority or replaying possibly billed requests. JSON is bound by SQLAlchemy.
    runs = sa.table("workspace_runs", sa.column("id", sa.String()), sa.column("session_id", sa.String()),
        sa.column("status", sa.String()), sa.column("error", sa.JSON()), sa.column("finished_at", sa.DateTime(timezone=True)))
    calls = sa.table("provider_calls", sa.column("run_id", sa.String()), sa.column("status", sa.String()),
        sa.column("error_code", sa.String()), sa.column("finished_at", sa.DateTime(timezone=True)))
    sessions = sa.table("solve_sessions", sa.column("id", sa.String()), sa.column("active_run_id", sa.String()),
                        sa.column("next_sequence_number", sa.Integer()))
    traces = sa.table("trace_events", sa.column("event_id", sa.String()), sa.column("session_id", sa.String()),
        sa.column("sequence_number", sa.Integer()), sa.column("event_type", sa.String()),
        sa.column("timestamp", sa.DateTime(timezone=True)), sa.column("envelope", sa.JSON()))
    connection = op.get_bind()
    ids = list(connection.scalars(sa.select(runs.c.id).where(runs.c.status.in_(["queued", "running"]))))
    if ids:
        # Migration is an explicit state transition too. Append safe events while
        # leaving every historical envelope untouched. 0005 adds checkpoints;
        # historical events remain explicitly unverified, without rehashing.
        for run_id in ids:
            sid = connection.scalar(sa.select(runs.c.session_id).where(runs.c.id == run_id))
            sequence = connection.scalar(sa.select(sessions.c.next_sequence_number).where(sessions.c.id == sid))
            for event_type, payload in (
                ("ERROR", {"stage": "migration", "code": "legacy_run_quarantined"}),
                ("SESSION_STATE_CHANGED", {"run_status": "failed", "reason": "legacy_run_quarantined", "replayed": False}),
            ):
                now, event_id = datetime.now(timezone.utc), str(uuid4())
                envelope = {"event_id": event_id, "session_id": sid, "sequence_number": sequence,
                    "event_type": event_type, "timestamp": now.isoformat(), "schema_version": "1.0",
                    "source": "server", "actor": "system", "payload": payload,
                    "resource_ids": {"run_id": run_id}, "correlation_id": run_id, "parent_event_id": None}
                connection.execute(traces.insert().values(event_id=event_id, session_id=sid,
                    sequence_number=sequence, event_type=event_type, timestamp=now, envelope=envelope))
                sequence += 1
            connection.execute(sessions.update().where(sessions.c.id == sid).values(next_sequence_number=sequence))
        connection.execute(runs.update().where(runs.c.id.in_(ids)).values(status="failed", finished_at=sa.func.now(),
            error={"code": "legacy_run_quarantined", "message": "This unauthenticated legacy run cannot be resumed automatically."}))
        connection.execute(calls.update().where(calls.c.run_id.in_(ids), calls.c.status == "started").values(
            status="failed", error_code="legacy_run_quarantined", finished_at=sa.func.now()))
        connection.execute(sessions.update().where(sessions.c.active_run_id.in_(ids)).values(active_run_id=None))


def downgrade():
    op.drop_index("ix_job_lease", table_name="jobs")
    op.drop_index("ix_job_schedule", table_name="jobs")
    op.drop_index("ix_jobs_session_id", table_name="jobs")
    op.drop_table("jobs")
