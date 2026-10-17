import json
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import select, update

from src.auth.models import Account
from src.config import ROOT
from src.profiles import progression
from src.shops.models import Category, Item, Offer, OwnedItem, Shop, Wallet


@lru_cache
def asset_index():
    data = json.loads(
        (ROOT.parent / "assets/catalogs/shop-assets.json").read_text(encoding="utf-8")
    )
    return {r["id"]: r for r in data["items"] if "display" in r or "walking" in r}


@lru_cache
def category_icons():
    data = json.loads(
        (ROOT.parent / "assets/catalogs/shop-categories.json").read_text(encoding="utf-8")
    )
    return {r["id"]: r for r in data["icons"]}


def check_category_icon(ident):
    if ident not in category_icons():
        raise HTTPException(422, "Выберите оригинальную иконку категории")


def check_asset(ident, needs_animation=False):
    row = asset_index().get(ident)
    if not row or (needs_animation and not ("standing" in row or "walking" in row)):
        raise HTTPException(422, "Нет подходящей графики предмета: " + str(ident))


def record(model):
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


async def get_shop(db, key, account=None):
    shop = await db.scalar(select(Shop).where(Shop.key == key))
    if not shop or (
        account is not None and (not shop.enabled or (shop.admin_only and not account.is_admin))
    ):
        raise HTTPException(404, "Магазин недоступен или не найден")
    return shop


async def balance(db, account_id):
    return await db.scalar(select(Wallet.coins).where(Wallet.account_id == account_id)) or 0


def legacy_item(item, ident=None, category=1, price=0, available=True):
    return {
        "id": ident or item.id,
        "typeId": item.id,
        "sCat": category,
        "pCat": item.inventory_category,
        "price": price,
        "src": 1,
        "mType": item.main_type,
        "inStock": available,
        "locked": False,
        "trd": 1,
        "s": 100,
        "sts": 0,
        "name": item.name,
    }


async def inventory(db, account_id, main_type=None):
    query = (
        select(OwnedItem, Item)
        .join(Item, Item.id == OwnedItem.item_id)
        .where(OwnedItem.account_id == account_id)
    )
    if main_type is not None:
        query = query.where(Item.main_type == main_type)
    return [legacy_item(item, owned.id) for owned, item in (await db.execute(query)).all()]


async def catalog(db, shop, account):
    owned = set(
        await db.scalars(select(OwnedItem.item_id).where(OwnedItem.account_id == account.id))
    )
    categories = list(
        await db.scalars(
            select(Category).where(Category.shop_id == shop.id).order_by(Category.sort, Category.id)
        )
    )
    visual_categories = {c.id: c.id * 100 + c.icon_id for c in categories}
    pairs = (
        await db.execute(
            select(Offer, Item)
            .join(Item, Item.id == Offer.item_id)
            .where(Offer.shop_id == shop.id, Offer.enabled.is_(True), Item.enabled.is_(True))
            .order_by(Offer.sort, Offer.id)
        )
    ).all()
    items = [
        legacy_item(
            item,
            category=visual_categories[offer.category_id],
            price=offer.price,
            available=(offer.stock is None or offer.stock > 0) and item.id not in owned,
        )
        for offer, item in pairs
    ]
    return {
        "key": shop.key,
        "title": shop.title,
        "kind": shop.kind,
        "admin_only": shop.admin_only,
        "categories": [{"typeId": visual_categories[c.id], "name": c.name} for c in categories],
        "items": items,
        "coins": await balance(db, account.id),
    }


async def purchase(db, account, key, item_id, expected_price):
    # All callers hold commerce_lock. The conditional updates also guard the
    # wallet/stock in SQLite; failure rolls back the entire purchase.
    account = await db.get(Account, account.id, populate_existing=True)
    shop = await get_shop(db, key, account)
    pair = (
        await db.execute(
            select(Offer, Item)
            .join(Item, Item.id == Offer.item_id)
            .where(
                Offer.shop_id == shop.id,
                Offer.item_id == item_id,
                Offer.enabled.is_(True),
                Item.enabled.is_(True),
            )
        )
    ).first()
    if not pair:
        raise HTTPException(404, "Предмет больше не продаётся")
    offer, item = pair
    if offer.price != expected_price:
        raise HTTPException(409, "Цена изменилась. Выберите предмет заново.")
    if await db.scalar(
        select(OwnedItem.id).where(OwnedItem.account_id == account.id, OwnedItem.item_id == item_id)
    ):
        raise HTTPException(409, "Этот предмет уже есть в инвентаре")
    if offer.stock is not None:
        result = await db.execute(
            update(Offer).where(Offer.id == offer.id, Offer.stock > 0).values(stock=Offer.stock - 1)
        )
        if not result.rowcount:
            raise HTTPException(409, "Предмет закончился")
    wallet = await db.get(Wallet, account.id)
    if wallet is None:
        db.add(Wallet(account_id=account.id, coins=0))
        await db.flush()
    paid = await db.execute(
        update(Wallet)
        .where(Wallet.account_id == account.id, Wallet.coins >= offer.price)
        .values(coins=Wallet.coins - offer.price)
    )
    if not paid.rowcount:
        raise HTTPException(409, "Не хватает монет")
    db.add(OwnedItem(account_id=account.id, item_id=item_id))
    reward = await progression.award(db, account.id, offer.experience)
    await db.commit()
    return {"status": True, "item_id": item_id, "coins": await balance(db, account.id), **reward}


async def changed(app):
    # This runs only after edits/purchases, never as a background poll.
    from src.legacy.socket import system, variables

    async with app.state.sessions() as db:
        for peer in list(app.state.world.connections.values()):
            if peer.user is None:
                continue
            coins = await balance(db, peer.account.id)
            account = await db.get(Account, peer.account.id)
            fields = {
                "mo_1": coins,
                "isMember": account.is_admin,
                "isAdmin": account.is_admin,
                "score": account.experience,
                "level": progression.level(account.experience),
            }
            updates = {key: value for key, value in fields.items() if peer.state.get(key) != value}
            if peer.room is not None and updates:
                peer.state.update(updates)
                app.state.world.broadcast(
                    peer.room,
                    system(
                        "uVarsUpdate",
                        f'<user id="{peer.account.id}"/>' + variables(updates),
                        peer.room,
                    ),
                )
            await peer.extension("shop__changed")
