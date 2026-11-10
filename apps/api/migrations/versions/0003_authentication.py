"""Accounts and revocable sessions; legacy browser identities remain quarantined."""
from alembic import op
import sqlalchemy as sa

revision = "0003_authentication"
down_revision = "0002_workspace"
branch_labels = None
depends_on = None


def upgrade():
    # A former bearer cookie is never sufficient to claim an account. No password,
    # username, active status, or privileged role is inferred from old records.
    op.add_column("users", sa.Column("username", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(256), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("uq_users_username", "users", ["username"], unique=True)
    sqlite = op.get_bind().dialect.name == "sqlite"
    if sqlite:
        with op.get_context().autocommit_block():
            op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("problems") as batch:
        batch.add_column(sa.Column("author_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_problem_author", "users", ["author_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_problems_author_id", ["author_id"])
    if sqlite:
        with op.get_context().autocommit_block():
            op.execute("PRAGMA foreign_keys=ON")
    op.create_table("auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table("auth_rate_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False))
    op.create_index("ix_auth_rate_limits_window_start", "auth_rate_limits", ["window_start"])


def downgrade():
    op.drop_table("auth_rate_limits")
    op.drop_table("auth_sessions")
    with op.batch_alter_table("problems") as batch:
        batch.drop_index("ix_problems_author_id")
        batch.drop_constraint("fk_problem_author", type_="foreignkey")
        batch.drop_column("author_id")
    op.drop_index("uq_users_username", table_name="users")
    for name in ("is_active", "password_hash", "username"):
        op.drop_column("users", name)
