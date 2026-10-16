"""Keep room positions in connection memory instead of SQLite."""

import sqlalchemy as sa

from alembic import op

revision = "d34e921b70a2"
down_revision = "c918a202ef70"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("world_player")


def downgrade():
    # Restoring the schema does not resurrect historical positions.
    op.create_table(
        "world_player",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.CheckConstraint("room_id = 2", name=op.f("ck_world_player_infoboard_only")),
        sa.CheckConstraint(
            "x >= 0 AND x < 768 AND y >= 0 AND y < 480",
            name=op.f("ck_world_player_position_bounds"),
        ),
        sa.ForeignKeyConstraint(["account_id"], ["auth_account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id"),
    )
