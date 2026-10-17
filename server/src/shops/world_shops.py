"""Original room shop points and editable, one-time starter assortments."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import delete, select

from src.config import ROOT
from src.shops.classification import classification
from src.shops.models import Category, Item, Offer, Shop, ShopPoint
from src.shops.service import get_shop
from src.world import catalog as rooms


@lru_cache
def points():
    rows = json.loads(Path(__file__).with_name("points.json").read_text(encoding="utf-8"))
    return {row["id"]: row for row in rows}


async def bindings(db):
    return {row.point_id: row.shop_id for row in await db.scalars(select(ShopPoint))}


async def assign(db, shop, selected):
    if selected is None:
        return
    if len(set(selected)) != len(selected) or any(ident not in points() for ident in selected):
        raise HTTPException(422, "Выберите существующие точки магазинов")
    await db.execute(delete(ShopPoint).where(ShopPoint.shop_id == shop.id))
    for ident in selected:
        binding = await db.get(ShopPoint, ident)
        if binding is None:
            db.add(ShopPoint(point_id=ident, shop_id=shop.id))
        else:
            binding.shop_id = shop.id


async def visible(db, account, room_key=None):
    if room_key is not None and room_key not in rooms.BY_KEY:
        raise HTTPException(404, "Неизвестная комната")
    records = (await db.execute(select(ShopPoint, Shop).join(Shop))).all()
    result = []
    for binding, shop in records:
        point = points().get(binding.point_id)
        if point and (room_key is None or point["room_key"] == room_key):
            if shop.enabled and (not shop.admin_only or account.is_admin):
                result.append({**point, "shop_key": shop.key, "shop_title": shop.title})
    return result


async def resolve(db, point_id, account):
    point = points().get(point_id)
    binding = await db.get(ShopPoint, point_id)
    if point is None or binding is None:
        raise HTTPException(404, "Магазин в этой точке не назначен")
    shop = await db.get(Shop, binding.shop_id)
    return point, await get_shop(db, shop.key, account)


async def populate(db):
    data = json.loads(
        (ROOT.parent / "assets/catalogs/world-shops.json").read_text(encoding="utf-8")
    )
    recovered = classification()
    created = []
    occupied = await bindings(db)
    for row in data["shops"]:
        if await db.scalar(select(Shop.id).where(Shop.key == row["key"])):
            continue  # Operator edits/removals survive subsequent startups.
        shop = Shop(key=row["key"], title=row["title"], kind=row["kind"], admin_only=False)
        db.add(shop)
        await db.flush()
        categories = {}
        for ident in row["items"]:
            item = await db.get(Item, ident)
            if item is None:
                continue
            group = recovered["items"][str(ident)]["category"]
            info = recovered["groups"][group]
            if group not in categories:
                category = Category(
                    shop_id=shop.id, name=info["name"], icon_id=info["icon_id"], sort=info["sort"]
                )
                db.add(category)
                await db.flush()
                categories[group] = category.id
            db.add(
                Offer(
                    shop_id=shop.id,
                    category_id=categories[group],
                    item_id=ident,
                    price=10,
                    experience=10,
                    enabled=True,
                    sort=ident,
                )
            )
        if row["point"] not in occupied:
            db.add(ShopPoint(point_id=row["point"], shop_id=shop.id))
            occupied[row["point"]] = shop.id
        created.append(shop.key)
    await db.commit()
    return {"shops_created": created}


def at_position(point, x, y):
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return False
    left, right, top, bottom = point["bounds"]
    return left - 12 <= x <= right + 12 and top - 12 <= y <= bottom + 12


async def nearby(db, account, room_key, x, y):
    for point in await visible(db, account, room_key):
        if at_position(point, x, y):
            return point, await get_shop(db, point["shop_key"], account)
    return None
