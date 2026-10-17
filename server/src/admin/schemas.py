from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdminRoleInput(Input):
    is_admin: bool = Field(strict=True)


class BalanceInput(Input):
    coins: int = Field(strict=True, ge=0, le=1000000000)
