"""Import the reconstructed catalog into three private administrative shops."""

import re

from sqlalchemy import delete, insert, select

from src.shops.classification import classification, group_for
from src.shops.models import Category, Item, Offer, Shop
from src.shops.service import asset_index

FAMILIES = {
    "clothing": ("1", "Админ: одежда и украшения"),
    "bumags": ("2", "Админ: бумаги"),
    "home": ("3", "Админ: интерьер дома"),
}


async def populate(db, key="admin"):
    # HTTP callers hold commerce_lock; CLI is an explicit local operation.
    data, assets = classification(), asset_index()
    shops = {}
    for family, (suffix, title) in FAMILIES.items():
        shop = await db.scalar(select(Shop).where(Shop.key == key + suffix))
        if shop is None:
            legacy_suffix = {"clothing": "", "bumags": "-bumags", "home": "-home"}[family]
            shop = await db.scalar(select(Shop).where(Shop.key == key + legacy_suffix))
            if shop is not None:
                shop.key = key + suffix
        if shop is None:
            shop = Shop(
                key=key + suffix,
                title=title,
                kind="clothing" if family == "clothing" else "objects",
                admin_only=True,
            )
            db.add(shop)
            await db.flush()
        elif shop.title == "Административный каталог":
            shop.title = title
        if family == "clothing":
            shop.kind = "clothing"
        shop.admin_only = True
        shops[family] = shop

    existing_items = {item.id: item for item in await db.scalars(select(Item))}
    new_items, items_classified = [], 0
    for ident in sorted(assets):
        recovered = data["items"][str(ident)]
        fields = {k: recovered[k] for k in ("name", "main_type", "inventory_category")}
        item = existing_items.get(ident)
        if item is None:
            new_items.append(dict(id=ident, enabled=True, **fields))
        elif item.main_type == item.inventory_category == 0 and item.name == f"Предмет {ident}":
            # Upgrade only untouched records from the previous bulk import.
            # Named/typed manual records, prices and ownership are preserved.
            for field, value in fields.items():
                setattr(item, field, value)
            items_classified += 1
    if new_items:
        await db.execute(insert(Item), new_items)
    await db.flush()
    items = {item.id: item for item in await db.scalars(select(Item))}
    groups = {ident: group_for(items[ident], data) for ident in assets}
    shop_ids = [shop.id for shop in shops.values()]
    categories = list(await db.scalars(select(Category).where(Category.shop_id.in_(shop_ids))))
    by_name = {(c.shop_id, c.name): c for c in categories}
    category_ids, categories_created = {}, 0
    for group in sorted(set(groups.values()), key=lambda g: data["groups"][g]["sort"]):
        info = data["groups"][group]
        shop = shops[info["family"]]
        category = by_name.get((shop.id, info["name"]))
        if category is None:
            category = Category(
                shop_id=shop.id,
                **{k: info[k] for k in ("name", "icon_id", "sort")},
            )
            db.add(category)
            await db.flush()
            categories_created += 1
        category_ids[group] = category.id

    offers = list(await db.scalars(select(Offer).where(Offer.shop_id.in_(shop_ids))))
    by_offer = {(o.shop_id, o.item_id): o for o in offers}
    legacy_categories = {c.id for c in categories if re.fullmatch(r"ID \d{4}–\d{4}", c.name)}
    offers_moved = 0
    for offer in offers:
        if offer.category_id not in legacy_categories or offer.item_id not in groups:
            continue
        group = groups[offer.item_id]
        destination = shops[data["groups"][group]["family"]]
        previous = (offer.shop_id, offer.item_id)
        target = (destination.id, offer.item_id)
        if target != previous and target in by_offer:
            # An explicitly configured destination takes precedence over the
            # duplicate legacy listing; purchases reference Item, never Offer.
            await db.delete(offer)
        else:
            offer.shop_id = destination.id
            offer.category_id = category_ids[group]
            by_offer.pop(previous)
            by_offer[target] = offer
        offers_moved += 1
    await db.flush()
    # Remove the obsolete numeric tabs only once their offers have moved.
    if legacy_categories:
        await db.execute(
            delete(Category).where(
                Category.id.in_(legacy_categories),
                Category.id.not_in(select(Offer.category_id)),
            )
        )
    new_offers = []
    for ident, group in sorted(groups.items()):
        shop = shops[data["groups"][group]["family"]]
        if (shop.id, ident) not in by_offer:
            new_offers.append(
                dict(
                    shop_id=shop.id,
                    item_id=ident,
                    category_id=category_ids[group],
                    price=0,
                    experience=0,
                    stock=None,
                    enabled=True,
                    sort=ident,
                )
            )
    if new_offers:
        await db.execute(insert(Offer), new_offers)
    await db.commit()
    return {
        "key": key,
        "shops": [
            {
                "key": shop.key,
                "family": family,
                "title": shop.title,
                "items": sum(data["groups"][g]["family"] == family for g in groups.values()),
            }
            for family, shop in shops.items()
        ],
        "total_assets": len(assets),
        "items_created": len(new_items),
        "items_classified": items_classified,
        "offers_created": len(new_offers),
        "offers_moved": offers_moved,
        "categories_created": categories_created,
        "walking_previews": sum("display" not in a for a in assets.values()),
    }
