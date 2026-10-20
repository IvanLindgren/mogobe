"""Persistent minigame results; no world positions are persisted."""

import sqlalchemy as sa

from alembic import op

revision = "e264minigames"
down_revision = "d153shoppoints"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "minigame_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("auth_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("game_key", sa.String(40), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.CheckConstraint("score >= 0 AND coins >= 0", name="positive_result"),
    )
    op.create_index("ix_minigame_run_account_id", "minigame_run", ["account_id"])


def downgrade():
    op.drop_table("minigame_run")
