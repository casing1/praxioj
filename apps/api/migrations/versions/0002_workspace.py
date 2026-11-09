"""Add durable local AI runs and logical workspace, retaining Milestone 1 data."""
from alembic import op
import sqlalchemy as sa
from uuid import uuid4

revision = "0002_workspace"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def alter_existing(up: bool):
    with op.batch_alter_table("solve_sessions") as batch:
        batch.drop_constraint("ck_session_status", type_="check")
        batch.create_check_constraint("ck_session_status", "status IN ('active', 'submitted', 'ended')" if up else "status IN ('active', 'submitted')")
        if up:
            batch.add_column(sa.Column("runtime_profile", sa.String(32), nullable=False, server_default="mock"))
            batch.add_column(sa.Column("profile_snapshot", sa.JSON(), nullable=False, server_default="{}"))
            batch.add_column(sa.Column("active_run_id", sa.String(36), nullable=True))
            batch.add_column(sa.Column("draft", sa.Text(), nullable=False, server_default=""))
        else:
            for name in ("runtime_profile", "profile_snapshot", "active_run_id", "draft"):
                batch.drop_column(name)
    with op.batch_alter_table("conversation_messages") as batch:
        batch.drop_constraint("ck_message_role", type_="check")
        batch.create_check_constraint("ck_message_role", "role IN ('user', 'assistant', 'tool')" if up else "role IN ('user', 'assistant')")
        if up:
            batch.add_column(sa.Column("tool_calls", sa.JSON(), nullable=False, server_default="[]"))
            batch.add_column(sa.Column("tool_call_id", sa.String(128), nullable=True))
        else:
            batch.drop_column("tool_calls")
            batch.drop_column("tool_call_id")
    with op.batch_alter_table("submissions") as batch:
        if up:
            batch.add_column(sa.Column("artifacts", sa.JSON(), nullable=False, server_default="[]"))
        else:
            batch.drop_column("artifacts")
    if up:
        for table, names in (("solve_sessions", ("runtime_profile", "profile_snapshot", "draft")),
                             ("conversation_messages", ("tool_calls",)), ("submissions", ("artifacts",))):
            with op.batch_alter_table(table) as batch:
                for name in names:
                    batch.alter_column(name, server_default=None)


def alter_safely(up: bool):
    if op.get_bind().dialect.name == "sqlite":
        # SQLite batch table rebuild must temporarily suspend FK checks, including
        # on populated M1 databases. Each table copy preserves every existing row.
        with op.get_context().autocommit_block():
            op.execute("PRAGMA foreign_keys=OFF")
        try:
            alter_existing(up)
        finally:
            with op.get_context().autocommit_block():
                op.execute("PRAGMA foreign_keys=ON")
    else:
        alter_existing(up)


def upgrade():
    alter_safely(True)
    op.create_table("workspace_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("solve_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "request_id", name="uq_run_request"),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name="ck_run_status"))
    op.create_index("ix_workspace_runs_session_id", "workspace_runs", ["session_id"])
    op.create_table("provider_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("solve_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("workspace_runs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated", sa.Boolean(), nullable=False),
        sa.Column("provider_request_id", sa.String(256), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_provider_calls_session_id", "provider_calls", ["session_id"])
    op.create_index("ix_provider_calls_run_id", "provider_calls", ["run_id"])
    # Retain pre-M2 successful call counts and the usage reported in M1 traces.
    # Missing historical usage remains NULL rather than becoming fabricated zero.
    connection = op.get_bind()
    messages = sa.table("conversation_messages", sa.column("id"), sa.column("session_id"),
                        sa.column("role"), sa.column("created_at", sa.DateTime(timezone=True)))
    traces = sa.table("trace_events", sa.column("event_type"), sa.column("envelope", sa.JSON()))
    usage_by_message = {}
    for envelope in connection.execute(sa.select(traces.c.envelope).where(traces.c.event_type == "ASSISTANT_MESSAGE")).scalars():
        usage_by_message[envelope.get("resource_ids", {}).get("message_id")] = envelope.get("payload", {}).get("usage", {})
    calls = sa.table("provider_calls", sa.column("id"), sa.column("session_id"), sa.column("status"),
                     sa.column("input_tokens"), sa.column("output_tokens"), sa.column("estimated", sa.Boolean()),
                     sa.column("created_at", sa.DateTime(timezone=True)), sa.column("finished_at", sa.DateTime(timezone=True)))
    for message in connection.execute(sa.select(messages).where(messages.c.role == "assistant")).mappings():
        usage = usage_by_message.get(message["id"], {})
        incoming, outgoing = usage.get("input_tokens"), usage.get("output_tokens")
        connection.execute(calls.insert().values(id=str(uuid4()), session_id=message["session_id"], status="completed",
            input_tokens=incoming if type(incoming) is int and incoming >= 0 else None,
            output_tokens=outgoing if type(outgoing) is int and outgoing >= 0 else None,
            estimated=usage.get("estimated") is True, created_at=message["created_at"], finished_at=message["created_at"]))
    op.create_table("workspace_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("solve_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("path", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("session_id", "path", name="uq_workspace_path"))
    op.create_index("ix_workspace_files_session_id", "workspace_files", ["session_id"])


def downgrade():
    op.drop_table("workspace_files")
    op.drop_table("provider_calls")
    op.drop_table("workspace_runs")
    op.execute("UPDATE solve_sessions SET status='active' WHERE status='ended'")
    op.execute("DELETE FROM conversation_messages WHERE role='tool'")
    alter_safely(False)
