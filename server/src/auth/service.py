import hashlib
import secrets
from collections import OrderedDict, deque
from datetime import UTC, datetime, timedelta
from time import monotonic

from fastapi import HTTPException
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.auth import models, schemas
from src.auth.exceptions import InvalidCredentials, RegistrationExpired, UsernameTaken
from src.config import Settings

PASSWORDS = PasswordHash.recommended()
# Computed once at import; unknown accounts still perform a real password check.
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AttemptLimiter:
    """Bounded per-process limiter. Deploy one worker until a shared limiter is added."""

    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.attempts: OrderedDict[str, deque] = OrderedDict()

    def check(self, peer: str) -> None:
        instant = monotonic()
        bucket = self.attempts.setdefault(peer, deque())
        self.attempts.move_to_end(peer)
        while bucket and bucket[0] <= instant - self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(429, "Слишком много попыток. Попробуйте позже")
        bucket.append(instant)
        if len(self.attempts) > 10000:
            self.attempts.popitem(last=False)


async def start_registration(
    db: AsyncSession, body: schemas.RegistrationStart, settings: Settings, old_token: str | None
) -> str:
    key = body.username.casefold()
    if await db.scalar(select(models.Account.id).where(models.Account.username_key == key)):
        raise UsernameTaken()
    hashed = await run_in_threadpool(PASSWORDS.hash, body.password.get_secret_value())
    token = secrets.token_urlsafe(32)
    await db.execute(
        delete(models.RegistrationDraft).where(models.RegistrationDraft.expires_at <= now())
    )
    if old_token:
        await db.execute(
            delete(models.RegistrationDraft).where(
                models.RegistrationDraft.token_hash == token_hash(old_token)
            )
        )
    db.add(
        models.RegistrationDraft(
            token_hash=token_hash(token),
            username=body.username,
            username_key=key,
            password_hash=hashed,
            color_id=body.color_id,
            expires_at=now() + timedelta(minutes=settings.registration_minutes),
        )
    )
    await db.commit()
    return token


async def finish_registration(
    db: AsyncSession, body: schemas.RegistrationFinish, token: str | None
) -> models.Account:
    # DELETE RETURNING claims a draft atomically, including concurrent submissions.
    # A rollback restores it if account creation fails.
    draft = (
        await db.execute(
            delete(models.RegistrationDraft)
            .where(
                models.RegistrationDraft.token_hash == token_hash(token or ""),
                models.RegistrationDraft.expires_at > now(),
            )
            .returning(models.RegistrationDraft)
        )
    ).scalar_one_or_none()
    if draft is None:
        raise RegistrationExpired()
    account = models.Account(
        username=draft.username,
        username_key=draft.username_key,
        password_hash=draft.password_hash,
        color_id=draft.color_id,
        age=body.age,
        chat_mode=body.chat_mode,
        newsletter=body.newsletter,
        parent_email=str(body.parent_email) if body.parent_email else None,
        terms_accepted_at=now() if body.accepted_terms else None,
        created_at=now(),
    )
    db.add(account)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise UsernameTaken() from exc
    return account


async def authenticate(db: AsyncSession, body: schemas.Credentials) -> models.Account:
    account = await db.scalar(
        select(models.Account).where(models.Account.username_key == body.username.casefold())
    )
    valid = await run_in_threadpool(
        PASSWORDS.verify,
        body.password.get_secret_value(),
        account.password_hash if account else DUMMY_HASH,
    )
    if account is None or not valid:
        raise InvalidCredentials()
    return account


async def create_session(
    db: AsyncSession,
    account_id: int,
    settings: Settings,
    remember_me: bool = False,
    previous_token: str | None = None,
) -> str:
    token = secrets.token_urlsafe(32)
    await db.execute(delete(models.Session).where(models.Session.expires_at <= now()))
    if previous_token:
        # Switching mogobes must keep the previous mogobe's remembered session alive.
        await db.execute(
            delete(models.Session).where(
                models.Session.token_hash == token_hash(previous_token),
                models.Session.account_id == account_id,
            )
        )
    lifetime = (
        timedelta(days=settings.remembered_session_days)
        if remember_me
        else timedelta(hours=settings.session_hours)
    )
    db.add(
        models.Session(
            token_hash=token_hash(token),
            account_id=account_id,
            expires_at=now() + lifetime,
        )
    )
    await db.commit()
    return token


async def find_account(db: AsyncSession, token: str | None) -> models.Account:
    account = await db.scalar(
        select(models.Account)
        .join(models.Session)
        .where(
            models.Session.token_hash == token_hash(token or ""), models.Session.expires_at > now()
        )
    )
    if account is None:
        raise HTTPException(401, "Войдите в аккаунт")
    return account


async def logout(db: AsyncSession, token: str | None) -> None:
    await db.execute(
        delete(models.Session).where(models.Session.token_hash == token_hash(token or ""))
    )
    await db.commit()
