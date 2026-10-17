"""Administrator chat commands; only server-owned permissions are accepted."""

from fastapi import HTTPException
from sqlalchemy import select

from src.auth.models import Account
from src.profiles import progression
from src.shops.models import Item, OwnedItem


async def give(app, account_id, text):
    parts = text.split()
    if (
        len(parts) != 3
        or parts[1].casefold() not in {"item", "exp"}
        or not parts[2].isascii()
        or not parts[2].isdecimal()
    ):
        raise HTTPException(422, "Команда: /give item ID или /give exp ЧИСЛО")
    value = int(parts[2])
    if not 1 <= value <= 1000000:
        raise HTTPException(422, "Укажите целое число от 1 до 1000000")
    async with app.state.commerce_lock:
        async with app.state.sessions() as db:
            account = await db.get(Account, account_id)
            if not account.is_admin:
                raise HTTPException(403, "Команда доступна только администраторам")
            if parts[1].casefold() == "exp":
                await progression.award(db, account_id, value)
                message = f"Начислено опыта: {value}"
            else:
                item = await db.get(Item, value)
                if item is None:
                    raise HTTPException(404, "Сначала создайте предмет с этим ID в админке")
                if await db.scalar(
                    select(OwnedItem.id).where(
                        OwnedItem.account_id == account_id, OwnedItem.item_id == value
                    )
                ):
                    raise HTTPException(409, "Этот предмет уже есть в инвентаре")
                db.add(OwnedItem(account_id=account_id, item_id=value))
                message = f"Выдан предмет: {item.name} (ID {value})"
            await db.commit()
        if parts[1].casefold() == "exp":
            await progression.notify(app, account_id, value)
        from src.shops.service import changed

        await changed(app)
    return message
