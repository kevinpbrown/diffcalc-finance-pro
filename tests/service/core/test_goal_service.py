"""Unit tests for GoalService."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import personal_finance.domain.balance_sheet  # noqa: F401 — registers ORM models
import personal_finance.domain.goals  # noqa: F401 — registers ORM models
from personal_finance.core.interfaces import QuoteService, SecuritySearchResult
from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet.account import (
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,
)
from personal_finance.domain.base import Base
from personal_finance.domain.goals.goal import (
    Goal,
    GoalAssetClassTarget,
    GoalBankPortionAutoFill,
    GoalBankPortionScalar,
    NoGoalValue,
    ScalarGoalValue,
    SimplePVGoalValue,
)
from personal_finance.service.core.balance_sheet_service import BalanceSheetService
from personal_finance.service.core.goal_service import GoalService

_AS_OF = date(2026, 5, 1)
_CREATED = date(2024, 1, 1)


class _StubQuoteService(QuoteService):
    """Not exercised by these tests — none allocate InvestmentAccounts to AutoFill goals."""

    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:
        raise NotImplementedError

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        raise NotImplementedError


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def svc() -> GoalService:
    return GoalService(BalanceSheetService(_StubQuoteService()))


def _scalar_goal(
    session: Session,
    claim: Decimal,
    date_created: date = date(2024, 1, 1),
    date_discarded: date | None = None,
) -> Goal:
    portion = GoalBankPortionScalar()
    portion.amount.offer_value(date_created, claim)  # type: ignore[union-attr]
    goal = Goal(
        name="Goal",
        date_created=date_created,
        date_effective=date_created,
        date_modified=date_created,
        date_discarded=date_discarded,
        goal_value=NoGoalValue(),
        bank_portion=portion,
    )
    session.add(goal)
    session.flush()
    return goal


class TestGetTotalBankClaim:
    async def test_no_goals_returns_zero(self, db_session: Session, svc: GoalService) -> None:
        assert await svc.get_total_bank_claim(db_session, _AS_OF) == Decimal("0")

    async def test_single_scalar_goal(self, db_session: Session, svc: GoalService) -> None:
        _scalar_goal(db_session, Decimal("3000.00"))
        assert await svc.get_total_bank_claim(db_session, _AS_OF) == Decimal("3000.00")

    async def test_multiple_goals_summed(self, db_session: Session, svc: GoalService) -> None:
        _scalar_goal(db_session, Decimal("1000.00"))
        _scalar_goal(db_session, Decimal("2500.00"))
        assert await svc.get_total_bank_claim(db_session, _AS_OF) == Decimal("3500.00")

    async def test_discarded_goal_excluded(self, db_session: Session, svc: GoalService) -> None:
        _scalar_goal(db_session, Decimal("1000.00"))
        _scalar_goal(db_session, Decimal("5000.00"), date_discarded=date(2025, 1, 1))
        assert await svc.get_total_bank_claim(db_session, _AS_OF) == Decimal("1000.00")

    async def test_auto_fill_goal_with_no_value_claims_zero(
        self, db_session: Session, svc: GoalService
    ) -> None:
        goal = Goal(
            name="Auto",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            goal_value=NoGoalValue(),
            bank_portion=GoalBankPortionAutoFill(),
        )
        db_session.add(goal)
        db_session.flush()
        assert await svc.get_total_bank_claim(db_session, _AS_OF) == Decimal("0")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_scalar_goal(
    session: Session,
    name: str = "Goal",
    target: Decimal = Decimal("10000"),
    bank_claim: Decimal = Decimal("0"),
    date_discarded: date | None = None,
) -> Goal:
    """Create and flush a Manual (ScalarGoalValue + GoalBankPortionScalar) goal."""
    value_strategy = ScalarGoalValue()
    value_strategy.value.offer_value(_CREATED, target)  # type: ignore[union-attr]
    bank = GoalBankPortionScalar()
    bank.amount.offer_value(_CREATED, bank_claim)  # type: ignore[union-attr]
    goal = Goal(
        name=name,
        date_created=_CREATED,
        date_effective=_CREATED,
        date_modified=_CREATED,
        date_discarded=date_discarded,
        goal_value=value_strategy,
        bank_portion=bank,
    )
    session.add(goal)
    session.flush()
    return goal


# ── TestListActiveGoals ────────────────────────────────────────────────────────


class TestListActiveGoals:
    def test_returns_active_goals(self, db_session: Session, svc: GoalService) -> None:
        _make_scalar_goal(db_session, "Active")
        assert len(svc.list_active_goals(db_session, _AS_OF)) == 1

    def test_excludes_discarded(self, db_session: Session, svc: GoalService) -> None:
        _make_scalar_goal(db_session, "Active")
        _make_scalar_goal(db_session, "Discarded", date_discarded=date(2025, 1, 1))
        active = svc.list_active_goals(db_session, _AS_OF)
        assert len(active) == 1
        assert active[0].name == "Active"

    def test_empty_returns_empty(self, db_session: Session, svc: GoalService) -> None:
        assert svc.list_active_goals(db_session, _AS_OF) == []


# ── TestDiscardGoal ────────────────────────────────────────────────────────────


class TestDiscardGoal:
    def test_discard_removes_from_active_list(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session)
        svc.discard_goal(db_session, goal.id, _AS_OF)
        assert svc.list_active_goals(db_session, _AS_OF) == []

    def test_discard_nonexistent_raises(self, db_session: Session, svc: GoalService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.discard_goal(db_session, 9999, _AS_OF)


# ── TestUpdateGoalName ─────────────────────────────────────────────────────────


class TestUpdateGoalName:
    def test_name_is_updated(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session, name="Old Name")
        svc.update_goal_name(db_session, goal.id, "New Name")
        db_session.flush()
        db_session.expire(goal)
        assert goal.name == "New Name"

    def test_empty_name_raises(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session)
        with pytest.raises(ValueError, match="cannot be empty"):
            svc.update_goal_name(db_session, goal.id, "   ")


# ── TestUpdateGoalScalarValue ──────────────────────────────────────────────────


class TestUpdateGoalScalarValue:
    def test_new_timeline_entry_appended(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session, target=Decimal("5000"))
        svc.update_goal_scalar_value(db_session, goal.id, Decimal("9999"), _AS_OF)
        assert goal.goal_value.calculate_target(_AS_OF) == Decimal("9999")

    def test_wrong_strategy_raises(self, db_session: Session, svc: GoalService) -> None:
        bank = GoalBankPortionScalar()
        bank.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
        goal = Goal(
            name="No target",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=NoGoalValue(),
            bank_portion=bank,
        )
        db_session.add(goal)
        db_session.flush()
        with pytest.raises(ValueError, match="scalar"):
            svc.update_goal_scalar_value(db_session, goal.id, Decimal("100"), _AS_OF)


# ── TestUpdateGoalBankScalar ───────────────────────────────────────────────────


class TestUpdateGoalBankScalar:
    def test_timeline_entry_appended(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session, bank_claim=Decimal("500"))
        svc.update_goal_bank_scalar(db_session, goal.id, Decimal("2000"), _AS_OF)
        assert goal.bank_portion.get_value(_AS_OF) == Decimal("2000")

    def test_autofill_goal_raises(self, db_session: Session, svc: GoalService) -> None:
        goal = Goal(
            name="AutoFill",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=NoGoalValue(),
            bank_portion=GoalBankPortionAutoFill(),
        )
        db_session.add(goal)
        db_session.flush()
        with pytest.raises(ValueError, match="scalar"):
            svc.update_goal_bank_scalar(db_session, goal.id, Decimal("100"), _AS_OF)


# ── TestSwitchBankPortion ──────────────────────────────────────────────────────


# ── TestCreateGoal ─────────────────────────────────────────────────────────────


class TestCreateGoal:
    def test_create_manual_no_value(self, db_session: Session, svc: GoalService) -> None:
        new_id = svc.create_goal(db_session, "Rainy day", "manual", _AS_OF)
        goal = db_session.get(Goal, new_id)
        assert goal is not None
        assert goal.name == "Rainy day"
        assert isinstance(goal.goal_value, ScalarGoalValue)
        assert isinstance(goal.bank_portion, GoalBankPortionScalar)
        # No value entry yet — calculate_target returns None
        assert goal.goal_value.calculate_target(_AS_OF) is None

    def test_create_manual_with_value(self, db_session: Session, svc: GoalService) -> None:
        new_id = svc.create_goal(db_session, "Vacation", "manual", _AS_OF, value=Decimal("5000"))
        goal = db_session.get(Goal, new_id)
        assert goal is not None
        assert isinstance(goal.goal_value, ScalarGoalValue)
        assert goal.goal_value.calculate_target(_AS_OF) == Decimal("5000")
        assert goal.bank_portion.get_value(_AS_OF) == Decimal("0")

    def test_create_pv_goal(self, db_session: Session, svc: GoalService) -> None:
        new_id = svc.create_goal(
            db_session,
            "Retirement",
            "pv",
            _AS_OF,
            future_value=Decimal("1000000"),
            start_date=date(2026, 1, 1),
            maturity_date=date(2046, 1, 1),
            discount_rate=Decimal("0.06"),
        )
        goal = db_session.get(Goal, new_id)
        assert goal is not None
        assert isinstance(goal.goal_value, SimplePVGoalValue)
        target = goal.goal_value.calculate_target(_AS_OF)
        assert target is not None and target > Decimal("0")

    def test_create_no_target_goal(self, db_session: Session, svc: GoalService) -> None:
        new_id = svc.create_goal(db_session, "General savings", "none", _AS_OF)
        goal = db_session.get(Goal, new_id)
        assert goal is not None
        assert isinstance(goal.goal_value, NoGoalValue)
        assert goal.goal_value.calculate_target(_AS_OF) is None

    def test_empty_name_raises(self, db_session: Session, svc: GoalService) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            svc.create_goal(db_session, "   ", "manual", _AS_OF)

    def test_pv_missing_fields_raises(self, db_session: Session, svc: GoalService) -> None:
        with pytest.raises(ValueError, match="require"):
            svc.create_goal(db_session, "Broken", "pv", _AS_OF, future_value=Decimal("1000"))

    def test_goal_appears_in_active_list(self, db_session: Session, svc: GoalService) -> None:
        svc.create_goal(db_session, "New goal", "manual", _AS_OF)
        assert len(svc.list_active_goals(db_session, _AS_OF)) == 1


class TestUpdateGoalValueStrategy:
    def test_manual_to_none(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session, target=Decimal("5000"))
        svc.update_goal_value_strategy(db_session, goal.id, "none", _AS_OF)
        db_session.refresh(goal)
        assert isinstance(goal.goal_value, NoGoalValue)
        assert goal.goal_value.calculate_target(_AS_OF) is None

    def test_none_to_manual_with_value(self, db_session: Session, svc: GoalService) -> None:
        new_id = svc.create_goal(db_session, "No target", "none", _AS_OF)
        svc.update_goal_value_strategy(db_session, new_id, "manual", _AS_OF, value=Decimal("12000"))
        goal = db_session.get(Goal, new_id)
        assert goal is not None
        db_session.refresh(goal)
        assert isinstance(goal.goal_value, ScalarGoalValue)
        assert goal.goal_value.calculate_target(_AS_OF) == Decimal("12000")

    def test_manual_to_pv(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session, target=Decimal("10000"))
        svc.update_goal_value_strategy(
            db_session,
            goal.id,
            "pv",
            _AS_OF,
            future_value=Decimal("200000"),
            start_date=date(2026, 1, 1),
            maturity_date=date(2036, 1, 1),
            discount_rate=Decimal("0.05"),
        )
        db_session.refresh(goal)
        assert isinstance(goal.goal_value, SimplePVGoalValue)
        assert goal.goal_value.future_value == Decimal("200000")
        assert goal.goal_value.discount_rate == Decimal("0.05")
        target = goal.goal_value.calculate_target(_AS_OF)
        assert target is not None and target > Decimal("0")

    def test_pv_to_manual(self, db_session: Session, svc: GoalService) -> None:
        new_id = svc.create_goal(
            db_session,
            "Car",
            "pv",
            _AS_OF,
            future_value=Decimal("30000"),
            start_date=date(2026, 1, 1),
            maturity_date=date(2030, 1, 1),
            discount_rate=Decimal("0.04"),
        )
        svc.update_goal_value_strategy(db_session, new_id, "manual", _AS_OF, value=Decimal("25000"))
        goal = db_session.get(Goal, new_id)
        assert goal is not None
        db_session.refresh(goal)
        assert isinstance(goal.goal_value, ScalarGoalValue)
        assert goal.goal_value.calculate_target(_AS_OF) == Decimal("25000")

    def test_manual_no_value_sets_none_target(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session, target=Decimal("5000"))
        svc.update_goal_value_strategy(db_session, goal.id, "manual", _AS_OF)
        db_session.refresh(goal)
        assert isinstance(goal.goal_value, ScalarGoalValue)
        assert goal.goal_value.calculate_target(_AS_OF) is None

    def test_pv_missing_fields_raises(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session)
        with pytest.raises(ValueError, match="require"):
            svc.update_goal_value_strategy(
                db_session, goal.id, "pv", _AS_OF, future_value=Decimal("50000")
            )

    def test_nonexistent_goal_raises(self, db_session: Session, svc: GoalService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_goal_value_strategy(db_session, 9999, "manual", _AS_OF)


class TestSwitchBankPortion:
    def test_switch_to_scalar_creates_zero_entry(
        self, db_session: Session, svc: GoalService
    ) -> None:
        goal = Goal(
            name="AutoFill",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=NoGoalValue(),
            bank_portion=GoalBankPortionAutoFill(),
        )
        db_session.add(goal)
        db_session.flush()
        svc.switch_bank_portion_to_scalar(db_session, goal.id, _AS_OF)
        db_session.refresh(goal)
        assert isinstance(goal.bank_portion, GoalBankPortionScalar)
        assert goal.bank_portion.get_value(_AS_OF) == Decimal("0")

    def test_switch_to_autofill(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session)
        svc.switch_bank_portion_to_autofill(db_session, goal.id)
        db_session.refresh(goal)
        assert isinstance(goal.bank_portion, GoalBankPortionAutoFill)


def _make_investment_account(session: Session, name: str = "TFSA") -> InvestmentAccount:
    """Create and flush a minimal InvestmentAccount for use in tests."""
    account = InvestmentAccount(
        name=name,
        date_created=_CREATED,
        classification=AccountClassification.ASSET_LONG_TERM,
        investment_registration=InvestmentRegistration.TFSA,
    )
    session.add(account)
    session.flush()
    return account


class TestUpdateGoalInvestmentAllocation:
    def test_assign_account_to_goal(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session)
        account = _make_investment_account(db_session)
        svc.update_goal_investment_allocation(db_session, goal.id, [account.id])
        db_session.flush()
        db_session.refresh(account)
        assert account.goal_id == goal.id

    def test_remove_account_from_goal(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session)
        account = _make_investment_account(db_session)
        account.goal_id = goal.id
        db_session.flush()
        svc.update_goal_investment_allocation(db_session, goal.id, [])
        db_session.flush()
        db_session.refresh(account)
        assert account.goal_id is None

    def test_replace_allocation(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session)
        a1 = _make_investment_account(db_session, "TFSA")
        a2 = _make_investment_account(db_session, "RRSP")
        a1.goal_id = goal.id
        db_session.flush()
        svc.update_goal_investment_allocation(db_session, goal.id, [a2.id])
        db_session.flush()
        db_session.refresh(a1)
        db_session.refresh(a2)
        assert a1.goal_id is None
        assert a2.goal_id == goal.id

    def test_account_assigned_to_other_goal_raises(
        self, db_session: Session, svc: GoalService
    ) -> None:
        goal_a = _make_scalar_goal(db_session)
        goal_b = _make_scalar_goal(db_session)
        account = _make_investment_account(db_session)
        account.goal_id = goal_b.id
        db_session.flush()
        with pytest.raises(ValueError, match="already allocated"):
            svc.update_goal_investment_allocation(db_session, goal_a.id, [account.id])

    def test_nonexistent_account_raises(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_scalar_goal(db_session)
        with pytest.raises(ValueError, match="not found"):
            svc.update_goal_investment_allocation(db_session, goal.id, [99999])

    def test_nonexistent_goal_raises(self, db_session: Session, svc: GoalService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_goal_investment_allocation(db_session, 99999, [])


# ── Helpers for asset-class tests ──────────────────────────────────────────────


def _make_asset_class(
    session: Session,
    name: str = "US Equity",
    order: int = 1,
    ac_id: int | None = None,
) -> AccountAssetClass:
    kwargs: dict = {"name": name, "order_precedence": order, "date_created": _CREATED}
    if ac_id is not None:
        kwargs["id"] = ac_id
    ac = AccountAssetClass(**kwargs)
    session.add(ac)
    session.flush()
    return ac


def _make_no_value_goal(
    session: Session,
    name: str = "Goal",
) -> Goal:
    """Create and flush a goal with NoGoalValue for asset-class target tests."""
    bank = GoalBankPortionScalar()
    bank.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
    goal = Goal(
        name=name,
        date_created=_CREATED,
        date_effective=_CREATED,
        date_modified=_CREATED,
        goal_value=NoGoalValue(),
        bank_portion=bank,
    )
    session.add(goal)
    session.flush()
    return goal


# ── TestGetGoalAssetClassTargets ───────────────────────────────────────────────


class TestGetGoalAssetClassTargets:
    def test_returns_active_targets(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_no_value_goal(db_session)
        ac = _make_asset_class(db_session)
        db_session.add(
            GoalAssetClassTarget(
                goal_id=goal.id,
                asset_class_id=ac.id,
                target_percent=Decimal("40"),
                date_created=_CREATED,
                date_effective=_CREATED,
                date_modified=_CREATED,
            )
        )
        db_session.flush()
        result = svc.get_goal_asset_class_targets(db_session, goal.id, _AS_OF)
        assert result == {ac.id: Decimal("40")}

    def test_excludes_discarded_targets(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_no_value_goal(db_session)
        ac = _make_asset_class(db_session)
        db_session.add(
            GoalAssetClassTarget(
                goal_id=goal.id,
                asset_class_id=ac.id,
                target_percent=Decimal("40"),
                date_created=_CREATED,
                date_effective=_CREATED,
                date_modified=_CREATED,
                date_discarded=date(2025, 1, 1),
            )
        )
        db_session.flush()
        result = svc.get_goal_asset_class_targets(db_session, goal.id, _AS_OF)
        assert result == {}

    def test_returns_empty_when_no_targets(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_no_value_goal(db_session)
        result = svc.get_goal_asset_class_targets(db_session, goal.id, _AS_OF)
        assert result == {}

    def test_nonexistent_goal_raises(self, db_session: Session, svc: GoalService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.get_goal_asset_class_targets(db_session, 99999, _AS_OF)


# ── TestUpdateGoalAssetClassTargets ───────────────────────────────────────────


class TestUpdateGoalAssetClassTargets:
    def test_inserts_new_targets(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_no_value_goal(db_session)
        ac = _make_asset_class(db_session)
        svc.update_goal_asset_class_targets(db_session, goal.id, [(ac.id, Decimal("60"))], _AS_OF)
        db_session.flush()
        db_session.expire_all()
        result = svc.get_goal_asset_class_targets(db_session, goal.id, _AS_OF)
        assert result == {ac.id: Decimal("60")}

    def test_overwrites_existing_targets(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_no_value_goal(db_session)
        ac = _make_asset_class(db_session)
        svc.update_goal_asset_class_targets(db_session, goal.id, [(ac.id, Decimal("40"))], _AS_OF)
        db_session.flush()
        db_session.expire_all()
        svc.update_goal_asset_class_targets(db_session, goal.id, [(ac.id, Decimal("70"))], _AS_OF)
        db_session.flush()
        db_session.expire_all()
        result = svc.get_goal_asset_class_targets(db_session, goal.id, _AS_OF)
        assert result == {ac.id: Decimal("70")}

    def test_old_targets_soft_deleted(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_no_value_goal(db_session)
        ac = _make_asset_class(db_session)
        svc.update_goal_asset_class_targets(db_session, goal.id, [(ac.id, Decimal("40"))], _AS_OF)
        db_session.flush()
        db_session.expire_all()
        overwrite_date = date(2026, 6, 1)
        svc.update_goal_asset_class_targets(
            db_session, goal.id, [(ac.id, Decimal("70"))], overwrite_date
        )
        db_session.flush()
        db_session.expire_all()
        # Old target visible before overwrite date, new target after.
        before = svc.get_goal_asset_class_targets(db_session, goal.id, _AS_OF)
        after = svc.get_goal_asset_class_targets(db_session, goal.id, overwrite_date)
        assert before == {ac.id: Decimal("40")}
        assert after == {ac.id: Decimal("70")}

    def test_clearing_all_targets(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_no_value_goal(db_session)
        ac = _make_asset_class(db_session)
        svc.update_goal_asset_class_targets(db_session, goal.id, [(ac.id, Decimal("50"))], _AS_OF)
        db_session.flush()
        db_session.expire_all()
        svc.update_goal_asset_class_targets(db_session, goal.id, [], _AS_OF)
        db_session.flush()
        db_session.expire_all()
        result = svc.get_goal_asset_class_targets(db_session, goal.id, _AS_OF)
        assert result == {}

    def test_invalid_asset_class_raises(self, db_session: Session, svc: GoalService) -> None:
        goal = _make_no_value_goal(db_session)
        with pytest.raises(ValueError, match="not found"):
            svc.update_goal_asset_class_targets(
                db_session, goal.id, [(99999, Decimal("50"))], _AS_OF
            )

    def test_nonexistent_goal_raises(self, db_session: Session, svc: GoalService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_goal_asset_class_targets(db_session, 99999, [], _AS_OF)


# ── TestListActiveAssetClasses ─────────────────────────────────────────────────


class TestListActiveAssetClasses:
    def test_returns_active_sorted_by_precedence(
        self, db_session: Session, svc: GoalService
    ) -> None:
        # Insert in non-sorted order; expect result sorted by order_precedence.
        _make_asset_class(db_session, name="Equity", order=2)
        _make_asset_class(db_session, name="Cash", order=0)
        _make_asset_class(db_session, name="Fixed Income", order=1)
        result = svc.list_active_asset_classes(db_session, _AS_OF)
        assert [ac.name for ac in result] == ["Cash", "Fixed Income", "Equity"]

    def test_excludes_disabled(self, db_session: Session, svc: GoalService) -> None:
        _make_asset_class(db_session, name="Active", order=1)
        disabled = AccountAssetClass(
            name="Old",
            order_precedence=2,
            date_created=_CREATED,
            date_disabled=date(2025, 1, 1),
        )
        db_session.add(disabled)
        db_session.flush()
        result = svc.list_active_asset_classes(db_session, _AS_OF)
        assert all(ac.name != "Old" for ac in result)
