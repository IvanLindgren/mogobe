"""Editable shop catalogs, administrator permission, balances and inventory."""

import sqlalchemy as sa

from alembic import op

revision = "a720shopscat"
down_revision = "f629a381d452"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "auth_account", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0")
    )
    op.create_table(
        "shop",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(40), nullable=False, unique=True),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("admin_only", sa.Boolean(), nullable=False),
        sa.Column("room_key", sa.String(40), unique=True),
    )
    op.create_table(
        "shop_item",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("main_type", sa.Integer(), nullable=False),
        sa.Column("inventory_category", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "shop_category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "shop_id", sa.Integer(), sa.ForeignKey("shop.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("icon_id", sa.Integer(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
    )
    op.create_index("ix_shop_category_shop_id", "shop_category", ["shop_id"])
    op.create_table(
        "shop_offer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "shop_id", sa.Integer(), sa.ForeignKey("shop.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("shop_item.id"), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("shop_category.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("stock", sa.Integer()),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.UniqueConstraint("shop_id", "item_id"),
        sa.CheckConstraint("price >= 0", name="positive_price"),
        sa.CheckConstraint("stock IS NULL OR stock >= 0", name="positive_stock"),
    )
    op.create_index("ix_shop_offer_shop_id", "shop_offer", ["shop_id"])
    op.create_table(
        "shop_wallet",
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("auth_account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.CheckConstraint("coins >= 0", name="positive_coins"),
    )
    op.create_table(
        "shop_owned_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("auth_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("shop_item.id"), nullable=False),
        sa.UniqueConstraint("account_id", "item_id"),
    )
    op.create_index("ix_shop_owned_item_account_id", "shop_owned_item", ["account_id"])


def downgrade():
    for name in [
        "shop_owned_item",
        "shop_wallet",
        "shop_offer",
        "shop_category",
        "shop_item",
        "shop",
    ]:
        op.drop_table(name)
    op.drop_column("auth_account", "is_admin")
