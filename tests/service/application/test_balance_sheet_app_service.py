"""Tests for BalanceSheetAppService."""

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
from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet.account import (
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.balance_sheet.holding import (
    ExactHolding,
    ListedSecurityHolding,
)
from personal_finance.domain.base import Base
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.person import Person
from personal_finance.service.application.balance_sheet_app_service import (
    AccountDetail,
    AllocationInput,
    BalanceSheetAppService,
    BalanceSheetSummary,
)
from personal_finance.service.core.balance_sheet_service import BalanceSheetService


class _NullQuoteService(QuoteService):
    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:  # pragma: no cover
        raise NotImplementedError

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:  # pragma: no cover
        return []


class _PricedQuoteService(QuoteService):
    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices

    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:
        return self._prices[symbol]

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        return []


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    # StaticPool + check_same_thread=False: every Session opened against this
    # engine (the test's db_session fixture, and every session the app service
    # opens internally via session_factory) shares one physical connection, so
    # they see each other's flushed-but-uncommitted data — mirroring how the
    # app itself always runs against one real on-disk SQLite file.
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


def _make_investment(
    session: Session,
    person: Person,
    name: str,
    classification: AccountClassification,
    cash_balance: Decimal = Decimal("0"),
    as_of: date = date(2024, 1, 1),
) -> InvestmentAccount:
    ea = EffectiveAmount()
    ea.offer_value(as_of, cash_balance)
    acct = InvestmentAccount(
        name=name,
        date_created=as_of,
        date_effective=as_of,
        date_modified=as_of,
        classification=classification,
        owners=[person],
        investment_registration=InvestmentRegistration.TFSA,
        cash_balance=ea,
    )
    session.add(acct)
    session.flush()
    return acct


AS_OF = date(2024, 6, 1)


def _svc(session_factory: sessionmaker[Session]) -> BalanceSheetAppService:
    return BalanceSheetAppService(BalanceSheetService(_NullQuoteService()), session_factory)


def _priced_svc(
    session_factory: sessionmaker[Session], prices: dict[str, Decimal]
) -> BalanceSheetAppService:
    return BalanceSheetAppService(BalanceSheetService(_PricedQuoteService(prices)), session_factory)


def _make_exact_holding(
    session: Session,
    account: InvestmentAccount,
    name: str,
    amount: Decimal,
    as_of: date = AS_OF,
) -> ExactHolding:
    ea = EffectiveAmount()
    ea.offer_value(as_of, amount)
    c = ExactHolding(
        investment_account=account,
        name=name,
        date_created=as_of,
        date_effective=as_of,
        date_modified=as_of,
        amount=ea,
    )
    session.add(c)
    session.flush()
    return c


def _make_listed_holding(
    session: Session,
    account: InvestmentAccount,
    name: str,
    symbol: str,
    quantity: Decimal,
    as_of: date = AS_OF,
) -> ListedSecurityHolding:
    ea = EffectiveAmount()
    ea.offer_value(as_of, quantity)
    c = ListedSecurityHolding(
        investment_account=account,
        name=name,
        symbol=symbol,
        date_created=as_of,
        date_effective=as_of,
        date_modified=as_of,
        quantity=ea,
    )
    session.add(c)
    session.flush()
    return c


def _make_asset_class(
    session: Session,
    name: str = "Equity",
    order: int = 1,
) -> AccountAssetClass:
    ac = AccountAssetClass(name=name, order_precedence=order, date_created=date(2024, 1, 1))
    session.add(ac)
    session.flush()
    return ac


# ── get_summary ───────────────────────────────────────────────────────────────


class TestGetSummary:
    async def test_empty_db_returns_zero_totals(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        summary: BalanceSheetSummary = await _svc(session_factory).get_summary(AS_OF)
        assert summary.current_assets.total == Decimal("0")
        assert summary.long_term_assets.total == Decimal("0")
        assert summary.current_liabilities.total == Decimal("0")
        assert summary.long_term_liabilities.total == Decimal("0")
        assert summary.current_net_worth == Decimal("0")
        assert summary.total_net_worth == Decimal("0")

    async def test_accounts_routed_to_correct_section(
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
        _make_simple(
            db_session,
            person,
            "Visa",
            AccountClassification.LIABILITY_CURRENT,
            SimpleAccountCategory.RECEIVABLE_PAYABLE,
            Decimal("500"),
        )
        _make_simple(
            db_session,
            person,
            "Mortgage",
            AccountClassification.LIABILITY_LONG_TERM,
            SimpleAccountCategory.REAL_ESTATE,
            Decimal("200000"),
        )
        summary = await _svc(session_factory).get_summary(AS_OF)
        assert len(summary.current_assets.accounts) == 1
        assert len(summary.long_term_assets.accounts) == 1
        assert len(summary.current_liabilities.accounts) == 1
        assert len(summary.long_term_liabilities.accounts) == 1

    async def test_current_net_worth_calculation(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        _make_simple(
            db_session,
            person,
            "Bank",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("5000"),
        )
        _make_simple(
            db_session,
            person,
            "Visa",
            AccountClassification.LIABILITY_CURRENT,
            SimpleAccountCategory.RECEIVABLE_PAYABLE,
            Decimal("1000"),
        )
        summary = await _svc(session_factory).get_summary(AS_OF)
        assert summary.current_net_worth == Decimal("4000")

    async def test_total_net_worth_calculation(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        _make_simple(
            db_session,
            person,
            "Bank",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("5000"),
        )
        _make_simple(
            db_session,
            person,
            "House",
            AccountClassification.ASSET_LONG_TERM,
            SimpleAccountCategory.REAL_ESTATE,
            Decimal("300000"),
        )
        _make_simple(
            db_session,
            person,
            "Mortgage",
            AccountClassification.LIABILITY_LONG_TERM,
            SimpleAccountCategory.REAL_ESTATE,
            Decimal("200000"),
        )
        summary = await _svc(session_factory).get_summary(AS_OF)
        assert summary.total_net_worth == Decimal("105000")

    async def test_investment_account_marked_correctly(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        _make_investment(
            db_session,
            person,
            "TFSA",
            AccountClassification.ASSET_LONG_TERM,
            cash_balance=Decimal("10000"),
        )
        summary = await _svc(session_factory).get_summary(AS_OF)
        assert len(summary.long_term_assets.accounts) == 1
        row = summary.long_term_assets.accounts[0]
        assert row.is_investment is True
        assert row.balance == Decimal("10000")

    async def test_investment_account_with_exact_holding(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(
            db_session,
            person,
            "TFSA",
            AccountClassification.ASSET_LONG_TERM,
            cash_balance=Decimal("1000"),
        )
        ea = EffectiveAmount()
        ea.offer_value(date(2024, 1, 1), Decimal("9000"))
        c = ExactHolding(
            name="GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=acct,
            amount=ea,
        )
        db_session.add(c)
        db_session.flush()
        summary = await _svc(session_factory).get_summary(AS_OF)
        row = summary.long_term_assets.accounts[0]
        assert row.balance == Decimal("10000")

    async def test_as_of_stored_in_summary(self, session_factory: sessionmaker[Session]) -> None:
        summary = await _svc(session_factory).get_summary(AS_OF)
        assert summary.as_of == AS_OF

    async def test_section_labels(self, session_factory: sessionmaker[Session]) -> None:
        summary = await _svc(session_factory).get_summary(AS_OF)
        assert summary.current_assets.label == "Current Assets"
        assert summary.long_term_assets.label == "Long-Term Assets"
        assert summary.current_liabilities.label == "Current Liabilities"
        assert summary.long_term_liabilities.label == "Long-Term Liabilities"


# ── get_account_detail ───────────────────────────────────────────────────────


class TestGetAccountDetail:
    def test_returns_detail_for_simple_account(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_simple(
            db_session,
            person,
            "Chequing",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("0"),
        )
        detail: AccountDetail = _svc(session_factory).get_account_detail(acct.id)
        assert detail.account_id == acct.id
        assert detail.name == "Chequing"
        assert detail.is_long_term is False
        assert detail.is_investment is False
        assert detail.simple_category == SimpleAccountCategory.BANK
        assert detail.investment_registration is None
        assert person.id in detail.owner_ids

    def test_returns_detail_for_investment_account(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        detail = _svc(session_factory).get_account_detail(acct.id)
        assert detail.is_long_term is True
        assert detail.is_investment is True
        assert detail.investment_registration == InvestmentRegistration.TFSA

    def test_raises_for_unknown_account(self, session_factory: sessionmaker[Session]) -> None:
        with pytest.raises(ValueError, match="not found"):
            _svc(session_factory).get_account_detail(99999)


# ── update_account_metadata ───────────────────────────────────────────────────


class TestUpdateAccountMetadata:
    def test_renames_simple_account(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_simple(
            db_session,
            person,
            "Old Name",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("100"),
        )
        _svc(session_factory).update_account_metadata(
            acct.id, "New Name", False, SimpleAccountCategory.BANK, None, [person.id]
        )
        db_session.expire(acct)
        assert acct.name == "New Name"

    def test_promotes_to_long_term_asset(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_simple(
            db_session,
            person,
            "House",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.REAL_ESTATE,
            Decimal("0"),
        )
        _svc(session_factory).update_account_metadata(
            acct.id, acct.name, True, SimpleAccountCategory.REAL_ESTATE, None, [person.id]
        )
        db_session.expire(acct)
        assert acct.classification == AccountClassification.ASSET_LONG_TERM

    def test_demotes_long_term_liability_to_current(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_simple(
            db_session,
            person,
            "Mortgage",
            AccountClassification.LIABILITY_LONG_TERM,
            SimpleAccountCategory.RECEIVABLE_PAYABLE,
            Decimal("0"),
        )
        _svc(session_factory).update_account_metadata(
            acct.id, acct.name, False, SimpleAccountCategory.RECEIVABLE_PAYABLE, None, [person.id]
        )
        db_session.expire(acct)
        assert acct.classification == AccountClassification.LIABILITY_CURRENT


# ── get_persons ──────────────────────────────────────────────────────────────


class TestGetPersons:
    def test_returns_person_options(
        self, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        result = _svc(session_factory).get_persons()
        assert any(p.id == person.id and p.name == person.name for p in result)


# ── create_account ────────────────────────────────────────────────────────────


class TestCreateAccount:
    def test_delegates_to_core(
        self, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        new_id = _svc(session_factory).create_account(
            name="Savings",
            classification=AccountClassification.ASSET_CURRENT,
            nature="simple",
            simple_category=SimpleAccountCategory.BANK,
            investment_registration=None,
            owner_ids=[person.id],
            as_of=AS_OF,
        )
        assert new_id is not None


# ── discard_account ───────────────────────────────────────────────────────────


class TestDiscardAccount:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_simple(
            db_session,
            person,
            "Old",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("0"),
        )
        _svc(session_factory).discard_account(acct.id, AS_OF)
        db_session.refresh(acct)
        assert acct.date_discarded == AS_OF


# ── update_simple_account_balance ─────────────────────────────────────────────


class TestUpdateSimpleAccountBalance:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_simple(
            db_session,
            person,
            "Bank",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            Decimal("100"),
        )
        _svc(session_factory).update_simple_account_balance(acct.id, AS_OF, Decimal("999"))
        # expire_all(), not expire(acct): the mutation happened via the app
        # service's own session/connection, so the nested EffectiveAmount
        # object already cached on db_session (from _make_simple) needs its
        # own reload too, not just acct's direct columns.
        db_session.expire_all()
        assert acct.get_balance(AS_OF) == Decimal("999")


# ── get_investment_details ────────────────────────────────────────────────────


class TestGetInvestmentDetails:
    async def test_returns_details_with_exact_holding(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        _make_exact_holding(db_session, acct, "GIC", Decimal("5000"))
        details = await _svc(session_factory).get_investment_details(acct.id, AS_OF)
        assert details.account_id == acct.id
        assert len(details.holdings) == 1
        row = details.holdings[0]
        assert row.holding_type == "exact"
        assert row.total == Decimal("5000")

    async def test_returns_details_with_listed_holding(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "TFSA", AccountClassification.ASSET_LONG_TERM)
        _make_listed_holding(db_session, acct, "Apple", "AAPL", Decimal("10"))
        details = await _priced_svc(
            session_factory, {"AAPL": Decimal("100")}
        ).get_investment_details(acct.id, AS_OF)
        assert len(details.holdings) == 1
        row = details.holdings[0]
        assert row.holding_type == "listed"
        assert row.symbol == "AAPL"
        assert row.total == Decimal("1000")


# ── update_uninvested_cash_balance ────────────────────────────────────────────


class TestUpdateUninvestedCashBalance:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        _svc(session_factory).update_uninvested_cash_balance(acct.id, AS_OF, Decimal("2000"))
        db_session.expire_all()
        assert acct.cash_balance.latest_value_as_of(AS_OF) == Decimal("2000")


# ── update_holding_name ───────────────────────────────────────────────────


class TestUpdateHoldingName:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        c = _make_exact_holding(db_session, acct, "GIC", Decimal("1000"))
        _svc(session_factory).update_holding_name(c.id, "Bond Fund")
        db_session.expire(c)
        assert c.name == "Bond Fund"


# ── discard_holding ───────────────────────────────────────────────────────


class TestDiscardHolding:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        c = _make_exact_holding(db_session, acct, "GIC", Decimal("1000"))
        _svc(session_factory).discard_holding(c.id, AS_OF)
        db_session.refresh(c)
        assert c.date_discarded == AS_OF


# ── update_holding_exact_amount ──────────────────────────────────────────


class TestUpdateHoldingExactAmount:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        c = _make_exact_holding(db_session, acct, "GIC", Decimal("1000"))
        _svc(session_factory).update_holding_exact_amount(c.id, AS_OF, Decimal("9999"))
        db_session.expire_all()
        assert c.get_value(AS_OF) == Decimal("9999")


# ── update_holding_listed_quantity ────────────────────────────────────────


class TestUpdateHoldingListedQuantity:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "TFSA", AccountClassification.ASSET_LONG_TERM)
        c = _make_listed_holding(db_session, acct, "Apple", "AAPL", Decimal("10"))
        _svc(session_factory).update_holding_listed_quantity(c.id, AS_OF, Decimal("25"))
        db_session.expire_all()
        assert c.quantity.latest_value_as_of(AS_OF) == Decimal("25")


# ── get_asset_classes ─────────────────────────────────────────────────────────


class TestGetAssetClasses:
    def test_returns_active_asset_classes(
        self, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        ac = _make_asset_class(db_session, "Equity", 1)
        result = _svc(session_factory).get_asset_classes(AS_OF)
        assert len(result) == 1
        assert result[0].id == ac.id
        assert result[0].name == "Equity"


# ── search_symbols ────────────────────────────────────────────────────────────


class TestSearchSymbols:
    async def test_delegates_to_core(self, session_factory: sessionmaker[Session]) -> None:
        result = await _svc(session_factory).search_symbols("AAPL")
        assert result == []


# ── get_unit_price ────────────────────────────────────────────────────────────


class TestGetUnitPrice:
    async def test_delegates_to_core(self, session_factory: sessionmaker[Session]) -> None:
        result = await _priced_svc(session_factory, {"AAPL": Decimal("150")}).get_unit_price(
            "AAPL", AS_OF
        )
        assert result == Decimal("150")


# ── add_holding ───────────────────────────────────────────────────────────


class TestAddHolding:
    def test_creates_listed_holding(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        ac = _make_asset_class(db_session)
        cid = _svc(session_factory).add_holding(
            account_id=acct.id,
            holding_type="listed",
            name="Apple",
            as_of=AS_OF,
            symbol="AAPL",
            initial_quantity=Decimal("10"),
            initial_amount=None,
            allocations=[AllocationInput(asset_class_id=ac.id, percent=Decimal("100"))],
        )
        assert db_session.get(ListedSecurityHolding, cid) is not None

    def test_creates_exact_holding(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        ac = _make_asset_class(db_session, "Fixed Income", 2)
        cid = _svc(session_factory).add_holding(
            account_id=acct.id,
            holding_type="exact",
            name="GIC",
            as_of=AS_OF,
            symbol=None,
            initial_quantity=None,
            initial_amount=Decimal("5000"),
            allocations=[AllocationInput(asset_class_id=ac.id, percent=Decimal("100"))],
        )
        assert db_session.get(ExactHolding, cid) is not None


# ── get_holding_allocations ───────────────────────────────────────────────


class TestGetHoldingAllocations:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        ac = _make_asset_class(db_session)
        cid = _svc(session_factory).add_holding(
            account_id=acct.id,
            holding_type="exact",
            name="GIC",
            as_of=AS_OF,
            symbol=None,
            initial_quantity=None,
            initial_amount=Decimal("1000"),
            allocations=[AllocationInput(asset_class_id=ac.id, percent=Decimal("100"))],
        )
        result = _svc(session_factory).get_holding_allocations(cid, AS_OF)
        assert result == {ac.id: Decimal("100")}


# ── update_holding_asset_allocation ───────────────────────────────────────


class TestUpdateHoldingAssetAllocation:
    def test_delegates_to_core(
        self, db_session: Session, session_factory: sessionmaker[Session], person: Person
    ) -> None:
        acct = _make_investment(db_session, person, "RRSP", AccountClassification.ASSET_LONG_TERM)
        ac1 = _make_asset_class(db_session, "Equity", 1)
        ac2 = _make_asset_class(db_session, "Fixed Income", 2)
        cid = _svc(session_factory).add_holding(
            account_id=acct.id,
            holding_type="exact",
            name="GIC",
            as_of=AS_OF,
            symbol=None,
            initial_quantity=None,
            initial_amount=Decimal("1000"),
            allocations=[AllocationInput(asset_class_id=ac1.id, percent=Decimal("100"))],
        )
        _svc(session_factory).update_holding_asset_allocation(
            cid, AS_OF, [AllocationInput(asset_class_id=ac2.id, percent=Decimal("100"))]
        )
        result = _svc(session_factory).get_holding_allocations(cid, AS_OF)
        assert result == {ac2.id: Decimal("100")}
