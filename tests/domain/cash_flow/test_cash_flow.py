"""Tests for cash flow domain models."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from personal_finance.domain.balance_sheet import (
    AccountClassification,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.base import Base
from personal_finance.domain.cash_flow import (
    AutomatedContribution,
    HouseholdExpense,
    HouseholdExpenseClassification,
    HouseholdExpenseFrequency,
    HouseholdExpenseSource,
    PersonalCashFlowProfile,
)
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.goals import Goal, GoalBankPortionScalar, NoGoalValue
from personal_finance.domain.person import Person

# ── Fixtures ──────────────────────────────────────────────────────────────────


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


@pytest.fixture()
def goal(db_session: Session) -> Goal:
    bp_amount = EffectiveAmount()
    bp_amount.offer_value(date(2024, 1, 1), Decimal("0.00"))
    g = Goal(
        name="RRSP",
        date_created=date(2024, 1, 1),
        date_effective=date(2024, 1, 1),
        date_modified=date(2024, 1, 1),
        bank_portion=GoalBankPortionScalar(amount=bp_amount),
        goal_value=NoGoalValue(),
    )
    db_session.add(g)
    db_session.flush()
    return g


@pytest.fixture()
def simple_account(db_session: Session, person: Person) -> SimpleAccount:
    account = SimpleAccount(
        name="Chequing",
        date_created=date(2024, 1, 1),
        date_effective=date(2024, 1, 1),
        date_modified=date(2024, 1, 1),
        classification=AccountClassification.ASSET_CURRENT,
        owners=[person],
        type=SimpleAccountCategory.BANK,
    )
    db_session.add(account)
    db_session.flush()
    return account


def _profile(person: Person, auto_rrsp_goal: Goal | None = None) -> PersonalCashFlowProfile:
    return PersonalCashFlowProfile(
        person=person,
        date_modified=date(2024, 1, 1),
        auto_rrsp_goal=auto_rrsp_goal,
    )


# ── PersonalCashFlowProfile ───────────────────────────────────────────────────


class TestPersonalCashFlowProfile:
    def test_db_round_trip_without_rrsp_goal(self, db_session: Session, person: Person) -> None:
        profile = _profile(person)
        db_session.add(profile)
        db_session.flush()

        db_session.expire(profile)
        assert profile.person_id == person.id
        assert profile.auto_rrsp_goal_id is None
        assert profile.auto_rrsp_goal is None

    def test_db_round_trip_with_rrsp_goal(
        self, db_session: Session, person: Person, goal: Goal
    ) -> None:
        profile = _profile(person, auto_rrsp_goal=goal)
        db_session.add(profile)
        db_session.flush()

        db_session.expire(profile)
        assert profile.auto_rrsp_goal_id == goal.id
        assert profile.auto_rrsp_goal.name == "RRSP"

    def test_money_timelines_are_independent(self, db_session: Session, person: Person) -> None:
        profile = _profile(person)
        db_session.add(profile)
        db_session.flush()

        assert profile.gross_annual_income_id != profile.net_annual_income_id
        assert profile.gross_bonus_id != profile.net_bonus_id
        assert profile.auto_rrsp_deducted_id != profile.rrsp_matched_id

    def test_money_timeline_values(self, db_session: Session, person: Person) -> None:
        profile = _profile(person)
        profile.gross_annual_income.offer_value(date(2024, 1, 1), Decimal("100000.00"))
        profile.net_annual_income.offer_value(date(2024, 1, 1), Decimal("75000.00"))
        db_session.add(profile)
        db_session.flush()

        db_session.expire_all()
        assert profile.gross_annual_income.latest_value_as_of(date(2024, 6, 1)) == Decimal(
            "100000.00"
        )
        assert profile.net_annual_income.latest_value_as_of(date(2024, 6, 1)) == Decimal("75000.00")


# ── HouseholdExpense ──────────────────────────────────────────────────────────


def _expense(
    date_created: date,
    date_discarded: date | None = None,
    classification: HouseholdExpenseClassification = HouseholdExpenseClassification.HOME,
    source: HouseholdExpenseSource = HouseholdExpenseSource.BANK,
    frequency: HouseholdExpenseFrequency = HouseholdExpenseFrequency.REGULAR,
) -> HouseholdExpense:
    return HouseholdExpense(
        name="Mortgage",
        date_created=date_created,
        date_effective=date_created,
        date_modified=date_created,
        date_discarded=date_discarded,
        classification=classification,
        source=source,
        frequency=frequency,
    )


class TestHouseholdExpenseIsActive:
    def test_active_when_created_on_query_date(self) -> None:
        e = _expense(date(2024, 1, 1))
        assert e.is_active(date(2024, 1, 1)) is True

    def test_inactive_when_created_after_query_date(self) -> None:
        e = _expense(date(2024, 6, 1))
        assert e.is_active(date(2024, 1, 1)) is False

    def test_active_indefinitely_when_not_discarded(self) -> None:
        e = _expense(date(2020, 1, 1))
        assert e.is_active(date(2099, 12, 31)) is True

    def test_inactive_on_discard_date(self) -> None:
        e = _expense(date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert e.is_active(date(2024, 6, 1)) is False

    def test_active_one_day_before_discard(self) -> None:
        e = _expense(date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert e.is_active(date(2024, 5, 31)) is True

    def test_inactive_after_discard(self) -> None:
        e = _expense(date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert e.is_active(date(2024, 12, 31)) is False


class TestHouseholdExpenseDb:
    def test_db_round_trip(self, db_session: Session) -> None:
        e = _expense(
            date(2024, 1, 1),
            classification=HouseholdExpenseClassification.AUTO,
            source=HouseholdExpenseSource.CREDIT,
            frequency=HouseholdExpenseFrequency.IRREGULAR,
        )
        db_session.add(e)
        db_session.flush()

        db_session.expire(e)
        assert e.name == "Mortgage"
        assert e.classification == HouseholdExpenseClassification.AUTO
        assert e.source == HouseholdExpenseSource.CREDIT
        assert e.frequency == HouseholdExpenseFrequency.IRREGULAR
        assert e.amount_id is not None

    def test_amount_timeline(self, db_session: Session) -> None:
        e = _expense(date(2024, 1, 1))
        e.amount.offer_value(date(2024, 1, 1), Decimal("2500.00"))
        db_session.add(e)
        db_session.flush()

        db_session.expire_all()
        assert e.amount.latest_value_as_of(date(2024, 6, 1)) == Decimal("2500.00")

    def test_all_classifications_persist(self, db_session: Session) -> None:
        for cls in HouseholdExpenseClassification:
            e = HouseholdExpense(
                name=cls.value,
                date_created=date(2024, 1, 1),
                date_effective=date(2024, 1, 1),
                date_modified=date(2024, 1, 1),
                classification=cls,
                source=HouseholdExpenseSource.BANK,
                frequency=HouseholdExpenseFrequency.REGULAR,
            )
            db_session.add(e)
        db_session.flush()

    def test_all_sources_persist(self, db_session: Session) -> None:
        for src in HouseholdExpenseSource:
            e = HouseholdExpense(
                name=src.value,
                date_created=date(2024, 1, 1),
                date_effective=date(2024, 1, 1),
                date_modified=date(2024, 1, 1),
                classification=HouseholdExpenseClassification.HOME,
                source=src,
                frequency=HouseholdExpenseFrequency.REGULAR,
            )
            db_session.add(e)
        db_session.flush()

    def test_all_frequencies_persist(self, db_session: Session) -> None:
        for freq in HouseholdExpenseFrequency:
            e = HouseholdExpense(
                name=freq.value,
                date_created=date(2024, 1, 1),
                date_effective=date(2024, 1, 1),
                date_modified=date(2024, 1, 1),
                classification=HouseholdExpenseClassification.HOME,
                source=HouseholdExpenseSource.BANK,
                frequency=freq,
            )
            db_session.add(e)
        db_session.flush()


# ── AutomatedContribution ─────────────────────────────────────────────────────


def _contribution(
    source: SimpleAccount,
    destination: SimpleAccount,
    goal: Goal,
    date_created: date,
    date_discarded: date | None = None,
) -> AutomatedContribution:
    return AutomatedContribution(
        name="RRSP Auto-Transfer",
        date_created=date_created,
        date_effective=date_created,
        date_modified=date_created,
        date_discarded=date_discarded,
        source_account=source,
        destination_account=destination,
        target_goal=goal,
    )


class TestAutomatedContributionIsActive:
    def test_active_when_created_on_query_date(
        self,
        db_session: Session,
        person: Person,
        simple_account: SimpleAccount,
        goal: Goal,
    ) -> None:
        c = _contribution(simple_account, simple_account, goal, date(2024, 1, 1))
        assert c.is_active(date(2024, 1, 1)) is True

    def test_inactive_when_created_after_query_date(
        self,
        db_session: Session,
        person: Person,
        simple_account: SimpleAccount,
        goal: Goal,
    ) -> None:
        c = _contribution(simple_account, simple_account, goal, date(2024, 6, 1))
        assert c.is_active(date(2024, 1, 1)) is False

    def test_inactive_on_discard_date(
        self,
        db_session: Session,
        person: Person,
        simple_account: SimpleAccount,
        goal: Goal,
    ) -> None:
        c = _contribution(
            simple_account, simple_account, goal, date(2024, 1, 1), date_discarded=date(2024, 6, 1)
        )
        assert c.is_active(date(2024, 6, 1)) is False

    def test_active_one_day_before_discard(
        self,
        db_session: Session,
        person: Person,
        simple_account: SimpleAccount,
        goal: Goal,
    ) -> None:
        c = _contribution(
            simple_account, simple_account, goal, date(2024, 1, 1), date_discarded=date(2024, 6, 1)
        )
        assert c.is_active(date(2024, 5, 31)) is True


class TestAutomatedContributionDb:
    def test_db_round_trip(
        self,
        db_session: Session,
        person: Person,
        simple_account: SimpleAccount,
        goal: Goal,
    ) -> None:
        destination = SimpleAccount(
            name="RRSP Cash",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            type=SimpleAccountCategory.BANK,
        )
        db_session.add(destination)
        db_session.flush()

        c = _contribution(simple_account, destination, goal, date(2024, 1, 1))
        db_session.add(c)
        db_session.flush()

        db_session.expire(c)
        assert c.name == "RRSP Auto-Transfer"
        assert c.source_account_id == simple_account.id
        assert c.destination_account_id == destination.id
        assert c.target_goal_id == goal.id
        assert c.amount_id is not None

    def test_amount_timeline(
        self,
        db_session: Session,
        person: Person,
        simple_account: SimpleAccount,
        goal: Goal,
    ) -> None:
        c = _contribution(simple_account, simple_account, goal, date(2024, 1, 1))
        c.amount.offer_value(date(2024, 1, 1), Decimal("500.00"))
        db_session.add(c)
        db_session.flush()

        db_session.expire_all()
        assert c.amount.latest_value_as_of(date(2024, 6, 1)) == Decimal("500.00")

    def test_distinct_source_and_destination_accounts(
        self,
        db_session: Session,
        person: Person,
        simple_account: SimpleAccount,
        goal: Goal,
    ) -> None:
        destination = SimpleAccount(
            name="Investment Account",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            type=SimpleAccountCategory.BANK,
        )
        db_session.add(destination)
        db_session.flush()

        c = _contribution(simple_account, destination, goal, date(2024, 1, 1))
        db_session.add(c)
        db_session.flush()

        assert c.source_account_id != c.destination_account_id
