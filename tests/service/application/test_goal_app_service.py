"""Tests for GoalAppService."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import personal_finance.domain.balance_sheet  # noqa: F401 — registers ORM models
import personal_finance.domain.cash_flow  # noqa: F401 — registers ORM models
import personal_finance.domain.goals  # noqa: F401 — registers ORM models
from personal_finance.core.interfaces import QuoteService
from personal_finance.domain.asset_class import AccountAssetClass, BuiltInAssetClassId
from personal_finance.domain.balance_sheet.account import (
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.base import Base
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.goals.goal import (
    Goal,
    GoalAssetClassTarget,
    GoalBankPortionAutoFill,
    GoalBankPortionScalar,
    NoGoalValue,
    ScalarGoalValue,
    SimplePVGoalValue,
)
from personal_finance.domain.person import Person
from personal_finance.service.application.goal_app_service import (
    GoalAppService,
)
from personal_finance.service.core.balance_sheet_service import BalanceSheetService
from personal_finance.service.core.goal_service import GoalService

_AS_OF = date(2026, 5, 1)
_CREATED = date(2024, 1, 1)


class _NullQuoteService(QuoteService):
    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:  # pragma: no cover
        raise NotImplementedError

    async def search_symbols(self, query: str) -> list:  # pragma: no cover
        raise NotImplementedError


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine)


@pytest.fixture()
def svc(session_factory: sessionmaker[Session]) -> GoalAppService:
    bs_svc = BalanceSheetService(_NullQuoteService())
    goal_svc = GoalService(bs_svc)
    return GoalAppService(goal_svc, bs_svc, session_factory)


# ── TestGetGoalValueParams ─────────────────────────────────────────────────────


class TestGetGoalValueParams:
    def test_manual_goal_returns_manual_type(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        bank = GoalBankPortionScalar()
        bank.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
        value_strategy = ScalarGoalValue()
        value_strategy.value.offer_value(_CREATED, Decimal("7500"))  # type: ignore[union-attr]
        goal = Goal(
            name="Savings",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=value_strategy,
            bank_portion=bank,
        )
        db_session.add(goal)
        db_session.flush()
        params = svc.get_goal_value_params(goal.id, _AS_OF)
        assert params.goal_type == "manual"
        assert params.manual_value == Decimal("7500")

    def test_manual_goal_no_entry_returns_none_value(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        bank = GoalBankPortionScalar()
        bank.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
        goal = Goal(
            name="Empty",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=ScalarGoalValue(),
            bank_portion=bank,
        )
        db_session.add(goal)
        db_session.flush()
        params = svc.get_goal_value_params(goal.id, _AS_OF)
        assert params.goal_type == "manual"
        assert params.manual_value is None

    def test_pv_goal_returns_pv_fields(self, db_session: Session, svc: GoalAppService) -> None:
        new_id = svc.create_goal(
            "Retirement",
            "pv",
            _AS_OF,
            future_value=Decimal("500000"),
            start_date=date(2026, 1, 1),
            maturity_date=date(2046, 1, 1),
            discount_rate=Decimal("0.07"),
        )
        params = svc.get_goal_value_params(new_id, _AS_OF)
        assert params.goal_type == "pv"
        assert params.future_value == Decimal("500000")
        assert params.start_date == date(2026, 1, 1)
        assert params.maturity_date == date(2046, 1, 1)
        assert params.discount_rate == Decimal("0.07")

    def test_no_target_goal_returns_none_type(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        new_id = svc.create_goal("General", "none", _AS_OF)
        params = svc.get_goal_value_params(new_id, _AS_OF)
        assert params.goal_type == "none"

    def test_nonexistent_goal_raises(self, svc: GoalAppService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.get_goal_value_params(9999, _AS_OF)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_goal(
    session: Session,
    bank_value: Decimal = Decimal("0"),
    name: str = "My Goal",
) -> Goal:
    bank = GoalBankPortionScalar()
    bank.amount.offer_value(_CREATED, bank_value)  # type: ignore[union-attr]
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


def _seed_cash(session: Session) -> AccountAssetClass:
    """Insert the built-in Cash asset class with reserved PK."""
    ac = AccountAssetClass(
        id=int(BuiltInAssetClassId.CASH),
        name="Cash",
        order_precedence=0,
        date_created=_CREATED,
    )
    session.add(ac)
    session.flush()
    return ac


# ── TestGetGoalsForAllocationView ──────────────────────────────────────────────


class TestGetGoalsForAllocationView:
    def test_returns_one_item_per_active_goal(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _make_goal(db_session, name="Goal A")
        _make_goal(db_session, name="Goal B")
        items = svc.get_goals_for_allocation_view(_AS_OF)
        assert len(items) == 2
        assert {i.name for i in items} == {"Goal A", "Goal B"}

    def test_target_sum_not_exceeded(self, db_session: Session, svc: GoalAppService) -> None:
        goal = _make_goal(db_session)
        ac = AccountAssetClass(name="Equity", order_precedence=1, date_created=_CREATED)
        db_session.add(ac)
        db_session.flush()
        db_session.add(
            GoalAssetClassTarget(
                goal_id=goal.id,
                asset_class_id=ac.id,
                target_percent=Decimal("50"),
                date_created=_CREATED,
                date_effective=_CREATED,
                date_modified=_CREATED,
            )
        )
        db_session.flush()
        items = svc.get_goals_for_allocation_view(_AS_OF)
        assert items[0].target_sum_exceeds_100 is False

    def test_target_sum_exceeds_100(self, db_session: Session, svc: GoalAppService) -> None:
        goal = _make_goal(db_session)
        ac = AccountAssetClass(name="Equity", order_precedence=1, date_created=_CREATED)
        db_session.add(ac)
        db_session.flush()
        db_session.add(
            GoalAssetClassTarget(
                goal_id=goal.id,
                asset_class_id=ac.id,
                target_percent=Decimal("110"),
                date_created=_CREATED,
                date_effective=_CREATED,
                date_modified=_CREATED,
            )
        )
        db_session.flush()
        items = svc.get_goals_for_allocation_view(_AS_OF)
        assert items[0].target_sum_exceeds_100 is True

    def test_excludes_discarded_goals(self, db_session: Session, svc: GoalAppService) -> None:
        _make_goal(db_session, name="Active")
        bank = GoalBankPortionScalar()
        bank.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
        discarded = Goal(
            name="Deleted",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=NoGoalValue(),
            bank_portion=bank,
            date_discarded=date(2025, 1, 1),
        )
        db_session.add(discarded)
        db_session.flush()
        items = svc.get_goals_for_allocation_view(_AS_OF)
        assert len(items) == 1
        assert items[0].name == "Active"


# ── TestGetGoalAllocationData ──────────────────────────────────────────────────


class TestGetGoalAllocationData:
    async def test_zero_total_value_gives_zero_actuals(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _seed_cash(db_session)
        goal = _make_goal(db_session, bank_value=Decimal("0"))
        data = await svc.get_goal_allocation_data(goal.id, _AS_OF)
        assert data.total_value == Decimal("0")
        assert all(row.actual_percent == Decimal("0") for row in data.rows)

    async def test_bank_portion_attributed_to_cash(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        cash_ac = _seed_cash(db_session)
        goal = _make_goal(db_session, bank_value=Decimal("1000"))
        data = await svc.get_goal_allocation_data(goal.id, _AS_OF)
        assert data.total_value == Decimal("1000")
        cash_row = next(r for r in data.rows if r.asset_class_id == cash_ac.id)
        assert cash_row.actual_percent == Decimal("100.00")

    async def test_difference_computed_correctly(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        cash_ac = _seed_cash(db_session)
        goal = _make_goal(db_session, bank_value=Decimal("1000"))
        # Set target at 60% for Cash
        db_session.add(
            GoalAssetClassTarget(
                goal_id=goal.id,
                asset_class_id=cash_ac.id,
                target_percent=Decimal("60"),
                date_created=_CREATED,
                date_effective=_CREATED,
                date_modified=_CREATED,
            )
        )
        db_session.flush()
        data = await svc.get_goal_allocation_data(goal.id, _AS_OF)
        cash_row = next(r for r in data.rows if r.asset_class_id == cash_ac.id)
        # actual=100%, target=60%, diff=+40%
        assert cash_row.target_percent == Decimal("60")
        assert cash_row.actual_percent == Decimal("100.00")
        assert cash_row.difference_percent == Decimal("40.00")
        assert cash_row.difference_amount == Decimal("400.00")

    async def test_rows_ordered_by_asset_class_precedence(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _seed_cash(db_session)  # order=0
        eq = AccountAssetClass(name="Equity", order_precedence=2, date_created=_CREATED)
        fi = AccountAssetClass(name="Fixed Income", order_precedence=1, date_created=_CREATED)
        db_session.add_all([eq, fi])
        db_session.flush()
        goal = _make_goal(db_session)
        data = await svc.get_goal_allocation_data(goal.id, _AS_OF)
        names = [r.asset_class_name for r in data.rows]
        assert names == ["Cash", "Fixed Income", "Equity"]

    async def test_nonexistent_goal_raises(self, svc: GoalAppService) -> None:
        with pytest.raises(ValueError, match="not found"):
            await svc.get_goal_allocation_data(99999, _AS_OF)

    async def test_investment_account_cash_balance_attributed_to_cash_class(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        cash_ac = _seed_cash(db_session)
        goal = _make_goal(db_session, bank_value=Decimal("0"))
        inv_acc = _make_investment_account(db_session, cash_balance=Decimal("500"))
        inv_acc.goal_id = goal.id
        db_session.flush()

        data = await svc.get_goal_allocation_data(goal.id, _AS_OF)

        assert data.total_value == Decimal("500")
        cash_row = next(r for r in data.rows if r.asset_class_id == cash_ac.id)
        assert cash_row.actual_percent == Decimal("100.00")

    async def test_null_bank_portion_value_treated_as_zero(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _seed_cash(db_session)
        # GoalBankPortionScalar with no timeline entry → get_value returns None
        bank = GoalBankPortionScalar()
        goal = Goal(
            name="No Bank Entry",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=NoGoalValue(),
            bank_portion=bank,
        )
        db_session.add(goal)
        db_session.flush()

        data = await svc.get_goal_allocation_data(goal.id, _AS_OF)

        assert data.total_value == Decimal("0")


# ── TestGetGoalsSummary ────────────────────────────────────────────────────────


def _make_bank_account(session: Session, balance: Decimal = Decimal("0")) -> SimpleAccount:
    """Seed a BANK SimpleAccount so get_total_bank_balance has something to read."""
    p = Person(name=f"Owner-{id(session)}")
    session.add(p)
    session.flush()
    bal = EffectiveAmount()
    bal.offer_value(_CREATED, balance)
    account = SimpleAccount(
        name="Chequing",
        date_created=_CREATED,
        date_effective=_CREATED,
        date_modified=_CREATED,
        classification=AccountClassification.ASSET_CURRENT,
        owners=[p],
        type=SimpleAccountCategory.BANK,
        balance=bal,
    )
    session.add(account)
    session.flush()
    return account


def _make_investment_account(
    session: Session, cash_balance: Decimal = Decimal("0")
) -> InvestmentAccount:
    p = Person(name=f"Investor-{id(session)}")
    session.add(p)
    session.flush()
    cb = EffectiveAmount()
    cb.offer_value(_CREATED, cash_balance)
    acc = InvestmentAccount(
        name="RRSP",
        date_created=_CREATED,
        date_effective=_CREATED,
        date_modified=_CREATED,
        classification=AccountClassification.ASSET_LONG_TERM,
        owners=[p],
        investment_registration=InvestmentRegistration.RRSP,
        cash_balance=cb,
    )
    session.add(acc)
    session.flush()
    return acc


class TestGetGoalsSummary:
    async def test_empty_goals_gives_empty_rows_no_overclaim(self, svc: GoalAppService) -> None:
        summary = await svc.get_goals_summary(_AS_OF)

        assert summary.rows == []
        assert summary.overclaim_amount is None

    async def test_no_goal_value_gives_none_type_and_no_difference(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _make_goal(db_session, bank_value=Decimal("500"))

        summary = await svc.get_goals_summary(_AS_OF)

        row = summary.rows[0]
        assert row.goal_type == "none"
        assert row.goal_target is None
        assert row.difference is None
        assert row.bank_allocation == Decimal("500")

    async def test_scalar_goal_gives_manual_type_and_difference(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        bank = GoalBankPortionScalar()
        bank.amount.offer_value(_CREATED, Decimal("2000"))  # type: ignore[union-attr]
        value_strategy = ScalarGoalValue()
        value_strategy.value.offer_value(_CREATED, Decimal("5000"))  # type: ignore[union-attr]
        goal = Goal(
            name="Emergency Fund",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=value_strategy,
            bank_portion=bank,
        )
        db_session.add(goal)
        db_session.flush()

        summary = await svc.get_goals_summary(_AS_OF)

        row = summary.rows[0]
        assert row.goal_type == "manual"
        assert row.goal_target == Decimal("5000")
        assert row.bank_allocation == Decimal("2000")
        assert row.investment_allocation == Decimal("0")
        # difference = inv + bank − target = 0 + 2000 − 5000 = −3000
        assert row.difference == Decimal("-3000")

    async def test_pv_goal_gives_pv_type(self, db_session: Session, svc: GoalAppService) -> None:
        bank = GoalBankPortionScalar()
        bank.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
        goal = Goal(
            name="Retirement",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=SimplePVGoalValue(
                future_value=Decimal("500000"),
                start_date=date(2026, 1, 1),
                maturity_date=date(2046, 1, 1),
                discount_rate=Decimal("0.07"),
            ),
            bank_portion=bank,
        )
        db_session.add(goal)
        db_session.flush()

        summary = await svc.get_goals_summary(_AS_OF)

        assert summary.rows[0].goal_type == "pv"

    async def test_autofill_bank_sets_is_autofill_true(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        goal = Goal(
            name="AutoFill Goal",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=NoGoalValue(),
            bank_portion=GoalBankPortionAutoFill(),
        )
        db_session.add(goal)
        db_session.flush()

        summary = await svc.get_goals_summary(_AS_OF)

        assert summary.rows[0].is_autofill is True

    async def test_scalar_bank_sets_is_autofill_false(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _make_goal(db_session)

        summary = await svc.get_goals_summary(_AS_OF)

        assert summary.rows[0].is_autofill is False

    async def test_overclaim_set_when_bank_claims_exceed_balance(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _make_bank_account(db_session, balance=Decimal("1000"))
        _make_goal(db_session, bank_value=Decimal("2000"))

        summary = await svc.get_goals_summary(_AS_OF)

        assert summary.overclaim_amount == Decimal("1000")
        assert summary.total_bank_balance == Decimal("1000")

    async def test_no_overclaim_when_bank_claims_within_balance(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _make_bank_account(db_session, balance=Decimal("5000"))
        _make_goal(db_session, bank_value=Decimal("2000"))

        summary = await svc.get_goals_summary(_AS_OF)

        assert summary.overclaim_amount is None

    async def test_investment_allocation_summed_from_allocated_accounts(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        goal = _make_goal(db_session, bank_value=Decimal("0"))
        inv_acc = _make_investment_account(db_session, cash_balance=Decimal("3000"))
        inv_acc.goal_id = goal.id
        db_session.flush()

        summary = await svc.get_goals_summary(_AS_OF)

        assert summary.rows[0].investment_allocation == Decimal("3000")


# ── TestGetInvestmentAccountsForDialog ────────────────────────────────────────


class TestGetInvestmentAccountsForDialog:
    async def test_empty_when_no_investment_accounts(self, svc: GoalAppService) -> None:
        options = await svc.get_investment_accounts_for_dialog(9999, _AS_OF)
        assert options == []

    async def test_unallocated_account_is_not_selected(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        goal = _make_goal(db_session)
        _make_investment_account(db_session)

        options = await svc.get_investment_accounts_for_dialog(goal.id, _AS_OF)

        assert len(options) == 1
        assert options[0].is_selected is False
        assert options[0].blocking_goal_name is None

    async def test_account_allocated_to_this_goal_is_selected(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        goal = _make_goal(db_session)
        inv_acc = _make_investment_account(db_session)
        inv_acc.goal_id = goal.id
        db_session.flush()

        options = await svc.get_investment_accounts_for_dialog(goal.id, _AS_OF)

        assert options[0].is_selected is True
        assert options[0].blocking_goal_name is None

    async def test_account_allocated_to_other_goal_shows_blocking_name(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        this_goal = _make_goal(db_session, name="My Goal")
        other_goal = _make_goal(db_session, name="Other Goal")
        inv_acc = _make_investment_account(db_session)
        inv_acc.goal_id = other_goal.id
        db_session.flush()

        options = await svc.get_investment_accounts_for_dialog(this_goal.id, _AS_OF)

        assert options[0].is_selected is False
        assert options[0].blocking_goal_name == "Other Goal"

    async def test_balance_included_in_option(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        goal = _make_goal(db_session)
        _make_investment_account(db_session, cash_balance=Decimal("7500"))

        options = await svc.get_investment_accounts_for_dialog(goal.id, _AS_OF)

        assert options[0].balance == Decimal("7500")


# ── TestProxies ────────────────────────────────────────────────────────────────


class TestProxies:
    """Each proxy method is a one-liner; one round-trip test per method suffices."""

    def test_discard_goal(self, db_session: Session, svc: GoalAppService) -> None:
        goal = _make_goal(db_session)
        svc.discard_goal(goal.id, _AS_OF)
        db_session.expire(goal)
        assert goal.date_discarded == _AS_OF

    def test_update_goal_name(self, db_session: Session, svc: GoalAppService) -> None:
        goal = _make_goal(db_session)
        svc.update_goal_name(goal.id, "Renamed")
        db_session.expire(goal)
        assert goal.name == "Renamed"

    def test_update_goal_scalar_value(self, db_session: Session, svc: GoalAppService) -> None:
        bank = GoalBankPortionScalar()
        bank.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
        value_strategy = ScalarGoalValue()
        goal = Goal(
            name="Manual",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=value_strategy,
            bank_portion=bank,
        )
        db_session.add(goal)
        db_session.flush()

        svc.update_goal_scalar_value(goal.id, Decimal("9999"), _AS_OF)

        db_session.expire(goal)
        assert goal.goal_value.calculate_target(_AS_OF) == Decimal("9999")

    def test_update_goal_bank_scalar(self, db_session: Session, svc: GoalAppService) -> None:
        goal = _make_goal(db_session, bank_value=Decimal("0"))
        svc.update_goal_bank_scalar(goal.id, Decimal("1234"), _AS_OF)
        db_session.expire_all()
        assert goal.bank_portion.get_value(_AS_OF) == Decimal("1234")

    def test_update_goal_value_strategy_to_none(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        bank = GoalBankPortionScalar()
        bank.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
        value_strategy = ScalarGoalValue()
        goal = Goal(
            name="Manual",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            goal_value=value_strategy,
            bank_portion=bank,
        )
        db_session.add(goal)
        db_session.flush()

        svc.update_goal_value_strategy(goal.id, "none", _AS_OF)

        db_session.expire(goal)
        assert isinstance(goal.goal_value, NoGoalValue)

    def test_switch_bank_to_scalar(self, db_session: Session, svc: GoalAppService) -> None:
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

        svc.switch_bank_to_scalar(goal.id, _AS_OF)

        db_session.expire(goal)
        assert isinstance(goal.bank_portion, GoalBankPortionScalar)

    def test_switch_bank_to_autofill(self, db_session: Session, svc: GoalAppService) -> None:
        goal = _make_goal(db_session)

        svc.switch_bank_to_autofill(goal.id)

        db_session.expire(goal)
        assert isinstance(goal.bank_portion, GoalBankPortionAutoFill)

    def test_update_goal_investment_allocation(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        goal = _make_goal(db_session)
        inv_acc = _make_investment_account(db_session)

        svc.update_goal_investment_allocation(goal.id, [inv_acc.id])

        db_session.expire(inv_acc)
        assert inv_acc.goal_id == goal.id

    def test_update_goal_asset_class_targets(
        self, db_session: Session, svc: GoalAppService
    ) -> None:
        _seed_cash(db_session)
        cash_id = int(BuiltInAssetClassId.CASH)
        goal = _make_goal(db_session)

        svc.update_goal_asset_class_targets(goal.id, [(cash_id, Decimal("60"))], _AS_OF)

        db_session.expire(goal)
        targets = {t.asset_class_id: t.target_percent for t in goal.asset_class_targets}
        assert targets[cash_id] == Decimal("60")
