"""Tests for goals domain models."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet import (
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,
)
from personal_finance.domain.base import Base
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.goals import (
    Goal,
    GoalAssetClassTarget,
    GoalBankPortion,
    GoalBankPortionAutoFill,
    GoalBankPortionScalar,
    GoalValue,
    NoGoalValue,
    ScalarGoalValue,
    SimplePVGoalValue,
)
from personal_finance.domain.person import Person

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def person(db_session: Session) -> Person:
    p = Person(name="Alice")
    db_session.add(p)
    db_session.flush()
    return p


def _investment_account(person: Person, name: str = "RRSP") -> InvestmentAccount:
    cash = EffectiveAmount()
    cash.offer_value(date(2024, 1, 1), Decimal("0.00"))
    return InvestmentAccount(
        name=name,
        date_created=date(2024, 1, 1),
        date_effective=date(2024, 1, 1),
        date_modified=date(2024, 1, 1),
        classification=AccountClassification.ASSET_LONG_TERM,
        owners=[person],
        investment_registration=InvestmentRegistration.RRSP,
        cash_balance=cash,
    )


def _ea(value: Decimal, as_of: date = date(2024, 1, 1)) -> EffectiveAmount:
    """Create a single-entry EffectiveAmount for use in tests."""
    ea = EffectiveAmount()
    ea.offer_value(as_of, value)
    return ea


def _scalar_goal(name: str = "Retirement") -> tuple[Goal, ScalarGoalValue]:
    gv = ScalarGoalValue(value=_ea(Decimal("500000.00")))
    goal = Goal(
        name=name,
        date_created=date(2024, 1, 1),
        date_effective=date(2024, 1, 1),
        date_modified=date(2024, 1, 1),
        bank_portion=GoalBankPortionScalar(amount=_ea(Decimal("0.00"))),
        goal_value=gv,
    )
    return goal, gv


# ── GoalValue STI ─────────────────────────────────────────────────────────────


class TestScalarGoalValue:
    def test_calculate_target_returns_value(self) -> None:
        gv = ScalarGoalValue(value=_ea(Decimal("100000.00")))
        assert gv.calculate_target(date(2024, 6, 1)) == Decimal("100000.00")

    def test_calculate_target_returns_none_before_first_entry(self) -> None:
        """Returns None when no entries exist on or before as_of."""
        ea = EffectiveAmount()
        ea.offer_value(date(2025, 1, 1), Decimal("100000.00"))
        gv = ScalarGoalValue(value=ea)
        assert gv.calculate_target(date(2024, 6, 1)) is None

    def test_db_round_trip(self, db_session: Session) -> None:
        gv = ScalarGoalValue(value=_ea(Decimal("250000.00")))
        db_session.add(gv)
        db_session.flush()
        db_session.expire(gv)

        reloaded = db_session.get(GoalValue, gv.id)
        assert isinstance(reloaded, ScalarGoalValue)
        assert reloaded.calculate_target(date(2024, 6, 1)) == Decimal("250000.00")


class TestSimplePVGoalValue:
    def test_calculate_target_zero_rate_equals_future_value(self) -> None:
        gv = SimplePVGoalValue(
            future_value=Decimal("100000.00"),
            start_date=date(2024, 1, 1),
            maturity_date=date(2034, 1, 1),
            discount_rate=Decimal("0.00"),
        )
        result = gv.calculate_target(date(2024, 6, 1))
        assert result is not None
        assert abs(result - Decimal("100000.00")) < Decimal("0.01")

    def test_calculate_target_discounts_future_value(self) -> None:
        # PV of $121 in 2 years at 10% = $100 (approximately)
        gv = SimplePVGoalValue(
            future_value=Decimal("121.00"),
            start_date=date(2024, 1, 1),
            maturity_date=date(2026, 1, 1),
            discount_rate=Decimal("0.10"),
        )
        result = gv.calculate_target(date(2024, 6, 1))
        assert result is not None
        assert abs(result - Decimal("100.00")) < Decimal("0.50")

    def test_calculate_target_increases_with_higher_discount_rate(self) -> None:
        base = {
            "future_value": Decimal("200000.00"),
            "start_date": date(2024, 1, 1),
            "maturity_date": date(2044, 1, 1),
        }
        low = SimplePVGoalValue(**base, discount_rate=Decimal("0.03"))
        high = SimplePVGoalValue(**base, discount_rate=Decimal("0.07"))
        assert high.calculate_target(date(2024, 6, 1)) < low.calculate_target(date(2024, 6, 1))  # type: ignore[operator]

    def test_db_round_trip(self, db_session: Session) -> None:
        gv = SimplePVGoalValue(
            future_value=Decimal("300000.00"),
            start_date=date(2025, 1, 1),
            maturity_date=date(2045, 1, 1),
            discount_rate=Decimal("0.05"),
        )
        db_session.add(gv)
        db_session.flush()
        db_session.expire(gv)

        reloaded = db_session.get(GoalValue, gv.id)
        assert isinstance(reloaded, SimplePVGoalValue)
        assert reloaded.future_value == Decimal("300000.00")
        assert reloaded.discount_rate == Decimal("0.05")
        assert reloaded.calculate_target(date(2024, 6, 1)) is not None


class TestSimplePVGoalValueMonthlyPayment:
    def _pv(
        self,
        future_value: Decimal,
        maturity_date: date,
        discount_rate: Decimal,
        start_date: date = date(2026, 1, 1),
    ) -> SimplePVGoalValue:
        return SimplePVGoalValue(
            future_value=future_value,
            start_date=start_date,
            maturity_date=maturity_date,
            discount_rate=discount_rate,
        )

    def test_known_pmt_value(self) -> None:
        # $1,200 FV in 12 months at 0% → $100/month
        gv = self._pv(
            Decimal("1200"),
            maturity_date=date(2027, 6, 1),
            discount_rate=Decimal("0"),
        )
        result = gv.monthly_payment(date(2026, 6, 1))
        assert result is not None
        assert abs(result - Decimal("100")) < Decimal("0.01")

    def test_positive_rate_lowers_payment(self) -> None:
        # Earning interest means you contribute less per month than FV/n
        gv_zero = self._pv(Decimal("12000"), date(2027, 6, 1), Decimal("0"))
        gv_rate = self._pv(Decimal("12000"), date(2027, 6, 1), Decimal("0.06"))
        pmt_zero = gv_zero.monthly_payment(date(2026, 6, 1))
        pmt_rate = gv_rate.monthly_payment(date(2026, 6, 1))
        assert pmt_zero is not None and pmt_rate is not None
        assert pmt_rate < pmt_zero

    def test_returns_none_when_maturity_in_past(self) -> None:
        gv = self._pv(Decimal("10000"), date(2025, 1, 1), Decimal("0.05"))
        assert gv.monthly_payment(date(2026, 6, 1)) is None

    def test_returns_none_when_same_month(self) -> None:
        gv = self._pv(Decimal("10000"), date(2026, 6, 1), Decimal("0.05"))
        assert gv.monthly_payment(date(2026, 6, 1)) is None

    def test_returns_none_when_future_value_missing(self) -> None:
        gv = SimplePVGoalValue(
            future_value=None,
            start_date=date(2026, 1, 1),
            maturity_date=date(2036, 1, 1),
            discount_rate=Decimal("0.05"),
        )
        assert gv.monthly_payment(date(2026, 6, 1)) is None

    def test_returns_none_when_discount_rate_missing(self) -> None:
        gv = SimplePVGoalValue(
            future_value=Decimal("10000"),
            start_date=date(2026, 1, 1),
            maturity_date=date(2036, 1, 1),
            discount_rate=None,
        )
        assert gv.monthly_payment(date(2026, 6, 1)) is None


class TestNoGoalValue:
    def test_calculate_target_returns_none(self) -> None:
        gv = NoGoalValue()
        assert gv.calculate_target(date(2024, 6, 1)) is None

    def test_db_round_trip(self, db_session: Session) -> None:
        gv = NoGoalValue()
        db_session.add(gv)
        db_session.flush()
        db_session.expire(gv)

        reloaded = db_session.get(GoalValue, gv.id)
        assert isinstance(reloaded, NoGoalValue)
        assert reloaded.calculate_target(date(2024, 6, 1)) is None


class TestGoalValuePolymorphism:
    def test_query_base_returns_correct_subtypes(self, db_session: Session) -> None:
        db_session.add_all(
            [
                ScalarGoalValue(value=_ea(Decimal("100.00"))),
                NoGoalValue(),
                SimplePVGoalValue(
                    future_value=Decimal("200.00"),
                    start_date=date(2024, 1, 1),
                    maturity_date=date(2034, 1, 1),
                    discount_rate=Decimal("0.05"),
                ),
            ]
        )
        db_session.flush()
        db_session.expire_all()

        results = db_session.query(GoalValue).all()
        assert len(results) == 3
        types = {type(r) for r in results}
        assert types == {ScalarGoalValue, NoGoalValue, SimplePVGoalValue}


# ── GoalBankPortion ───────────────────────────────────────────────────────────


class TestGoalBankPortionScalar:
    def test_get_value_returns_amount_as_of_date(self, db_session: Session) -> None:
        goal, _ = _scalar_goal()
        db_session.add(goal)
        db_session.flush()
        db_session.expire_all()

        reloaded = db_session.get(GoalBankPortion, goal.bank_portion.id)
        assert isinstance(reloaded, GoalBankPortionScalar)
        assert reloaded.get_value(date(2024, 6, 1)) == Decimal("0.00")

    def test_get_value_uses_as_of_for_temporal_lookup(self, db_session: Session) -> None:
        """get_value uses as_of to retrieve the correct entry from the EffectiveAmount timeline."""
        amount = EffectiveAmount()
        amount.offer_value(date(2024, 1, 1), Decimal("5000.00"))
        amount.offer_value(date(2025, 1, 1), Decimal("6000.00"))
        portion = GoalBankPortionScalar(amount=amount)
        gv = ScalarGoalValue(value=_ea(Decimal("100000.00")))
        goal = Goal(
            name="Test",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=portion,
            goal_value=gv,
        )
        db_session.add(goal)
        db_session.flush()

        assert portion.get_value(date(2024, 6, 1)) == Decimal("5000.00")
        assert portion.get_value(date(2025, 6, 1)) == Decimal("6000.00")

    def test_get_value_returns_none_before_first_entry(self, db_session: Session) -> None:
        amount = EffectiveAmount()
        amount.offer_value(date(2024, 6, 1), Decimal("5000.00"))
        portion = GoalBankPortionScalar(amount=amount)
        gv = ScalarGoalValue(value=_ea(Decimal("100000.00")))
        goal = Goal(
            name="Test",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=portion,
            goal_value=gv,
        )
        db_session.add(goal)
        db_session.flush()

        assert portion.get_value(date(2024, 1, 1)) is None


class TestGoalBankPortionAutoFill:
    def test_get_value_no_goal_value_returns_zero(self, db_session: Session) -> None:
        portion = GoalBankPortionAutoFill()
        goal = Goal(
            name="Test",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=portion,
            goal_value=NoGoalValue(),
        )
        db_session.add(goal)
        db_session.flush()

        assert portion.get_value(date(2024, 6, 1)) == Decimal("0")

    def test_get_value_no_accounts_returns_full_target(self, db_session: Session) -> None:
        portion = GoalBankPortionAutoFill()
        goal = Goal(
            name="Test",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=portion,
            goal_value=ScalarGoalValue(value=_ea(Decimal("100000.00"))),
        )
        db_session.add(goal)
        db_session.flush()

        assert portion.get_value(date(2024, 6, 1)) == Decimal("100000.00")

    def test_get_value_subtracts_allocated_account_balances(
        self, db_session: Session, person: Person
    ) -> None:
        cash = EffectiveAmount()
        cash.offer_value(date(2024, 1, 1), Decimal("60000.00"))
        account = _investment_account(person)
        account.cash_balance = cash

        portion = GoalBankPortionAutoFill()
        goal = Goal(
            name="Test",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=portion,
            goal_value=ScalarGoalValue(value=_ea(Decimal("100000.00"))),
        )
        goal.allocated_accounts.append(account)
        db_session.add(goal)
        db_session.flush()

        # target($100K) - account_balance($60K) = $40K claimed from bank
        assert portion.get_value(date(2024, 6, 1)) == Decimal("40000.00")

    def test_get_value_overallocated_returns_zero(
        self, db_session: Session, person: Person
    ) -> None:
        cash = EffectiveAmount()
        cash.offer_value(date(2024, 1, 1), Decimal("150000.00"))
        account = _investment_account(person)
        account.cash_balance = cash

        portion = GoalBankPortionAutoFill()
        goal = Goal(
            name="Test",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=portion,
            goal_value=ScalarGoalValue(value=_ea(Decimal("100000.00"))),
        )
        goal.allocated_accounts.append(account)
        db_session.add(goal)
        db_session.flush()

        # account_balance($150K) > target($100K) — bank claim is floored at $0
        assert portion.get_value(date(2024, 6, 1)) == Decimal("0")

    def test_get_value_skips_inactive_accounts(self, db_session: Session, person: Person) -> None:
        cash = EffectiveAmount()
        cash.offer_value(date(2024, 1, 1), Decimal("40000.00"))
        account = _investment_account(person)
        account.cash_balance = cash
        account.date_discarded = date(2024, 3, 1)

        portion = GoalBankPortionAutoFill()
        goal = Goal(
            name="Test",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=portion,
            goal_value=ScalarGoalValue(value=_ea(Decimal("100000.00"))),
        )
        goal.allocated_accounts.append(account)
        db_session.add(goal)
        db_session.flush()

        # account is discarded before as_of — excluded
        assert portion.get_value(date(2024, 6, 1)) == Decimal("100000.00")
        # account is active on its discard day - 1
        assert portion.get_value(date(2024, 2, 28)) == Decimal("60000.00")


# ── Goal ──────────────────────────────────────────────────────────────────────


class TestGoalCreation:
    def test_creation_with_scalar_goal_value(self) -> None:
        goal, gv = _scalar_goal()
        assert goal.name == "Retirement"
        assert goal.goal_value is gv
        assert isinstance(goal.bank_portion, GoalBankPortionScalar)
        assert goal.bank_portion.amount.latest_value_as_of(date(2024, 6, 1)) == Decimal("0.00")

    def test_date_discarded_is_optional(self) -> None:
        goal, _ = _scalar_goal()
        assert goal.date_discarded is None

    def test_allocated_accounts_starts_empty(self) -> None:
        goal, _ = _scalar_goal()
        assert goal.allocated_accounts == []

    def test_asset_class_targets_starts_empty(self) -> None:
        goal, _ = _scalar_goal()
        assert goal.asset_class_targets == []

    def test_db_round_trip(self, db_session: Session) -> None:
        goal, _ = _scalar_goal("Emergency Fund")
        db_session.add(goal)
        db_session.flush()
        db_session.expire(goal)

        reloaded = db_session.get(Goal, goal.id)
        assert reloaded is not None
        assert reloaded.name == "Emergency Fund"
        assert isinstance(reloaded.bank_portion, GoalBankPortionScalar)
        assert isinstance(reloaded.goal_value, ScalarGoalValue)

    def test_goal_value_relationship_round_trips(self, db_session: Session) -> None:
        gv = ScalarGoalValue(value=_ea(Decimal("75000.00")))
        goal = Goal(
            name="House Down Payment",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=GoalBankPortionAutoFill(),
            goal_value=gv,
        )
        db_session.add(goal)
        db_session.flush()
        db_session.expire(goal)

        reloaded = db_session.get(Goal, goal.id)
        assert reloaded is not None
        assert reloaded.goal_value.calculate_target(date(2024, 6, 1)) == Decimal("75000.00")


class TestGoalIsActive:
    def _goal(self, **kwargs: object) -> Goal:
        gv = NoGoalValue()
        defaults: dict[str, object] = {
            "name": "Test",
            "date_created": date(2024, 1, 1),
            "date_effective": date(2024, 1, 1),
            "date_modified": date(2024, 1, 1),
            "bank_portion": GoalBankPortionScalar(amount=_ea(Decimal("0.00"))),
            "goal_value": gv,
        }
        return Goal(**{**defaults, **kwargs})

    def test_active_on_effective_date(self) -> None:
        g = self._goal(date_effective=date(2024, 1, 1))
        assert g.is_active(date(2024, 1, 1)) is True

    def test_active_after_effective_date(self) -> None:
        g = self._goal(date_effective=date(2024, 1, 1))
        assert g.is_active(date(2025, 6, 1)) is True

    def test_inactive_before_effective_date(self) -> None:
        g = self._goal(date_effective=date(2024, 6, 1))
        assert g.is_active(date(2024, 1, 1)) is False

    def test_active_indefinitely_when_not_discarded(self) -> None:
        g = self._goal(date_effective=date(2020, 1, 1), date_discarded=None)
        assert g.is_active(date(2099, 12, 31)) is True

    def test_inactive_on_discard_date(self) -> None:
        g = self._goal(date_effective=date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert g.is_active(date(2024, 6, 1)) is False

    def test_active_one_day_before_discard(self) -> None:
        g = self._goal(date_effective=date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert g.is_active(date(2024, 5, 31)) is True

    def test_inactive_after_discard_date(self) -> None:
        g = self._goal(date_effective=date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert g.is_active(date(2025, 1, 1)) is False


# ── Goal ↔ InvestmentAccount allocation ───────────────────────────────────────


class TestGoalAllocatedAccounts:
    def test_assign_account_via_goal_relationship(
        self, db_session: Session, person: Person
    ) -> None:
        goal, _ = _scalar_goal()
        account = _investment_account(person)
        goal.allocated_accounts.append(account)

        db_session.add(goal)
        db_session.flush()
        db_session.expire_all()

        reloaded_goal = db_session.get(Goal, goal.id)
        assert reloaded_goal is not None
        assert len(reloaded_goal.allocated_accounts) == 1
        assert reloaded_goal.allocated_accounts[0].name == "RRSP"

    def test_account_goal_id_set(self, db_session: Session, person: Person) -> None:
        goal, _ = _scalar_goal()
        account = _investment_account(person)
        goal.allocated_accounts.append(account)

        db_session.add(goal)
        db_session.flush()
        db_session.expire_all()

        reloaded = db_session.get(InvestmentAccount, account.id)
        assert reloaded is not None
        assert reloaded.goal_id == goal.id

    def test_account_without_goal_has_null_goal_id(
        self, db_session: Session, person: Person
    ) -> None:
        account = _investment_account(person)
        db_session.add(account)
        db_session.flush()
        db_session.expire(account)

        reloaded = db_session.get(InvestmentAccount, account.id)
        assert reloaded is not None
        assert reloaded.goal_id is None

    def test_multiple_accounts_can_be_allocated_to_same_goal(
        self, db_session: Session, person: Person
    ) -> None:
        goal, _ = _scalar_goal()
        a1 = _investment_account(person, "RRSP")
        a2 = _investment_account(person, "TFSA")
        goal.allocated_accounts.extend([a1, a2])

        db_session.add(goal)
        db_session.flush()
        db_session.expire_all()

        reloaded_goal = db_session.get(Goal, goal.id)
        assert reloaded_goal is not None
        assert len(reloaded_goal.allocated_accounts) == 2


# ── GoalAssetClassTarget ──────────────────────────────────────────────────────


class TestGoalAssetClassTarget:
    def _asset_class(self, db_session: Session, name: str = "Equity") -> AccountAssetClass:
        ac = AccountAssetClass(name=name, order_precedence=1, date_created=date(2024, 1, 1))
        db_session.add(ac)
        db_session.flush()
        return ac

    def test_creation_and_db_round_trip(self, db_session: Session) -> None:
        ac = self._asset_class(db_session)
        goal, _ = _scalar_goal()
        db_session.add(goal)
        db_session.flush()

        target = GoalAssetClassTarget(
            goal=goal,
            asset_class=ac,
            target_percent=Decimal("60.00"),
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
        )
        db_session.add(target)
        db_session.flush()
        db_session.expire(target)

        reloaded = db_session.get(GoalAssetClassTarget, target.id)
        assert reloaded is not None
        assert reloaded.target_percent == Decimal("60.00")
        assert reloaded.asset_class.name == "Equity"

    def test_target_via_goal_relationship(self, db_session: Session) -> None:
        ac = self._asset_class(db_session)
        goal, _ = _scalar_goal()
        GoalAssetClassTarget(
            goal=goal,
            asset_class=ac,
            target_percent=Decimal("40.00"),
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
        )
        db_session.add(goal)
        db_session.flush()
        db_session.expire(goal)

        reloaded_goal = db_session.get(Goal, goal.id)
        assert reloaded_goal is not None
        assert len(reloaded_goal.asset_class_targets) == 1
        assert reloaded_goal.asset_class_targets[0].target_percent == Decimal("40.00")

    def test_sum_can_exceed_100_percent(self, db_session: Session) -> None:
        equity = self._asset_class(db_session, "Equity")
        fixed = self._asset_class(db_session, "Fixed Income")
        goal, _ = _scalar_goal()
        db_session.add(goal)
        db_session.flush()

        for ac, pct in [(equity, Decimal("70.00")), (fixed, Decimal("60.00"))]:
            db_session.add(
                GoalAssetClassTarget(
                    goal=goal,
                    asset_class=ac,
                    target_percent=pct,
                    date_created=date(2024, 1, 1),
                    date_effective=date(2024, 1, 1),
                    date_modified=date(2024, 1, 1),
                )
            )
        db_session.flush()

        total = sum(t.target_percent for t in goal.asset_class_targets)
        assert total == Decimal("130.00")

    def test_is_active(self) -> None:
        gv = NoGoalValue()
        goal = Goal(
            name="Test",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            bank_portion=GoalBankPortionScalar(amount=_ea(Decimal("0.00"))),
            goal_value=gv,
        )
        ac = AccountAssetClass(name="Equity", order_precedence=1, date_created=date(2024, 1, 1))
        target = GoalAssetClassTarget(
            goal=goal,
            asset_class=ac,
            target_percent=Decimal("50.00"),
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            date_discarded=date(2024, 6, 1),
        )
        assert target.is_active(date(2024, 5, 31)) is True
        assert target.is_active(date(2024, 6, 1)) is False
        assert target.is_active(date(2024, 12, 31)) is False

    def test_cascade_delete_with_goal(self, db_session: Session) -> None:
        ac = self._asset_class(db_session)
        goal, _ = _scalar_goal()
        GoalAssetClassTarget(
            goal=goal,
            asset_class=ac,
            target_percent=Decimal("50.00"),
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
        )
        db_session.add(goal)
        db_session.flush()
        target_id = goal.asset_class_targets[0].id

        db_session.delete(goal)
        db_session.flush()

        assert db_session.get(GoalAssetClassTarget, target_id) is None
