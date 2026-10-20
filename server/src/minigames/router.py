from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from src.auth.dependencies import CurrentAccount, Database
from src.inventory.service import equipped
from src.minigames import schemas, service
from src.minigames.catalog import GAMES
from src.minigames.dependencies import CurrentPlayer
from src.minigames.models import GameRun

router = APIRouter(prefix="/api/minigames", tags=["minigames"])


@router.get("")
async def games(account: CurrentAccount):
    return {"games": [{"key": g["key"], "title": g["title"]} for g in GAMES.values()]}


@router.get("/results")
async def results(account: CurrentAccount, db: Database):
    rows = await db.scalars(
        select(GameRun)
        .where(GameRun.account_id == account.id, GameRun.status != "active")
        .order_by(GameRun.started_at.desc())
        .limit(20)
    )
    return {"results": [service.result(run) for run in rows]}


@router.post("/{key}/start", status_code=201)
async def start(key: str, peer: CurrentPlayer, db: Database, request: Request):
    async with request.app.state.commerce_lock:
        run, game = await service.start(db, request.app, peer, key)
        items = await equipped(db, peer.account.id)
    return {
        **game,
        "id": run.id,
        "player": {
            "avatarName": peer.account.username,
            "avatarColor": peer.account.color_id,
            "avatarItems": [item["typeId"] for item in items],
        },
    }


@router.post("/runs/{run_id}/finish")
async def finish(
    run_id: UUID,
    body: schemas.FinishInput,
    peer: CurrentPlayer,
    db: Database,
    request: Request,
):
    async with request.app.state.commerce_lock:
        data, changed = await service.finish(db, request.app, peer, str(run_id), body)
    if changed and data["coins_awarded"]:
        from src.legacy.socket import system, variables
        from src.shops.service import balance

        coins = await balance(db, peer.account.id)
        peer.state["mo_1"] = coins
        request.app.state.world.broadcast(
            peer.room,
            system(
                "uVarsUpdate",
                f'<user id="{peer.account.id}"/>' + variables({"mo_1": coins}),
                peer.room,
            ),
        )
    if changed and data["experience_awarded"]:
        from src.profiles.progression import notify

        await notify(request.app, peer.account.id, data["experience_awarded"])
    return data
