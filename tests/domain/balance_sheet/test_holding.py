"""Tests for investment account holding domain models."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet import (
    AccountClassification,
    ExactHolding,
    HoldingAssetClassAllocation,
    InvestmentAccount,
    InvestmentAccountHolding,
    InvestmentRegistration,
    ListedSecurityHolding,
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
def investment_account(db_session: Session) -> InvestmentAccount:
    person = Person(name="Bob")
    db_session.add(person)
    db_session.flush()

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


@pytest.fixture()
def asset_class(db_session: Session) -> AccountAssetClass:
    ac = AccountAssetClass(name="Equity", order_precedence=1, date_created=date(2024, 1, 1))
    db_session.add(ac)
    db_session.flush()
    return ac


def _allocation(
    percent: Decimal,
    date_effective: date,
    date_discarded: date | None = None,
) -> HoldingAssetClassAllocation:
    return HoldingAssetClassAllocation(
        percent_allocated=percent,
        date_created=date_effective,
        date_effective=date_effective,
        date_modified=date_effective,
        date_discarded=date_discarded,
    )


# ── InvestmentAccountHolding.is_active ────────────────────────────────────


def _exact(investment_account: InvestmentAccount, **kwargs: object) -> ExactHolding:
    defaults: dict[str, object] = {
        "name": "GIC",
        "date_created": date(2024, 1, 1),
        "date_effective": date(2024, 1, 1),
        "date_modified": date(2024, 1, 1),
    }
    return ExactHolding(investment_account=investment_account, **{**defaults, **kwargs})


class TestHoldingIsActive:
    def test_active_when_effective_on_query_date(
        self, investment_account: InvestmentAccount
    ) -> None:
        c = _exact(investment_account, date_effective=date(2024, 1, 1))
        assert c.is_active(date(2024, 1, 1)) is True

    def test_active_when_effective_before_query_date(
        self, investment_account: InvestmentAccount
    ) -> None:
        c = _exact(investment_account, date_effective=date(2024, 1, 1))
        assert c.is_active(date(2024, 6, 1)) is True

    def test_inactive_when_effective_after_query_date(
        self, investment_account: InvestmentAccount
    ) -> None:
        c = _exact(investment_account, date_effective=date(2024, 6, 1))
        assert c.is_active(date(2024, 1, 1)) is False

    def test_active_indefinitely_when_not_discarded(
        self, investment_account: InvestmentAccount
    ) -> None:
        c = _exact(investment_account, date_effective=date(2020, 1, 1), date_discarded=None)
        assert c.is_active(date(2099, 12, 31)) is True

    def test_inactive_when_discarded_on_query_date(
        self, investment_account: InvestmentAccount
    ) -> None:
        c = _exact(
            investment_account,
            date_effective=date(2024, 1, 1),
            date_discarded=date(2024, 6, 1),
        )
        assert c.is_active(date(2024, 6, 1)) is False

    def test_active_one_day_before_discard(self, investment_account: InvestmentAccount) -> None:
        c = _exact(
            investment_account,
            date_effective=date(2024, 1, 1),
            date_discarded=date(2024, 6, 1),
        )
        assert c.is_active(date(2024, 5, 31)) is True

    def test_inactive_after_discard_date(self, investment_account: InvestmentAccount) -> None:
        c = _exact(
            investment_account,
            date_effective=date(2024, 1, 1),
            date_discarded=date(2024, 6, 1),
        )
        assert c.is_active(date(2024, 12, 31)) is False


# ── HoldingAssetClassAllocation.is_active ─────────────────────────────────


class TestAllocationIsActive:
    def test_active_when_effective_on_query_date(self) -> None:
        a = _allocation(Decimal("100"), date(2024, 1, 1))
        assert a.is_active(date(2024, 1, 1)) is True

    def test_active_when_effective_before_query_date(self) -> None:
        a = _allocation(Decimal("100"), date(2024, 1, 1))
        assert a.is_active(date(2024, 6, 1)) is True

    def test_inactive_when_effective_after_query_date(self) -> None:
        a = _allocation(Decimal("100"), date(2024, 6, 1))
        assert a.is_active(date(2024, 1, 1)) is False

    def test_active_indefinitely_when_not_discarded(self) -> None:
        a = _allocation(Decimal("100"), date(2020, 1, 1), date_discarded=None)
        assert a.is_active(date(2099, 12, 31)) is True

    def test_inactive_when_discarded_on_query_date(self) -> None:
        a = _allocation(Decimal("100"), date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert a.is_active(date(2024, 6, 1)) is False

    def test_active_one_day_before_discard(self) -> None:
        a = _allocation(Decimal("100"), date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert a.is_active(date(2024, 5, 31)) is True

    def test_inactive_after_discard_date(self) -> None:
        a = _allocation(Decimal("100"), date(2024, 1, 1), date_discarded=date(2024, 6, 1))
        assert a.is_active(date(2024, 12, 31)) is False


# ── validate_allocations ──────────────────────────────────────────────────────


class TestValidateAllocations:
    def _holding_with_allocations(
        self,
        *allocations: HoldingAssetClassAllocation,
    ) -> InvestmentAccountHolding:
        c = ExactHolding(
            name="GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
        )
        c.allocations = list(allocations)
        return c

    def test_raises_when_no_allocations(self) -> None:
        c = self._holding_with_allocations()
        with pytest.raises(ValueError, match="100"):
            c.validate_allocations(date(2024, 6, 1))

    def test_passes_when_active_allocations_sum_to_100(self) -> None:
        c = self._holding_with_allocations(
            _allocation(Decimal("60"), date(2024, 1, 1)),
            _allocation(Decimal("40"), date(2024, 1, 1)),
        )
        c.validate_allocations(date(2024, 6, 1))  # must not raise

    def test_raises_when_active_allocations_sum_below_100(self) -> None:
        c = self._holding_with_allocations(
            _allocation(Decimal("60"), date(2024, 1, 1)),
            _allocation(Decimal("30"), date(2024, 1, 1)),
        )
        with pytest.raises(ValueError, match="100"):
            c.validate_allocations(date(2024, 6, 1))

    def test_raises_when_active_allocations_sum_above_100(self) -> None:
        c = self._holding_with_allocations(
            _allocation(Decimal("60"), date(2024, 1, 1)),
            _allocation(Decimal("50"), date(2024, 1, 1)),
        )
        with pytest.raises(ValueError, match="100"):
            c.validate_allocations(date(2024, 6, 1))

    def test_inactive_allocations_are_excluded_from_sum(self) -> None:
        c = self._holding_with_allocations(
            _allocation(Decimal("100"), date(2024, 1, 1), date_discarded=date(2024, 3, 1)),
            _allocation(Decimal("70"), date(2024, 3, 1)),
            _allocation(Decimal("30"), date(2024, 3, 1)),
        )
        # The first allocation is discarded by 2024-06-01; only the last two (70+30) are active.
        c.validate_allocations(date(2024, 6, 1))  # must not raise

    def test_raises_when_only_discarded_allocations_exist(self) -> None:
        c = self._holding_with_allocations(
            _allocation(Decimal("100"), date(2024, 1, 1), date_discarded=date(2024, 3, 1)),
        )
        with pytest.raises(ValueError, match="100"):
            c.validate_allocations(date(2024, 6, 1))

    def test_single_allocation_at_100_passes(self) -> None:
        c = self._holding_with_allocations(
            _allocation(Decimal("100"), date(2024, 1, 1)),
        )
        c.validate_allocations(date(2024, 6, 1))  # must not raise

    def test_error_message_contains_actual_sum(self) -> None:
        c = self._holding_with_allocations(
            _allocation(Decimal("42"), date(2024, 1, 1)),
        )
        with pytest.raises(ValueError, match="42"):
            c.validate_allocations(date(2024, 6, 1))


# ── ExactHolding ──────────────────────────────────────────────────────────


class TestExactHolding:
    def test_creation_with_required_fields(self, investment_account: InvestmentAccount) -> None:
        amount = EffectiveAmount()
        amount.offer_value(date(2024, 1, 1), Decimal("5000.00"))
        holding = ExactHolding(
            name="GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            amount=amount,
        )
        assert holding.name == "GIC"
        assert holding.amount is amount

    def test_db_round_trip(
        self, db_session: Session, investment_account: InvestmentAccount
    ) -> None:
        amount = EffectiveAmount()
        amount.offer_value(date(2024, 1, 1), Decimal("5000.00"))
        holding = ExactHolding(
            name="GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            amount=amount,
        )
        db_session.add(holding)
        db_session.flush()
        db_session.expire(holding)

        reloaded = db_session.get(ExactHolding, holding.id)
        assert reloaded is not None
        assert reloaded.name == "GIC"
        assert reloaded.amount.latest_value_as_of(date(2024, 12, 31)) == Decimal("5000.00")

    def test_get_value_returns_amount_as_of_date(
        self, investment_account: InvestmentAccount
    ) -> None:
        amount = EffectiveAmount()
        amount.offer_value(date(2024, 1, 1), Decimal("5000.00"))
        amount.offer_value(date(2024, 6, 1), Decimal("5200.00"))
        holding = ExactHolding(
            name="GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            amount=amount,
        )
        assert holding.get_value(date(2024, 3, 1)) == Decimal("5000.00")
        assert holding.get_value(date(2024, 9, 1)) == Decimal("5200.00")

    def test_get_value_returns_none_before_first_entry(
        self, investment_account: InvestmentAccount
    ) -> None:
        holding = ExactHolding(
            name="GIC",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
        )
        assert holding.get_value(date(2023, 12, 31)) is None


# ── ListedSecurityHolding ─────────────────────────────────────────────────


class TestListedSecurityHolding:
    def test_creation_with_required_fields(self, investment_account: InvestmentAccount) -> None:
        qty = EffectiveAmount()
        qty.offer_value(date(2024, 1, 1), Decimal("10.5"))
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=qty,
        )
        assert holding.symbol == "AAPL"
        assert holding.quantity.latest_value_as_of(date(2024, 6, 1)) == Decimal("10.5")

    def test_db_round_trip(
        self, db_session: Session, investment_account: InvestmentAccount
    ) -> None:
        qty = EffectiveAmount()
        qty.offer_value(date(2024, 1, 1), Decimal("10.5"))
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=qty,
        )
        db_session.add(holding)
        db_session.flush()
        db_session.expire(holding)

        reloaded = db_session.get(ListedSecurityHolding, holding.id)
        assert reloaded is not None
        assert reloaded.symbol == "AAPL"
        assert reloaded.quantity.latest_value_as_of(date(2024, 6, 1)) == Decimal("10.5")

    def test_quantity_auto_created_when_omitted(
        self, investment_account: InvestmentAccount
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
        )
        assert holding.quantity.latest_value_as_of(date(2024, 6, 1)) is None

    def test_validate_quantity_passes_with_positive_entry(
        self, investment_account: InvestmentAccount
    ) -> None:
        qty = EffectiveAmount()
        qty.offer_value(date(2024, 1, 1), Decimal("10"))
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=qty,
        )
        holding.validate_quantity(date(2024, 6, 1))  # must not raise

    def test_validate_quantity_raises_when_no_entry(
        self, investment_account: InvestmentAccount
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
        )
        with pytest.raises(ValueError, match="no quantity entry"):
            holding.validate_quantity(date(2024, 6, 1))

    def test_validate_quantity_raises_when_zero(
        self, investment_account: InvestmentAccount
    ) -> None:
        qty = EffectiveAmount()
        qty.offer_value(date(2024, 1, 1), Decimal("0"))
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=qty,
        )
        with pytest.raises(ValueError, match="non-positive"):
            holding.validate_quantity(date(2024, 6, 1))

    def test_validate_quantity_raises_when_negative(
        self, investment_account: InvestmentAccount
    ) -> None:
        qty = EffectiveAmount()
        qty.offer_value(date(2024, 1, 1), Decimal("-5"))
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=qty,
        )
        with pytest.raises(ValueError, match="non-positive"):
            holding.validate_quantity(date(2024, 6, 1))

    def test_validate_quantity_raises_when_entry_is_after_query_date(
        self, investment_account: InvestmentAccount
    ) -> None:
        qty = EffectiveAmount()
        qty.offer_value(date(2024, 9, 1), Decimal("10"))  # entry after AS_OF
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=qty,
        )
        with pytest.raises(ValueError, match="no quantity entry"):
            holding.validate_quantity(date(2024, 6, 1))

    def test_get_value_returns_none_when_not_priced(
        self, investment_account: InvestmentAccount
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
        )
        assert holding.get_value(date(2024, 6, 1)) is None

    def test_get_value_multiplies_unit_price_by_quantity(
        self, investment_account: InvestmentAccount
    ) -> None:
        effective = date(2024, 6, 1)
        qty = EffectiveAmount()
        qty.offer_value(date(2024, 1, 1), Decimal("10"))
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=qty,
        )
        holding.set_unit_price(effective, Decimal("150.00"))
        assert holding.get_value(effective) == Decimal("1500.00")

    def test_get_value_reflects_updated_quantity_without_reprice(
        self, investment_account: InvestmentAccount
    ) -> None:
        """After a quantity timeline update, get_value recomputes using the new qty.

        This is the key benefit of storing unit price rather than a pre-multiplied
        total: a quantity change (BS-OP-10) is reflected in the next get_value call
        at the same as_of without a new network price fetch.
        """
        effective = date(2024, 6, 1)
        qty = EffectiveAmount()
        qty.offer_value(date(2024, 1, 1), Decimal("10"))
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
            quantity=qty,
        )
        holding.set_unit_price(effective, Decimal("100.00"))
        assert holding.get_value(effective) == Decimal("1000.00")

        # Simulate a quantity update at the same effective date (BS-OP-10).
        qty.offer_value(effective, Decimal("20"))
        assert holding.get_value(effective) == Decimal("2000.00")

    def test_get_value_raises_on_date_mismatch(self, investment_account: InvestmentAccount) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
        )
        holding.set_unit_price(date(2024, 6, 1), Decimal("150.00"))
        with pytest.raises(ValueError, match="2024-06-01"):
            holding.get_value(date(2024, 9, 1))

    def test_get_value_returns_none_when_no_quantity_entry(
        self, investment_account: InvestmentAccount
    ) -> None:
        effective = date(2024, 6, 1)
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
        )
        holding.set_unit_price(effective, Decimal("150.00"))
        assert holding.get_value(effective) is None

    def test_unit_price_reset_on_db_load(
        self, db_session: Session, investment_account: InvestmentAccount
    ) -> None:
        effective = date(2024, 6, 1)
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
        )
        holding.set_unit_price(effective, Decimal("150.00"))
        db_session.add(holding)
        db_session.flush()

        # Expunge evicts the instance from the identity map, so the next get()
        # creates a fresh Python object and invokes @reconstructor.
        holding_id = holding.id
        db_session.expunge(holding)

        reloaded = db_session.get(ListedSecurityHolding, holding_id)
        assert reloaded is not None
        assert reloaded.get_value(effective) is None


# ── HoldingAssetClassAllocation DB round-trip ─────────────────────────────


class TestAllocationDbRoundTrip:
    def test_allocation_persists_with_holding_and_asset_class(
        self,
        db_session: Session,
        investment_account: InvestmentAccount,
        asset_class: AccountAssetClass,
    ) -> None:
        holding = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
        )
        allocation = HoldingAssetClassAllocation(
            holding=holding,
            asset_class=asset_class,
            percent_allocated=Decimal("100"),
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
        )
        holding.allocations.append(allocation)
        db_session.add(holding)
        db_session.flush()
        db_session.expire(holding)

        reloaded = db_session.get(ListedSecurityHolding, holding.id)
        assert reloaded is not None
        assert len(reloaded.allocations) == 1
        assert reloaded.allocations[0].percent_allocated == Decimal("100")
        assert reloaded.allocations[0].asset_class.name == "Equity"

    def test_holding_polymorphism_from_base_query(
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
        listed = ListedSecurityHolding(
            name="Apple",
            date_created=date(2024, 1, 1),
            date_effective=date(2024, 1, 1),
            date_modified=date(2024, 1, 1),
            investment_account=investment_account,
            symbol="AAPL",
        )
        db_session.add_all([exact, listed])
        db_session.flush()
        db_session.expire_all()

        holdings = db_session.query(InvestmentAccountHolding).all()
        assert len(holdings) == 2
        types = {type(c) for c in holdings}
        assert types == {ExactHolding, ListedSecurityHolding}
