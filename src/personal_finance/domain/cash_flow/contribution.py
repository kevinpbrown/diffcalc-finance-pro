"""Automated contribution domain model."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from personal_finance.domain.base import Base, Discardable
from personal_finance.domain.effective_amount import EffectiveAmount

if TYPE_CHECKING:
    from personal_finance.domain.balance_sheet.account import Account
    from personal_finance.domain.goals.goal import Goal


class AutomatedContribution(Base, Discardable):
    """A regular automated transfer between two accounts, optionally linked to a goal."""

    __tablename__ = "automated_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    date_created: Mapped[date] = mapped_column(Date)
    amount_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    source_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    destination_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    target_goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"))

    amount: Mapped[EffectiveAmount] = relationship()
    source_account: Mapped[Account] = relationship(foreign_keys=[source_account_id])
    destination_account: Mapped[Account] = relationship(foreign_keys=[destination_account_id])
    target_goal: Mapped[Goal] = relationship(foreign_keys=[target_goal_id])

    def __init__(self, **kwargs: object) -> None:
        """Ensure a fresh EffectiveAmount amount timeline is created when none is supplied."""
        if "amount" not in kwargs:
            kwargs["amount"] = EffectiveAmount()
        super().__init__(**kwargs)
