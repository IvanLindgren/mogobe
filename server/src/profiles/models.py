"""Accepted pairs, directed requests and personal social preferences."""

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class Friendship(Base):
    __tablename__ = "social_friendship"
    __table_args__ = (CheckConstraint("first_id < second_id", name="ordered_accounts"),)
    first_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), primary_key=True
    )
    second_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class FriendRequest(Base):
    __tablename__ = "social_request"
    __table_args__ = (CheckConstraint("sender_id != recipient_id", name="different_accounts"),)
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), primary_key=True
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class SocialPreference(Base):
    __tablename__ = "social_preference"
    __table_args__ = (CheckConstraint("owner_id != buddy_id", name="different_accounts"),)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), primary_key=True
    )
    buddy_id: Mapped[int] = mapped_column(
        ForeignKey("auth_account.id", ondelete="CASCADE"), primary_key=True
    )
    muted: Mapped[bool] = mapped_column(default=False, server_default="0")
    best: Mapped[bool] = mapped_column(default=False, server_default="0")
