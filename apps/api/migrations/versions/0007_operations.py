"""Operational quotas and worker registry; existing participant rows are preserved."""
from alembic import op
import sqlalchemy as sa
revision = "0007_operations"
down_revision = "0006_auth_hardening"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("admission_gates", sa.Column("id", sa.String(24), primary_key=True))
    op.bulk_insert(sa.table("admission_gates", sa.column("id", sa.String())), [{"id": "global"}])
    op.create_table("quota_buckets",
        sa.Column("key", sa.String(64), primary_key=True), sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(128), nullable=False), sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        *[sa.Column(name, sa.Integer(), nullable=False) for name in ("model_calls", "tool_calls", "uncertain_calls")],
        *[sa.Column(name, sa.BigInteger(), nullable=False) for name in ("input_tokens", "output_tokens", "reserved_units")],
        sa.CheckConstraint("model_calls >= 0 AND tool_calls >= 0 AND reserved_units >= 0", name="ck_quota_nonnegative"))
    op.create_index("ix_quota_window", "quota_buckets", ["window_start"])
    op.create_index("ix_quota_subject", "quota_buckets", ["scope", "subject"])
    op.create_table("provider_reservations",
        sa.Column("call_id", sa.String(36), sa.ForeignKey("provider_calls.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False), sa.Column("problem_id", sa.String(128), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("units", sa.BigInteger(), nullable=False), sa.Column("state", sa.String(16), nullable=False))
    op.create_index("ix_provider_reservations_window_start", "provider_reservations", ["window_start"])
    op.create_table("trace_usage", sa.Column("session_id", sa.String(36),
        sa.ForeignKey("solve_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("bytes_used", sa.BigInteger(), nullable=False),
        sa.Column("terminal_base_bytes", sa.BigInteger(), nullable=False),
        sa.Column("terminal_base_events", sa.Integer(), nullable=False))
    size = "octet_length(CAST(envelope AS TEXT))" if op.get_bind().dialect.name == "postgresql" else "length(CAST(envelope AS BLOB))"
    # Existing history is retained, even if it exceeds a new admission cap. A
    # fixed historical checkpoint permits bounded finalization without allowing
    # repeated normal writes to ratchet the cap upwards. Raw JSON storage length
    # is conservative relative to new compact UTF-8 payload accounting.
    op.execute(sa.text(f"""INSERT INTO trace_usage (session_id, bytes_used, terminal_base_bytes, terminal_base_events)
        SELECT s.id, COALESCE(t.bytes, 0), COALESCE(t.bytes, 0), s.next_sequence_number - 1
        FROM solve_sessions s LEFT JOIN
        (SELECT session_id, SUM({size}) AS bytes FROM trace_events GROUP BY session_id) t ON t.session_id = s.id"""))
    op.create_table("worker_records", sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        *[sa.Column(name, sa.DateTime(timezone=True), nullable=False) for name in ("started_at", "heartbeat_at")],
        sa.Column("stopped_at", sa.DateTime(timezone=True)), sa.Column("current_job_id", sa.String(36)),
        *[sa.Column(name, sa.Integer(), nullable=False) for name in ("completed_jobs", "failed_jobs", "recovered_jobs")],
        *[sa.Column(name, sa.Float(), nullable=False) for name in ("total_wait_seconds", "total_run_seconds")])
    op.create_index("ix_worker_records_heartbeat_at", "worker_records", ["heartbeat_at"])


def downgrade():
    for name in ("worker_records", "trace_usage", "provider_reservations", "quota_buckets", "admission_gates"):
        op.drop_table(name)
