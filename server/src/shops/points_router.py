"""Open assigned shops from original room interaction points."""

from fastapi import APIRouter, HTTPException, Request

from src.auth.dependencies import CurrentAccount, Database
from src.profiles.service import public_profile
from src.shops import service, world_shops
from src.world import catalog as rooms

router = APIRouter(tags=["shop points"])


@router.get("/api/shop-points")
async def room_points(account: CurrentAccount, db: Database, room: str | None = None):
    return {"room": room, "points": await world_shops.visible(db, account, room)}


@router.post("/api/shop-points/{point_id}/open")
async def open_point(point_id: str, account: CurrentAccount, db: Database, request: Request):
    point, shop = await world_shops.resolve(db, point_id, account)
    peer = request.app.state.world.connections.get(account.id)
    if peer is None or peer.room != rooms.BY_KEY[point["room_key"]]["id"]:
        raise HTTPException(409, "Сначала перейдите в комнату этого магазина")
    if not world_shops.at_position(point, peer.state.get("x"), peer.state.get("y")):
        raise HTTPException(409, "Подойдите к торговой точке")
    return {**await service.catalog(db, shop, account), "user": await public_profile(db, account)}
