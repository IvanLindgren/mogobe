"""Shared administration entry point, authentication and server overview."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi import Response as CookieResponse
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select

from src.admin.accounts import router as accounts_router
from src.admin.dependencies import AdminAccount
from src.auth import schemas as auth_schemas
from src.auth import service as auth_service
from src.auth.dependencies import Config, Database, get_token, limit_attempts
from src.auth.models import Account
from src.auth.router import set_session_cookie
from src.shops.models import Item, Shop
from src.world import catalog as rooms

router = APIRouter(tags=["administration"])
router.include_router(accounts_router, prefix="/api/admin")
# Keep saved scripts/bookmarks working; only canonical routes appear in /docs.
router.include_router(accounts_router, prefix="/api/admin/shops", include_in_schema=False)
WEB = Path(__file__).with_name("web")


@router.get("/admin", include_in_schema=False)
@router.get("/admin/", include_in_schema=False)
async def admin_page():
    return FileResponse(WEB / "index.html")


@router.get("/admin/app.js", include_in_schema=False)
async def admin_script():
    return FileResponse(WEB / "app.js", media_type="text/javascript")


@router.get("/admin/style.css", include_in_schema=False)
async def admin_style():
    return FileResponse(WEB / "style.css", media_type="text/css")


@router.get("/admin/shops", include_in_schema=False)
async def old_admin_page():
    return RedirectResponse("/admin", status_code=307)


@router.get("/admin/shops/app.js", include_in_schema=False)
async def old_admin_script():
    return RedirectResponse("/admin/app.js", status_code=307)


@router.get("/admin/shops/style.css", include_in_schema=False)
async def old_admin_style():
    return RedirectResponse("/admin/style.css", status_code=307)


@router.get("/api/admin/overview")
async def overview(account: AdminAccount, db: Database, request: Request):
    return {
        "server_name": request.app.state.settings.server_name,
        "online": len(request.app.state.world.players),
        "accounts": await db.scalar(select(func.count()).select_from(Account)),
        "administrators": await db.scalar(
            select(func.count()).select_from(Account).where(Account.is_admin.is_(True))
        ),
        "rooms": len(rooms.BY_ID),
        "shops": await db.scalar(select(func.count()).select_from(Shop)),
        "items": await db.scalar(select(func.count()).select_from(Item)),
    }


@router.post("/api/admin/login")
@router.post("/api/admin/shops/login", include_in_schema=False)
async def admin_login(
    body: auth_schemas.Credentials,
    db: Database,
    request: Request,
    response: CookieResponse,
    settings: Config,
):
    limit_attempts(request)
    account = await auth_service.authenticate(db, body)
    if not account.is_admin:
        raise HTTPException(403, "Нужны права администратора")
    token = await auth_service.create_session(
        db, account.id, settings, previous_token=get_token(request)
    )
    set_session_cookie(response, token, settings)
    return {"username": account.username}


@router.get("/api/admin/me")
@router.get("/api/admin/shops/me", include_in_schema=False)
async def admin_me(account: AdminAccount):
    return {"username": account.username}
