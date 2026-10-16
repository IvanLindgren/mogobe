from fastapi import APIRouter, Request, Response

from src.auth import schemas, service
from src.auth.dependencies import Config, CurrentAccount, Database, get_token, limit_attempts

router = APIRouter(prefix="/api/auth", tags=["auth"])


def set_session_cookie(response: Response, token: str, settings, remember_me: bool = False) -> None:
    response.set_cookie(
        "mogobe_session",
        token,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=(
            settings.remembered_session_days * 86400
            if remember_me
            else settings.session_hours * 3600
        ),
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/registration-drafts", status_code=201)
async def start_registration(
    body: schemas.RegistrationStart,
    request: Request,
    response: Response,
    db: Database,
    settings: Config,
):
    limit_attempts(request)
    token = await service.start_registration(
        db, body, settings, request.cookies.get("mogobe_registration")
    )
    response.set_cookie(
        "mogobe_registration",
        token,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=settings.registration_minutes * 60,
    )
    return {"next_step": 4}


@router.post("/register", status_code=201, response_model=schemas.AccountPublic)
async def register(
    body: schemas.RegistrationFinish,
    request: Request,
    response: Response,
    db: Database,
    settings: Config,
):
    account = await service.finish_registration(
        db, body, request.cookies.get("mogobe_registration")
    )
    token = await service.create_session(
        db, account.id, settings, previous_token=get_token(request)
    )
    set_session_cookie(response, token, settings)
    response.delete_cookie("mogobe_registration", httponly=True, samesite="strict")
    return account


@router.post("/login", response_model=schemas.AccountPublic)
async def login(
    body: schemas.Credentials,
    request: Request,
    response: Response,
    db: Database,
    settings: Config,
):
    limit_attempts(request)
    account = await service.authenticate(db, body)
    async with request.app.state.world.login_guard(account.id):
        token = await service.create_session(
            db, account.id, settings, body.remember_me, get_token(request)
        )
    set_session_cookie(response, token, settings, body.remember_me)
    return account


@router.get("/me", response_model=schemas.AccountPublic)
async def me(account: CurrentAccount):
    return account


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: Database):
    await service.logout(db, get_token(request))
    response.delete_cookie("mogobe_session", httponly=True, samesite="strict")
