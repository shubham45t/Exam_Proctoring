"""evidence table; cameras.object_detection

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(64), primary_key=True),
        sa.Column("camera_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("file_name", sa.String(100), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
    )
    op.create_index("ix_evidence_camera_id", "evidence", ["camera_id"])
    op.create_index("ix_evidence_captured_at", "evidence", ["captured_at"])
    with op.batch_alter_table("cameras") as b:
        b.add_column(sa.Column("object_detection", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("cameras") as b:
        b.drop_column("object_detection")
    op.drop_table("evidence")
