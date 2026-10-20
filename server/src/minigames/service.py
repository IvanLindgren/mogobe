"""Persistent results and one active run per authenticated world connection.

The SWF reports its score. Time/score bounds and an atomic single-use payout
limit abuse; this is not a server simulation or proof of every caught item.
"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update

from src.minigames.catalog import GAMES
from src.minigames.models import GameRun
from src.profiles import progression
from src.shops.models import Wallet

MAX_COINS = 1000000000


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def connected(app, peer):
    if app.state.world.connections.get(peer.account.id) is not peer or peer.room is None:
        raise HTTPException(409, "Игровое подключение завершилось")


async def start(db, app, peer, key):
    connected(app, peer)
    game = GAMES.get(key.casefold())
    if game is None:
        raise HTTPException(404, "Миниигра не найдена")
    active = await db.scalar(
        select(GameRun).where(GameRun.account_id == peer.account.id, GameRun.status == "active")
    )
    if active:
        if getattr(peer, "minigame_run", None) == active.id:
            raise HTTPException(409, "Сначала завершите текущую миниигру")
        active.status, active.finished_at = "cancelled", now()
    run = GameRun(
        id=str(uuid4()),
        account_id=peer.account.id,
        game_key=game["key"],
        room_id=peer.room,
        started_at=now(),
        score=0,
        coins=0,
        experience=0,
    )
    db.add(run)
    await db.commit()
    connected(app, peer)
    peer.minigame_run = run.id
    return run, game


def result(run):
    return {
        "id": run.id,
        "key": run.game_key,
        "status": run.status,
        "score": run.score,
        "coins_awarded": run.coins,
        "experience_awarded": run.experience,
    }


async def finish(db, app, peer, run_id, body):
    connected(app, peer)
    run = await db.get(GameRun, run_id)
    if run is None or run.account_id != peer.account.id:
        raise HTTPException(404, "Игра не найдена")
    if run.status != "active":
        return result(run), False  # Retrying a lost HTTP response never pays twice.
    if getattr(peer, "minigame_run", None) != run.id or peer.room != run.room_id:
        raise HTTPException(409, "Эта миниигра больше не активна")
    elapsed = (now() - run.started_at).total_seconds()
    if not body.cancelled:
        if not 0 <= elapsed <= 3600 or (body.completed and elapsed < 43):
            raise HTTPException(409, "Недопустимая длительность игры")
        if body.score > elapsed * 1000:
            raise HTTPException(422, "Недопустимый результат игры")
    game = GAMES[run.game_key]
    coins = 0 if body.cancelled else min(body.score // game["score_per_coin"], game["max_coins"])
    experience = (
        0
        if body.cancelled
        else min(body.score // game["score_per_experience"], game["max_experience"])
    )
    if coins:
        wallet = await db.get(Wallet, peer.account.id)
        if wallet is None:
            wallet = Wallet(account_id=peer.account.id, coins=0)
            db.add(wallet)
            await db.flush()
        coins = min(coins, max(0, MAX_COINS - wallet.coins))
        await db.execute(
            update(Wallet)
            .where(Wallet.account_id == peer.account.id)
            .values(coins=Wallet.coins + coins)
        )
    if experience:
        await progression.award(db, peer.account.id, experience)
    run.status = "cancelled" if body.cancelled else "finished" if body.completed else "stopped"
    run.finished_at, run.score, run.coins = now(), body.score, coins
    run.experience = experience
    await db.commit()
    if getattr(peer, "minigame_run", None) == run.id:
        peer.minigame_run = None
    return result(run), True


async def cancel_connection(app, peer):
    run_id = getattr(peer, "minigame_run", None)
    if not run_id:
        return
    async with app.state.commerce_lock:
        async with app.state.sessions() as db:
            await db.execute(
                update(GameRun)
                .where(
                    GameRun.id == run_id,
                    GameRun.account_id == peer.account.id,
                    GameRun.status == "active",
                )
                .values(status="cancelled", finished_at=now())
            )
            await db.commit()
        if getattr(peer, "minigame_run", None) == run_id:
            peer.minigame_run = None
