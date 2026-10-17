"""Account directory and role management for the separate administration app."""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from src.auth.dependencies import Database
from src.auth.models import Account
from src.profiles.progression import level
from src.shops.dependencies import AdminAccount
from src.shops.models import Wallet
from src.shops.schemas import AdminRoleInput
from src.shops.service import changed

router = APIRouter(prefix="/api/admin/shops/accounts", tags=["administration"])


@router.get("")
async def accounts(
    account: AdminAccount,
    db: Database,
    request: Request,
    q: str = Query(default="", max_length=30),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    condition = Account.username_key.contains(q.strip().casefold(), autoescape=True)
    total = await db.scalar(select(func.count()).select_from(Account).where(condition))
    rows = (
        await db.execute(
            select(Account, Wallet.coins)
            .outerjoin(Wallet, Wallet.account_id == Account.id)
            .where(condition)
            .order_by(Account.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "total": total,
        "offset": offset,
        "accounts": [
            {
                "id": a.id,
                "username": a.username,
                "color_id": a.color_id,
                "is_admin": a.is_admin,
                "score": a.experience,
                "level": level(a.experience),
                "coins": coins or 0,
                "created_at": a.created_at,
                "online": a.id in request.app.state.world.players,
            }
            for a, coins in rows
        ],
    }


@router.put("/{ident}/admin")
async def role(
    ident: int, body: AdminRoleInput, account: AdminAccount, db: Database, request: Request
):
    async with request.app.state.commerce_lock:
        # Recheck under the same lock used to mutate roles and run /give.
        actor = await db.get(Account, account.id, populate_existing=True)
        if not actor.is_admin:
            raise HTTPException(403, "Нужны права администратора")
        target = await db.get(Account, ident)
        if target is None:
            raise HTTPException(404, "Могоби не найден")
        if target.is_admin and not body.is_admin:
            count = await db.scalar(
                select(func.count()).select_from(Account).where(Account.is_admin.is_(True))
            )
            if count <= 1:
                raise HTTPException(409, "Нельзя снять права у последнего администратора")
        target.is_admin = body.is_admin
        await db.commit()
        await changed(request.app)
        return {"id": target.id, "username": target.username, "is_admin": target.is_admin}
