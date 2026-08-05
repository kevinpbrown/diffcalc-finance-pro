"""Goals domain models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.base import Base, Discardable
from personal_finance.domain.effective_amount import EffectiveAmount

if TYPE_CHECKING:
    from personal_finance.domain.balance_sheet.account import InvestmentAccount


class GoalValue(Base):
    """Strategy base for determining a Goal's target amount.

    Uses single-table inheritance. Concrete subclasses share the ``goal_values``
    table; columns unused by a given subtype are stored as NULL.
    """

    __tablename__ = "goal_values"
    __mapper_args__ = {
        "polymorphic_on": "value_type",
        "polymorphic_identity": "base",
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    value_type: Mapped[str] = mapped_column(String(20))

    # ScalarGoalValue — temporal timeline replacing the former Decimal scalar
    value_id: Mapped[int | None] = mapped_column(
        ForeignKey("effective_amount_timelines.id"), nullable=True
    )
    value: Mapped[EffectiveAmount | None] = relationship(foreign_keys=[value_id])

    # SimplePVGoalValue
    future_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=28, scale=10), nullable=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    discount_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=28, scale=10), nullable=True
    )

    def calculate_target(self, as_of: date) -> Decimal | None:
        """Return the goal's target amount as of the given date, or None when there is no cap."""
        raise NotImplementedError


class ScalarGoalValue(GoalValue):
    """A goal target expressed as a temporal EffectiveAmount timeline."""

    __mapper_args__ = {"polymorphic_identity": "scalar"}

    def __init__(self, **kwargs: object) -> None:
        """Ensure a fresh EffectiveAmount value timeline is created when none is supplied."""
        if "value" not in kwargs:
            kwargs["value"] = EffectiveAmount()
        super().__init__(**kwargs)

    def calculate_target(self, as_of: date) -> Decimal | None:
        """Return the latest committed value on or before ``as_of``, or None."""
        return self.value.latest_value_as_of(as_of) if self.value else None


def calculate_present_value(
    future_value: Decimal, discount_rate: Decimal, start_date: date, maturity_date: date
) -> Decimal:
    """Compute PV = FV / (1 + r)^t.

    Shared by :meth:`SimplePVGoalValue.calculate_target` (the persisted calculation)
    and the Goals UI's live keystroke preview in ``ui/screens/goal_dialogs.py`` (a
    pre-save preview that never touches the database), so the formula lives in one
    place rather than being duplicated.

    Args:
        future_value: The target amount at ``maturity_date``.
        discount_rate: Annual discount rate (e.g. ``Decimal("0.05")`` for 5%).
        start_date: The date PV is measured from.
        maturity_date: The date ``future_value`` is reached.

    Returns:
        Present value as of ``start_date``.
    """
    years = Decimal((maturity_date - start_date).days) / Decimal("365.25")
    factor = (Decimal("1") + discount_rate) ** years
    return future_value / factor


def calculate_monthly_payment(
    future_value: Decimal, discount_rate: Decimal, effective_date: date, maturity_date: date
) -> Decimal | None:
    """Compute the monthly savings payment needed to reach ``future_value`` by ``maturity_date``.

    Formula: PMT = FV × r / ((1 + r)^n − 1), where r = discount_rate / 12
    and n = whole calendar months from effective_date to maturity_date.

    Shared by :meth:`SimplePVGoalValue.monthly_payment` (the persisted calculation)
    and the Goals UI's live keystroke preview in ``ui/screens/goal_dialogs.py`` (a
    pre-save preview that never touches the database), so the formula lives in one
    place rather than being duplicated.

    Args:
        future_value: The target amount at ``maturity_date``.
        discount_rate: Annual discount rate (e.g. ``Decimal("0.05")`` for 5%).
        effective_date: The reference date from which remaining months are counted.
        maturity_date: The date ``future_value`` is due.

    Returns:
        Monthly payment amount, or ``None`` when ``maturity_date`` is already on or
        before ``effective_date`` (n ≤ 0 whole months remaining).
    """
    n = (maturity_date.year - effective_date.year) * 12 + (
        maturity_date.month - effective_date.month
    )
    if n <= 0:
        return None
    r = discount_rate / Decimal("12")
    if r == Decimal("0"):
        return future_value / Decimal(str(n))
    factor = (Decimal("1") + r) ** Decimal(n)
    return future_value * r / (factor - Decimal("1"))


