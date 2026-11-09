"""Initial versioned problem, participant workspace, trace and evaluation schema.

Revision ID: 0001_initial
Revises: none
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("identity_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('administrator', 'author', 'participant')", name="ck_user_role"))
    op.create_table("problems",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("problem_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("problem_id", sa.String(128), sa.ForeignKey("problems.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("problem_id", "version", name="uq_problem_version"))
    op.create_index("ix_problem_versions_problem_id", "problem_versions", ["problem_id"])
    op.create_table("solve_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("problem_version_id", sa.String(36), sa.ForeignKey("problem_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("next_sequence_number", sa.Integer(), nullable=False),
        sa.Column("user_message_count", sa.Integer(), nullable=False),
        sa.Column("model_configuration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'submitted')", name="ck_session_status"),
        sa.CheckConstraint("next_sequence_number >= 1", name="ck_next_sequence"),
        sa.CheckConstraint("user_message_count >= 0", name="ck_message_count"))
    op.create_index("ix_solve_sessions_user_id", "solve_sessions", ["user_id"])
    op.create_table("conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("solve_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "position", name="uq_message_position"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"))
    op.create_index("ix_conversation_messages_session_id", "conversation_messages", ["session_id"])
    op.create_table("trace_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("solve_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.UniqueConstraint("session_id", "sequence_number", name="uq_trace_session_sequence"),
        sa.CheckConstraint("sequence_number >= 1", name="ck_trace_sequence"))
    op.create_index("ix_trace_events_session_id", "trace_events", ["session_id"])
    op.create_table("submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("solve_sessions.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("evaluations")
    op.drop_table("submissions")
    op.drop_table("trace_events")
    op.drop_table("conversation_messages")
    op.drop_table("solve_sessions")
    op.drop_table("problem_versions")
    op.drop_table("problems")
    op.drop_table("users")
