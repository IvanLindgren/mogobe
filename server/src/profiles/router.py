from fastapi import APIRouter, Request
from sqlalchemy import select

from src.auth.dependencies import CurrentAccount, Database
from src.auth.models import Account
from src.profiles import social
from src.profiles.schemas import MuteUpdate
from src.profiles.service import find_profile
from src.profiles.social import muted_ids, pending_count, set_mute

router = APIRouter(prefix="/api/social", tags=["social"])


@router.get("/me")
async def me(account: CurrentAccount, db: Database):
    ids = await muted_ids(db, account.id)
    names = (
        list(await db.scalars(select(Account.username).where(Account.id.in_(ids)))) if ids else []
    )
    return {"muted_names": names, "pending_requests": await pending_count(db, account.id)}


@router.post("/mute")
async def mute(body: MuteUpdate, account: CurrentAccount, db: Database, request: Request):
    hub = request.app.state.world
    async with hub.social_lock:
        target = await find_profile(db, {"userName": body.username})
        await set_mute(db, account.id, target.id, body.muted)
        await db.commit()
        own = hub.connections.get(account.id)
        if own is not None:
            own.muted_ids = await muted_ids(db, account.id)
        # Cancelled requests disappear from an already open original list.
        for ident in (account.id, target.id):
            peer = hub.connections.get(ident)
            if peer is not None and peer.user is not None:
                buddies = await social.buddy_list(db, ident, hub)
                await peer.extension("buddyList__getUserBuddies", buddies=buddies)
    return {"username": target.username, "muted": body.muted}
