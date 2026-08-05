"""Tests for BalanceSheetService."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import personal_finance.domain.balance_sheet  # noqa: F401 — registers ORM models
import personal_finance.domain.goals  # noqa: F401
from personal_finance.core.interfaces import QuoteService, QuoteServiceError, SecuritySearchResult
from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet.account import (
    Account,
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
from personal_finance.service.core.balance_sheet_service import BalanceSheetService

# ── Mock quote service ────────────────────────────────────────────────────────


class _MockQuoteService(QuoteService):
    """Returns pre-configured prices or raises QuoteServiceError for configured symbols."""

    def __init__(
        self,
        prices: dict[str, Decimal],
        raise_for: set[str] | None = None,
        search_results: list[SecuritySearchResult] | None = None,
    ) -> None:
        self._prices = prices
        self._raise_for: set[str] = raise_for or set()
        self._search_results: list[SecuritySearchResult] = search_results or []
        self.calls: list[tuple[str, date]] = []

    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:
        self.calls.append((symbol, as_of))
        if symbol in self._raise_for:
            raise QuoteServiceError(f"Provider failed for {symbol!r}")
        return self._prices[symbol]

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        return self._search_results


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
def simple_account(db_session: Session, person: Person) -> SimpleAccount:
    balance = EffectiveAmount()
    balance.offer_value(date(2024, 1, 1), Decimal("10000"))
    account = SimpleAccount(
        name="Chequing",
        date_created=date(2024, 1, 1),
        date_effective=date(2024, 1, 1),
        date_modified=date(2024, 1, 1),
        classification=AccountClassification.ASSET_CURRENT,
        owners=[person],
        type=SimpleAccountCategory.BANK,
        balance=balance,
    )
    db_session.add(account)
    db_session.flush()
    return account


@pytest.fixture()
def investment_account(db_session: Session, person: Person) -> InvestmentAccount:
    account = InvestmentAccount(
        name="RRSP",
        date_created=date(2024, 1, 1),
        date_effective=date(2024, 1, 1),
        date_modified=date(2024, 1, 1),
        classification=AccountClassification.ASSET_LONG_TERM,
        owners=[person],
        investment_registration=InvestmentRegistration.RRSP,
    )
    db_session.add(account)
    db_session.flush()
    return account


AS_OF = date(2024, 6, 1)


# ── list_all_accounts — basic structure ───────────────────────────────────────


class TestListAllAccountsBasic:
    async def test_returns_all_persisted_accounts(
        self,
        db_session: Session,
        simple_account: SimpleAccount,
        investment_account: InvestmentAccount,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        accounts = await svc.list_all_accounts(db_session, AS_OF)
        ids = {a.id for a in accounts}
        assert simple_account.id in ids
        assert investment_account.id in ids

    async def test_no_quote_calls_when_no_investment_accounts(
        self,
        db_session: Session,
        simple_account: SimpleAccount,
    ) -> None:
        mock = _MockQuoteService({})
        svc = BalanceSheetService(mock)
        await svc.list_all_accounts(db_session, AS_OF)
        assert mock.calls == []

    async def test_no_quote_calls_for_simple_account(
        self,
        db_session: Session,
        simple_account: SimpleAccount,
        investment_account: InvestmentAccount,
    ) -> None:
        mock = _MockQuoteService({})
        svc = BalanceSheetService(mock)
        await svc.list_all_accounts(db_session, AS_OF)
        # investment_account has no holdings → no calls expected
        assert mock.calls == []


# ── list_all_accounts — listed security pricing ───────────────────────────────


def _qty(value: Decimal, effective: date = date(2024, 1, 1)) -> EffectiveAmount:
    """Return an EffectiveAmount with a single quantity entry."""
    ea = EffectiveAmount()
    ea.offer_value(effective, value)
    return ea


class TestListAllAccountsPricing:
    async def test_listed_security_is_priced(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=_qty(Decimal("10")),
        )
        db_session.add(holding)
        db_session.flush()

        mock = _MockQuoteService({"AAPL": Decimal("150.00")})
        svc = BalanceSheetService(mock)
        await svc.list_all_accounts(db_session, AS_OF)

        assert holding.get_value(AS_OF) == Decimal("1500.00")

    async def test_multiple_listed_securities_all_priced(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
    ) -> None:
        c1 = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=_qty(Decimal("5")),
        )
        c2 = ListedSecurityHolding(
            name="Vanguard",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="XEQT.TO",
            quantity=_qty(Decimal("100")),
        )
        db_session.add_all([c1, c2])
        db_session.flush()

        mock = _MockQuoteService({"AAPL": Decimal("200"), "XEQT.TO": Decimal("30")})
        svc = BalanceSheetService(mock)
        await svc.list_all_accounts(db_session, AS_OF)

        assert c1.get_value(AS_OF) == Decimal("1000")
        assert c2.get_value(AS_OF) == Decimal("3000")

    async def test_quote_service_called_with_correct_symbol_and_date(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=_qty(Decimal("1")),
        )
        db_session.add(holding)
        db_session.flush()

        mock = _MockQuoteService({"AAPL": Decimal("100")})
        svc = BalanceSheetService(mock)
        await svc.list_all_accounts(db_session, AS_OF)

        assert mock.calls == [("AAPL", AS_OF)]

    async def test_quote_service_error_propagates(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=_qty(Decimal("10")),
        )
        db_session.add(holding)
        db_session.flush()

        mock = _MockQuoteService({}, raise_for={"AAPL"})
        svc = BalanceSheetService(mock)
        with pytest.raises(QuoteServiceError):
            await svc.list_all_accounts(db_session, AS_OF)

    async def test_missing_quantity_raises_value_error(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            # no quantity entry — violates the invariant
        )
        db_session.add(holding)
        db_session.flush()

        mock = _MockQuoteService({"AAPL": Decimal("150")})
        svc = BalanceSheetService(mock)
        with pytest.raises(ValueError, match="no quantity entry"):
            await svc.list_all_accounts(db_session, AS_OF)

    async def test_inactive_holding_is_not_priced(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            date_discarded=date(2024, 3, 1),  # discarded before AS_OF
            investment_account=investment_account,
            symbol="AAPL",
        )
        db_session.add(holding)
        db_session.flush()

        mock = _MockQuoteService({"AAPL": Decimal("150")})
        svc = BalanceSheetService(mock)
        await svc.list_all_accounts(db_session, AS_OF)

        assert mock.calls == []
        assert holding.get_value(AS_OF) is None

    async def test_exact_holding_not_sent_to_quote_service(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
    ) -> None:
        exact = ExactHolding(
            name="GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
        )
        db_session.add(exact)
        db_session.flush()

        mock = _MockQuoteService({})
        svc = BalanceSheetService(mock)
        await svc.list_all_accounts(db_session, AS_OF)

        assert mock.calls == []


# ── get_total_bank_balance ────────────────────────────────────────────────────


def _simple_account(
    session: Session,
    person: Person,
    balance: Decimal,
    account_type: SimpleAccountCategory,
    classification: AccountClassification,
    date_created: date = date(2024, 1, 1),
    date_discarded: date | None = None,
) -> SimpleAccount:
    ea = EffectiveAmount()
    ea.offer_value(date_created, balance)
    acct = SimpleAccount(
        name="Account",
        date_created=date_created,
        date_effective=date_created,
        date_modified=date_created,
        date_discarded=date_discarded,
        classification=classification,
        type=account_type,
        owners=[person],
        balance=ea,
    )
    session.add(acct)
    session.flush()
    return acct


class TestGetTotalBankBalance:
    def test_no_accounts_returns_zero(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_bank_balance(db_session, AS_OF) == Decimal("0")

    def test_single_bank_account(self, db_session: Session, person: Person) -> None:
        _simple_account(
            db_session,
            person,
            Decimal("5000.00"),
            SimpleAccountCategory.BANK,
            AccountClassification.ASSET_CURRENT,
        )
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_bank_balance(db_session, AS_OF) == Decimal("5000.00")

    def test_multiple_bank_accounts_summed(self, db_session: Session, person: Person) -> None:
        _simple_account(
            db_session,
            person,
            Decimal("3000.00"),
            SimpleAccountCategory.BANK,
            AccountClassification.ASSET_CURRENT,
        )
        _simple_account(
            db_session,
            person,
            Decimal("7000.00"),
            SimpleAccountCategory.BANK,
            AccountClassification.ASSET_CURRENT,
        )
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_bank_balance(db_session, AS_OF) == Decimal("10000.00")

    def test_non_bank_account_excluded(self, db_session: Session, person: Person) -> None:
        _simple_account(
            db_session,
            person,
            Decimal("5000.00"),
            SimpleAccountCategory.RECEIVABLE_PAYABLE,
            AccountClassification.ASSET_CURRENT,
        )
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_bank_balance(db_session, AS_OF) == Decimal("0")

    def test_discarded_bank_account_excluded(self, db_session: Session, person: Person) -> None:
        _simple_account(
            db_session,
            person,
            Decimal("5000.00"),
            SimpleAccountCategory.BANK,
            AccountClassification.ASSET_CURRENT,
            date_discarded=date(2024, 3, 1),  # discarded before AS_OF
        )
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_bank_balance(db_session, AS_OF) == Decimal("0")


# ── get_total_current_liability_balance ───────────────────────────────────────


class TestGetTotalCurrentLiabilityBalance:
    def test_no_accounts_returns_zero(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_current_liability_balance(db_session, AS_OF) == Decimal("0")

    def test_single_current_liability(self, db_session: Session, person: Person) -> None:
        _simple_account(
            db_session,
            person,
            Decimal("1500.00"),
            SimpleAccountCategory.RECEIVABLE_PAYABLE,
            AccountClassification.LIABILITY_CURRENT,
        )
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_current_liability_balance(db_session, AS_OF) == Decimal("1500.00")

    def test_long_term_liability_excluded(self, db_session: Session, person: Person) -> None:
        _simple_account(
            db_session,
            person,
            Decimal("50000.00"),
            SimpleAccountCategory.RECEIVABLE_PAYABLE,
            AccountClassification.LIABILITY_LONG_TERM,
        )
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_current_liability_balance(db_session, AS_OF) == Decimal("0")

    def test_discarded_liability_excluded(self, db_session: Session, person: Person) -> None:
        _simple_account(
            db_session,
            person,
            Decimal("1500.00"),
            SimpleAccountCategory.RECEIVABLE_PAYABLE,
            AccountClassification.LIABILITY_CURRENT,
            date_discarded=date(2024, 3, 1),  # discarded before AS_OF
        )
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_total_current_liability_balance(db_session, AS_OF) == Decimal("0")


# ── get_account_detail ───────────────────────────────────────────────────────


class TestGetAccountDetail:
    def test_returns_simple_account(
        self, db_session: Session, simple_account: SimpleAccount
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        account = svc.get_account_detail(db_session, simple_account.id)
        assert account.id == simple_account.id
        assert isinstance(account, SimpleAccount)

    def test_returns_investment_account(
        self, db_session: Session, investment_account: InvestmentAccount
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        account = svc.get_account_detail(db_session, investment_account.id)
        assert account.id == investment_account.id
        assert isinstance(account, InvestmentAccount)

    def test_raises_for_unknown_account(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.get_account_detail(db_session, 99999)


# ── update_account_metadata ───────────────────────────────────────────────────


class TestUpdateAccountMetadata:
    def test_renames_account(
        self, db_session: Session, simple_account: SimpleAccount, person: Person
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_account_metadata(
            db_session,
            simple_account.id,
            "Savings",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            None,
            [person.id],
        )
        db_session.flush()
        db_session.expire(simple_account)
        assert simple_account.name == "Savings"

    def test_updates_classification(
        self, db_session: Session, simple_account: SimpleAccount, person: Person
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_account_metadata(
            db_session,
            simple_account.id,
            simple_account.name,
            AccountClassification.ASSET_LONG_TERM,
            SimpleAccountCategory.REAL_ESTATE,
            None,
            [person.id],
        )
        db_session.flush()
        db_session.expire(simple_account)
        assert simple_account.classification == AccountClassification.ASSET_LONG_TERM

    def test_updates_simple_category(
        self, db_session: Session, simple_account: SimpleAccount, person: Person
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_account_metadata(
            db_session,
            simple_account.id,
            simple_account.name,
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.OTHER,
            None,
            [person.id],
        )
        db_session.flush()
        db_session.expire(simple_account)
        assert simple_account.type == SimpleAccountCategory.OTHER

    def test_updates_investment_registration(
        self, db_session: Session, investment_account: InvestmentAccount, person: Person
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_account_metadata(
            db_session,
            investment_account.id,
            investment_account.name,
            AccountClassification.ASSET_LONG_TERM,
            None,
            InvestmentRegistration.TFSA,
            [person.id],
        )
        db_session.flush()
        db_session.expire(investment_account)
        assert investment_account.investment_registration == InvestmentRegistration.TFSA

    def test_replaces_owners(self, db_session: Session, simple_account: SimpleAccount) -> None:
        new_person = Person(name="Bob")
        db_session.add(new_person)
        db_session.flush()
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_account_metadata(
            db_session,
            simple_account.id,
            simple_account.name,
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            None,
            [new_person.id],
        )
        db_session.flush()
        db_session.expire(simple_account)
        assert [o.id for o in simple_account.owners] == [new_person.id]

    def test_updates_date_modified(
        self, db_session: Session, simple_account: SimpleAccount, person: Person
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_account_metadata(
            db_session,
            simple_account.id,
            "Savings",
            AccountClassification.ASSET_CURRENT,
            SimpleAccountCategory.BANK,
            None,
            [person.id],
        )
        db_session.flush()
        db_session.expire(simple_account)
        assert simple_account.date_modified == date.today()

    def test_raises_for_unknown_account(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.update_account_metadata(
                db_session,
                99999,
                "Ghost",
                AccountClassification.ASSET_CURRENT,
                SimpleAccountCategory.BANK,
                None,
                [1],
            )

    def test_raises_for_empty_owner_ids(
        self, db_session: Session, simple_account: SimpleAccount
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="At least one"):
            svc.update_account_metadata(
                db_session,
                simple_account.id,
                "Ghost",
                AccountClassification.ASSET_CURRENT,
                SimpleAccountCategory.BANK,
                None,
                [],
            )

    def test_raises_for_unknown_owner(
        self, db_session: Session, simple_account: SimpleAccount
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.update_account_metadata(
                db_session,
                simple_account.id,
                "Ghost",
                AccountClassification.ASSET_CURRENT,
                SimpleAccountCategory.BANK,
                None,
                [99999],
            )


# ── list_persons ─────────────────────────────────────────────────────────────


class TestListPersons:
    def test_returns_persons_when_present(self, db_session: Session, person: Person) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        result = svc.list_persons(db_session)
        assert any(p.id == person.id for p in result)

    def test_returns_empty_when_no_persons(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.list_persons(db_session) == []


# ── create_account ────────────────────────────────────────────────────────────


class TestCreateAccount:
    def test_creates_simple_account(self, db_session: Session, person: Person) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        new_id = svc.create_account(
            db_session,
            name="Chequing",
            classification=AccountClassification.ASSET_CURRENT,
            nature="simple",
            simple_category=SimpleAccountCategory.BANK,
            investment_registration=None,
            owner_ids=[person.id],
            as_of=date(2024, 1, 1),
        )
        account = db_session.get(SimpleAccount, new_id)
        assert account is not None
        assert account.name == "Chequing"
        assert account.classification == AccountClassification.ASSET_CURRENT
        assert account.type == SimpleAccountCategory.BANK
        assert person in account.owners

    def test_creates_investment_account(self, db_session: Session, person: Person) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        new_id = svc.create_account(
            db_session,
            name="My TFSA",
            classification=AccountClassification.ASSET_LONG_TERM,
            nature="investment",
            simple_category=None,
            investment_registration=InvestmentRegistration.TFSA,
            owner_ids=[person.id],
            as_of=date(2024, 1, 1),
        )
        account = db_session.get(InvestmentAccount, new_id)
        assert account is not None
        assert account.name == "My TFSA"
        assert account.classification == AccountClassification.ASSET_LONG_TERM
        assert account.investment_registration == InvestmentRegistration.TFSA

    def test_creates_liability_account(self, db_session: Session, person: Person) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        new_id = svc.create_account(
            db_session,
            name="Visa",
            classification=AccountClassification.LIABILITY_CURRENT,
            nature="simple",
            simple_category=SimpleAccountCategory.RECEIVABLE_PAYABLE,
            investment_registration=None,
            owner_ids=[person.id],
            as_of=date(2024, 1, 1),
        )
        account = db_session.get(SimpleAccount, new_id)
        assert account is not None
        assert account.classification == AccountClassification.LIABILITY_CURRENT

    def test_raises_for_empty_owner_ids(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="At least one"):
            svc.create_account(
                db_session,
                name="Ghost",
                classification=AccountClassification.ASSET_CURRENT,
                nature="simple",
                simple_category=SimpleAccountCategory.BANK,
                investment_registration=None,
                owner_ids=[],
                as_of=date(2024, 1, 1),
            )

    def test_raises_for_unknown_owner(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.create_account(
                db_session,
                name="Ghost",
                classification=AccountClassification.ASSET_CURRENT,
                nature="simple",
                simple_category=SimpleAccountCategory.BANK,
                investment_registration=None,
                owner_ids=[99999],
                as_of=date(2024, 1, 1),
            )

    def test_raises_when_simple_category_missing(self, db_session: Session, person: Person) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="simple_category"):
            svc.create_account(
                db_session,
                name="Whoops",
                classification=AccountClassification.ASSET_CURRENT,
                nature="simple",
                simple_category=None,
                investment_registration=None,
                owner_ids=[person.id],
                as_of=date(2024, 1, 1),
            )

    def test_raises_when_registration_missing(self, db_session: Session, person: Person) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="investment_registration"):
            svc.create_account(
                db_session,
                name="Whoops",
                classification=AccountClassification.ASSET_LONG_TERM,
                nature="investment",
                simple_category=None,
                investment_registration=None,
                owner_ids=[person.id],
                as_of=date(2024, 1, 1),
            )

    def test_new_account_appears_in_list(self, db_session: Session, person: Person) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.create_account(
            db_session,
            name="Savings",
            classification=AccountClassification.ASSET_CURRENT,
            nature="simple",
            simple_category=SimpleAccountCategory.BANK,
            investment_registration=None,
            owner_ids=[person.id],
            as_of=date(2024, 1, 1),
        )
        accounts = db_session.query(Account).all()
        assert any(a.name == "Savings" for a in accounts)


# ── update_simple_account_balance ─────────────────────────────────────────────


class TestUpdateSimpleAccountBalance:
    def test_appends_new_balance_entry(
        self, db_session: Session, simple_account: SimpleAccount
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        new_date = date(2024, 7, 1)
        svc.update_simple_account_balance(
            db_session, simple_account.id, new_date, Decimal("99999.00")
        )
        db_session.expire(simple_account)
        assert simple_account.get_balance(new_date) == Decimal("99999.00")

    def test_original_balance_preserved_before_new_date(
        self, db_session: Session, simple_account: SimpleAccount
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_simple_account_balance(
            db_session, simple_account.id, date(2024, 7, 1), Decimal("99999.00")
        )
        db_session.expire(simple_account)
        # Original balance was seeded at 2024-01-01; querying before the new entry
        assert simple_account.get_balance(date(2024, 6, 30)) == Decimal("10000")

    def test_raises_for_unknown_account(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.update_simple_account_balance(db_session, 99999, AS_OF, Decimal("0"))


class TestDiscardAccount:
    def test_sets_date_discarded(
        self,
        db_session: Session,
        simple_account: SimpleAccount,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        assert simple_account.date_discarded is None
        svc.discard_account(db_session, simple_account.id, date(2024, 6, 1))
        db_session.flush()
        db_session.refresh(simple_account)
        assert simple_account.date_discarded == date(2024, 6, 1)

    async def test_discarded_account_absent_from_list(
        self,
        db_session: Session,
        simple_account: SimpleAccount,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.discard_account(db_session, simple_account.id, AS_OF)
        accounts = await svc.list_all_accounts(db_session, AS_OF)
        assert simple_account.id not in {a.id for a in accounts}

    def test_raises_for_unknown_account(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.discard_account(db_session, 99999, AS_OF)

    def test_raises_if_already_discarded(
        self,
        db_session: Session,
        simple_account: SimpleAccount,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.discard_account(db_session, simple_account.id, date(2024, 6, 1))
        with pytest.raises(ValueError, match="already discarded"):
            svc.discard_account(db_session, simple_account.id, date(2024, 6, 1))


# ── Additional fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def asset_class(db_session: Session) -> AccountAssetClass:
    ac = AccountAssetClass(name="Equity", order_precedence=1, date_created=date(2024, 1, 1))
    db_session.add(ac)
    db_session.flush()
    return ac


@pytest.fixture()
def exact_holding(db_session: Session, investment_account: InvestmentAccount) -> ExactHolding:
    ea = EffectiveAmount()
    ea.offer_value(AS_OF, Decimal("5000"))
    c = ExactHolding(
        investment_account_id=investment_account.id,
        name="GIC",
        date_created=AS_OF,
        date_effective=AS_OF,
        date_modified=AS_OF,
        amount=ea,
    )
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture()
def listed_holding(
    db_session: Session, investment_account: InvestmentAccount
) -> ListedSecurityHolding:
    c = ListedSecurityHolding(
        investment_account_id=investment_account.id,
        name="Apple",
        symbol="AAPL",
        date_created=AS_OF,
        date_effective=AS_OF,
        date_modified=AS_OF,
        quantity=_qty(Decimal("10")),
    )
    db_session.add(c)
    db_session.flush()
    return c


# ── get_investment_account_details ────────────────────────────────────────────


class TestGetInvestmentAccountDetails:
    async def test_returns_account(
        self, db_session: Session, investment_account: InvestmentAccount
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        result = await svc.get_investment_account_details(db_session, investment_account.id, AS_OF)
        assert result.id == investment_account.id

    async def test_raises_for_unknown_account(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            await svc.get_investment_account_details(db_session, 99999, AS_OF)


# ── update_uninvested_cash_balance ────────────────────────────────────────────


class TestUpdateUninvestedCashBalance:
    def test_appends_new_entry(
        self, db_session: Session, investment_account: InvestmentAccount
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_uninvested_cash_balance(
            db_session, investment_account.id, AS_OF, Decimal("2500")
        )
        db_session.expire(investment_account)
        assert investment_account.cash_balance.latest_value_as_of(AS_OF) == Decimal("2500")

    def test_raises_for_unknown_account(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.update_uninvested_cash_balance(db_session, 99999, AS_OF, Decimal("0"))


# ── update_holding_name ───────────────────────────────────────────────────


class TestUpdateHoldingName:
    def test_renames_holding(self, db_session: Session, exact_holding: ExactHolding) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_holding_name(db_session, exact_holding.id, "Bond Fund")
        db_session.flush()
        db_session.expire(exact_holding)
        assert exact_holding.name == "Bond Fund"

    def test_raises_for_unknown_holding(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.update_holding_name(db_session, 99999, "New Name")


# ── discard_holding ───────────────────────────────────────────────────────


class TestDiscardHolding:
    def test_sets_date_discarded(self, db_session: Session, exact_holding: ExactHolding) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.discard_holding(db_session, exact_holding.id, AS_OF)
        db_session.flush()
        db_session.refresh(exact_holding)
        assert exact_holding.date_discarded == AS_OF

    def test_raises_for_unknown_holding(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.discard_holding(db_session, 99999, AS_OF)


# ── update_holding_exact_amount ──────────────────────────────────────────


class TestUpdateHoldingExactAmount:
    def test_appends_new_entry(self, db_session: Session, exact_holding: ExactHolding) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_holding_exact_amount(db_session, exact_holding.id, AS_OF, Decimal("7500"))
        db_session.expire(exact_holding)
        assert exact_holding.get_value(AS_OF) == Decimal("7500")

    def test_raises_for_unknown_holding(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.update_holding_exact_amount(db_session, 99999, AS_OF, Decimal("100"))


# ── update_holding_listed_quantity ────────────────────────────────────────


class TestUpdateHoldingListedQuantity:
    def test_appends_new_entry(
        self, db_session: Session, listed_holding: ListedSecurityHolding
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        svc.update_holding_listed_quantity(db_session, listed_holding.id, AS_OF, Decimal("20"))
        db_session.expire(listed_holding)
        assert listed_holding.quantity.latest_value_as_of(AS_OF) == Decimal("20")

    def test_raises_for_zero_quantity(
        self, db_session: Session, listed_holding: ListedSecurityHolding
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="positive"):
            svc.update_holding_listed_quantity(db_session, listed_holding.id, AS_OF, Decimal("0"))

    def test_raises_for_negative_quantity(
        self, db_session: Session, listed_holding: ListedSecurityHolding
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="positive"):
            svc.update_holding_listed_quantity(db_session, listed_holding.id, AS_OF, Decimal("-5"))

    def test_raises_for_unknown_holding(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.update_holding_listed_quantity(db_session, 99999, AS_OF, Decimal("10"))


# ── list_active_asset_classes ─────────────────────────────────────────────────


class TestListActiveAssetClasses:
    def test_returns_active_class(
        self, db_session: Session, asset_class: AccountAssetClass
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        result = svc.list_active_asset_classes(db_session, AS_OF)
        assert any(ac.id == asset_class.id for ac in result)

    def test_excludes_disabled_class(self, db_session: Session) -> None:
        ac = AccountAssetClass(
            name="Bonds",
            order_precedence=2,
            date_created=date(2024, 1, 1),
            date_disabled=date(2024, 3, 1),
        )
        db_session.add(ac)
        db_session.flush()
        svc = BalanceSheetService(_MockQuoteService({}))
        result = svc.list_active_asset_classes(db_session, AS_OF)
        assert ac.id not in {c.id for c in result}

    def test_ordered_by_precedence(self, db_session: Session) -> None:
        ac1 = AccountAssetClass(name="Equity", order_precedence=2, date_created=date(2024, 1, 1))
        ac2 = AccountAssetClass(
            name="Fixed Income", order_precedence=1, date_created=date(2024, 1, 1)
        )
        db_session.add_all([ac1, ac2])
        db_session.flush()
        svc = BalanceSheetService(_MockQuoteService({}))
        result = svc.list_active_asset_classes(db_session, AS_OF)
        precedences = [c.order_precedence for c in result]
        assert precedences == sorted(precedences)


# ── add_holding ───────────────────────────────────────────────────────────


class TestAddHolding:
    def test_creates_listed_holding(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
        asset_class: AccountAssetClass,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        cid = svc.add_holding(
            db_session,
            account_id=investment_account.id,
            holding_type="listed",
            name="Apple",
            as_of=AS_OF,
            symbol="AAPL",
            initial_quantity=Decimal("5"),
            initial_amount=None,
            allocations=[(asset_class.id, Decimal("100"))],
        )
        holding = db_session.get(ListedSecurityHolding, cid)
        assert holding is not None
        assert holding.symbol == "AAPL"
        assert holding.quantity.latest_value_as_of(AS_OF) == Decimal("5")

    def test_creates_exact_holding(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
        asset_class: AccountAssetClass,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        cid = svc.add_holding(
            db_session,
            account_id=investment_account.id,
            holding_type="exact",
            name="GIC",
            as_of=AS_OF,
            symbol=None,
            initial_quantity=None,
            initial_amount=Decimal("10000"),
            allocations=[(asset_class.id, Decimal("100"))],
        )
        holding = db_session.get(ExactHolding, cid)
        assert holding is not None
        assert holding.get_value(AS_OF) == Decimal("10000")

    def test_raises_for_unknown_account(
        self, db_session: Session, asset_class: AccountAssetClass
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.add_holding(
                db_session,
                account_id=99999,
                holding_type="exact",
                name="GIC",
                as_of=AS_OF,
                symbol=None,
                initial_quantity=None,
                initial_amount=Decimal("1000"),
                allocations=[(asset_class.id, Decimal("100"))],
            )

    def test_raises_when_allocations_do_not_sum_to_100(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
        asset_class: AccountAssetClass,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="100%"):
            svc.add_holding(
                db_session,
                account_id=investment_account.id,
                holding_type="exact",
                name="GIC",
                as_of=AS_OF,
                symbol=None,
                initial_quantity=None,
                initial_amount=Decimal("1000"),
                allocations=[(asset_class.id, Decimal("50"))],
            )


# ── get_holding_allocations ───────────────────────────────────────────────


class TestGetHoldingAllocations:
    def test_returns_active_allocations(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
        asset_class: AccountAssetClass,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        cid = svc.add_holding(
            db_session,
            account_id=investment_account.id,
            holding_type="exact",
            name="GIC",
            as_of=AS_OF,
            symbol=None,
            initial_quantity=None,
            initial_amount=Decimal("1000"),
            allocations=[(asset_class.id, Decimal("100"))],
        )
        result = svc.get_holding_allocations(db_session, cid, AS_OF)
        assert result == {asset_class.id: Decimal("100")}

    def test_returns_empty_for_unknown_holding(self, db_session: Session) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        assert svc.get_holding_allocations(db_session, 99999, AS_OF) == {}


# ── update_holding_asset_allocation ───────────────────────────────────────


class TestUpdateHoldingAssetAllocation:
    def test_overwrites_allocations(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
        asset_class: AccountAssetClass,
    ) -> None:
        ac2 = AccountAssetClass(
            name="Fixed Income", order_precedence=2, date_created=date(2024, 1, 1)
        )
        db_session.add(ac2)
        db_session.flush()
        svc = BalanceSheetService(_MockQuoteService({}))
        cid = svc.add_holding(
            db_session,
            account_id=investment_account.id,
            holding_type="exact",
            name="GIC",
            as_of=AS_OF,
            symbol=None,
            initial_quantity=None,
            initial_amount=Decimal("1000"),
            allocations=[(asset_class.id, Decimal("100"))],
        )
        svc.update_holding_asset_allocation(db_session, cid, AS_OF, [(ac2.id, Decimal("100"))])
        result = svc.get_holding_allocations(db_session, cid, AS_OF)
        assert result == {ac2.id: Decimal("100")}

    def test_raises_for_unknown_holding(
        self, db_session: Session, asset_class: AccountAssetClass
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        with pytest.raises(ValueError, match="not found"):
            svc.update_holding_asset_allocation(
                db_session, 99999, AS_OF, [(asset_class.id, Decimal("100"))]
            )

    def test_raises_when_allocations_do_not_sum_to_100(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
        asset_class: AccountAssetClass,
    ) -> None:
        svc = BalanceSheetService(_MockQuoteService({}))
        cid = svc.add_holding(
            db_session,
            account_id=investment_account.id,
            holding_type="exact",
            name="GIC",
            as_of=AS_OF,
            symbol=None,
            initial_quantity=None,
            initial_amount=Decimal("1000"),
            allocations=[(asset_class.id, Decimal("100"))],
        )
        with pytest.raises(ValueError, match="100%"):
            svc.update_holding_asset_allocation(
                db_session, cid, AS_OF, [(asset_class.id, Decimal("50"))]
            )


# ── search_symbols ────────────────────────────────────────────────────────────


class TestSearchSymbols:
    async def test_delegates_to_quote_service(self, db_session: Session) -> None:
        expected = [SecuritySearchResult(symbol="AAPL", name="Apple Inc.", exchange="NASDAQ")]
        mock = _MockQuoteService({}, search_results=expected)
        svc = BalanceSheetService(mock)
        result = await svc.search_symbols("AAPL")
        assert result == expected


# ── get_unit_price ────────────────────────────────────────────────────────────


class TestGetUnitPrice:
    async def test_delegates_to_quote_service(self, db_session: Session) -> None:
        mock = _MockQuoteService({"AAPL": Decimal("175.50")})
        svc = BalanceSheetService(mock)
        result = await svc.get_unit_price("AAPL", AS_OF)
        assert result == Decimal("175.50")
