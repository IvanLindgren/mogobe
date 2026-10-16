from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from src.auth import schemas, service
from src.auth.dependencies import Config, CurrentAccount, Database, get_token, limit_attempts
from src.auth.router import set_session_cookie
from src.world.presence import server_snapshot

router = APIRouter(prefix="/legacy", tags=["original-swf"])


def xml(element: Element) -> Response:
    return Response(tostring(element, encoding="utf-8"), media_type="application/xml")


@router.post("/login")
async def login(body: schemas.Credentials, request: Request, db: Database, settings: Config):
    root = Element("Response")
    try:
        limit_attempts(request)
        account = await service.authenticate(db, body)
        async with request.app.state.world.login_guard(account.id):
            token = await service.create_session(
                db, account.id, settings, body.remember_me, get_token(request)
            )
    except HTTPException as exc:
        SubElement(
            root,
            "Login",
            status="7" if exc.status_code == 409 else "2" if exc.status_code == 401 else "4",
            message=str(exc.detail) if exc.status_code == 409 else "",
        )
        return xml(root)
    result = SubElement(
        root,
        "Login",
        status="1",
        allow="true",
        isMember="false",
        username=account.username,
        colorId=str(account.color_id),
    )
    screens = SubElement(result, "FirstLoadingScreens")
    SubElement(screens, "Screen", i="0", t="2")
    response = xml(root)
    set_session_cookie(response, token, settings, body.remember_me)
    return response


@router.post("/resume")
async def resume(body: schemas.ResumeSession, request: Request, db: Database):
    root = Element("Response")
    try:
        account = await service.find_account(db, get_token(request))
        if account.username_key != body.username.casefold():
            raise HTTPException(401, "Сессия принадлежит другому могоби")
        request.app.state.world.require_available(account.id)
    except HTTPException as exc:
        SubElement(
            root,
            "Login",
            status="7" if exc.status_code == 409 else "2",
            message=str(exc.detail) if exc.status_code == 409 else "",
        )
        return xml(root)
    result = SubElement(
        root,
        "Login",
        status="1",
        allow="true",
        isMember="false",
        username=account.username,
        colorId=str(account.color_id),
    )
    screens = SubElement(result, "FirstLoadingScreens")
    SubElement(screens, "Screen", i="0", t="2")
    return xml(root)


@router.get("/servers")
async def servers(account: CurrentAccount, request: Request, db: Database):
    snapshot = await server_snapshot(db, account.id, request.app.state.world)
    root = Element("Response")
    collection = SubElement(root, "Servers")
    SubElement(
        collection,
        "S",
        id="1",
        ip="127.0.0.1",
        port="9339",
        webPort="0",
        name=snapshot["name"],
        percentage=str(snapshot["percentage"]),
        currentUsers=str(snapshot["online"]),
        status="1",
        chatMode="true",
        friends=str(snapshot["friends"]),
    )
    return xml(root)
