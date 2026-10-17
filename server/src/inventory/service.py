"""Server-owned outfit slots and original client item records."""

import json

from fastapi import HTTPException
from sqlalchemy import delete, select

from src.config import ROOT
from src.inventory.models import EquippedItem
from src.shops.models import Item, OwnedItem
from src.shops.service import legacy_item


async def equipped(db, account_id):
    rows = await db.execute(
        select(OwnedItem, Item)
        .join(Item, Item.id == OwnedItem.item_id)
        .join(EquippedItem, EquippedItem.owned_item_id == OwnedItem.id)
        .where(EquippedItem.account_id == account_id)
        .order_by(EquippedItem.slot)
    )
    return [legacy_item(item, owned.id) for owned, item in rows.all()]


async def change(db, account_id, ids, *, wear):
    # Caller holds commerce_lock. Validate the entire request before mutation.
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 24
        or any(type(i) is not int or i <= 0 for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise HTTPException(422, "Некорректный список вещей")
    rows = (
        await db.execute(
            select(OwnedItem, Item)
            .join(Item, Item.id == OwnedItem.item_id)
            .where(OwnedItem.account_id == account_id, OwnedItem.id.in_(ids))
        )
    ).all()
    if len(rows) != len(ids):
        raise HTTPException(404, "Вещь не принадлежит этому могоби")
    slots = [item.inventory_category for _, item in rows]
    if wear and (
        len(set(slots)) != len(slots)
        or any(
            item.main_type != 1
            or not 1 <= item.inventory_category <= 23
            or not (ROOT.parent / f"assets/compat/item-animations/{item.id}.swf").is_file()
            for _, item in rows
        )
    ):
        raise HTTPException(422, "Эту вещь нельзя надеть")
    if wear:
        await db.execute(
            delete(EquippedItem).where(
                EquippedItem.account_id == account_id, EquippedItem.slot.in_(slots)
            )
        )
        for owned, item in rows:
            db.add(
                EquippedItem(
                    account_id=account_id, slot=item.inventory_category, owned_item_id=owned.id
                )
            )
    else:
        await db.execute(
            delete(EquippedItem).where(
                EquippedItem.account_id == account_id, EquippedItem.owned_item_id.in_(ids)
            )
        )
    await db.commit()
    return await equipped(db, account_id)


async def available(db, account_id, main_type, categories):
    query = (
        select(OwnedItem, Item)
        .join(Item, Item.id == OwnedItem.item_id)
        .where(
            OwnedItem.account_id == account_id,
            OwnedItem.id.not_in(
                select(EquippedItem.owned_item_id).where(EquippedItem.account_id == account_id)
            ),
        )
    )

    # MyCardPopup builds these codes with name.split("_"): the original
    # SmartFox payload therefore contains strings, including pet main types.
    def code(value):
        if type(value) is int:
            return value
        if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 5:
            return int(value)
        return None

    if main_type is not None:
        selected_type = code(main_type)
        if selected_type is None:
            return []
        query = query.where(Item.main_type == selected_type)
    if categories is not None:
        if not isinstance(categories, list):
            return []
        selected_categories = [code(value) for value in categories]
        if any(value is None for value in selected_categories):
            return []
        if selected_categories:
            query = query.where(Item.inventory_category.in_(selected_categories))
    return [legacy_item(item, owned.id) for owned, item in (await db.execute(query)).all()]


async def notify(app, account_id, items):
    from src.legacy.socket import system, variables

    peer = app.state.world.connections.get(account_id)
    if peer is None or peer.user is None:
        return
    values = {"items": json.dumps(items, ensure_ascii=False)}
    peer.state.update(values)
    if peer.room is not None:
        app.state.world.broadcast(
            peer.room,
            system("uVarsUpdate", f'<user id="{account_id}"/>' + variables(values), peer.room),
        )
