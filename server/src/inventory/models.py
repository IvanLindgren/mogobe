from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class EquippedItem(Base):
    __tablename__ = "inventory_equipped"
    __table_args__ = (UniqueConstraint("owned_item_id"),)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(primary_key=True)
    owned_item_id: Mapped[int] = mapped_column(ForeignKey("shop_owned_item.id", ondelete="CASCADE"))
