"""EffectiveAmount timeline domain model."""

from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from personal_finance.domain.base import Base


class EffectiveAmountEntrySource(enum.Enum):
    """Origin of an EffectiveAmountEntry value."""

    DATA_ENTRY = "DATA_ENTRY"
    AUTOMATED = "AUTOMATED"


class EffectiveAmountEntry(Base):
    """A single immutable value on an EffectiveAmount timeline.

    Once an EffectiveAmountEntry is associated with a session, its fields must
    not be mutated. All changes to a timeline are expressed by appending a new
    entry via ``EffectiveAmount.offer_value()``. The entry's primary key
    (auto-increment) establishes insertion order; when entries share an
    ``effective_date``, the highest ``id`` is authoritative.
    """

    __tablename__ = "effective_amount_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    effective_amount_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    effective_date: Mapped[date] = mapped_column(Date)
    date_created: Mapped[date] = mapped_column(Date)
    source: Mapped[EffectiveAmountEntrySource] = mapped_column(
        Enum(EffectiveAmountEntrySource, native_enum=False, length=20)
    )
    value: Mapped[Decimal] = mapped_column(Numeric(precision=28, scale=10))

    timeline: Mapped[EffectiveAmount] = relationship(back_populates="entries")


class EffectiveAmount(Base):
    """A temporal timeline of monetary values.

    Maintains an ordered sequence of EffectiveAmountEntry items. The active
    value as of a given date is the most recently inserted entry whose
    ``effective_date`` is on or before the queried date. Entries are always
    appended, never replaced.
    """

    __tablename__ = "effective_amount_timelines"

    id: Mapped[int] = mapped_column(primary_key=True)
    entries: Mapped[list[EffectiveAmountEntry]] = relationship(
        back_populates="timeline",
        order_by=EffectiveAmountEntry.id,
        cascade="all, delete-orphan",
    )

    def latest_value_as_of(self, effective_date: date) -> Decimal | None:
        """Return the most recently inserted value on or before effective_date.

        Args:
            effective_date: The date ceiling for entry eligibility.

        Returns:
            The Decimal value, or None if no entries fall on or before the date.
        """
        eligible = [e for e in self.entries if e.effective_date <= effective_date]
        return eligible[-1].value if eligible else None

    def offer_value(
        self,
        effective_date: date,
        value: Decimal,
        source: EffectiveAmountEntrySource = EffectiveAmountEntrySource.DATA_ENTRY,
    ) -> EffectiveAmountEntry:
        """Append a new entry to this timeline, always inserting rather than replacing.

        The entry's auto-increment primary key establishes its position in the
        timeline. When multiple entries share an effective_date, the one with
        the highest id (most recently inserted) is authoritative.

        Args:
            effective_date: The date from which this value is in effect.
            value: The monetary amount.
            source: The origin of this value. Defaults to DATA_ENTRY.

        Returns:
            The newly created EffectiveAmountEntry (not yet persisted to the database).
        """
        entry = EffectiveAmountEntry(
            effective_date=effective_date,
            date_created=date.today(),
            source=source,
            value=value,
        )
        self.entries.append(entry)
        return entry
