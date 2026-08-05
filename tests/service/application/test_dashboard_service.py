"""Tests for DashboardService."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

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
from personal_finance.domain.person import Person
from personal_finance.service.application.balance_sheet_app_service import BalanceSheetAppService
from personal_finance.service.application.dashboard_service import (
    DashboardService,
    DashboardSummary,
)
from personal_finance.service.core.balance_sheet_service import BalanceSheetService
from personal_finance.service.core.general_service import GeneralService
from personal_finance.service.core.goal_service import GoalService


class _NullQuoteService(QuoteService):
    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:  # pragma: no cover
        raise NotImplementedError

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:  # pragma: no cover
        return []


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    # StaticPool + check_same_thread=False: every Session opened against this
    # engine shares one physical connection, matching the app's real single
    # on-disk SQLite behaviour — required since DashboardService.get_summary
    # opens two independent sessions internally.
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
def person(db_session: Session) -> Person:
    p = Person(name="Alice")
    db_session.add(p)
    db_session.flush()
    return p


def _make_simple(
    session: Session,
    person: Person,
    name: str,
    classification: AccountClassification,
    category: SimpleAccountCategory,
    balance: Decimal,
    as_of: date = date(2024, 1, 1),
) -> SimpleAccount:
    ea = EffectiveAmount()
    ea.offer_value(as_of, balance)
    acct = SimpleAccount(
        name=name,
        date_created=as_of,
        date_effective=as_of,
        date_modified=as_of,
        classification=classification,
        owners=[person],
        type=category,
        balance=ea,
    )
    session.add(acct)
    session.flush()
    return acct


AS_OF = date(2024, 6, 1)


def _svc(
    session_factory: sessionmaker[Session], cushion: Decimal = Decimal("0")
) -> DashboardService:
    balance_sheet_svc = BalanceSheetService(_NullQuoteService())
    goal_svc = GoalService(balance_sheet_svc)
    general_svc = GeneralService(balance_sheet_svc, goal_svc, cushion)
    balance_sheet_app_svc = BalanceSheetAppService(balance_sheet_svc, session_factory)
    return DashboardService(general_svc, balance_sheet_app_svc, session_factory)


# ── get_amount_left_to_invest ────────────────────────────────────────────────


class TestGetAmountLeftToInvest:
    async def test_delegates_to_general_service(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        _make_simple(
            db_session,
            person,
            "Bank",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("1000"),
        )
        amount_left = await _svc(session_factory).get_amount_left_to_invest(AS_OF)
        assert amount_left == Decimal("1000")

    async def test_applies_cushion(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        _make_simple(
            db_session,
            person,
            "Bank",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("1000"),
        )
        amount_left = await _svc(session_factory, cushion=Decimal("200")).get_amount_left_to_invest(
            AS_OF
        )
        assert amount_left == Decimal("800")

    async def test_empty_db_returns_negative_cushion(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        amount_left = await _svc(session_factory, cushion=Decimal("50")).get_amount_left_to_invest(
            AS_OF
        )
        assert amount_left == Decimal("-50")


# ── get_summary ───────────────────────────────────────────────────────────────


class TestGetSummary:
    async def test_empty_db_returns_zero_net_worth(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        summary = await _svc(session_factory).get_summary(AS_OF)
        assert isinstance(summary, DashboardSummary)
        assert summary.amount_left == Decimal("0")
        assert summary.current_net_worth == Decimal("0")
        assert summary.total_net_worth == Decimal("0")

    async def test_combines_amount_left_and_net_worth(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        _make_simple(
            db_session,
            person,
            "Bank",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("1000"),
        )
        _make_simple(
            db_session,
            person,
            "House",
            AccountClassification.ASSET_LONG_TERM,
            SimpleAccountCategory.REAL_ESTATE,
            Decimal("500000"),
        )
        summary = await _svc(session_factory).get_summary(AS_OF)
        assert summary.amount_left == Decimal("1000")
        assert summary.current_net_worth == Decimal("1000")
        assert summary.total_net_worth == Decimal("501000")

    async def test_does_not_duplicate_net_worth_calculation(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        """DashboardSummary's net worth figures must match BalanceSheetAppService's directly."""
        _make_simple(
            db_session,
            person,
            "Bank",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("2500"),
        )
        svc = _svc(session_factory)
        summary = await svc.get_summary(AS_OF)
        bs_summary = await BalanceSheetAppService(
            BalanceSheetService(_NullQuoteService()), session_factory
        ).get_summary(AS_OF)
        assert summary.current_net_worth == bs_summary.current_net_worth
        assert summary.total_net_worth == bs_summary.total_net_worth
