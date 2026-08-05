"""Account asset class domain model."""

from __future__ import annotations

from datetime import date
from enum import IntEnum

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from personal_finance.domain.base import Base


class BuiltInAssetClassId(IntEnum):
    """Reserved primary keys for built-in asset classes seeded from code, not TOML.

    These IDs are stable constants. The seed script inserts the corresponding
    AccountAssetClass row with the explicit primary key defined here. Built-in
    classes can never be disabled via configuration.
    """

    CASH = 1


class AccountAssetClass(Base):
    """A categorization used for investment asset allocation (e.g., Equity, Fixed Income).

    Instances are seeded from TOML configuration at startup. An asset class is
    active as of a given date when its ``date_created`` is on or before that date
    and its ``date_disabled`` is null or strictly after that date.
    """

    __tablename__ = "account_asset_classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    order_precedence: Mapped[int] = mapped_column()
    date_created: Mapped[date] = mapped_column(Date)
    date_disabled: Mapped[date | None] = mapped_column(Date, nullable=True)

    def is_active(self, as_of: date) -> bool:
        """Return True if this asset class is active as of the given date."""
        return self.date_created <= as_of and (
            self.date_disabled is None or self.date_disabled > as_of
        )
