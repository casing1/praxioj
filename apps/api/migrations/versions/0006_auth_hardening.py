"""Explicit short-lived password confirmation; legacy sessions are unconfirmed."""
from alembic import op
import sqlalchemy as sa

revision = "0006_auth_hardening"
down_revision = "0005_trace"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("auth_sessions", sa.Column("reauthenticated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("auth_sessions", "reauthenticated_at")
