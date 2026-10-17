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


class ItemInput(Input):
    id: int = Field(strict=True, ge=1, le=1000000)
    name: str = Field(min_length=1, max_length=80)
    main_type: Literal[1, 2] = 1
    inventory_category: int = Field(strict=True, ge=1, le=10000, default=1)
    enabled: bool = True


class CategoryInput(Input):
    name: str = Field(min_length=1, max_length=60)
    icon_id: int = Field(strict=True, ge=1)
    sort: int = Field(strict=True, ge=0, le=100000, default=0)


class AdminRoleInput(Input):
    is_admin: bool = Field(strict=True)


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


class BalanceInput(Input):
    coins: int = Field(strict=True, ge=0, le=1000000000)
