"""Per-person annual cash flow profile."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from personal_finance.domain.base import Base
from personal_finance.domain.effective_amount import EffectiveAmount
from personal_finance.domain.person import Person

if TYPE_CHECKING:
    from personal_finance.domain.goals.goal import Goal


class PersonalCashFlowProfile(Base):
    """Per-person annual financial breakdown.

    All monetary fields are EffectiveAmount timelines so their values can change over time.
    ``auto_rrsp_goal`` is nullable at the DB level; the service layer must reject
    any save where ``auto_rrsp_deducted`` or ``rrsp_matched`` have entries > 0
    but ``auto_rrsp_goal`` is null.
    """

    __tablename__ = "personal_cash_flow_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"))
    date_modified: Mapped[date] = mapped_column(Date, default=date.today)
    gross_annual_income_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    net_annual_income_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    gross_bonus_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    net_bonus_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    auto_rrsp_deducted_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    rrsp_matched_id: Mapped[int] = mapped_column(ForeignKey("effective_amount_timelines.id"))
    auto_rrsp_goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id"), nullable=True)

    person: Mapped[Person] = relationship(back_populates="cash_flow_profile")
    gross_annual_income: Mapped[EffectiveAmount] = relationship(
        foreign_keys=[gross_annual_income_id]
    )
    net_annual_income: Mapped[EffectiveAmount] = relationship(foreign_keys=[net_annual_income_id])
    gross_bonus: Mapped[EffectiveAmount] = relationship(foreign_keys=[gross_bonus_id])
    net_bonus: Mapped[EffectiveAmount] = relationship(foreign_keys=[net_bonus_id])
    auto_rrsp_deducted: Mapped[EffectiveAmount] = relationship(foreign_keys=[auto_rrsp_deducted_id])
    rrsp_matched: Mapped[EffectiveAmount] = relationship(foreign_keys=[rrsp_matched_id])
    auto_rrsp_goal: Mapped[Goal | None] = relationship(foreign_keys=[auto_rrsp_goal_id])

    def __init__(self, **kwargs: object) -> None:
        """Ensure fresh EffectiveAmount timelines are created for all income fields when omitted."""
        for field in (
            "gross_annual_income",
            "net_annual_income",
            "gross_bonus",
            "net_bonus",
            "auto_rrsp_deducted",
            "rrsp_matched",
        ):
            if field not in kwargs:
                kwargs[field] = EffectiveAmount()
        super().__init__(**kwargs)
