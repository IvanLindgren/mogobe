from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class Shop(Base):
    __tablename__ = "shop"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(12), default="clothing")
    enabled: Mapped[bool] = mapped_column(default=True)
    admin_only: Mapped[bool] = mapped_column(default=False)
    room_key: Mapped[str | None] = mapped_column(String(40), unique=True)


class Item(Base):
    __tablename__ = "shop_item"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(80))
    main_type: Mapped[int] = mapped_column(default=1)
    inventory_category: Mapped[int] = mapped_column(default=1)
    enabled: Mapped[bool] = mapped_column(default=True)


class Category(Base):
    __tablename__ = "shop_category"
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shop.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    icon_id: Mapped[int] = mapped_column(default=1)
    sort: Mapped[int] = mapped_column(default=0)


class Offer(Base):
    __tablename__ = "shop_offer"
    __table_args__ = (
        UniqueConstraint("shop_id", "item_id"),
        CheckConstraint("price >= 0", name="positive_price"),
        CheckConstraint("stock IS NULL OR stock >= 0", name="positive_stock"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shop.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("shop_item.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("shop_category.id", ondelete="CASCADE"))
    experience: Mapped[int] = mapped_column(default=10, server_default="10")
    price: Mapped[int] = mapped_column(default=0)
    stock: Mapped[int | None]
    enabled: Mapped[bool] = mapped_column(default=True)
    sort: Mapped[int] = mapped_column(default=0)


class Wallet(Base):
    __tablename__ = "shop_wallet"
    __table_args__ = (CheckConstraint("coins >= 0", name="positive_coins"),)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), primary_key=True
    )
    coins: Mapped[int] = mapped_column(default=0)


class OwnedItem(Base):
    __tablename__ = "shop_owned_item"
    __table_args__ = (UniqueConstraint("account_id", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("shop_item.id"))
