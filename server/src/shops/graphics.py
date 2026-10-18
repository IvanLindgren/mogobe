"""Export compatibility classes around unchanged original item graphics."""

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from src.auth.dependencies import Database
from src.config import ROOT
from src.shops.models import Category
from src.shops.service import category_icons
from src.shops.swf_graphics import metadata as metadata
from src.shops.swf_graphics import wrapped as build_graphic

router = APIRouter(prefix="/api/shop-assets", tags=["shop graphics"])
ASSETS = ROOT.parent / "assets/original/Swf/Items"


@lru_cache(maxsize=5000)
def wrapped(role, ident, category_id=0):
    try:
        return build_graphic(role, ident, category_id)
    except KeyError:
        raise HTTPException(404, "Графика предмета не найдена") from None


@router.get("/category-icons/{ident}.png")
async def category_icon(ident: int):
    if ident not in category_icons():
        raise HTTPException(404)
    return FileResponse(
        ROOT.parent / f"assets/compat/shop-categories/{ident}.png", media_type="image/png"
    )


@router.get("/raw/{ident}.swf")
async def raw_graphic(ident: int):
    role = "Display" if (ASSETS / "Display" / f"{ident}.swf").is_file() else "Walking"
    path = ASSETS / role / f"{ident}.swf"
    if not path.is_file():
        raise HTTPException(404, "Нет изображения или анимации")
    return FileResponse(
        path,
        media_type="application/x-shockwave-flash",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/preview/{ident}.swf")
async def preview_graphic(ident: int):
    return Response(
        wrapped("Preview", ident),
        media_type="application/x-shockwave-flash",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/{role}/{ident}.swf")
async def graphic(role: str, ident: int, db: Database):
    if role not in ("Display", "InUse", "Cats"):
        raise HTTPException(404)
    if role == "Cats":
        category = await db.get(Category, ident // 100)
        if not category or ident % 100 != category.icon_id:
            raise HTTPException(404)
        data = wrapped(role, category.icon_id, ident)
    elif role == "InUse":
        path = ROOT.parent / f"assets/compat/item-animations/{ident}.swf"
        if not path.is_file():
            raise HTTPException(404, "Нет полной анимации предмета")
        return FileResponse(
            path,
            media_type="application/x-shockwave-flash",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    else:
        data = wrapped(role, ident)
    return Response(
        data,
        media_type="application/x-shockwave-flash",
        headers={"Cache-Control": "public, max-age=3600"},
    )
