"""add app_settings

Revision ID: e4f2a1c8b3d7
Revises: 82318fbd2666
Create Date: 2026-07-14 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4f2a1c8b3d7"
down_revision = "82318fbd2666"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, server_default="1"),
        sa.Column("rsyslog_host", sa.String(length=255), nullable=True),
        sa.Column("rsyslog_port", sa.Integer(), nullable=False, server_default="514"),
        sa.Column("rsyslog_proto", sa.String(length=8), nullable=False, server_default="tcp"),
        sa.Column("rsyslog_facility", sa.String(length=32), nullable=False, server_default="local0"),
        sa.Column("log_retention_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rsyslog_proto IN ('tcp', 'udp')", name="ck_settings_proto"),
        sa.CheckConstraint("rsyslog_port BETWEEN 1 AND 65535", name="ck_settings_port"),
        sa.CheckConstraint("log_retention_days >= 1", name="ck_settings_retention"),
    )
    # Seed the singleton row so reads always succeed.
    op.execute(
        "INSERT INTO app_settings (id, rsyslog_host, rsyslog_port, rsyslog_proto, "
        "rsyslog_facility, log_retention_days, updated_at) "
        "VALUES (1, NULL, 514, 'tcp', 'local0', 7, CURRENT_TIMESTAMP)"
    )


def downgrade():
    op.drop_table("app_settings")
