"""Shared SQLAlchemy declarative base, global decimal context, and domain mixins.

All ORM models must inherit from Base defined here. Importing this module also
configures the global decimal context to 28-digit precision with ROUND_HALF_UP.
"""

from __future__ import annotations

import decimal
from datetime import date

from sqlalchemy import Date
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

decimal.getcontext().prec = 28
decimal.getcontext().rounding = decimal.ROUND_HALF_UP


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class Discardable:
    """Mixin for domain entities that support soft-deletion against the financial timeline.

    Provides ``date_effective``, ``date_modified``, ``date_discarded`` columns, an
    ``is_discarded`` convenience property, and a ``discard(as_of)`` method.

    All entity classes that support soft-deletion must inherit this mixin. No
    service, application, or UI code may set ``date_discarded`` directly; all
    soft-deletes must go through ``discard()``.

    Column semantics:
    - ``date_effective``: financial effective date when the entity enters the timeline;
      set from the session's global effective date at creation time.
    - ``date_modified``: wall-clock audit timestamp; initialised to ``date_created``
      on insert and updated whenever a scalar field on the entity changes. Mutations
      to owned EffectiveAmount timelines do NOT update this field.
    - ``date_discarded``: financial effective date when the entity leaves the timeline;
      null until discarded.
    """

    date_effective: Mapped[date] = mapped_column(Date, default=date.today)
    date_modified: Mapped[date] = mapped_column(Date, default=date.today)
    date_discarded: Mapped[date | None] = mapped_column(Date, nullable=True)

    def is_active(self, as_of: date) -> bool:
        """Return True when the entity is on the timeline as of ``as_of``.

        An entity is active when ``date_effective <= as_of`` and it has not yet
        been discarded (``date_discarded`` is null or strictly after ``as_of``).
        """
        return self.date_effective <= as_of and (
            self.date_discarded is None or self.date_discarded > as_of
        )

    @property
    def is_discarded(self) -> bool:
        """Return True if this entity has been soft-deleted at any point."""
        return self.date_discarded is not None

    def discard(self, as_of: date) -> None:
        """Soft-delete this entity as of the given financial effective date.

        Rules:
        1. ``as_of`` must be on or after ``date_effective``.
        2. If not yet discarded: sets ``date_discarded = as_of``.
        3. If already discarded and ``as_of < date_discarded``: moves the discard
           date earlier (correction case — user rewound the effective date).
        4. If already discarded and ``as_of >= date_discarded``: raises — the entity
           is already discarded on or before ``as_of``.

        Raises:
            ValueError: If ``as_of < date_effective`` or the entity is already
                discarded on or before ``as_of``.
        """
        if as_of < self.date_effective:
            raise ValueError(
                f"{type(self).__name__} cannot be discarded before its "
                f"effective date ({self.date_effective})"
            )
        if self.date_discarded is not None and as_of >= self.date_discarded:
            raise ValueError(
                f"{type(self).__name__} is already discarded as of {self.date_discarded}"
            )
        self.date_discarded = as_of
