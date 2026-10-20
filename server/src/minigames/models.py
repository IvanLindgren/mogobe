from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class GameRun(Base):
    __tablename__ = "minigame_run"
    __table_args__ = (CheckConstraint("score >= 0 AND coins >= 0", name="positive_result"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), index=True
    )
    game_key: Mapped[str] = mapped_column(String(40))
    room_id: Mapped[int]
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(12), default="active")
    score: Mapped[int] = mapped_column(default=0)
    coins: Mapped[int] = mapped_column(default=0)
    experience: Mapped[int] = mapped_column(default=0, server_default="0")
