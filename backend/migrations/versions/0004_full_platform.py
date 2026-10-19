"""full platform: users, exams, candidate_incidents, review_alerts, incident_reviews; camera toggles

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # 2. exams
    op.create_table(
        "exams",
        sa.Column("exam_id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("course_code", sa.String(50), nullable=True),
        sa.Column("room_id", sa.String(64), sa.ForeignKey("rooms.room_id", ondelete="SET NULL"), nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="SCHEDULED"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_exams_status", "exams", ["status"])

    # 3. candidate_incidents
    op.create_table(
        "candidate_incidents",
        sa.Column("incident_id", sa.String(64), primary_key=True),
        sa.Column("exam_id", sa.String(64), sa.ForeignKey("exams.exam_id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("camera_id", sa.String(64), nullable=False),
        sa.Column("seat_id", sa.String(64), nullable=True),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("review_priority_score", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("rules_triggered", sa.JSON(), nullable=False),
        sa.Column("observation_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_candidate_incidents_created_at", "candidate_incidents", ["created_at"])
    op.create_index("ix_candidate_incidents_exam_id", "candidate_incidents", ["exam_id"])

    # 4. review_alerts
    op.create_table(
        "review_alerts",
        sa.Column("alert_id", sa.String(64), primary_key=True),
        sa.Column("incident_id", sa.String(64), sa.ForeignKey("candidate_incidents.incident_id", ondelete="CASCADE"), nullable=False),
        sa.Column("exam_id", sa.String(64), sa.ForeignKey("exams.exam_id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("notice", sa.Text(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_review_alerts_status", "review_alerts", ["status"])
    op.create_index("ix_review_alerts_created_at", "review_alerts", ["created_at"])

    # 5. incident_reviews
    op.create_table(
        "incident_reviews",
        sa.Column("review_id", sa.String(64), primary_key=True),
        sa.Column("alert_id", sa.String(64), sa.ForeignKey("review_alerts.alert_id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_incident_reviews_alert_id", "incident_reviews", ["alert_id"])

    # 6. camera toggles
    with op.batch_alter_table("cameras") as b:
        b.add_column(sa.Column("head_pose_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        b.add_column(sa.Column("spatial_rules_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("cameras") as b:
        b.drop_column("spatial_rules_enabled")
        b.drop_column("head_pose_enabled")
    op.drop_table("incident_reviews")
    op.drop_table("review_alerts")
    op.drop_table("candidate_incidents")
    op.drop_table("exams")
    op.drop_table("users")
