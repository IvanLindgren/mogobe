from pydantic import BaseModel, StrictBool

from src.auth.schemas import Username


class MuteUpdate(BaseModel):
    username: Username
    muted: StrictBool
