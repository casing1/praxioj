"""Trace chain checkpoints, bounded retention policy, and separate audit metadata.

Existing traces are not rehashed: a migration cannot prove their original integrity.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_trace"
down_revision = "0004_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("solve_sessions", sa.Column("trace_head_sha256", sa.String(64), nullable=True))
    op.add_column("solve_sessions", sa.Column("trace_retention_days", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("solve_sessions", sa.Column("trace_purged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("solve_sessions", sa.Column("trace_expires_at", sa.DateTime(timezone=True), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("UPDATE solve_sessions SET trace_expires_at = created_at + INTERVAL '30 days'")
    else:
        op.execute("UPDATE solve_sessions SET trace_expires_at = datetime(created_at, '+30 days')")
    op.create_table("audit_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_records_created_at", "audit_records", ["created_at"])


def downgrade():
    op.drop_table("audit_records")
    for column in ("trace_expires_at", "trace_purged_at", "trace_retention_days", "trace_head_sha256"):
        op.drop_column("solve_sessions", column)
