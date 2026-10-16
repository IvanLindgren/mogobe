"""Store accepted friendships for accurate profile counters."""

import sqlalchemy as sa

from alembic import op

revision = "e51bd92a36c0"
down_revision = "d34e921b70a2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "social_friendship",
        sa.Column("first_id", sa.Integer(), nullable=False),
        sa.Column("second_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["first_id"], ["auth_account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["second_id"], ["auth_account.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "first_id < second_id", name=op.f("ck_social_friendship_ordered_accounts")
        ),
        sa.PrimaryKeyConstraint("first_id", "second_id"),
    )
    op.create_index("ix_social_friendship_second_id", "social_friendship", ["second_id"])


def downgrade():
    op.drop_table("social_friendship")