class SimplePVGoalValue(GoalValue):
    """A goal target computed as the present value of a future amount.

    PV = FV / (1 + r)^t, where t is fractional years between start_date and maturity_date
    and r is the annual discount_rate.

    Unlike every other calculate_target / get_value in the domain, this result is computed
    live from the four scalar attributes rather than read from an EffectiveAmount timeline.
    Any change to those attributes retroactively affects all effective dates. If temporal
    isolation of historical PV snapshots becomes a requirement, the attributes will need
    to be converted to EffectiveAmount timelines.
    """

    __mapper_args__ = {"polymorphic_identity": "simple_pv"}

    def calculate_target(self, as_of: date) -> Decimal | None:
        """Compute and return PV = FV / (1 + r)^t as of ``as_of``."""
        assert self.future_value is not None
        assert self.start_date is not None
        assert self.maturity_date is not None
        assert self.discount_rate is not None
        return calculate_present_value(
            self.future_value, self.discount_rate, self.start_date, self.maturity_date
        )

    def monthly_payment(self, effective_date: date) -> Decimal | None:
        """Compute the monthly savings payment needed to reach FV by maturity_date.

        Args:
            effective_date: The reference date from which remaining months are counted.

        Returns:
            Monthly payment amount, or ``None`` when the goal is already past maturity
            or required fields are absent.
        """
        if any(v is None for v in [self.future_value, self.maturity_date, self.discount_rate]):
            return None
        assert self.future_value is not None
        assert self.maturity_date is not None
        assert self.discount_rate is not None
        return calculate_monthly_payment(
            self.future_value, self.discount_rate, effective_date, self.maturity_date
        )


class NoGoalValue(GoalValue):
    """Sentinel subtype indicating the goal has no explicit target amount."""

    __mapper_args__ = {"polymorphic_identity": "none"}

    def calculate_target(self, as_of: date) -> Decimal | None:
        """Return None — this goal has no cap."""
        return None


class GoalBankPortion(Base):
    """Strategy base for how much of a Goal's target is claimed from the bank.

    Uses single-table inheritance. GoalBankPortionAutoFill claims the difference
    between the goal target and the allocated investment account values.
    GoalBankPortionScalar claims a fixed explicit amount.
    """

    __tablename__ = "goal_bank_portions"
    __mapper_args__ = {
        "polymorphic_on": "portion_type",
        "polymorphic_identity": "base",
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    portion_type: Mapped[str] = mapped_column(String(20))

    # GoalBankPortionScalar only — temporal timeline replacing the former Decimal scalar
    amount_id: Mapped[int | None] = mapped_column(
        ForeignKey("effective_amount_timelines.id"), nullable=True
    )
    amount: Mapped[EffectiveAmount | None] = relationship(foreign_keys=[amount_id])

    goal: Mapped[Goal] = relationship("Goal", back_populates="bank_portion", uselist=False)

    def get_value(self, as_of: date) -> Decimal | None:
        """Return the amount claimed from the bank as of the given date."""
        raise NotImplementedError


class GoalBankPortionAutoFill(GoalBankPortion):
    """Claims goal target minus the sum of allocated investment account balances.

    Evaluates to $0 when the goal's GoalValue is NoGoalValue.
    """

    __mapper_args__ = {"polymorphic_identity": "auto_fill"}

    def get_value(self, as_of: date) -> Decimal | None:
        """Return target minus allocated investment balances, floored at $0.

        When allocated investment balances exceed the goal target the bank claim
        is $0; bank allocations are never negative.
        """
        target = self.goal.goal_value.calculate_target(as_of)
        if target is None:
            return Decimal("0")
        allocated_sum = Decimal("0")
        for acc in self.goal.allocated_accounts:
            if acc.is_active(as_of):
                balance = acc.get_balance(as_of)
                if balance is not None:
                    allocated_sum += balance
        return max(Decimal("0"), target - allocated_sum)


class GoalBankPortionScalar(GoalBankPortion):
    """Claims an explicit temporal amount from the bank."""

    __mapper_args__ = {"polymorphic_identity": "scalar"}

    def __init__(self, **kwargs: object) -> None:
        """Ensure a fresh EffectiveAmount amount timeline is created when none is supplied."""
        if "amount" not in kwargs:
            kwargs["amount"] = EffectiveAmount()
        super().__init__(**kwargs)

    def get_value(self, as_of: date) -> Decimal | None:
        """Return the latest committed claim amount on or before ``as_of``."""
        return self.amount.latest_value_as_of(as_of) if self.amount else None


class Goal(Base, Discardable):
    """A financial target that claims a portion of assets."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    date_created: Mapped[date] = mapped_column(Date)
    goal_value_id: Mapped[int] = mapped_column(ForeignKey("goal_values.id"))
    bank_portion_id: Mapped[int] = mapped_column(ForeignKey("goal_bank_portions.id"))

    goal_value: Mapped[GoalValue] = relationship()
    bank_portion: Mapped[GoalBankPortion] = relationship(back_populates="goal")
    allocated_accounts: Mapped[list[InvestmentAccount]] = relationship("InvestmentAccount")
    asset_class_targets: Mapped[list[GoalAssetClassTarget]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
    )


class GoalAssetClassTarget(Base, Discardable):
    """Desired asset class composition for a Goal.

    The sum of active target_percent values is not constrained to 100%; unconstrained
    portions are allowed. UI-level validation warns when the sum exceeds 100%.
    """

    __tablename__ = "goal_asset_class_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"))
    asset_class_id: Mapped[int] = mapped_column(ForeignKey("account_asset_classes.id"))
    target_percent: Mapped[Decimal] = mapped_column(Numeric(precision=28, scale=10))
    date_created: Mapped[date] = mapped_column(Date)

    goal: Mapped[Goal] = relationship(back_populates="asset_class_targets")
    asset_class: Mapped[AccountAssetClass] = relationship()
