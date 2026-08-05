"""Tests for balance sheet account domain models."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from personal_finance.domain.balance_sheet import (
    Account,
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.base import Base
from personal_finance.domain.effective_amount import EffectiveAmount
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
def money(db_session: Session) -> EffectiveAmount:
    m = EffectiveAmount()
    m.offer_value(date(2024, 1, 1), Decimal("1000.00"))
    db_session.add(m)
    db_session.flush()
    return m


# ── SimpleAccount ─────────────────────────────────────────────────────────────


class TestSimpleAccount:
    def test_creation_with_required_fields(self, person: Person, money: EffectiveAmount) -> None:
        account = SimpleAccount(
            name="Chequing",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_CURRENT,
            owners=[person],
            type=SimpleAccountCategory.BANK,
            balance=money,
        )
        assert account.name == "Chequing"
        assert account.type == SimpleAccountCategory.BANK
        assert account.balance is money

    def test_date_discarded_is_optional(self, person: Person, money: EffectiveAmount) -> None:
        account = SimpleAccount(
            name="Savings",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_CURRENT,
            owners=[person],
            type=SimpleAccountCategory.BANK,
            balance=money,
        )
        assert account.date_discarded is None

    def test_db_round_trip(
        self, db_session: Session, person: Person, money: EffectiveAmount
    ) -> None:
        account = SimpleAccount(
            name="Chequing",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_CURRENT,
            owners=[person],
            type=SimpleAccountCategory.BANK,
            balance=money,
        )
        db_session.add(account)
        db_session.flush()
        db_session.expire(account)

        reloaded = db_session.get(SimpleAccount, account.id)
        assert reloaded is not None
        assert reloaded.name == "Chequing"
        assert reloaded.type == SimpleAccountCategory.BANK
        assert reloaded.classification == AccountClassification.ASSET_CURRENT

    def test_balance_relationship_round_trips(
        self, db_session: Session, person: Person, money: EffectiveAmount
    ) -> None:
        account = SimpleAccount(
            name="Savings",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_CURRENT,
            owners=[person],
            type=SimpleAccountCategory.BANK,
            balance=money,
        )
        db_session.add(account)
        db_session.flush()
        db_session.expire(account)

        reloaded = db_session.get(SimpleAccount, account.id)
        assert reloaded is not None
        assert reloaded.balance.latest_value_as_of(date(2024, 12, 31)) == Decimal("1000.00")

    def test_real_estate_category(
        self, db_session: Session, person: Person, money: EffectiveAmount
    ) -> None:
        account = SimpleAccount(
            name="Home",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            type=SimpleAccountCategory.REAL_ESTATE,
            balance=money,
        )
        db_session.add(account)
        db_session.flush()
        db_session.expire(account)

        reloaded = db_session.get(SimpleAccount, account.id)
        assert reloaded is not None
        assert reloaded.type == SimpleAccountCategory.REAL_ESTATE
        assert reloaded.classification == AccountClassification.ASSET_LONG_TERM


# ── InvestmentAccount ─────────────────────────────────────────────────────────


class TestInvestmentAccount:
    def test_creation_with_required_fields(self, person: Person, money: EffectiveAmount) -> None:
        account = InvestmentAccount(
            name="RRSP",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            investment_registration=InvestmentRegistration.RRSP,
            cash_balance=money,
        )
        assert account.name == "RRSP"
        assert account.investment_registration == InvestmentRegistration.RRSP
        assert account.holdings == []

    def test_db_round_trip(
        self, db_session: Session, person: Person, money: EffectiveAmount
    ) -> None:
        account = InvestmentAccount(
            name="TFSA",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            investment_registration=InvestmentRegistration.TFSA,
            cash_balance=money,
        )
        db_session.add(account)
        db_session.flush()
        db_session.expire(account)

        reloaded = db_session.get(InvestmentAccount, account.id)
        assert reloaded is not None
        assert reloaded.name == "TFSA"
        assert reloaded.investment_registration == InvestmentRegistration.TFSA

    def test_cash_balance_round_trips(
        self, db_session: Session, person: Person, money: EffectiveAmount
    ) -> None:
        account = InvestmentAccount(
            name="RRSP",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            investment_registration=InvestmentRegistration.RRSP,
            cash_balance=money,
        )
        db_session.add(account)
        db_session.flush()
        db_session.expire(account)

        reloaded = db_session.get(InvestmentAccount, account.id)
        assert reloaded is not None
        assert reloaded.cash_balance.latest_value_as_of(date(2024, 12, 31)) == Decimal("1000.00")

    def test_owner_relationship_round_trips(
        self, db_session: Session, person: Person, money: EffectiveAmount
    ) -> None:
        account = InvestmentAccount(
            name="RRSP",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            investment_registration=InvestmentRegistration.RRSP,
            cash_balance=money,
        )
        db_session.add(account)
        db_session.flush()
        db_session.expire(account)

        reloaded = db_session.get(InvestmentAccount, account.id)
        assert reloaded is not None
        assert person in reloaded.owners


# ── Polymorphism ──────────────────────────────────────────────────────────────


class TestPolymorphism:
    def test_query_account_base_returns_correct_subtypes(
        self, db_session: Session, person: Person
    ) -> None:
        simple = SimpleAccount(
            name="Bank",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_CURRENT,
            owners=[person],
            type=SimpleAccountCategory.BANK,
        )
        investment = InvestmentAccount(
            name="RRSP",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            investment_registration=InvestmentRegistration.RRSP,
        )
        db_session.add_all([simple, investment])
        db_session.flush()
        db_session.expire_all()

        accounts = db_session.query(Account).all()
        assert len(accounts) == 2
        types = {type(a) for a in accounts}
        assert types == {SimpleAccount, InvestmentAccount}


# ── Account.is_active ─────────────────────────────────────────────────────────


def _simple(
    person: Person, money: EffectiveAmount | None = None, **kwargs: object
) -> SimpleAccount:
    defaults: dict[str, object] = {
        "name": "Bank",
        "date_created": date(2024, 1, 1),
        "date_effective": date(2024, 1, 1),
        "date_modified": date(2024, 1, 1),
        "classification": AccountClassification.ASSET_CURRENT,
        "type": SimpleAccountCategory.BANK,
    }
    extras: dict[str, object] = {"balance": money} if money is not None else {}
    return SimpleAccount(owners=[person], **{**defaults, **extras, **kwargs})


class TestAccountIsActive:
    def test_active_when_effective_on_query_date(
        self, person: Person, money: EffectiveAmount
    ) -> None:
        a = _simple(person, money, date_effective=date(2024, 1, 1))
        assert a.is_active(date(2024, 1, 1)) is True

    def test_active_when_effective_before_query_date(
        self, person: Person, money: EffectiveAmount
    ) -> None:
        a = _simple(person, money, date_effective=date(2024, 1, 1))
        assert a.is_active(date(2024, 6, 1)) is True

    def test_inactive_when_effective_after_query_date(
        self, person: Person, money: EffectiveAmount
    ) -> None:
        a = _simple(person, money, date_effective=date(2024, 6, 1))
        assert a.is_active(date(2024, 1, 1)) is False

    def test_active_indefinitely_when_not_discarded(
        self, person: Person, money: EffectiveAmount
    ) -> None:
        a = _simple(person, money, date_effective=date(2020, 1, 1), date_discarded=None)
        assert a.is_active(date(2099, 12, 31)) is True

    def test_inactive_when_discarded_on_query_date(
        self, person: Person, money: EffectiveAmount
    ) -> None:
        a = _simple(person, money, date_effective=date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert a.is_active(date(2024, 6, 1)) is False

    def test_active_one_day_before_discard(self, person: Person, money: EffectiveAmount) -> None:
        a = _simple(person, money, date_effective=date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert a.is_active(date(2024, 5, 31)) is True

    def test_inactive_after_discard_date(self, person: Person, money: EffectiveAmount) -> None:
        a = _simple(person, money, date_effective=date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert a.is_active(date(2024, 12, 31)) is False


# ── AccountClassification enum helpers ────────────────────────────────────────


class TestAccountClassificationHelpers:
    @pytest.mark.parametrize(
        "classification,expected_current,expected_long_term,expected_asset,expected_liability",
        [
            (AccountClassification.ASSET_CURRENT, True, False, True, False),
            (AccountClassification.ASSET_LONG_TERM, False, True, True, False),
            (AccountClassification.LIABILITY_CURRENT, True, False, False, True),
            (AccountClassification.LIABILITY_LONG_TERM, False, True, False, True),
        ],
    )
    def test_classification_helpers(
        self,
        classification: AccountClassification,
        expected_current: bool,
        expected_long_term: bool,
        expected_asset: bool,
        expected_liability: bool,
    ) -> None:
        assert classification.is_current() is expected_current
        assert classification.is_long_term() is expected_long_term
        assert classification.is_asset() is expected_asset
        assert classification.is_liability() is expected_liability


# ── SimpleAccount.get_balance ─────────────────────────────────────────────────


class TestSimpleAccountGetBalance:
    def test_returns_balance_on_exact_date(self, person: Person, money: EffectiveAmount) -> None:
        account = _simple(person, money)
        assert account.get_balance(date(2024, 1, 1)) == Decimal("1000.00")

    def test_returns_balance_after_entry_date(self, person: Person, money: EffectiveAmount) -> None:
        account = _simple(person, money)
        assert account.get_balance(date(2024, 12, 31)) == Decimal("1000.00")

    def test_returns_none_before_first_entry(self, person: Person) -> None:
        account = _simple(person)
        assert account.get_balance(date(2023, 1, 1)) is None

    def test_returns_latest_entry_when_multiple(self, person: Person) -> None:
        m = EffectiveAmount()
        m.offer_value(date(2024, 1, 1), Decimal("1000.00"))
        m.offer_value(date(2024, 6, 1), Decimal("1500.00"))
        account = _simple(person, m)
        assert account.get_balance(date(2024, 9, 1)) == Decimal("1500.00")
        assert account.get_balance(date(2024, 3, 1)) == Decimal("1000.00")


# ── InvestmentAccount.get_balance ─────────────────────────────────────────────


class TestInvestmentAccountGetBalance:
    def _account(self, person: Person, cash: EffectiveAmount | None = None) -> InvestmentAccount:
        extras: dict[str, object] = {"cash_balance": cash} if cash is not None else {}
        return InvestmentAccount(
            name="RRSP",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            classification=AccountClassification.ASSET_LONG_TERM,
            owners=[person],
            investment_registration=InvestmentRegistration.RRSP,
            **extras,
        )

    def test_returns_cash_when_no_holdings(self, person: Person) -> None:
        cash = EffectiveAmount()
        cash.offer_value(date(2024, 1, 1), Decimal("500.00"))
        account = self._account(person, cash)
        assert account.get_balance(date(2024, 6, 1)) == Decimal("500.00")

    def test_returns_none_when_cash_has_no_entry(self, person: Person) -> None:
        account = self._account(person)
        assert account.get_balance(date(2024, 6, 1)) is None

    def test_adds_exact_holding_to_cash(self, person: Person) -> None:
        from personal_finance.domain.balance_sheet import ExactHolding

        cash = EffectiveAmount()
        cash.offer_value(date(2024, 1, 1), Decimal("200.00"))
        account = self._account(person, cash)

        amount = EffectiveAmount()
        amount.offer_value(date(2024, 1, 1), Decimal("800.00"))
        ExactHolding(
            name="GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=account,  # back_populates adds to account.holdings
            amount=amount,
        )

        assert account.get_balance(date(2024, 6, 1)) == Decimal("1000.00")

    def test_excludes_inactive_holdings(self, person: Person) -> None:
        from personal_finance.domain.balance_sheet import ExactHolding

        cash = EffectiveAmount()
        cash.offer_value(date(2024, 1, 1), Decimal("500.00"))
        account = self._account(person, cash)

        amount = EffectiveAmount()
        amount.offer_value(date(2024, 1, 1), Decimal("999.00"))
        discarded = ExactHolding(
            name="Closed GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            date_discarded=date(2024, 3, 1),  # discarded before query date
            investment_account=account,
            amount=amount,
        )
        account.holdings.append(discarded)

        assert account.get_balance(date(2024, 6, 1)) == Decimal("500.00")

    def test_returns_none_when_listed_security_present(self, person: Person) -> None:
        from personal_finance.domain.balance_sheet import ListedSecurityHolding

        cash = EffectiveAmount()
        cash.offer_value(date(2024, 1, 1), Decimal("500.00"))
        account = self._account(person, cash)

        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=account,
            symbol="AAPL",
        )
        account.holdings.append(holding)

        assert account.get_balance(date(2024, 6, 1)) is None

    def test_sums_multiple_exact_holdings(self, person: Person) -> None:
        from personal_finance.domain.balance_sheet import ExactHolding

        cash = EffectiveAmount()
        cash.offer_value(date(2024, 1, 1), Decimal("100.00"))
        account = self._account(person, cash)

        for value in (Decimal("300.00"), Decimal("200.00"), Decimal("400.00")):
            m = EffectiveAmount()
            m.offer_value(date(2024, 1, 1), value)
            ExactHolding(
                name="GIC",
                date_created=date(2024, 1, 1),
                date_effective=date(2024, 1, 1),
                date_modified=date(2024, 1, 1),
                investment_account=account,  # back_populates adds to account.holdings
                amount=m,
            )

        assert account.get_balance(date(2024, 6, 1)) == Decimal("1000.00")
