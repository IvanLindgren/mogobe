"""Persistent clothing slots, independent of room coordinates."""

import sqlalchemy as sa
from alembic import op

revision = "c942wardrobe"
down_revision = "b831experience"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_equipped",
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("auth_account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("slot", sa.Integer(), primary_key=True),
        sa.Column(
            "owned_item_id",
            sa.Integer(),
            sa.ForeignKey("shop_owned_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("owned_item_id"),
    )


def downgrade():
    op.drop_table("inventory_equipped")
