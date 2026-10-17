"""Initial server defaults. Existing credentials and manual catalog edits are preserved."""

import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.concurrency import run_in_threadpool

from src.auth.models import Account
from src.auth.service import PASSWORDS, now
from src.config import Settings
from src.database import make_engine
from src.shops.import_catalog import populate


async def initialize(db):
    account = await db.scalar(select(Account).where(Account.username_key == "admin"))
    created = account is None
    if created:
        account = Account(
            username="admin",
            username_key="admin",
            password_hash=await run_in_threadpool(PASSWORDS.hash, "admin"),
            color_id=3,
            age=12,
            chat_mode="open",
            is_admin=True,
            created_at=now(),
        )
        db.add(account)
    # populate commits the account and catalog together, or rolls both back on failure.
    catalog = await populate(db)
    from src.shops.world_shops import populate as populate_world

    world = await populate_world(db)
    return {"admin_created": created, **catalog, "world": world}


async def main():
    engine = make_engine(Settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            print(json.dumps(await initialize(db), ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
