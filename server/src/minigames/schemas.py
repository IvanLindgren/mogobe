from pydantic import BaseModel, ConfigDict, Field


class FinishInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(strict=True, ge=0, le=1000000)
    completed: bool = Field(strict=True)
    cancelled: bool = Field(default=False, strict=True)
