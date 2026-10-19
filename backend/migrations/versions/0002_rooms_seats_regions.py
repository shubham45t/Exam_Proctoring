"""rooms, seats, camera seat regions; cameras.room_id + baseline_at

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("room_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("width_m", sa.Float(), nullable=False),
        sa.Column("depth_m", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "seats",
        sa.Column("room_id", sa.String(64), sa.ForeignKey("rooms.room_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("seat_id", sa.String(64), primary_key=True),
        sa.Column("row", sa.Integer(), nullable=False),
        sa.Column("col", sa.Integer(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("monitored", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "camera_seat_regions",
        sa.Column("camera_id", sa.String(64), sa.ForeignKey("cameras.camera_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("room_id", sa.String(64), primary_key=True),
        sa.Column("seat_id", sa.String(64), primary_key=True),
        sa.Column("polygon", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["room_id", "seat_id"], ["seats.room_id", "seats.seat_id"], ondelete="CASCADE"),
    )
    with op.batch_alter_table("cameras") as b:
        b.add_column(sa.Column("room_id", sa.String(64), nullable=True))
        b.add_column(sa.Column("baseline_at", sa.DateTime(), nullable=True))
        b.create_foreign_key("fk_cameras_room", "rooms", ["room_id"], ["room_id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("cameras") as b:
        b.drop_constraint("fk_cameras_room", type_="foreignkey")
        b.drop_column("baseline_at")
        b.drop_column("room_id")
    op.drop_table("camera_seat_regions")
    op.drop_table("seats")
    op.drop_table("rooms")
