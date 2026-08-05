"""Tests for EffectiveAmount and EffectiveAmountEntry domain models."""

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from personal_finance.domain.base import Base
from personal_finance.domain.effective_amount import (
    EffectiveAmount,
    EffectiveAmountEntrySource,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """In-memory SQLite session with a fresh schema for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def effective_amount() -> EffectiveAmount:
    """A transient EffectiveAmount timeline with no entries."""
    return EffectiveAmount()


# ── offer_value ───────────────────────────────────────────────────────────────


class TestOfferValue:
    """EffectiveAmount.offer_value() always inserts a new entry, never replaces."""

    def test_appends_entry_to_empty_timeline(self, effective_amount: EffectiveAmount) -> None:
        """offer_value on an empty timeline produces exactly one entry."""
        entry = effective_amount.offer_value(date(2024, 1, 1), Decimal("100.00"))
        assert len(effective_amount.entries) == 1
        assert effective_amount.entries[0] is entry

    def test_date_created_is_set_to_today(self, effective_amount: EffectiveAmount) -> None:
        entry = effective_amount.offer_value(date(2024, 1, 1), Decimal("100.00"))
        assert entry.date_created == date.today()

    def test_default_source_is_data_entry(self, effective_amount: EffectiveAmount) -> None:
        entry = effective_amount.offer_value(date(2024, 1, 1), Decimal("100.00"))
        assert entry.source == EffectiveAmountEntrySource.DATA_ENTRY

    def test_explicit_source_is_preserved(self, effective_amount: EffectiveAmount) -> None:
        entry = effective_amount.offer_value(
            date(2024, 1, 1), Decimal("100.00"), EffectiveAmountEntrySource.AUTOMATED
        )
        assert entry.source == EffectiveAmountEntrySource.AUTOMATED

    def test_effective_date_is_preserved(self, effective_amount: EffectiveAmount) -> None:
        d = date(2024, 6, 15)
        entry = effective_amount.offer_value(d, Decimal("500.00"))
        assert entry.effective_date == d

    def test_value_is_preserved(self, effective_amount: EffectiveAmount) -> None:
        v = Decimal("1234.5678901234")
        entry = effective_amount.offer_value(date(2024, 1, 1), v)
        assert entry.value == v

    def test_allows_duplicate_effective_dates(self, effective_amount: EffectiveAmount) -> None:
        """Multiple entries may share an effective_date; insertion order distinguishes them."""
        d = date(2024, 1, 1)
        effective_amount.offer_value(d, Decimal("100.00"))
        effective_amount.offer_value(d, Decimal("200.00"))
        assert len(effective_amount.entries) == 2

    def test_returns_entry_with_correct_attributes(self, effective_amount: EffectiveAmount) -> None:
        d = date(2024, 3, 31)
        v = Decimal("9999.99")
        entry = effective_amount.offer_value(d, v, EffectiveAmountEntrySource.AUTOMATED)
        assert entry.effective_date == d
        assert entry.value == v
        assert entry.source == EffectiveAmountEntrySource.AUTOMATED
        assert entry.date_created == date.today()


# ── latest_value_as_of ────────────────────────────────────────────────────────


class TestLatestValueAsOf:
    """EffectiveAmount.latest_value_as_of() returns the most recently inserted eligible entry."""

    def test_returns_none_when_no_entries(self, effective_amount: EffectiveAmount) -> None:
        assert effective_amount.latest_value_as_of(date(2024, 1, 1)) is None

    def test_returns_none_when_all_entries_are_after_date(
        self, effective_amount: EffectiveAmount
    ) -> None:
        effective_amount.offer_value(date(2024, 6, 1), Decimal("100.00"))
        assert effective_amount.latest_value_as_of(date(2024, 1, 1)) is None

    def test_returns_value_on_exact_effective_date(self, effective_amount: EffectiveAmount) -> None:
        d = date(2024, 3, 15)
        effective_amount.offer_value(d, Decimal("500.00"))
        assert effective_amount.latest_value_as_of(d) == Decimal("500.00")

    def test_returns_value_when_entry_is_before_date(
        self, effective_amount: EffectiveAmount
    ) -> None:
        effective_amount.offer_value(date(2024, 1, 1), Decimal("100.00"))
        assert effective_amount.latest_value_as_of(date(2024, 12, 31)) == Decimal("100.00")

    def test_returns_latest_eligible_entry(self, effective_amount: EffectiveAmount) -> None:
        effective_amount.offer_value(date(2024, 1, 1), Decimal("100.00"))
        effective_amount.offer_value(date(2024, 6, 1), Decimal("200.00"))
        effective_amount.offer_value(date(2025, 1, 1), Decimal("300.00"))
        assert effective_amount.latest_value_as_of(date(2024, 9, 1)) == Decimal("200.00")

    def test_excludes_entries_strictly_after_date(self, effective_amount: EffectiveAmount) -> None:
        effective_amount.offer_value(date(2024, 1, 1), Decimal("100.00"))
        effective_amount.offer_value(date(2024, 6, 1), Decimal("200.00"))
        assert effective_amount.latest_value_as_of(date(2024, 3, 1)) == Decimal("100.00")

    def test_last_inserted_wins_on_same_effective_date(
        self, effective_amount: EffectiveAmount
    ) -> None:
        """When entries share an effective_date, the last inserted supersedes."""
        d = date(2024, 1, 1)
        effective_amount.offer_value(d, Decimal("100.00"))  # inserted first
        effective_amount.offer_value(d, Decimal("999.00"))  # inserted last — supersedes
        assert effective_amount.latest_value_as_of(d) == Decimal("999.00")

    def test_insertion_order_not_effective_date_determines_recency(
        self, effective_amount: EffectiveAmount
    ) -> None:
        """Only the eligible entries' insertion order matters, not their effective dates."""
        effective_amount.offer_value(date(2024, 1, 1), Decimal("100.00"))  # eligible
        effective_amount.offer_value(date(2024, 6, 1), Decimal("200.00"))  # after cutoff, excluded
        assert effective_amount.latest_value_as_of(date(2024, 3, 1)) == Decimal("100.00")

    def test_single_entry_exactly_on_query_date_is_included(
        self, effective_amount: EffectiveAmount
    ) -> None:
        effective_amount.offer_value(date(2024, 12, 31), Decimal("42.00"))
        assert effective_amount.latest_value_as_of(date(2024, 12, 31)) == Decimal("42.00")


# ── Database round-trip ───────────────────────────────────────────────────────


class TestDatabaseRoundTrip:
    """Schema correctness and FK integrity checks using in-memory SQLite."""

    def test_effective_amount_and_entries_persist_and_reload(self, db_session: Session) -> None:
        ea = EffectiveAmount()
        ea.offer_value(date(2024, 1, 1), Decimal("100.00"))
        ea.offer_value(date(2024, 6, 1), Decimal("200.00"))
        db_session.add(ea)
        db_session.flush()

        db_session.expire(ea)
        reloaded = db_session.get(EffectiveAmount, ea.id)
        assert reloaded is not None
        assert len(reloaded.entries) == 2
        assert reloaded.latest_value_as_of(date(2024, 12, 31)) == Decimal("200.00")

    def test_entries_are_ordered_by_insertion_from_db(self, db_session: Session) -> None:
        ea = EffectiveAmount()
        ea.offer_value(date(2024, 3, 1), Decimal("300.00"))
        ea.offer_value(date(2024, 1, 1), Decimal("100.00"))
        ea.offer_value(date(2024, 2, 1), Decimal("200.00"))
        db_session.add(ea)
        db_session.flush()
        db_session.expire(ea)

        reloaded = db_session.get(EffectiveAmount, ea.id)
        assert reloaded is not None
        # Entries ordered by id (insertion order); effective_dates are not sequential
        ids = [e.id for e in reloaded.entries]
        assert ids == sorted(ids)

    def test_date_created_round_trips(self, db_session: Session) -> None:
        ea = EffectiveAmount()
        ea.offer_value(date(2024, 1, 1), Decimal("100.00"))
        db_session.add(ea)
        db_session.flush()
        db_session.expire(ea)

        reloaded = db_session.get(EffectiveAmount, ea.id)
        assert reloaded is not None
        assert reloaded.entries[0].date_created == date.today()

    def test_source_enum_round_trips(self, db_session: Session) -> None:
        ea = EffectiveAmount()
        ea.offer_value(date(2024, 1, 1), Decimal("50.00"), EffectiveAmountEntrySource.AUTOMATED)
        db_session.add(ea)
        db_session.flush()
        db_session.expire(ea)

        reloaded = db_session.get(EffectiveAmount, ea.id)
        assert reloaded is not None
        assert reloaded.entries[0].source == EffectiveAmountEntrySource.AUTOMATED
