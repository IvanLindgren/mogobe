from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi import Response as CookieResponse
from fastapi.responses import FileResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.auth import schemas as auth_schemas
from src.auth import service as auth_service
from src.auth.dependencies import Config, CurrentAccount, Database, get_token, limit_attempts
from src.auth.models import Account
from src.auth.router import set_session_cookie
from src.profiles import progression
from src.profiles.service import public_profile
from src.shops import schemas, service
from src.shops.accounts import router as accounts_router
from src.shops.dependencies import AdminAccount
from src.shops.models import Category, Item, Offer, Shop, Wallet
from src.world import catalog as rooms

router = APIRouter()
router.include_router(accounts_router)
WEB = Path(__file__).with_name("web")


@router.get("/admin/shops", include_in_schema=False)
async def admin_page():
    return FileResponse(WEB / "index.html")


@router.get("/admin/shops/app.js", include_in_schema=False)
async def admin_script():
    return FileResponse(WEB / "app.js", media_type="text/javascript")


@router.get("/admin/shops/style.css", include_in_schema=False)
async def admin_style():
    return FileResponse(WEB / "style.css", media_type="text/css")


@router.get("/api/shops/{key}")
async def shop_view(key: str, account: CurrentAccount, db: Database):
    shop = await service.get_shop(db, key, account)
    return {**await service.catalog(db, shop, account), "user": await public_profile(db, account)}


@router.post("/api/shops/{key}/buy")
async def buy(
    key: str, body: schemas.PurchaseInput, account: CurrentAccount, db: Database, request: Request
):
    async with request.app.state.commerce_lock:
        result = await service.purchase(db, account, key, body.item_id, body.expected_price)
        await service.changed(request.app)
        await progression.notify(request.app, account.id, result["experience_awarded"])
        return result


@router.get("/api/inventory")
async def inventory(account: CurrentAccount, db: Database):
    return {
        "items": await service.inventory(db, account.id),
        "coins": await service.balance(db, account.id),
    }


@router.post("/api/admin/shops/login")
async def admin_login(
    body: auth_schemas.Credentials,
    db: Database,
    request: Request,
    response: CookieResponse,
    settings: Config,
):
    limit_attempts(request)
    account = await auth_service.authenticate(db, body)
    if not account.is_admin:
        raise HTTPException(403, "Нужны права администратора")
    token = await auth_service.create_session(
        db, account.id, settings, previous_token=get_token(request)
    )
    set_session_cookie(response, token, settings)
    return {"username": account.username}


@router.get("/api/admin/shops/me")
async def admin_me(account: AdminAccount):
    return {"username": account.username}


@router.get("/api/admin/shops/assets")
async def assets(account: AdminAccount):
    return [
        {"id": ident, "standing": "standing" in row, "walking": "walking" in row}
        for ident, row in service.asset_index().items()
    ]


@router.get("/api/admin/shops/category-icons")
async def category_icons(account: AdminAccount):
    return [{"id": r["id"], "name": r["name"]} for r in service.category_icons().values()]


@router.get("/api/admin/shops/items")
async def items(account: AdminAccount, db: Database):
    return [service.record(item) for item in await db.scalars(select(Item).order_by(Item.id))]


@router.put("/api/admin/shops/items/{ident}")
async def save_item(
    ident: int, body: schemas.ItemInput, account: AdminAccount, db: Database, request: Request
):
    if ident != body.id:
        raise HTTPException(422, "ID нельзя изменить")
    service.check_asset(body.id, body.main_type == 1)
    async with request.app.state.commerce_lock:
        item = await db.get(Item, ident)
        if item is None:
            item = Item(**body.model_dump())
            db.add(item)
        else:
            for key, value in body.model_dump().items():
                setattr(item, key, value)
        await db.commit()
        await service.changed(request.app)
        return service.record(item)


@router.get("/api/admin/shops")
async def shops(account: AdminAccount, db: Database):
    return [service.record(shop) for shop in await db.scalars(select(Shop).order_by(Shop.key))]


