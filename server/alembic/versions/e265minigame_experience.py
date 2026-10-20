"""Experience awarded with original minigame results."""

import sqlalchemy as sa

from alembic import op

revision = "e265minigameexp"
down_revision = "e264minigames"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "minigame_run", sa.Column("experience", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade():
    op.drop_column("minigame_run", "experience")
