"""Person domain model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from personal_finance.domain.base import Base

if TYPE_CHECKING:
    from personal_finance.domain.cash_flow.profile import PersonalCashFlowProfile


class Person(Base):
    """An individual whose finances are tracked.

    Persons are seeded manually in the database and exist solely for referential
    integrity. They are never created or modified through the application UI.
    """

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    cash_flow_profile: Mapped[PersonalCashFlowProfile] = relationship(
        "PersonalCashFlowProfile",
        uselist=False,
        back_populates="person",
        cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs: object) -> None:
        """Auto-create a PersonalCashFlowProfile unless one is provided."""
        if "cash_flow_profile" not in kwargs:
            from personal_finance.domain.cash_flow.profile import (
                PersonalCashFlowProfile,  # noqa: PLC0415
            )

            kwargs["cash_flow_profile"] = PersonalCashFlowProfile()
        super().__init__(**kwargs)
