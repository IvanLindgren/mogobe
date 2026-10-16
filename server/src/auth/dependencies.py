from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from src.auth import models, service
from src.config import Settings
from src.database import get_session

Database = Annotated[AsyncSession, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


Config = Annotated[Settings, Depends(get_settings)]


def get_token(request: HTTPConnection) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return request.cookies.get("mogobe_session")


async def current_account(db: Database, request: Request) -> models.Account:
    return await service.find_account(db, get_token(request))


CurrentAccount = Annotated[models.Account, Depends(current_account)]


def limit_attempts(request: Request) -> None:
    # Called from async routes in the event loop; no blocking I/O or awaits here.
    peer = request.client.host if request.client else "unknown"
    request.app.state.attempt_limiter.check(peer)
