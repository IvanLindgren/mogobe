"""Persist friend requests, personal mute and best friends."""

import sqlalchemy as sa

from alembic import op

revision = "f629a381d452"
down_revision = "e51bd92a36c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "social_request",
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["sender_id"], ["auth_account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["auth_account.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "sender_id != recipient_id", name=op.f("ck_social_request_different_accounts")
        ),
        sa.PrimaryKeyConstraint("sender_id", "recipient_id"),
    )
    op.create_index("ix_social_request_recipient_id", "social_request", ["recipient_id"])
    op.create_table(
        "social_preference",
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("buddy_id", sa.Integer(), nullable=False),
        sa.Column("muted", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("best", sa.Boolean(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["auth_account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["buddy_id"], ["auth_account.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "owner_id != buddy_id", name=op.f("ck_social_preference_different_accounts")
        ),
        sa.PrimaryKeyConstraint("owner_id", "buddy_id"),
    )


def downgrade():
    op.drop_table("social_preference")
    op.drop_table("social_request")
