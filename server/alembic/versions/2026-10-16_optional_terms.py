"""Allow registration without accepting the optional rules checkbox."""

import sqlalchemy as sa

from alembic import op

revision = "b74f17a319a1"
down_revision = "ec87067cfd5e"
branch_labels = None
depends_on = None


def set_nullable(nullable):
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        # Batch alteration rebuilds the parent table. Disable FK cascades outside
        # a transaction so rebuilding it cannot delete existing login sessions.
        with op.get_context().autocommit_block():
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            try:
                with op.batch_alter_table("auth_account") as batch:
                    batch.alter_column(
                        "terms_accepted_at", existing_type=sa.DateTime(), nullable=nullable
                    )
            finally:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    else:
        op.alter_column(
            "auth_account", "terms_accepted_at", existing_type=sa.DateTime(), nullable=nullable
        )


def upgrade():
    set_nullable(True)


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM auth_account WHERE terms_accepted_at IS NULL LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Cannot downgrade while accounts without accepted terms exist")
    set_nullable(False)
