"""Household expense domain model."""

from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from personal_finance.domain.base import Base, Discardable
from personal_finance.domain.effective_amount import EffectiveAmount


class HouseholdExpenseClassification(enum.Enum):
    """Broad category for a household expense."""

    HOME = "HOME"
    AUTO = "AUTO"
    OTHER = "OTHER"


class HouseholdExpenseSource(enum.Enum):
    """Payment method for a household expense."""

    BANK = "BANK"
    CREDIT = "CREDIT"
    OTHER = "OTHER"


class HouseholdExpenseFrequency(enum.Enum):
    """Recurrence pattern for a household expense."""

    REGULAR = "REGULAR"
    IRREGULAR = "IRREGULAR"


class HouseholdExpense(Base, Discardable):
    """A recurring or one-off household cost tracked for planning purposes."""

    __tablename__ = "household_expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    date_created: Mapped[date] = mapped_column(Date)
    amount_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    classification: Mapped[HouseholdExpenseClassification] = mapped_column(
        Enum(HouseholdExpenseClassification, native_enum=False, length=20)
    )
    source: Mapped[HouseholdExpenseSource] = mapped_column(
        Enum(HouseholdExpenseSource, native_enum=False, length=20)
    )
    frequency: Mapped[HouseholdExpenseFrequency] = mapped_column(
        Enum(HouseholdExpenseFrequency, native_enum=False, length=20)
    )

    amount: Mapped[EffectiveAmount] = relationship()

    def __init__(self, **kwargs: object) -> None:
        """Ensure a fresh EffectiveAmount amount timeline is created when none is supplied."""
        if "amount" not in kwargs:
            kwargs["amount"] = EffectiveAmount()
        super().__init__(**kwargs)
