"""Investment account holding domain models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, reconstructor, relationship

from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet.account import InvestmentAccount
from personal_finance.domain.base import Base, Discardable
from personal_finance.domain.effective_amount import EffectiveAmount


class InvestmentAccountHolding(Base, Discardable):
    """Mapped base for a holding within an InvestmentAccount.

    Uses joined-table inheritance. Concrete subclasses extend via their own table.
    This class is not abstract at the Python level — it has its own table — but no
    bare ``InvestmentAccountHolding`` row should be created directly.
    """

    __tablename__ = "investment_account_holdings"
    __mapper_args__ = {
        "polymorphic_on": "holding_type",
        "polymorphic_identity": "holding",
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_type: Mapped[str] = mapped_column(String(50))
    investment_account_id: Mapped[int] = mapped_column(ForeignKey("investment_accounts.id"))
    name: Mapped[str] = mapped_column(String(255))
    date_created: Mapped[date] = mapped_column(Date)

    investment_account: Mapped[InvestmentAccount] = relationship(back_populates="holdings")
    allocations: Mapped[list[HoldingAssetClassAllocation]] = relationship(
        back_populates="holding",
        cascade="all, delete-orphan",
    )

    def get_value(self, effective_date: date) -> Decimal | None:
        """Return the holding's market value as of effective_date.

        Subclasses must override this. Returns None when the value cannot be
        determined (e.g. a ListedSecurityHolding before price-provider integration).
        """
        raise NotImplementedError

    def validate_allocations(self, as_of: date) -> None:
        """Raise ValueError if active allocations do not sum to exactly 100%.

        Args:
            as_of: The effective date for determining which allocations are active.
        """
        total = sum(
            (a.percent_allocated for a in self.allocations if a.is_active(as_of)),
            Decimal("0"),
        )
        if total != Decimal("100"):
            raise ValueError(
                f"Active allocations must sum to 100%; got {total} for holding {self.id!r}"
            )


class ExactHolding(InvestmentAccountHolding):
    """A holding managed by providing its exact scalar value over time (e.g. GIC)."""

    __tablename__ = "exact_holdings"
    __mapper_args__ = {"polymorphic_identity": "exact"}

    id: Mapped[int] = mapped_column(ForeignKey("investment_account_holdings.id"), primary_key=True)
    amount_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    amount: Mapped[EffectiveAmount] = relationship()

    def __init__(self, **kwargs: object) -> None:
        """Ensure a fresh EffectiveAmount amount timeline is created when none is supplied."""
        if "amount" not in kwargs:
            kwargs["amount"] = EffectiveAmount()
        super().__init__(**kwargs)

    def get_value(self, effective_date: date) -> Decimal | None:
        """Return the most recent amount entry on or before effective_date."""
        return self.amount.latest_value_as_of(effective_date)


class ListedSecurityHolding(InvestmentAccountHolding):
    """A holding managed by shares and market value.

    Market value is not stored in the database. The service layer must call
    ``set_unit_price`` after fetching the price from a ``QuoteService``
    before any call to ``get_value`` will return a non-``None`` result.
    """

    __tablename__ = "listed_security_holdings"
    __mapper_args__ = {"polymorphic_identity": "listed_security"}

    id: Mapped[int] = mapped_column(ForeignKey("investment_account_holdings.id"), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    quantity_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    quantity: Mapped[EffectiveAmount] = relationship()

    def __init__(self, **kwargs: object) -> None:
        """Initialise the holding and set transient pricing fields to None."""
        if "quantity" not in kwargs:
            kwargs["quantity"] = EffectiveAmount()
        elif not isinstance(kwargs["quantity"], EffectiveAmount):
            raise TypeError(
                f"quantity must be an EffectiveAmount timeline, got "
                f"{type(kwargs['quantity']).__name__}"
            )
        super().__init__(**kwargs)
        # Annotated here (not at class level) to keep SQLAlchemy's declarative
        # scanner from misinterpreting them as mapped columns.
        self._unit_price: Decimal | None = None
        self._priced_as_of: date | None = None

    @reconstructor
    def _init_on_load(self) -> None:
        """Initialise transient fields when this instance is reconstructed from the DB."""
        self._unit_price = None
        self._priced_as_of = None

    def validate_quantity(self, as_of: date) -> None:
        """Raise ValueError if no positive quantity entry exists on or before as_of.

        A ``ListedSecurityHolding`` must have a non-zero quantity entry covering
        its entire active timeframe. This invariant is enforced at the service layer
        during creation (BS-OP-8) and before every pricing call.

        Args:
            as_of: The effective date to check. Should be within the holding's
                active period (``dateCreated ≤ as_of < dateDiscarded``).

        Raises:
            ValueError: If no quantity entry exists as of ``as_of``, or if the
                most recent entry on or before ``as_of`` is zero or negative.
        """
        value = self.quantity.latest_value_as_of(as_of)
        if value is None:
            raise ValueError(
                f"Holding {self.id!r} (symbol={self.symbol!r}) has no quantity "
                f"entry on or before {as_of}. A non-zero entry must exist as of "
                f"dateCreated ({self.date_created}) at the latest."
            )
        if value <= 0:
            raise ValueError(
                f"Holding {self.id!r} (symbol={self.symbol!r}) has a "
                f"non-positive quantity {value} as of {as_of}."
            )

    @property
    def unit_price(self) -> Decimal | None:
        """Return the currently-injected unit price per share, or None if not yet priced."""
        return self._unit_price

    def is_priced(self, as_of: date) -> bool:
        """Return True if a unit price has already been injected for ``as_of``."""
        return self._unit_price is not None and self._priced_as_of == as_of

    def set_unit_price(self, as_of: date, price_per_share: Decimal) -> None:
        """Inject the market price per share fetched by the service layer.

        Called by the service layer after a successful price lookup. Subsequent
        calls to ``get_value(as_of)`` will multiply this price by
        ``quantity.latest_value_as_of(as_of)`` on the fly.

        The ``as_of`` date is stored so that ``get_value`` can enforce that the
        caller queries at the same date the price was fetched for. Mixing a price
        from one date with a quantity lookup at a different date would silently
        produce an incorrect total; the guard in ``get_value`` converts that into
        a loud programming error instead.

        Args:
            as_of: The effective date the price was fetched for.
            price_per_share: The market price per share in CAD as of ``as_of``.
        """
        self._priced_as_of = as_of
        self._unit_price = price_per_share

    def get_value(self, effective_date: date) -> Decimal | None:
        """Return the market value computed from the injected unit price and quantity.

        Args:
            effective_date: Must match the date passed to ``set_unit_price``. The
                quantity timeline is looked up at this date; the stored unit price
                is then multiplied by that quantity.

        Returns:
            ``unit_price × quantity.latest_value_as_of(effective_date)``, or ``None``
            if the unit price has not been injected or no quantity entry exists as of
            ``effective_date``.

        Raises:
            ValueError: If ``effective_date`` does not match ``_priced_as_of``. This
                guards against callers accidentally mixing a price fetched for one
                date with a quantity lookup at another date, which would silently
                return a wrong value.
        """
        if self._unit_price is None:
            return None
        if effective_date != self._priced_as_of:
            raise ValueError(
                f"Holding {self.id!r} was priced as of {self._priced_as_of}, "
                f"but get_value was called with {effective_date}."
            )
        qty = self.quantity.latest_value_as_of(effective_date)
        if qty is None:
            return None
        return self._unit_price * qty


class HoldingAssetClassAllocation(Base, Discardable):
    """Assigns a percentage of a holding's value to an asset class.

    Invariant: the sum of active allocations for any holding must equal 100%.
    Enforced at the domain level via
    ``InvestmentAccountHolding.validate_allocations()``, not by a DB constraint.
    """

    __tablename__ = "holding_asset_class_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_id: Mapped[int] = mapped_column(ForeignKey("investment_account_holdings.id"))
    asset_class_id: Mapped[int] = mapped_column(ForeignKey("account_asset_classes.id"))
    percent_allocated: Mapped[Decimal] = mapped_column(Numeric(precision=28, scale=10))
    date_created: Mapped[date] = mapped_column(Date)

    holding: Mapped[InvestmentAccountHolding] = relationship(back_populates="allocations")
    asset_class: Mapped[AccountAssetClass] = relationship()
