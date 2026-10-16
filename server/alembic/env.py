import asyncio

from alembic import context
from src.auth import models  # noqa: F401 - register domain tables
from src.config import Settings
from src.database import make_engine
from src.models import Base
from src.profiles import models as profile_models  # noqa: F401


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = make_engine(Settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
