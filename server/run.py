"""Apply versioned migrations, then start FastAPI. No development reload by default."""

import argparse
import logging
from pathlib import Path

import uvicorn
from alembic.config import Config
from sqlalchemy.engine import make_url

from alembic import command
from src.config import ROOT, Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--migrate-only", action="store_true")
    parser.add_argument(
        "--log-level", choices=["debug", "info", "warning", "error", "critical"], default="info"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    url = make_url(Settings().database_url)
    if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
        Path(url.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    if not args.migrate_only:
        # Our middleware emits route/status/timing without raw credential-bearing URLs.
        uvicorn.run(
            "src.main:app",
            host=args.host,
            port=args.port,
            access_log=False,
            workers=1,  # The shared room and exclusive account claims live in this process.
            log_level=args.log_level,
        )


if __name__ == "__main__":
    main()
