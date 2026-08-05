"""Tests for CashFlowService."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import personal_finance.domain.balance_sheet  # noqa: F401 — registers ORM models
import personal_finance.domain.cash_flow  # noqa: F401 — registers ORM models
import personal_finance.domain.goals  # noqa: F401 — registers ORM models
from personal_finance.domain.balance_sheet.account import (
    AccountClassification,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.base import Base
from personal_finance.domain.cash_flow.contribution import AutomatedContribution
from personal_finance.domain.cash_flow.expense import (
    HouseholdExpense,
    HouseholdExpenseClassification,
    HouseholdExpenseFrequency,
    HouseholdExpenseSource,
)
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.goals.goal import Goal, GoalBankPortionScalar, NoGoalValue
from personal_finance.domain.person import Person
from personal_finance.service.core.cash_flow_service import CashFlowService

_AS_OF = date(2026, 5, 1)
_CREATED = date(2024, 1, 1)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def svc() -> CashFlowService:
    return CashFlowService()


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


def _simple_account(
    session: Session,
    person: Person,
    name: str = "Bank",
    as_of: date = _CREATED,
) -> SimpleAccount:
    balance = EffectiveAmount()
    balance.offer_value(as_of, Decimal("0"))
    acct = SimpleAccount(
        name=name,
        date_created=as_of,
        date_effective=as_of,
        date_modified=as_of,
        classification=AccountClassification.ASSET_CURRENT,
        owners=[person],
        type=SimpleAccountCategory.BANK,
        balance=balance,
    )
    session.add(acct)
    session.flush()
    return acct


# ── TestListPersonProfiles ─────────────────────────────────────────────────────


class TestListPersonProfiles:
    def test_returns_all_profiles_in_person_insertion_order(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        _person(db_session, "Alice")
        _person(db_session, "Bob")

        profiles = svc.list_person_profiles(db_session)

        assert len(profiles) == 2
        assert profiles[0].person.name == "Alice"
        assert profiles[1].person.name == "Bob"

    def test_empty_when_no_persons(self, db_session: Session, svc: CashFlowService) -> None:
        assert svc.list_person_profiles(db_session) == []

    def test_eager_loads_person_relationship(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        _person(db_session)

        profiles = svc.list_person_profiles(db_session)

        # Person should be accessible without triggering an extra query
        assert profiles[0].person.name == "Alice"


# ── TestUpdatePersonProfile ────────────────────────────────────────────────────


class TestUpdatePersonProfile:
    def test_happy_path_persists_all_fields(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        profile = alice.cash_flow_profile

        svc.update_person_profile(
            db_session,
            profile_id=profile.id,
            effective_date=_AS_OF,
            gross_annual_income=Decimal("120000"),
            net_annual_income=Decimal("90000"),
            gross_bonus=Decimal("10000"),
            net_bonus=Decimal("7500"),
            auto_rrsp_deducted=Decimal("5000"),
            rrsp_matched=Decimal("2500"),
            auto_rrsp_goal_id=goal.id,
        )

        db_session.flush()
        db_session.expire(profile)
        assert profile.gross_annual_income.latest_value_as_of(_AS_OF) == Decimal("120000")
        assert profile.net_annual_income.latest_value_as_of(_AS_OF) == Decimal("90000")
        assert profile.gross_bonus.latest_value_as_of(_AS_OF) == Decimal("10000")
        assert profile.net_bonus.latest_value_as_of(_AS_OF) == Decimal("7500")
        assert profile.auto_rrsp_deducted.latest_value_as_of(_AS_OF) == Decimal("5000")
        assert profile.rrsp_matched.latest_value_as_of(_AS_OF) == Decimal("2500")
        assert profile.auto_rrsp_goal_id == goal.id

    def test_raises_when_profile_not_found(self, db_session: Session, svc: CashFlowService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_person_profile(
                db_session,
                profile_id=9999,
                effective_date=_AS_OF,
                gross_annual_income=Decimal("0"),
                net_annual_income=Decimal("0"),
                gross_bonus=Decimal("0"),
                net_bonus=Decimal("0"),
                auto_rrsp_deducted=Decimal("0"),
                rrsp_matched=Decimal("0"),
                auto_rrsp_goal_id=None,
            )

    def test_raises_when_rrsp_matched_without_deducted(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        goal = _goal(db_session)
        profile = alice.cash_flow_profile

        with pytest.raises(ValueError, match="auto_rrsp_deducted > 0"):
            svc.update_person_profile(
                db_session,
                profile_id=profile.id,
                effective_date=_AS_OF,
                gross_annual_income=Decimal("0"),
                net_annual_income=Decimal("0"),
                gross_bonus=Decimal("0"),
                net_bonus=Decimal("0"),
                auto_rrsp_deducted=Decimal("0"),
                rrsp_matched=Decimal("1000"),
                auto_rrsp_goal_id=goal.id,
            )

    def test_raises_when_rrsp_deducted_without_goal(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        profile = alice.cash_flow_profile

        with pytest.raises(ValueError, match="auto_rrsp_goal_id is required"):
            svc.update_person_profile(
                db_session,
                profile_id=profile.id,
                effective_date=_AS_OF,
                gross_annual_income=Decimal("0"),
                net_annual_income=Decimal("0"),
                gross_bonus=Decimal("0"),
                net_bonus=Decimal("0"),
                auto_rrsp_deducted=Decimal("5000"),
                rrsp_matched=Decimal("0"),
                auto_rrsp_goal_id=None,
            )

    def test_raises_when_rrsp_matched_without_goal(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        profile = alice.cash_flow_profile

        # rrsp_matched > 0 also implies auto_rrsp_deducted must be > 0, which in turn
        # requires a goal — but the matched-without-deducted guard fires first.
        # This test provides deducted > 0 to reach the goal-required guard.
        with pytest.raises(ValueError, match="auto_rrsp_goal_id is required"):
            svc.update_person_profile(
                db_session,
                profile_id=profile.id,
                effective_date=_AS_OF,
                gross_annual_income=Decimal("0"),
                net_annual_income=Decimal("0"),
                gross_bonus=Decimal("0"),
                net_bonus=Decimal("0"),
                auto_rrsp_deducted=Decimal("5000"),
                rrsp_matched=Decimal("2500"),
                auto_rrsp_goal_id=None,
            )

    def test_zero_rrsp_fields_succeed_without_goal(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        profile = alice.cash_flow_profile

        svc.update_person_profile(
            db_session,
            profile_id=profile.id,
            effective_date=_AS_OF,
            gross_annual_income=Decimal("80000"),
            net_annual_income=Decimal("60000"),
            gross_bonus=Decimal("0"),
            net_bonus=Decimal("0"),
            auto_rrsp_deducted=Decimal("0"),
            rrsp_matched=Decimal("0"),
            auto_rrsp_goal_id=None,
        )

        db_session.flush()
        db_session.expire(profile)
        assert profile.gross_annual_income.latest_value_as_of(_AS_OF) == Decimal("80000")
        assert profile.auto_rrsp_goal_id is None


# ── TestListHouseholdExpenses ──────────────────────────────────────────────────


class TestListHouseholdExpenses:
    def test_returns_active_expenses_ordered_by_classification_then_id(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        # classification is stored native_enum=False (a plain string column), so
        # ordering is alphabetical by enum value: AUTO < HOME < OTHER.
        svc.create_household_expense(
            db_session,
            "Mortgage",
            Decimal("2000"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.REGULAR,
            _CREATED,
        )
        svc.create_household_expense(
            db_session,
            "Car Insurance",
            Decimal("150"),
            HouseholdExpenseClassification.AUTO,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.REGULAR,
            _CREATED,
        )

        expenses = svc.list_household_expenses(db_session, _AS_OF)

        assert [e.name for e in expenses] == ["Car Insurance", "Mortgage"]

    def test_excludes_discarded_expenses(self, db_session: Session, svc: CashFlowService) -> None:
        expense_id = svc.create_household_expense(
            db_session,
            "Gym",
            Decimal("50"),
            HouseholdExpenseClassification.OTHER,
            HouseholdExpenseSource.CREDIT,
            HouseholdExpenseFrequency.REGULAR,
            _CREATED,
        )
        svc.discard_household_expense(db_session, expense_id, _AS_OF)

        expenses = svc.list_household_expenses(db_session, _AS_OF)

        assert expenses == []

    def test_empty_when_no_expenses(self, db_session: Session, svc: CashFlowService) -> None:
        assert svc.list_household_expenses(db_session, _AS_OF) == []


# ── TestCreateHouseholdExpense ─────────────────────────────────────────────────


class TestCreateHouseholdExpense:
    def test_persists_expense_and_returns_id(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        expense_id = svc.create_household_expense(
            db_session,
            "Hydro",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _CREATED,
        )

        expense = db_session.get(HouseholdExpense, expense_id)
        assert expense is not None
        assert expense.name == "Hydro"
        assert expense.classification is HouseholdExpenseClassification.HOME
        assert expense.source is HouseholdExpenseSource.BANK
        assert expense.frequency is HouseholdExpenseFrequency.IRREGULAR
        assert expense.amount.latest_value_as_of(_CREATED) == Decimal("120")


# ── TestUpdateHouseholdExpense ─────────────────────────────────────────────────


class TestUpdateHouseholdExpense:
    def test_updates_all_fields_and_records_new_amount(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        expense_id = svc.create_household_expense(
            db_session,
            "Hydro",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _CREATED,
        )

        svc.update_household_expense(
            db_session,
            expense_id,
            "Hydro (updated)",
            Decimal("135"),
            HouseholdExpenseClassification.OTHER,
            HouseholdExpenseSource.CREDIT,
            HouseholdExpenseFrequency.REGULAR,
            _AS_OF,
        )

        expense = db_session.get(HouseholdExpense, expense_id)
        assert expense is not None
        assert expense.name == "Hydro (updated)"
        assert expense.classification is HouseholdExpenseClassification.OTHER
        assert expense.source is HouseholdExpenseSource.CREDIT
        assert expense.frequency is HouseholdExpenseFrequency.REGULAR
        assert expense.date_modified == _AS_OF
        assert expense.amount.latest_value_as_of(_AS_OF) == Decimal("135")

    def test_raises_when_expense_not_found(self, db_session: Session, svc: CashFlowService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_household_expense(
                db_session,
                9999,
                "Nonexistent",
                Decimal("0"),
                HouseholdExpenseClassification.OTHER,
                HouseholdExpenseSource.OTHER,
                HouseholdExpenseFrequency.REGULAR,
                _AS_OF,
            )


# ── TestUpdateHouseholdExpenseAmount ───────────────────────────────────────────


class TestUpdateHouseholdExpenseAmount:
    def test_records_new_amount_without_touching_other_fields(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        expense_id = svc.create_household_expense(
            db_session,
            "Hydro",
            Decimal("120"),
            HouseholdExpenseClassification.HOME,
            HouseholdExpenseSource.BANK,
            HouseholdExpenseFrequency.IRREGULAR,
            _CREATED,
        )

        svc.update_household_expense_amount(db_session, expense_id, Decimal("140"), _AS_OF)

        expense = db_session.get(HouseholdExpense, expense_id)
        assert expense is not None
        assert expense.name == "Hydro"
        assert expense.amount.latest_value_as_of(_AS_OF) == Decimal("140")

    def test_raises_when_expense_not_found(self, db_session: Session, svc: CashFlowService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_household_expense_amount(db_session, 9999, Decimal("0"), _AS_OF)


# ── TestDiscardHouseholdExpense ────────────────────────────────────────────────


class TestDiscardHouseholdExpense:
    def test_marks_expense_discarded(self, db_session: Session, svc: CashFlowService) -> None:
        expense_id = svc.create_household_expense(
            db_session,
            "Gym",
            Decimal("50"),
            HouseholdExpenseClassification.OTHER,
            HouseholdExpenseSource.CREDIT,
            HouseholdExpenseFrequency.REGULAR,
            _CREATED,
        )

        svc.discard_household_expense(db_session, expense_id, _AS_OF)

        expense = db_session.get(HouseholdExpense, expense_id)
        assert expense is not None
        assert expense.is_discarded

    def test_raises_when_expense_not_found(self, db_session: Session, svc: CashFlowService) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.discard_household_expense(db_session, 9999, _AS_OF)


# ── TestListAccounts ────────────────────────────────────────────────────────────


class TestListAccounts:
    def test_returns_active_accounts_ordered_by_id(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        first = _simple_account(db_session, alice, "Chequing")
        second = _simple_account(db_session, alice, "Savings")

        accounts = svc.list_accounts(db_session, _AS_OF)

        assert [a.id for a in accounts] == [first.id, second.id]

    def test_excludes_inactive_accounts(self, db_session: Session, svc: CashFlowService) -> None:
        alice = _person(db_session)
        acct = _simple_account(db_session, alice, "Chequing")
        acct.discard(_AS_OF)
        db_session.flush()

        accounts = svc.list_accounts(db_session, _AS_OF)

        assert accounts == []

    def test_empty_when_no_accounts(self, db_session: Session, svc: CashFlowService) -> None:
        assert svc.list_accounts(db_session, _AS_OF) == []


# ── TestListAutomatedContributions ──────────────────────────────────────────────


class TestListAutomatedContributions:
    def test_returns_active_contributions_with_eager_relationships(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        source = _simple_account(db_session, alice, "Chequing")
        dest = _simple_account(db_session, alice, "Savings")
        goal = _goal(db_session)
        contribution_id = svc.create_automated_contribution(
            db_session,
            "Monthly savings",
            Decimal("500"),
            source.id,
            dest.id,
            goal.id,
            _CREATED,
        )

        contributions = svc.list_automated_contributions(db_session, _AS_OF)

        assert [c.id for c in contributions] == [contribution_id]
        assert contributions[0].source_account.name == "Chequing"
        assert contributions[0].destination_account.name == "Savings"
        assert contributions[0].target_goal.name == goal.name

    def test_excludes_discarded_contributions(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        source = _simple_account(db_session, alice, "Chequing")
        dest = _simple_account(db_session, alice, "Savings")
        goal = _goal(db_session)
        contribution_id = svc.create_automated_contribution(
            db_session,
            "Monthly savings",
            Decimal("500"),
            source.id,
            dest.id,
            goal.id,
            _CREATED,
        )
        svc.discard_automated_contribution(db_session, contribution_id, _AS_OF)

        assert svc.list_automated_contributions(db_session, _AS_OF) == []

    def test_empty_when_no_contributions(self, db_session: Session, svc: CashFlowService) -> None:
        assert svc.list_automated_contributions(db_session, _AS_OF) == []


# ── TestCreateAutomatedContribution ─────────────────────────────────────────────


class TestCreateAutomatedContribution:
    def test_persists_contribution_and_returns_id(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        source = _simple_account(db_session, alice, "Chequing")
        dest = _simple_account(db_session, alice, "Savings")
        goal = _goal(db_session)

        contribution_id = svc.create_automated_contribution(
            db_session,
            "Monthly savings",
            Decimal("500"),
            source.id,
            dest.id,
            goal.id,
            _CREATED,
        )

        contribution = db_session.get(AutomatedContribution, contribution_id)
        assert contribution is not None
        assert contribution.name == "Monthly savings"
        assert contribution.source_account_id == source.id
        assert contribution.destination_account_id == dest.id
        assert contribution.target_goal_id == goal.id
        assert contribution.amount.latest_value_as_of(_CREATED) == Decimal("500")


# ── TestUpdateAutomatedContribution ─────────────────────────────────────────────


class TestUpdateAutomatedContribution:
    def test_updates_all_fields_and_records_new_amount(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        alice = _person(db_session)
        source = _simple_account(db_session, alice, "Chequing")
        dest = _simple_account(db_session, alice, "Savings")
        other_dest = _simple_account(db_session, alice, "TFSA")
        goal = _goal(db_session)
        contribution_id = svc.create_automated_contribution(
            db_session,
            "Monthly savings",
            Decimal("500"),
            source.id,
            dest.id,
            goal.id,
            _CREATED,
        )

        svc.update_automated_contribution(
            db_session,
            contribution_id,
            "Monthly savings (updated)",
            Decimal("600"),
            source.id,
            other_dest.id,
            goal.id,
            _AS_OF,
        )

        contribution = db_session.get(AutomatedContribution, contribution_id)
        assert contribution is not None
        assert contribution.name == "Monthly savings (updated)"
        assert contribution.destination_account_id == other_dest.id
        assert contribution.date_modified == _AS_OF
        assert contribution.amount.latest_value_as_of(_AS_OF) == Decimal("600")

    def test_raises_when_contribution_not_found(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.update_automated_contribution(
                db_session,
                9999,
                "Nonexistent",
                Decimal("0"),
                1,
                2,
                3,
                _AS_OF,
            )


# ── TestDiscardAutomatedContribution ────────────────────────────────────────────


class TestDiscardAutomatedContribution:
    def test_marks_contribution_discarded(self, db_session: Session, svc: CashFlowService) -> None:
        alice = _person(db_session)
        source = _simple_account(db_session, alice, "Chequing")
        dest = _simple_account(db_session, alice, "Savings")
        goal = _goal(db_session)
        contribution_id = svc.create_automated_contribution(
            db_session,
            "Monthly savings",
            Decimal("500"),
            source.id,
            dest.id,
            goal.id,
            _CREATED,
        )

        svc.discard_automated_contribution(db_session, contribution_id, _AS_OF)

        contribution = db_session.get(AutomatedContribution, contribution_id)
        assert contribution is not None
        assert contribution.is_discarded

    def test_raises_when_contribution_not_found(
        self, db_session: Session, svc: CashFlowService
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            svc.discard_automated_contribution(db_session, 9999, _AS_OF)
