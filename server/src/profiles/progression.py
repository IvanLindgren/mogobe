"""Authoritative experience totals and original Mogobe level thresholds."""

from fastapi import HTTPException
from sqlalchemy import update

from src.auth.models import Account

MAX_EXPERIENCE = 2**31 - 1
THRESHOLDS = (1000, 2000, 4000, 8000, 16000, 32000, 64000, 124000, 256000, 512000, 1024000)


def level(score):
    return 1 + sum(score >= threshold for threshold in THRESHOLDS)


async def award(db, account_id, amount):
    if type(amount) is not int or not 0 <= amount <= 1000000:
        raise HTTPException(422, "Опыт должен быть целым числом от 0 до 1000000")
    result = await db.execute(
        update(Account)
        .where(Account.id == account_id, Account.experience <= MAX_EXPERIENCE - amount)
        .values(experience=Account.experience + amount)
        .returning(Account.experience)
    )
    score = result.scalar_one_or_none()
    if score is None:
        raise HTTPException(409, "Достигнут предел опыта")
    return {"experience_awarded": amount, "score": score, "level": level(score)}


async def notify(app, account_id, amount):
    # Original Main handles this extension by creating mlWorldScoreSign.
    from src.legacy.socket import system, variables

    peer = app.state.world.connections.get(account_id)
    if peer is None or peer.room is None:
        return
    async with app.state.sessions() as db:
        account = await db.get(Account, account_id)
        values = {"score": account.experience, "level": level(account.experience)}
    peer.state.update(values)
    app.state.world.broadcast(
        peer.room,
        system("uVarsUpdate", f'<user id="{account_id}"/>' + variables(values), peer.room),
    )
    if amount > 0:
        await peer.extension("user__worldScoreChange", score=amount)
