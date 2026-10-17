from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import Account
from src.auth.service import now
from src.inventory.service import equipped
from src.profiles.models import Friendship
from src.profiles.progression import level
from src.shops.service import balance


def days_registered(created_at: datetime, instant: datetime | None = None) -> int:
    def utc(value):
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value

    return max(0, (utc(instant or now()) - utc(created_at)).days)


async def public_profile(db: AsyncSession, account: Account) -> dict:
    friends = await db.scalar(
        select(func.count())
        .select_from(Friendship)
        .where(or_(Friendship.first_id == account.id, Friendship.second_id == account.id))
    )
    return {
        "userId": account.id,
        "appUserId": account.id,
        "userName": account.username,
        "color": account.color_id,
        "age": days_registered(account.created_at),
        "friends": friends,
        "score": account.experience,
        "level": level(account.experience),
        "items": await equipped(db, account.id),
        "isMember": account.is_admin,
        "isAdmin": account.is_admin,
        **{f"mo_{n}": 0 for n in range(1, 11)},
        "mo_1": await balance(db, account.id),
    }


async def find_profile(db: AsyncSession, params: dict) -> Account:
    ident = params.get("userId", params.get("appUserId"))
    name = params.get("userName")
    if ident is not None and ident != -1:
        if type(ident) is not int or not 0 < ident < 2**31:
            raise HTTPException(404, "Могоби не найден")
        account = await db.get(Account, ident)
    elif isinstance(name, str) and 4 <= len(name) <= 15:
        account = await db.scalar(select(Account).where(Account.username_key == name.casefold()))
    else:
        account = None
    if account is None:
        raise HTTPException(404, "Могоби не найден")
    if name is not None and (not isinstance(name, str) or name.casefold() != account.username_key):
        raise HTTPException(404, "Могоби не найден")
    return account
