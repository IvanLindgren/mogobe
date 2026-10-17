"""Editable room shop bindings and optional inventory slots on categories."""

import sqlalchemy as sa

from alembic import op

revision = "d153shoppoints"
down_revision = "c942wardrobe"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shop_category", sa.Column("inventory_category", sa.Integer(), nullable=True))
    op.create_table(
        "shop_point",
        sa.Column("point_id", sa.String(100), primary_key=True),
        sa.Column(
            "shop_id", sa.Integer(), sa.ForeignKey("shop.id", ondelete="CASCADE"), nullable=False
        ),
    )
    op.create_index("ix_shop_point_shop_id", "shop_point", ["shop_id"])


def downgrade():
    op.drop_table("shop_point")
    op.drop_column("shop_category", "inventory_category")
