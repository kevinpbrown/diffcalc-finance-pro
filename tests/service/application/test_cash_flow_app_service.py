"""Tests for CashFlowAppService."""

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
from personal_finance.core.interfaces import QuoteService, SecuritySearchResult
from personal_finance.domain.balance_sheet.account import (
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.base import Base
from personal_finance.domain.cash_flow.expense import (
    HouseholdExpenseClassification,
    HouseholdExpenseFrequency,
    HouseholdExpenseSource,
)
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.goals.goal import Goal, GoalBankPortionScalar, NoGoalValue
from personal_finance.domain.person import Person
from personal_finance.service.application.cash_flow_app_service import CashFlowAppService
from personal_finance.service.core.balance_sheet_service import BalanceSheetService
from personal_finance.service.core.cash_flow_service import CashFlowService
from personal_finance.service.core.goal_service import GoalService

_AS_OF = date(2026, 5, 1)
_CREATED = date(2024, 1, 1)


class _NullQuoteService(QuoteService):
    """Not exercised by these tests — no AutoFill goal bank-claim paths are hit."""

    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:  # pragma: no cover
        raise NotImplementedError

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:  # pragma: no cover
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
def svc(session_factory: sessionmaker[Session]) -> CashFlowAppService:
    goal_svc = GoalService(BalanceSheetService(_NullQuoteService()))
    return CashFlowAppService(CashFlowService(), goal_svc, session_factory)


def _person(session: Session, name: str = "Alice") -> Person:
    p = Person(name=name)
    session.add(p)
    session.flush()
    return p


def _goal(session: Session, name: str = "RRSP") -> Goal:
    bp_amount = EffectiveAmount()
    bp_amount.offer_value(_CREATED, Decimal("0"))
    g = Goal(
        name=name,
        date_created=_CREATED,
        date_effective=_CREATED,
        date_modified=_CREATED,
        bank_portion=GoalBankPortionScalar(amount=bp_amount),
        goal_value=NoGoalValue(),
    )
    session.add(g)
    session.flush()
    return g


def _bank_account(session: Session, person: Person, name: str = "Chequing") -> SimpleAccount:
    balance = EffectiveAmount()
    balance.offer_value(_CREATED, Decimal("0"))
    acct = SimpleAccount(
        name=name,
        date_created=_CREATED,
        date_effective=_CREATED,
        date_modified=_CREATED,
        classification=AccountClassification.ASSET_CURRENT,
        owners=[person],
        type=SimpleAccountCategory.BANK,
        balance=balance,
    )
    session.add(acct)
    session.flush()
    return acct


def _investment_account(session: Session, person: Person, name: str = "TFSA") -> InvestmentAccount:
    cash = EffectiveAmount()
    cash.offer_value(_CREATED, Decimal("0"))
    acct = InvestmentAccount(
        name=name,
        date_created=_CREATED,
        date_effective=_CREATED,
        date_modified=_CREATED,
        classification=AccountClassification.ASSET_LONG_TERM,
        owners=[person],
        investment_registration=InvestmentRegistration.TFSA,
        cash_balance=cash,
    )
    session.add(acct)
    session.flush()
    return acct


# ── TestGetPersonNavItems ──────────────────────────────────────────────────────


class TestGetPersonNavItems:
    def test_returns_one_item_per_person(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        _person(db_session, "Alice")
        _person(db_session, "Bob")

        items = svc.get_person_nav_items()

        assert len(items) == 2
        names = [i.person_name for i in items]
        assert "Alice" in names
        assert "Bob" in names

    def test_nav_item_carries_correct_ids(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)

        items = svc.get_person_nav_items()

        item = items[0]
        assert item.person_id == alice.id
        assert item.profile_id == alice.cash_flow_profile.id
        assert item.person_name == "Alice"

    def test_empty_when_no_persons(self, svc: CashFlowAppService) -> None:
        assert svc.get_person_nav_items() == []


# ── TestGetPersonProfileFormData ───────────────────────────────────────────────


class TestGetPersonProfileFormData:
    def test_returns_correct_values_when_entries_exist(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        profile = alice.cash_flow_profile
        profile.gross_annual_income.offer_value(_CREATED, Decimal("100000"))
        profile.net_annual_income.offer_value(_CREATED, Decimal("75000"))
        profile.gross_bonus.offer_value(_CREATED, Decimal("8000"))
        profile.net_bonus.offer_value(_CREATED, Decimal("6000"))
        profile.auto_rrsp_deducted.offer_value(_CREATED, Decimal("5000"))
        profile.rrsp_matched.offer_value(_CREATED, Decimal("2500"))
        profile.auto_rrsp_goal = goal
        db_session.flush()

        data = svc.get_person_profile_form_data(profile.id, _AS_OF)

        assert data.profile_id == profile.id
        assert data.person_id == alice.id
        assert data.person_name == "Alice"
        assert data.gross_annual_income == Decimal("100000")
        assert data.net_annual_income == Decimal("75000")
        assert data.gross_bonus == Decimal("8000")
        assert data.net_bonus == Decimal("6000")
        assert data.auto_rrsp_deducted == Decimal("5000")
        assert data.rrsp_matched == Decimal("2500")
        assert data.auto_rrsp_goal_id == goal.id
        assert data.auto_rrsp_goal_name == "RRSP"

    def test_missing_timeline_entries_fall_back_to_zero(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)

        data = svc.get_person_profile_form_data(alice.cash_flow_profile.id, _AS_OF)

        assert data.gross_annual_income == Decimal("0")
        assert data.net_annual_income == Decimal("0")
        assert data.gross_bonus == Decimal("0")
        assert data.net_bonus == Decimal("0")
        assert data.auto_rrsp_deducted == Decimal("0")
        assert data.rrsp_matched == Decimal("0")

    def test_no_rrsp_goal_gives_none_goal_fields(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)

        data = svc.get_person_profile_form_data(alice.cash_flow_profile.id, _AS_OF)

        assert data.auto_rrsp_goal_id is None
        assert data.auto_rrsp_goal_name is None

    def test_raises_when_profile_not_found(self, svc: CashFlowAppService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.get_person_profile_form_data(9999, _AS_OF)


# ── TestGetGoalOptions ─────────────────────────────────────────────────────────


class TestGetGoalOptions:
    def test_returns_all_active_goals(self, db_session: Session, svc: CashFlowAppService) -> None:
        _goal(db_session, "RRSP")
        _goal(db_session, "TFSA")

        options = svc.get_goal_options(_AS_OF)

        names = [o.name for o in options]
        assert "RRSP" in names
        assert "TFSA" in names

    def test_excludes_discarded_goals(self, db_session: Session, svc: CashFlowAppService) -> None:
        _goal(db_session, "RRSP")
        bp = GoalBankPortionScalar()
        bp.amount.offer_value(_CREATED, Decimal("0"))  # type: ignore[union-attr]
        discarded = Goal(
            name="Old Fund",
            date_created=_CREATED,
            date_effective=_CREATED,
            date_modified=_CREATED,
            bank_portion=bp,
            goal_value=NoGoalValue(),
            date_discarded=date(2025, 1, 1),
        )
        db_session.add(discarded)
        db_session.flush()

        options = svc.get_goal_options(_AS_OF)

        assert len(options) == 1
        assert options[0].name == "RRSP"

    def test_option_carries_goal_id(self, db_session: Session, svc: CashFlowAppService) -> None:
        goal = _goal(db_session)

        options = svc.get_goal_options(_AS_OF)

        assert options[0].goal_id == goal.id


# ── TestUpdatePersonProfile ────────────────────────────────────────────────────


class TestUpdatePersonProfile:
    def test_delegates_to_core_service_and_persists(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        profile = alice.cash_flow_profile

        svc.update_person_profile(
            profile_id=profile.id,
            effective_date=_AS_OF,
            gross_annual_income=Decimal("120000"),
            net_annual_income=Decimal("90000"),
            gross_bonus=Decimal("0"),
            net_bonus=Decimal("0"),
            auto_rrsp_deducted=Decimal("0"),
            rrsp_matched=Decimal("0"),
            auto_rrsp_goal_id=None,
        )

        db_session.expire(profile)
        assert profile.gross_annual_income.latest_value_as_of(_AS_OF) == Decimal("120000")
        assert profile.net_annual_income.latest_value_as_of(_AS_OF) == Decimal("90000")

    def test_propagates_validation_errors(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        profile = alice.cash_flow_profile

        with pytest.raises(ValueError):
            svc.update_person_profile(
                profile_id=profile.id,
                effective_date=_AS_OF,
                gross_annual_income=Decimal("0"),
                net_annual_income=Decimal("0"),
                gross_bonus=Decimal("0"),
                net_bonus=Decimal("0"),
                auto_rrsp_deducted=Decimal("5000"),
                rrsp_matched=Decimal("0"),
                auto_rrsp_goal_id=None,  # missing required goal
            )


# ── TestGetExpensesViewData ─────────────────────────────────────────────────────


class TestGetExpensesViewData:
    def test_groups_by_classification(self, svc: CashFlowAppService) -> None:
        svc.create_expense(
            "Mortgage",
            Decimal("2000"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.REGULAR,
            _AS_OF,
        )
        svc.create_expense(
            "Car Insurance",
            Decimal("150"),
            HouseholdExpenseClassification.AUTO,
            HouseholdExpenseSource.CREDIT,
            HouseholdExpenseFrequency.REGULAR,
            _AS_OF,
        )
        svc.create_expense(
            "Gym",
            Decimal("50"),
            HouseholdExpenseClassification.OTHER,
            HouseholdExpenseSource.CREDIT,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )

        data = svc.get_expenses_view_data(_AS_OF)

        assert [r.name for r in data.home] == ["Mortgage"]
        assert [r.name for r in data.auto] == ["Car Insurance"]
        assert [r.name for r in data.other] == ["Gym"]
        assert data.home[0].amount == Decimal("2000")

    def test_computes_cross_tab_summary(self, svc: CashFlowAppService) -> None:
        svc.create_expense(
            "Mortgage",
            Decimal("2000"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.REGULAR,
            _AS_OF,
        )
        svc.create_expense(
            "Property Tax",
            Decimal("300"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )
        svc.create_expense(
            "Car Insurance",
            Decimal("150"),
            HouseholdExpenseClassification.AUTO,
            HouseholdExpenseSource.CREDIT,
            HouseholdExpenseFrequency.REGULAR,
            _AS_OF,
        )
        svc.create_expense(
            "Gym",
            Decimal("50"),
            HouseholdExpenseClassification.OTHER,
            HouseholdExpenseSource.OTHER,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )

        summary = svc.get_expenses_view_data(_AS_OF).summary

        assert summary.bank_regular == Decimal("2000")
        assert summary.bank_irregular == Decimal("300")
        assert summary.credit_regular == Decimal("150")
        assert summary.credit_irregular == Decimal("0")
        assert summary.other_regular == Decimal("0")
        assert summary.other_irregular == Decimal("50")

    def test_empty_when_no_expenses(self, svc: CashFlowAppService) -> None:
        data = svc.get_expenses_view_data(_AS_OF)

        assert data.home == []
        assert data.auto == []
        assert data.other == []
        assert data.summary.bank_regular == Decimal("0")


# ── TestCreateExpense ────────────────────────────────────────────────────────────


class TestCreateExpense:
    def test_persists_and_returns_id(self, svc: CashFlowAppService) -> None:
        expense_id = svc.create_expense(
            "Hydro",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )

        data = svc.get_expenses_view_data(_AS_OF)
        assert data.home[0].expense_id == expense_id

    def test_strips_name(self, svc: CashFlowAppService) -> None:
        svc.create_expense(
            "  Hydro  ",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )

        assert svc.get_expenses_view_data(_AS_OF).home[0].name == "Hydro"

    def test_raises_on_empty_name(self, svc: CashFlowAppService) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            svc.create_expense(
                "   ",
                Decimal("120"),
                HouseholdExpenseClassification.HOME,
                HouseholdExpenseSource.BANK,
                HouseholdExpenseFrequency.IRREGULAR,
                _AS_OF,
            )


# ── TestUpdateExpense ─────────────────────────────────────────────────────────────


class TestUpdateExpense:
    def test_updates_all_fields(self, svc: CashFlowAppService) -> None:
        expense_id = svc.create_expense(
            "Hydro",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )

        svc.update_expense(
            expense_id,
            "Hydro (updated)",
            Decimal("135"),
            HouseholdExpenseClassification.OTHER,
            HouseholdExpenseSource.CREDIT,
            HouseholdExpenseFrequency.REGULAR,
            _AS_OF,
        )

        row = svc.get_expenses_view_data(_AS_OF).other[0]
        assert row.name == "Hydro (updated)"
        assert row.amount == Decimal("135")
        assert row.source == HouseholdExpenseSource.CREDIT
        assert row.frequency == HouseholdExpenseFrequency.REGULAR

    def test_raises_on_empty_name(self, svc: CashFlowAppService) -> None:
        expense_id = svc.create_expense(
            "Hydro",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            svc.update_expense(
                expense_id,
                "   ",
                Decimal("135"),
                HouseholdExpenseClassification.HOME,
                HouseholdExpenseSource.BANK,
                HouseholdExpenseFrequency.IRREGULAR,
                _AS_OF,
            )

    def test_propagates_not_found(self, svc: CashFlowAppService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_expense(
                9999,
                "Nonexistent",
                Decimal("0"),
                HouseholdExpenseClassification.OTHER,
                HouseholdExpenseSource.OTHER,
                HouseholdExpenseFrequency.REGULAR,
                _AS_OF,
            )


# ── TestUpdateExpenseAmount ────────────────────────────────────────────────────


class TestUpdateExpenseAmount:
    def test_updates_amount_only(self, svc: CashFlowAppService) -> None:
        expense_id = svc.create_expense(
            "Hydro",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )

        svc.update_expense_amount(expense_id, Decimal("140"), _AS_OF)

        row = svc.get_expenses_view_data(_AS_OF).home[0]
        assert row.name == "Hydro"
        assert row.amount == Decimal("140")

    def test_propagates_not_found(self, svc: CashFlowAppService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_expense_amount(9999, Decimal("0"), _AS_OF)


# ── TestDiscardExpense ────────────────────────────────────────────────────────


class TestDiscardExpense:
    def test_removes_expense_from_view(self, svc: CashFlowAppService) -> None:
        expense_id = svc.create_expense(
            "Hydro",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _AS_OF,
        )

        svc.discard_expense(expense_id, _AS_OF)

        assert svc.get_expenses_view_data(_AS_OF).home == []

    def test_propagates_not_found(self, svc: CashFlowAppService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.discard_expense(9999, _AS_OF)


# ── TestGetAccountOptions ──────────────────────────────────────────────────────


class TestGetAccountOptions:
    def test_returns_all_active_accounts(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        bank = _bank_account(db_session, alice, "Chequing")
        invest = _investment_account(db_session, alice, "TFSA")

        options = svc.get_account_options(_AS_OF)

        ids = {o.account_id for o in options}
        assert ids == {bank.id, invest.id}

    def test_empty_when_no_accounts(self, svc: CashFlowAppService) -> None:
        assert svc.get_account_options(_AS_OF) == []


class TestGetBankAccountOptions:
    def test_returns_only_bank_accounts(self, db_session: Session, svc: CashFlowAppService) -> None:
        alice = _person(db_session)
        bank = _bank_account(db_session, alice, "Chequing")
        _investment_account(db_session, alice, "TFSA")

        options = svc.get_bank_account_options(_AS_OF)

        assert [o.account_id for o in options] == [bank.id]

    def test_empty_when_no_bank_accounts(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        _investment_account(db_session, alice, "TFSA")

        assert svc.get_bank_account_options(_AS_OF) == []


class TestGetInvestmentAccountOptions:
    def test_returns_only_investment_accounts(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        _bank_account(db_session, alice, "Chequing")
        invest = _investment_account(db_session, alice, "TFSA")

        options = svc.get_investment_account_options(_AS_OF)

        assert [o.account_id for o in options] == [invest.id]

    def test_empty_when_no_investment_accounts(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        _bank_account(db_session, alice, "Chequing")

        assert svc.get_investment_account_options(_AS_OF) == []


# ── TestGetReportViewData ──────────────────────────────────────────────────────


class TestGetReportViewData:
    def test_empty_db_returns_zero_report(self, svc: CashFlowAppService) -> None:
        report = svc.get_report_view_data(_AS_OF)

        assert report.gross_monthly == Decimal("0")
        assert report.net_monthly == Decimal("0")
        assert report.rrsp_deduction_lines == []
        assert report.avg_monthly_expenses == Decimal("0")
        assert report.contributions == []
        assert report.total_monthly_retained == Decimal("0")
        assert report.goal_contributions == []

    def test_full_scenario_computes_every_figure(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        rrsp_goal = _goal(db_session, "RRSP Goal")
        tfsa_goal = _goal(db_session, "TFSA Goal")
        source = _bank_account(db_session, alice, "Chequing")
        dest = _investment_account(db_session, alice, "TFSA")

        svc.update_person_profile(
            profile_id=alice.cash_flow_profile.id,
            effective_date=_AS_OF,
            gross_annual_income=Decimal("120000"),
            net_annual_income=Decimal("72000"),
            gross_bonus=Decimal("0"),
            net_bonus=Decimal("1200"),
            auto_rrsp_deducted=Decimal("6000"),
            rrsp_matched=Decimal("3000"),
            auto_rrsp_goal_id=rrsp_goal.id,
        )
        svc.create_expense(
            "Groceries",
            Decimal("200"),
            HouseholdExpenseClassification.OTHER,
            HouseholdExpenseSource.CREDIT,
            HouseholdExpenseFrequency.REGULAR,
            _AS_OF,
        )
        svc.create_automated_contribution(
            "TFSA transfer",
            Decimal("500"),
            source.id,
            dest.id,
            tfsa_goal.id,
            _AS_OF,
        )

        report = svc.get_report_view_data(_AS_OF)

        assert report.gross_monthly == Decimal("10000")
        assert report.net_monthly == Decimal("6000")
        assert len(report.rrsp_deduction_lines) == 1
        assert report.rrsp_deduction_lines[0].person_name == "Alice"
        assert report.rrsp_deduction_lines[0].monthly_amount == Decimal("750")
        assert report.taxes_other_monthly == Decimal("3250")
        assert report.avg_monthly_expenses == Decimal("200")
        assert len(report.contributions) == 1
        assert report.contributions[0].amount == Decimal("500")
        assert report.total_monthly_retained == Decimal("5300")
        assert report.total_annual_retained == Decimal("63600")
        assert report.total_net_bonus == Decimal("1200")
        assert report.final_annual_retained == Decimal("64800")
        assert report.gross_annual_total == Decimal("120000")

        goal_totals = {g.goal_name: g.annual_amount for g in report.goal_contributions}
        assert goal_totals == {
            "RRSP Goal": Decimal("9000"),
            "TFSA Goal": Decimal("6000"),
        }

    def test_rrsp_and_automated_contribution_to_same_goal_are_additive(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        goal = _goal(db_session, "Shared Goal")
        source = _bank_account(db_session, alice, "Chequing")
        dest = _investment_account(db_session, alice, "TFSA")

        svc.update_person_profile(
            profile_id=alice.cash_flow_profile.id,
            effective_date=_AS_OF,
            gross_annual_income=Decimal("0"),
            net_annual_income=Decimal("0"),
            gross_bonus=Decimal("0"),
            net_bonus=Decimal("0"),
            auto_rrsp_deducted=Decimal("6000"),
            rrsp_matched=Decimal("0"),
            auto_rrsp_goal_id=goal.id,
        )
        svc.create_automated_contribution(
            "Extra savings", Decimal("100"), source.id, dest.id, goal.id, _AS_OF
        )

        report = svc.get_report_view_data(_AS_OF)

        assert len(report.goal_contributions) == 1
        # RRSP (6000 annual) + automated contribution (100/mo * 12 = 1200 annual)
        assert report.goal_contributions[0].goal_name == "Shared Goal"
        assert report.goal_contributions[0].annual_amount == Decimal("7200")


# ── TestCreateAutomatedContribution ─────────────────────────────────────────────


class TestCreateAutomatedContribution:
    def test_persists_and_returns_id(self, db_session: Session, svc: CashFlowAppService) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        source = _bank_account(db_session, alice)
        dest = _investment_account(db_session, alice)

        contribution_id = svc.create_automated_contribution(
            "Monthly savings", Decimal("500"), source.id, dest.id, goal.id, _AS_OF
        )

        report = svc.get_report_view_data(_AS_OF)
        assert report.contributions[0].contribution_id == contribution_id

    def test_strips_name(self, db_session: Session, svc: CashFlowAppService) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        source = _bank_account(db_session, alice)
        dest = _investment_account(db_session, alice)

        svc.create_automated_contribution(
            "  Monthly savings  ", Decimal("500"), source.id, dest.id, goal.id, _AS_OF
        )

        assert svc.get_report_view_data(_AS_OF).contributions[0].name == "Monthly savings"

    def test_raises_on_empty_name(self, db_session: Session, svc: CashFlowAppService) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        source = _bank_account(db_session, alice)
        dest = _investment_account(db_session, alice)

        with pytest.raises(ValueError, match="cannot be empty"):
            svc.create_automated_contribution(
                "   ", Decimal("500"), source.id, dest.id, goal.id, _AS_OF
            )


# ── TestUpdateAutomatedContribution ─────────────────────────────────────────────


class TestUpdateAutomatedContribution:
    def test_updates_all_fields(self, db_session: Session, svc: CashFlowAppService) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        source = _bank_account(db_session, alice, "Chequing")
        dest = _investment_account(db_session, alice, "TFSA")
        other_dest = _investment_account(db_session, alice, "RRSP")
        contribution_id = svc.create_automated_contribution(
            "Monthly savings", Decimal("500"), source.id, dest.id, goal.id, _AS_OF
        )

        svc.update_automated_contribution(
            contribution_id,
            "Monthly savings (updated)",
            Decimal("600"),
            source.id,
            other_dest.id,
            goal.id,
            _AS_OF,
        )

        row = svc.get_report_view_data(_AS_OF).contributions[0]
        assert row.name == "Monthly savings (updated)"
        assert row.amount == Decimal("600")
        assert row.destination_account_id == other_dest.id

    def test_raises_on_empty_name(self, db_session: Session, svc: CashFlowAppService) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        source = _bank_account(db_session, alice)
        dest = _investment_account(db_session, alice)
        contribution_id = svc.create_automated_contribution(
            "Monthly savings", Decimal("500"), source.id, dest.id, goal.id, _AS_OF
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            svc.update_automated_contribution(
                contribution_id, "   ", Decimal("500"), source.id, dest.id, goal.id, _AS_OF
            )

    def test_propagates_not_found(self, svc: CashFlowAppService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_automated_contribution(9999, "Nonexistent", Decimal("0"), 1, 2, 3, _AS_OF)


# ── TestDiscardAutomatedContribution ────────────────────────────────────────────


class TestDiscardAutomatedContribution:
    def test_removes_contribution_from_report(
        self, db_session: Session, svc: CashFlowAppService
    ) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        source = _bank_account(db_session, alice)
        dest = _investment_account(db_session, alice)
        contribution_id = svc.create_automated_contribution(
            "Monthly savings", Decimal("500"), source.id, dest.id, goal.id, _AS_OF
        )

        svc.discard_automated_contribution(contribution_id, _AS_OF)

        assert svc.get_report_view_data(_AS_OF).contributions == []

    def test_propagates_not_found(self, svc: CashFlowAppService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.discard_automated_contribution(9999, _AS_OF)
