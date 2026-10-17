"""Shop and item management inside the shared server administration API."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.admin.dependencies import AdminAccount
from src.auth.dependencies import Database
from src.inventory import reclassification
from src.shops import schemas, service, world_shops
from src.shops.classification import classification
from src.shops.models import Category, Item, Offer, Shop
from src.world import catalog as rooms

router = APIRouter(tags=["shop administration"])


@router.get("/api/admin/assets")
@router.get("/api/admin/shops/assets", include_in_schema=False)
async def assets(account: AdminAccount):
    data = classification()
    return [
        {
            "id": ident,
            "display": "display" in row,
            "standing": "standing" in row,
            "walking": "walking" in row,
            "family": data["items"][str(ident)]["family"],
            "category": data["groups"][data["items"][str(ident)]["category"]]["name"],
            "evidence": data["items"][str(ident)]["evidence"],
        }
        for ident, row in service.asset_index().items()
    ]


@router.get("/api/admin/items/category-icons")
@router.get("/api/admin/shops/category-icons", include_in_schema=False)
async def category_icons(account: AdminAccount):
    return [{"id": r["id"], "name": r["name"]} for r in service.category_icons().values()]


@router.get("/api/admin/items")
@router.get("/api/admin/shops/items", include_in_schema=False)
async def items(account: AdminAccount, db: Database):
    return [service.record(item) for item in await db.scalars(select(Item).order_by(Item.id))]


@router.put("/api/admin/items/{ident}")
@router.put("/api/admin/shops/items/{ident}", include_in_schema=False)
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
        owners = await reclassification.reconcile(db, item)
        await db.commit()
        await reclassification.refresh(request.app, owners)
        await service.changed(request.app)
        return service.record(item)


@router.get("/api/admin/shops")
async def shops(account: AdminAccount, db: Database):
    assigned = await world_shops.bindings(db)
    return [
        {**service.record(shop), "points": [p for p, ident in assigned.items() if ident == shop.id]}
        for shop in await db.scalars(select(Shop).order_by(Shop.key))
    ]


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
        values = body.model_dump(exclude={"points"})
        if shop is None:
            shop = Shop(**values)
            db.add(shop)
        else:
            for name, value in values.items():
                setattr(shop, name, value)
        try:
            await db.flush()
            await world_shops.assign(db, shop, body.points)
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
        "shop": {
            **service.record(shop),
            "points": [
                p for p, ident in (await world_shops.bindings(db)).items() if ident == shop.id
            ],
        },
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
        owners = set()
        if category.inventory_category is not None:
            for item in await db.scalars(
                select(Item)
                .join(Offer)
                .where(Offer.category_id == category.id, Item.main_type == 1)
            ):
                item.inventory_category = category.inventory_category
                owners.update(await reclassification.reconcile(db, item))
        await db.commit()
        await reclassification.refresh(request.app, owners)
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
        owners = set()
        item = await db.get(Item, item_id)
        if category.inventory_category is not None and item.main_type == 1:
            item.inventory_category = category.inventory_category
            owners = await reclassification.reconcile(db, item)
        await db.commit()
        await reclassification.refresh(request.app, owners)
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


@router.post("/api/admin/shops/{key}/import-assets")
async def import_assets(key: str, account: AdminAccount, db: Database, request: Request):
    # Validate the key exactly as when creating a normal shop.
    from pydantic import ValidationError

    from src.auth.models import Account
    from src.shops.import_catalog import populate

    try:
        schemas.ShopInput(key=key, title="Каталог")
        if len(key) > 39:
            raise HTTPException(422, "Основа ключа каталога должна быть не длиннее 39 символов")
    except ValidationError:
        raise HTTPException(422, "Некорректный ключ магазина") from None
    async with request.app.state.commerce_lock:
        actor = await db.get(Account, account.id, populate_existing=True)
        if not actor.is_admin:
            raise HTTPException(403, "Нужны права администратора")
        result = await populate(db, key)
        await service.changed(request.app)
        return result


@router.get("/api/admin/shop-points")
async def shop_points(account: AdminAccount):
    return list(world_shops.points().values())


@router.post("/api/admin/shop-defaults")
async def seed_world_shops(account: AdminAccount, db: Database, request: Request):
    async with request.app.state.commerce_lock:
        result = await world_shops.populate(db)
        await service.changed(request.app)
        return result
