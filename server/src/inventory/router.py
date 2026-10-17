from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from src.auth.dependencies import CurrentAccount, Database
from src.inventory import service

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class ChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owned_item_id: int = Field(strict=True, gt=0)


@router.get("/equipped")
async def outfit(account: CurrentAccount, db: Database):
    return {"items": await service.equipped(db, account.id)}


@router.post("/{action}")
async def change(
    action: str, body: ChangeInput, account: CurrentAccount, db: Database, request: Request
):
    from fastapi import HTTPException

    if action not in ("equip", "unequip"):
        raise HTTPException(404)
    async with request.app.state.commerce_lock:
        items = await service.change(db, account.id, [body.owned_item_id], wear=action == "equip")
        await service.notify(request.app, account.id, items)
    return {"items": items}
