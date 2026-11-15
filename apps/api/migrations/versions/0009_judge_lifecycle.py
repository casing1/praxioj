"""Bounded Judge evidence/history retention; preserve all existing M5 records."""
from alembic import op
import sqlalchemy as sa

revision = "0009_judge_lifecycle"
down_revision = "0008_judge_execution"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("judge_jobs", sa.Column("evidence_purged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_judge_retention", "judge_jobs", ["finished_at", "id"],
        postgresql_where=sa.text("state IN ('COMPLETED', 'FAILED', 'CANCELLED')"),
        sqlite_where=sa.text("state IN ('COMPLETED', 'FAILED', 'CANCELLED')"))


def downgrade():
    op.drop_index("ix_judge_retention", table_name="judge_jobs")
    op.drop_column("judge_jobs", "evidence_purged_at")
