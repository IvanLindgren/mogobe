"""Keep equipped slots consistent with globally edited item metadata."""

from sqlalchemy import select

from src.config import ROOT
from src.inventory.models import EquippedItem
from src.inventory.service import equipped, notify
from src.shops.models import OwnedItem


async def reconcile(db, item):
    owners = set(await db.scalars(select(OwnedItem.account_id).where(OwnedItem.item_id == item.id)))
    worn = list(
        await db.scalars(
            select(EquippedItem)
            .join(OwnedItem, EquippedItem.owned_item_id == OwnedItem.id)
            .where(OwnedItem.item_id == item.id)
        )
    )
    wearable = (
        item.enabled
        and item.main_type == 1
        and 1 <= item.inventory_category <= 23
        and (ROOT.parent / f"assets/compat/item-animations/{item.id}.swf").is_file()
    )
    for entry in worn:
        if not wearable:
            await db.delete(entry)
        elif entry.slot != item.inventory_category:
            conflict = await db.get(EquippedItem, (entry.account_id, item.inventory_category))
            if conflict is None:
                entry.slot = item.inventory_category
            else:
                # Keep the garment already occupying the destination slot;
                # the edited garment remains owned and can be worn later.
                await db.delete(entry)
    await db.flush()
    return owners


async def refresh(app, owners):
    async with app.state.sessions() as db:
        for ident in owners:
            peer = app.state.world.connections.get(ident)
            if peer is None or peer.user is None:
                continue
            await notify(app, ident, await equipped(db, ident))
            # This standard response makes MyCardPopup reload its current
            # inventory tab; no permanent profile polling is introduced.
            await peer.extension("user__setNotInUseItem", items=[])
