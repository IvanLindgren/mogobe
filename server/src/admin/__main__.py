"""Grant/revoke server administration: python -m src.admin grant USERNAME."""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.auth.models import Account
from src.config import Settings
from src.database import make_engine


async def change(name, allowed):
    engine = make_engine(Settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            account = await db.scalar(
                select(Account).where(Account.username_key == name.casefold())
            )
            if not account:
                raise SystemExit("Могоби не найден: " + name)
            account.is_admin = allowed
            await db.commit()
            print(
                account.username
                + (": права администратора выданы" if allowed else ": права администратора сняты")
            )
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["grant", "revoke"])
    parser.add_argument("username")
    args = parser.parse_args()
    asyncio.run(change(args.username, args.action == "grant"))


if __name__ == "__main__":
    main()
