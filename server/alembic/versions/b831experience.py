"""Persistent experience and configurable purchase rewards."""

import sqlalchemy as sa

from alembic import op

revision = "b831experience"
down_revision = "a720shopscat"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "auth_account", sa.Column("experience", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "shop_offer", sa.Column("experience", sa.Integer(), nullable=False, server_default="10")
    )


def downgrade():
    op.drop_column("shop_offer", "experience")
    op.drop_column("auth_account", "experience")
