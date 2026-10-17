from fastapi import APIRouter, Request

from src.auth.dependencies import CurrentAccount, Database
from src.profiles import progression
from src.profiles.service import public_profile
from src.shops import schemas, service

router = APIRouter()


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
