import asyncio

import httpx
import pytest
from alembic.config import Config

from alembic import command
from src.config import ROOT, Settings
from src.main import create_app


@pytest.fixture
async def app(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'test.sqlite3').as_posix()}"
    monkeypatch.setenv("MOGOBE_DATABASE_URL", url)
    monkeypatch.setenv("MOGOBE_BOOTSTRAP_DEFAULTS", "false")
    await asyncio.to_thread(command.upgrade, Config(str(ROOT / "alembic.ini")), "head")
    application = create_app(Settings(database_url=url))
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
