"""Unit tests for GeneralService.get_amount_left_to_invest (GEN-OP-1)."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import personal_finance.domain.balance_sheet  # noqa: F401 — registers ORM models
import personal_finance.domain.goals  # noqa: F401
from personal_finance.core.interfaces import QuoteService, SecuritySearchResult
from personal_finance.domain.balance_sheet.account import (
    AccountClassification,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.base import Base
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.goals.goal import (
    Goal,
    GoalBankPortionAutoFill,
    GoalBankPortionScalar,
    NoGoalValue,
)
from personal_finance.domain.person import Person
from personal_finance.service.core.balance_sheet_service import BalanceSheetService
from personal_finance.service.core.general_service import GeneralService
from personal_finance.service.core.goal_service import GoalService

_AS_OF = date(2026, 5, 1)
_CUSHION = Decimal("2000.00")


class _NullQuoteService(QuoteService):
    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:  # pragma: no cover
        return Decimal("0")

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:  # pragma: no cover
        return []


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
def svc() -> GeneralService:
    balance_sheet = BalanceSheetService(_NullQuoteService())
    goals = GoalService(balance_sheet)
    return GeneralService(balance_sheet, goals, _CUSHION)


def _bank_account(
    session: Session,
    person: Person,
    balance: Decimal,
    active_from: date = date(2024, 1, 1),
    classification: AccountClassification = AccountClassification.ASSET_CURRENT,
) -> SimpleAccount:
    ea = EffectiveAmount()
    ea.offer_value(active_from, balance)
    acct = SimpleAccount(
        name="Bank",
        date_created=active_from,
        date_effective=active_from,
        date_modified=active_from,
        classification=classification,
        type=SimpleAccountCategory.BANK,
        owners=[person],
        balance=ea,
    )
    session.add(acct)
    session.flush()
    return acct


def _liability_account(
    session: Session,
    person: Person,
    balance: Decimal,
    active_from: date = date(2024, 1, 1),
) -> SimpleAccount:
    ea = EffectiveAmount()
    ea.offer_value(active_from, balance)
    acct = SimpleAccount(
        name="Credit Card",
        date_created=active_from,
        date_effective=active_from,
        date_modified=active_from,
        classification=AccountClassification.LIABILITY_CURRENT,
        type=SimpleAccountCategory.RECEIVABLE_PAYABLE,
        owners=[person],
        balance=ea,
    )
    session.add(acct)
    session.flush()
    return acct


def _goal_with_scalar_bank_claim(
    session: Session,
    claim: Decimal,
) -> Goal:
    portion = GoalBankPortionScalar()
    portion.amount.offer_value(date(2024, 1, 1), claim)  # type: ignore[union-attr]
    goal = Goal(
        name="Test Goal",
        date_created=date(2024, 1, 1),
        date_effective=date(2024, 1, 1),
        date_modified=date(2024, 1, 1),
        goal_value=NoGoalValue(),
        bank_portion=portion,
    )
    session.add(goal)
    session.flush()
    return goal


class TestGetAmountLeftToInvest:
    async def test_all_zeros_returns_negative_cushion(
        self, db_session: Session, svc: GeneralService
    ) -> None:
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == -_CUSHION

    async def test_bank_balance_minus_cushion(
        self, db_session: Session, person: Person, svc: GeneralService
    ) -> None:
        _bank_account(db_session, person, Decimal("10000.00"))
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == Decimal("8000.00")

    async def test_current_liability_subtracted(
        self, db_session: Session, person: Person, svc: GeneralService
    ) -> None:
        _bank_account(db_session, person, Decimal("10000.00"))
        _liability_account(db_session, person, Decimal("1500.00"))
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == Decimal("6500.00")

    async def test_goal_bank_claim_subtracted(
        self, db_session: Session, person: Person, svc: GeneralService
    ) -> None:
        _bank_account(db_session, person, Decimal("10000.00"))
        _goal_with_scalar_bank_claim(db_session, Decimal("3000.00"))
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == Decimal("5000.00")

    async def test_discarded_bank_account_excluded(
        self, db_session: Session, person: Person, svc: GeneralService
    ) -> None:
        ea = EffectiveAmount()
        ea.offer_value(date(2024, 1, 1), Decimal("10000.00"))
        acct = SimpleAccount(
            name="Old Bank",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            date_discarded=date(2025, 1, 1),
            classification=AccountClassification.ASSET_CURRENT,
            type=SimpleAccountCategory.BANK,
            owners=[person],
            balance=ea,
        )
        db_session.add(acct)
        db_session.flush()
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == -_CUSHION

    async def test_long_term_liability_not_subtracted(
        self, db_session: Session, person: Person, svc: GeneralService
    ) -> None:
        _bank_account(db_session, person, Decimal("10000.00"))
        ea = EffectiveAmount()
        ea.offer_value(date(2024, 1, 1), Decimal("50000.00"))
        mortgage = SimpleAccount(
            name="Mortgage",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.LIABILITY_LONG_TERM,
            type=SimpleAccountCategory.RECEIVABLE_PAYABLE,
            owners=[person],
            balance=ea,
        )
        db_session.add(mortgage)
        db_session.flush()
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == Decimal("8000.00")

    async def test_discarded_goal_excluded(
        self, db_session: Session, person: Person, svc: GeneralService
    ) -> None:
        _bank_account(db_session, person, Decimal("10000.00"))
        portion = GoalBankPortionScalar()
        portion.amount.offer_value(date(2024, 1, 1), Decimal("3000.00"))  # type: ignore[union-attr]
        goal = Goal(
            name="Old Goal",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            date_discarded=date(2025, 1, 1),
            goal_value=NoGoalValue(),
            bank_portion=portion,
        )
        db_session.add(goal)
        db_session.flush()
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == Decimal("8000.00")

    async def test_auto_fill_goal_with_no_target_claims_zero(
        self, db_session: Session, person: Person, svc: GeneralService
    ) -> None:
        _bank_account(db_session, person, Decimal("10000.00"))
        goal = Goal(
            name="No Target Goal",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            goal_value=NoGoalValue(),
            bank_portion=GoalBankPortionAutoFill(),
        )
        db_session.add(goal)
        db_session.flush()
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == Decimal("8000.00")

    async def test_multiple_banks_and_liabilities_and_goals(
        self, db_session: Session, person: Person, svc: GeneralService
    ) -> None:
        _bank_account(db_session, person, Decimal("5000.00"))
        _bank_account(db_session, person, Decimal("3000.00"))
        _liability_account(db_session, person, Decimal("800.00"))
        _goal_with_scalar_bank_claim(db_session, Decimal("1000.00"))
        # 5000 + 3000 - 800 - 1000 - 2000
        assert await svc.get_amount_left_to_invest(db_session, _AS_OF) == Decimal("4200.00")
