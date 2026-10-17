"""Fill the three private shops: uv run python -m src.shops.seed_admin."""

import asyncio
import json

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.config import Settings
from src.database import make_engine
from src.shops.import_catalog import populate


async def main():
    engine = make_engine(Settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            result = await populate(db)
            print(json.dumps(result, ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
