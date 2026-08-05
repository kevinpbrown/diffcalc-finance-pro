"""Balance sheet account domain models."""

from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Column, Date, Enum, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from personal_finance.domain.base import Base, Discardable
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.person import Person

# Association table for the many-to-many Account ↔ Person ownership relationship.
# Defined at module level so SQLAlchemy registers it on Base.metadata before any
# Account subclass is declared.
account_owners = Table(
    "account_owners",
    Base.metadata,
    Column("account_id", ForeignKey("accounts.id"), primary_key=True),
    Column("person_id", ForeignKey("persons.id"), primary_key=True),
)

if TYPE_CHECKING:
    from personal_finance.domain.balance_sheet.holding import InvestmentAccountHolding


class AccountClassification(enum.Enum):
    """Balance sheet classification for an account."""

    ASSET_CURRENT = "ASSET_CURRENT"
    ASSET_LONG_TERM = "ASSET_LONG_TERM"
    LIABILITY_CURRENT = "LIABILITY_CURRENT"
    LIABILITY_LONG_TERM = "LIABILITY_LONG_TERM"

    def is_current(self) -> bool:
        """Return True when this is a current (short-term) classification."""
        return self in (
            AccountClassification.ASSET_CURRENT,
            AccountClassification.LIABILITY_CURRENT,
        )

    def is_long_term(self) -> bool:
        """Return True when this is a long-term classification."""
        return self in (
            AccountClassification.ASSET_LONG_TERM,
            AccountClassification.LIABILITY_LONG_TERM,
        )

    def is_asset(self) -> bool:
        """Return True when this classification represents an asset."""
        return self in (
            AccountClassification.ASSET_CURRENT,
            AccountClassification.ASSET_LONG_TERM,
        )

    def is_liability(self) -> bool:
        """Return True when this classification represents a liability."""
        return self in (
            AccountClassification.LIABILITY_CURRENT,
            AccountClassification.LIABILITY_LONG_TERM,
        )


class SimpleAccountCategory(enum.Enum):
    """Subcategory for a SimpleAccount."""

    BANK = "BANK"
    RECEIVABLE_PAYABLE = "RECEIVABLE_PAYABLE"
    REAL_ESTATE = "REAL_ESTATE"
    VEHICLE = "VEHICLE"
    OTHER = "OTHER"


class InvestmentRegistration(enum.Enum):
    """Registered account type for an InvestmentAccount."""

    UNREGISTERED = "UNREGISTERED"
    RRSP = "RRSP"
    TFSA = "TFSA"
    RESP = "RESP"
    LIRA = "LIRA"
    DPSP = "DPSP"


class Account(Base, Discardable):
    """Mapped base for all balance sheet accounts.

    Uses joined-table inheritance. Concrete subclasses extend via their own table.
    This class is not abstract at the Python level — it has its own ``accounts``
    table — but no ``Account`` row should be created directly.
    """

    __tablename__ = "accounts"
    __mapper_args__ = {
        "polymorphic_on": "account_type",
        "polymorphic_identity": "account",
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    account_type: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    date_created: Mapped[date] = mapped_column(Date)
    classification: Mapped[AccountClassification] = mapped_column(
        Enum(AccountClassification, native_enum=False, length=30)
    )
    owners: Mapped[list[Person]] = relationship(secondary=account_owners)

    def get_balance(self, effective_date: date) -> Decimal | None:
        """Return the account balance as of the given date.

        Subclasses must override this. Returns None when the balance cannot be
        determined (e.g. an unpriced holding in an InvestmentAccount).
        """
        raise NotImplementedError


class SimpleAccount(Account):
    """A standard account with a balance timeline (bank, real estate, credit card, etc.)."""

    __tablename__ = "simple_accounts"
    __mapper_args__ = {"polymorphic_identity": "simple"}

    id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    type: Mapped[SimpleAccountCategory] = mapped_column(
        Enum(SimpleAccountCategory, native_enum=False, length=30)
    )
    balance_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    balance: Mapped[EffectiveAmount] = relationship()

    def __init__(self, **kwargs: object) -> None:
        """Ensure a fresh EffectiveAmount balance timeline is created when none is supplied."""
        if "balance" not in kwargs:
            kwargs["balance"] = EffectiveAmount()
        super().__init__(**kwargs)

    def get_balance(self, effective_date: date) -> Decimal | None:
        """Return the most recent balance entry on or before effective_date."""
        return self.balance.latest_value_as_of(effective_date)


class InvestmentAccount(Account):
    """An investment account holding holdings and a cash buffer."""

    __tablename__ = "investment_accounts"
    __mapper_args__ = {"polymorphic_identity": "investment"}

    id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    investment_registration: Mapped[InvestmentRegistration] = mapped_column(
        Enum(InvestmentRegistration, native_enum=False, length=20)
    )
    cash_balance_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id"), nullable=True)
    cash_balance: Mapped[EffectiveAmount] = relationship()
    holdings: Mapped[list[InvestmentAccountHolding]] = relationship(
        "InvestmentAccountHolding",
        back_populates="investment_account",
    )

    def __init__(self, **kwargs: object) -> None:
        """Ensure a fresh EffectiveAmount cash-balance timeline is created when none is supplied."""
        if "cash_balance" not in kwargs:
            kwargs["cash_balance"] = EffectiveAmount()
        super().__init__(**kwargs)

    def get_balance(self, effective_date: date) -> Decimal | None:
        """Return cash balance plus the sum of all active holding values.

        Returns None when the cash balance has no entry on or before effective_date,
        or when any active holding cannot be priced (e.g. a ListedSecurityHolding
        before price-provider integration).
        """
        cash = self.cash_balance.latest_value_as_of(effective_date)
        if cash is None:
            return None
        total = cash
        for holding in self.holdings:
            if not holding.is_active(effective_date):
                continue
            value = holding.get_value(effective_date)
            if value is None:
                return None
            total += value
        return total