@router.put("/api/admin/shops/{key}")
async def save_shop(
    key: str, body: schemas.ShopInput, account: AdminAccount, db: Database, request: Request
):
    if key != body.key:
        raise HTTPException(422, "Ключ нельзя изменить")
    if body.room_key and body.room_key not in rooms.BY_KEY:
        raise HTTPException(422, "Неизвестная комната")
    async with request.app.state.commerce_lock:
        shop = await db.scalar(select(Shop).where(Shop.key == key))
        if shop is None:
            shop = Shop(**body.model_dump())
            db.add(shop)
        else:
            for name, value in body.model_dump().items():
                setattr(shop, name, value)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(409, "Эта комната уже связана с другим магазином") from None
        await service.changed(request.app)
        return service.record(shop)


@router.get("/api/admin/shops/{key}/catalog")
async def admin_catalog(key: str, account: AdminAccount, db: Database):
    shop = await service.get_shop(db, key)
    return {
        "shop": service.record(shop),
        "categories": [
            service.record(c)
            for c in await db.scalars(
                select(Category)
                .where(Category.shop_id == shop.id)
                .order_by(Category.sort, Category.id)
            )
        ],
        "offers": [
            service.record(o)
            for o in await db.scalars(
                select(Offer).where(Offer.shop_id == shop.id).order_by(Offer.sort, Offer.id)
            )
        ],
    }


@router.post("/api/admin/shops/{key}/categories", status_code=201)
async def new_category(
    key: str, body: schemas.CategoryInput, account: AdminAccount, db: Database, request: Request
):
    service.check_category_icon(body.icon_id)
    async with request.app.state.commerce_lock:
        shop = await service.get_shop(db, key)
        category = Category(shop_id=shop.id, **body.model_dump())
        db.add(category)
        await db.commit()
        await service.changed(request.app)
        return service.record(category)


@router.put("/api/admin/shops/{key}/categories/{ident}")
async def save_category(
    key: str,
    ident: int,
    body: schemas.CategoryInput,
    account: AdminAccount,
    db: Database,
    request: Request,
):
    service.check_category_icon(body.icon_id)
    async with request.app.state.commerce_lock:
        shop = await service.get_shop(db, key)
        category = await db.get(Category, ident)
        if category is None or category.shop_id != shop.id:
            raise HTTPException(404, "Категория не найдена")
        for name, value in body.model_dump().items():
            setattr(category, name, value)
        await db.commit()
        await service.changed(request.app)
        return service.record(category)


@router.put("/api/admin/shops/{key}/offers/{item_id}")
async def save_offer(
    key: str,
    item_id: int,
    body: schemas.OfferInput,
    account: AdminAccount,
    db: Database,
    request: Request,
):
    if item_id != body.item_id:
        raise HTTPException(422, "ID нельзя изменить")
    async with request.app.state.commerce_lock:
        shop = await service.get_shop(db, key)
        category = await db.get(Category, body.category_id)
        if not category or category.shop_id != shop.id or not await db.get(Item, item_id):
            raise HTTPException(422, "Выберите предмет и категорию этого магазина")
        offer = await db.scalar(
            select(Offer).where(Offer.shop_id == shop.id, Offer.item_id == item_id)
        )
        if not offer:
            offer = Offer(shop_id=shop.id, **body.model_dump())
            db.add(offer)
        else:
            for name, value in body.model_dump().items():
                setattr(offer, name, value)
        await db.commit()
        await service.changed(request.app)
        return service.record(offer)


@router.delete("/api/admin/shops/{key}/offers/{item_id}", status_code=204)
async def remove_offer(
    key: str, item_id: int, account: AdminAccount, db: Database, request: Request
):
    async with request.app.state.commerce_lock:
        shop = await service.get_shop(db, key)
        await db.execute(delete(Offer).where(Offer.shop_id == shop.id, Offer.item_id == item_id))
        await db.commit()
        await service.changed(request.app)
    return Response(status_code=204)


@router.post("/api/admin/shops/accounts/{username}/balance")
async def set_balance(
    username: str, body: schemas.BalanceInput, account: AdminAccount, db: Database, request: Request
):
    async with request.app.state.commerce_lock:
        target = await db.scalar(select(Account).where(Account.username_key == username.casefold()))
        if not target:
            raise HTTPException(404, "Могоби не найден")
        wallet = await db.get(Wallet, target.id)
        if not wallet:
            wallet = Wallet(account_id=target.id, coins=body.coins)
            db.add(wallet)
        else:
            wallet.coins = body.coins
        await db.commit()
        await service.changed(request.app)
        return {"username": target.username, "coins": wallet.coins}
