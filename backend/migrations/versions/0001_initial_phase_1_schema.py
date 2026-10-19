"""initial phase 1 schema: cameras, events, audit_logs

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("camera_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_uri", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("schema_version", sa.String(10), nullable=False),
        sa.Column("camera_id", sa.String(64), nullable=True),
        sa.Column("seat_id", sa.String(64), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_camera_ts", "events", ["camera_id", "timestamp"])
    op.create_index("ix_events_ts", "events", ["timestamp"])
    op.create_table(
        "audit_logs",
        sa.Column("audit_id", sa.String(64), primary_key=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("events")
    op.drop_table("cameras")
