from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ShopInput(Input):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    title: str = Field(min_length=1, max_length=80)
    kind: Literal["clothing", "objects"] = "clothing"
    enabled: bool = True
    admin_only: bool = False
    room_key: str | None = Field(default=None, max_length=40)
    points: list[str] | None = Field(default=None, max_length=200)


class ItemInput(Input):
    id: int = Field(strict=True, ge=1, le=1000000)
    name: str = Field(min_length=1, max_length=80)
    main_type: int = Field(strict=True, ge=0, le=14, default=1)
    inventory_category: int = Field(strict=True, ge=0, le=10000, default=1)
    enabled: bool = True


class CategoryInput(Input):
    inventory_category: int | None = Field(default=None, strict=True, ge=0, le=23)
    name: str = Field(min_length=1, max_length=60)
    icon_id: int = Field(strict=True, ge=1)
    sort: int = Field(strict=True, ge=0, le=100000, default=0)


class OfferInput(Input):
    item_id: int = Field(strict=True, ge=1)
    category_id: int = Field(strict=True, ge=1)
    experience: int = Field(strict=True, ge=0, le=1000000, default=10)
    price: int = Field(strict=True, ge=0, le=1000000000, default=0)
    stock: int | None = Field(strict=True, ge=0, le=1000000, default=None)
    enabled: bool = True
    sort: int = Field(strict=True, ge=0, le=100000, default=0)


class PurchaseInput(Input):
    item_id: int = Field(strict=True, ge=1)
    expected_price: int = Field(strict=True, ge=0)
