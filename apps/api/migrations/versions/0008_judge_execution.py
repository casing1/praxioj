"""Separate synthetic Judge requests, attempts and hash-only capabilities."""
from alembic import op
import sqlalchemy as sa

revision = "0008_judge_execution"
down_revision = "0007_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("judge_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("solve_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("fixture_id", sa.String(64), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("spec_digest", sa.String(64), nullable=False),
        sa.Column("fence", sa.Integer(), nullable=False),
        sa.Column("reserved_output_bytes", sa.BigInteger(), nullable=False),
        sa.Column("reservation_active", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(64)), sa.Column("result", sa.JSON()), sa.Column("assessment", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("owner_id", "request_id", name="uq_judge_owner_request"),
        sa.CheckConstraint("state IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')", name="ck_judge_job_state"),
        sa.CheckConstraint("fence >= 0 AND reserved_output_bytes >= 0", name="ck_judge_job_budget"))
    for column in ("owner_id", "session_id", "submission_id"):
        op.create_index("ix_judge_jobs_" + column, "judge_jobs", [column])
    op.create_index("ix_judge_schedule", "judge_jobs", ["state", "created_at", "id"])
    op.create_table("judge_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("judge_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("fence", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(64), nullable=False),
        sa.Column("capability_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("audience", sa.String(64), nullable=False), sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        *[sa.Column(name, sa.DateTime(timezone=True), nullable=False) for name in (
            "created_at", "deadline_at", "expires_at", "lease_expires_at", "heartbeat_at")],
        sa.Column("consumed_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("job_id", "fence", name="uq_judge_attempt_fence"),
        sa.CheckConstraint("fence > 0", name="ck_judge_attempt_fence"))
    op.create_index("ix_judge_attempts_job_id", "judge_attempts", ["job_id"])
    op.create_index("ix_judge_attempt_lease", "judge_attempts", ["lease_expires_at"])


def downgrade():
    op.drop_table("judge_attempts")
    op.drop_table("judge_jobs")
