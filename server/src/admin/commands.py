"""Privileged chat commands, with an optional online or offline recipient."""

import re

from fastapi import HTTPException
from sqlalchemy import select, update

from src.auth.models import Account
from src.profiles import progression
from src.shops.models import Item, OwnedItem, Wallet

MAX_COINS = 1000000000


async def give(app, account_id, text):
    parts = text.split()
    if (
        len(parts) not in (3, 4)
        or parts[0].casefold() != "/give"
        or parts[1].casefold() not in {"item", "exp", "coins"}
        or not parts[2].isascii()
        or not parts[2].isdecimal()
    ):
        raise HTTPException(
            422, "Команда: /give item ID [ник], /give exp ЧИСЛО [ник] или /give coins ЧИСЛО [ник]"
        )
    kind = parts[1].casefold()
    value = int(parts[2])
    maximum = MAX_COINS if kind == "coins" else 1000000
    if not 1 <= value <= maximum:
        raise HTTPException(422, f"Укажите целое число от 1 до {maximum}")
    if len(parts) == 4 and not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9_]{4,15}", parts[3]):
        raise HTTPException(422, "Укажите существующий ник без пробелов")
    async with app.state.commerce_lock:
        async with app.state.sessions() as db:
            actor = await db.get(Account, account_id)
            if actor is None or not actor.is_admin:
                raise HTTPException(403, "Команда доступна только администраторам")
            target = (
                actor
                if len(parts) == 3
                else await db.scalar(
                    select(Account).where(Account.username_key == parts[3].casefold())
                )
            )
            if target is None:
                raise HTTPException(404, "Могоби не найден: " + parts[3])
            target_id, target_name = target.id, target.username
            if kind == "exp":
                await progression.award(db, target_id, value)
                message = f"Начислено опыта: {value}"
            elif kind == "coins":
                if await db.get(Wallet, target_id) is None:
                    db.add(Wallet(account_id=target_id, coins=0))
                    await db.flush()
                result = await db.execute(
                    update(Wallet)
                    .where(Wallet.account_id == target_id, Wallet.coins <= MAX_COINS - value)
                    .values(coins=Wallet.coins + value)
                )
                if not result.rowcount:
                    raise HTTPException(409, "Достигнут предел монет")
                message = f"Начислено монет: {value}"
            else:
                item = await db.get(Item, value)
                if item is None:
                    raise HTTPException(404, "Сначала создайте предмет с этим ID в админке")
                if await db.scalar(
                    select(OwnedItem.id).where(
                        OwnedItem.account_id == target_id, OwnedItem.item_id == value
                    )
                ):
                    raise HTTPException(
                        409, "Этот предмет уже есть в инвентаре могоби " + target_name
                    )
                db.add(OwnedItem(account_id=target_id, item_id=value))
                message = f"Выдан предмет: {item.name} (ID {value})"
            await db.commit()
        if kind == "exp":
            await progression.notify(app, target_id, value)
        from src.shops.service import changed

        await changed(app)
    return message + " → " + target_name


async def alert(app, account_id, text):
    command, _, message = text.partition(" ")
    message = message.strip()
    if (
        command.casefold() != "/alert"
        or not message
        or len(message) > 230
        or any(ord(c) < 32 for c in message)
    ):
        raise HTTPException(422, "Команда: /alert сообщение (до 230 символов)")
    async with app.state.commerce_lock:
        async with app.state.sessions() as db:
            actor = await db.get(Account, account_id)
            if actor is None or not actor.is_admin:
                raise HTTPException(403, "Команда доступна только администраторам")
        recipients = [
            peer
            for peer in list(app.state.world.connections.values())
            if peer.user is not None and peer.room is not None
        ]
        for peer in recipients:
            # Original Main recognizes this command; native gateway adds the modal notice.
            await peer.extension(
                "msg__sendPublicMsg", messageType="alert", text=message, sender=actor.username
            )
    return f"Объявление отправлено игрокам: {len(recipients)}"
