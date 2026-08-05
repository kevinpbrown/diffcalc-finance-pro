"""Cash flow core service — domain operations for cash flow data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from personal_finance.domain.cash_flow.contribution import AutomatedContribution
from personal_finance.domain.cash_flow.expense import (
    HouseholdExpense,
    HouseholdExpenseClassification,
    HouseholdExpenseFrequency,
    HouseholdExpenseSource,
)
from personal_finance.domain.cash_flow.profile import PersonalCashFlowProfile
from personal_finance.domain.person import Person

if TYPE_CHECKING:
    from personal_finance.domain.balance_sheet.account import Account

__all__ = ["CashFlowService"]


class CashFlowService:
    """Domain operations for the Cash Flow module.

    Session-per-application-operation: this service holds no session state.
    Every method that touches the database takes ``session`` as an explicit
    first parameter, supplied by the calling application-service method, which
    owns that session's lifetime and commit/rollback via ``db.transaction()``.
    Methods do not call ``session.commit()`` themselves; they use ``flush()``
    only where a subsequent step in the same call needs a generated primary key.
    """

    # ── CF-OP-1 support ────────────────────────────────────────────────────────

    def list_person_profiles(self, session: Session) -> list[PersonalCashFlowProfile]:
        """Return all PersonalCashFlowProfile records, ordered by person primary key.

        Eagerly loads the ``person`` relationship so callers can read
        ``profile.person.name`` without a second round-trip.

        Args:
            session: The SQLAlchemy session for this operation.

        Returns:
            All profiles in person insertion order.
        """
        return (
            session.query(PersonalCashFlowProfile)
            .join(PersonalCashFlowProfile.person)
            .order_by(Person.id)
            .all()
        )

    # ── CF-OP-2 ────────────────────────────────────────────────────────────────

    def update_person_profile(
        self,
        session: Session,
        profile_id: int,
        effective_date: date,
        gross_annual_income: Decimal,
        net_annual_income: Decimal,
        gross_bonus: Decimal,
        net_bonus: Decimal,
        auto_rrsp_deducted: Decimal,
        rrsp_matched: Decimal,
        auto_rrsp_goal_id: int | None,
    ) -> None:
        """CF-OP-2: Update a person's cash flow profile.

        Appends new EffectiveAmountEntry items to each temporal field and updates
        the scalar ``auto_rrsp_goal_id`` linkage.

        Args:
            session: The SQLAlchemy session for this operation.
            profile_id: Primary key of the PersonalCashFlowProfile to update.
            effective_date: The date from which the new values are in effect.
            gross_annual_income: Annual gross income.
            net_annual_income: Annual net (take-home) income.
            gross_bonus: Annual gross bonus.
            net_bonus: Annual net bonus.
            auto_rrsp_deducted: Annual automated RRSP contribution deducted from payroll.
            rrsp_matched: Annual employer RRSP match contribution.
            auto_rrsp_goal_id: Goal that RRSP contributions target; required when
                either RRSP field is > 0.

        Raises:
            ValueError: If the profile does not exist, invariants are violated, or
                a goal is required but not provided.
        """
        profile = session.get(PersonalCashFlowProfile, profile_id)
        if profile is None:
            raise ValueError(f"PersonalCashFlowProfile {profile_id!r} not found")

        _D0 = Decimal("0")

        if rrsp_matched > _D0 and auto_rrsp_deducted == _D0:
            raise ValueError("rrsp_matched > 0 requires auto_rrsp_deducted > 0")

        if (auto_rrsp_deducted > _D0 or rrsp_matched > _D0) and auto_rrsp_goal_id is None:
            raise ValueError(
                "auto_rrsp_goal_id is required when auto_rrsp_deducted or rrsp_matched > 0"
            )

        profile.gross_annual_income.offer_value(effective_date, gross_annual_income)
        profile.net_annual_income.offer_value(effective_date, net_annual_income)
        profile.gross_bonus.offer_value(effective_date, gross_bonus)
        profile.net_bonus.offer_value(effective_date, net_bonus)
        profile.auto_rrsp_deducted.offer_value(effective_date, auto_rrsp_deducted)
        profile.rrsp_matched.offer_value(effective_date, rrsp_matched)

        profile.auto_rrsp_goal_id = auto_rrsp_goal_id
        profile.date_modified = effective_date

    # ── CF-OP-3 support ────────────────────────────────────────────────────────

    def list_household_expenses(self, session: Session, as_of: date) -> list[HouseholdExpense]:
        """Return all active HouseholdExpense records as of ``as_of``.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Session effective date.

        Returns:
            Active expenses ordered by classification then insertion order.
        """
        all_expenses = (
            session.query(HouseholdExpense)
            .order_by(HouseholdExpense.classification, HouseholdExpense.id)
            .all()
        )
        return [e for e in all_expenses if e.is_active(as_of)]

    # ── CF-OP-4 ────────────────────────────────────────────────────────────────

    def create_household_expense(
        self,
        session: Session,
        name: str,
        amount: Decimal,
        classification: HouseholdExpenseClassification,
        source: HouseholdExpenseSource,
        frequency: HouseholdExpenseFrequency,
        effective_date: date,
    ) -> int:
        """CF-OP-4: Persist a new household expense.

        Args:
            session: The SQLAlchemy session for this operation.
            name: Display label for the expense.
            amount: Monthly amount.
            classification: HOME, AUTO, or OTHER.
            source: BANK, CREDIT, or OTHER.
            frequency: REGULAR or IRREGULAR.
            effective_date: Session effective date.

        Returns:
            Primary key of the newly created expense.
        """
        expense = HouseholdExpense(
            name=name,
            date_created=effective_date,
            date_effective=effective_date,
            date_modified=effective_date,
            classification=classification,
            source=source,
            frequency=frequency,
        )
        expense.amount.offer_value(effective_date, amount)
        session.add(expense)
        session.flush()
        return expense.id

    # ── CF-OP-5 ────────────────────────────────────────────────────────────────

    def update_household_expense(
        self,
        session: Session,
        expense_id: int,
        name: str,
        amount: Decimal,
        classification: HouseholdExpenseClassification,
        source: HouseholdExpenseSource,
        frequency: HouseholdExpenseFrequency,
        effective_date: date,
    ) -> None:
        """CF-OP-5: Update all scalar fields and record a new temporal amount.

        Args:
            session: The SQLAlchemy session for this operation.
            expense_id: Primary key of the expense to update.
            name: Updated display label.
            amount: New monthly amount.
            classification: Updated classification.
            source: Updated payment source.
            frequency: Updated recurrence.
            effective_date: Session effective date.

        Raises:
            ValueError: If no expense with ``expense_id`` exists.
        """
        expense = session.get(HouseholdExpense, expense_id)
        if expense is None:
            raise ValueError(f"HouseholdExpense {expense_id!r} not found")
        expense.name = name
        expense.classification = classification
        expense.source = source
        expense.frequency = frequency
        expense.date_modified = effective_date
        expense.amount.offer_value(effective_date, amount)

    def update_household_expense_amount(
        self,
        session: Session,
        expense_id: int,
        amount: Decimal,
        effective_date: date,
    ) -> None:
        """CF-OP-5 (inline amount edit): Record a new temporal amount only.

        Args:
            session: The SQLAlchemy session for this operation.
            expense_id: Primary key of the expense to update.
            amount: New monthly amount.
            effective_date: Session effective date.

        Raises:
            ValueError: If no expense with ``expense_id`` exists.
        """
        expense = session.get(HouseholdExpense, expense_id)
        if expense is None:
            raise ValueError(f"HouseholdExpense {expense_id!r} not found")
        expense.amount.offer_value(effective_date, amount)

    # ── CF-OP-6 ────────────────────────────────────────────────────────────────

    def discard_household_expense(
        self, session: Session, expense_id: int, effective_date: date
    ) -> None:
        """CF-OP-6: Soft-delete a household expense.

        Args:
            session: The SQLAlchemy session for this operation.
            expense_id: Primary key of the expense to discard.
            effective_date: Session effective date.

        Raises:
            ValueError: If no expense with ``expense_id`` exists.
        """
        expense = session.get(HouseholdExpense, expense_id)
        if expense is None:
            raise ValueError(f"HouseholdExpense {expense_id!r} not found")
        expense.discard(effective_date)

    # ── CF-OP-7 support ────────────────────────────────────────────────────────

    def list_accounts(self, session: Session, as_of: date) -> list[Account]:
        """Return all active accounts for dropdown population.

        Performs a plain name/ID query without the async pricing overhead
        required by ``BalanceSheetService.list_all_accounts``.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Session effective date.

        Returns:
            Active accounts ordered by primary key.
        """
        from personal_finance.domain.balance_sheet.account import Account  # noqa: PLC0415

        all_accounts = session.query(Account).order_by(Account.id).all()
        return [a for a in all_accounts if a.is_active(as_of)]

    def list_automated_contributions(
        self, session: Session, as_of: date
    ) -> list[AutomatedContribution]:
        """Return all active AutomatedContribution records.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Session effective date.

        Returns:
            Active contributions ordered by primary key, with
            ``source_account``, ``destination_account``, and ``target_goal``
            relationships eagerly accessible.
        """
        all_contribs = session.query(AutomatedContribution).order_by(AutomatedContribution.id).all()
        return [c for c in all_contribs if c.is_active(as_of)]

    # ── CF-OP-8 ────────────────────────────────────────────────────────────────

    def create_automated_contribution(
        self,
        session: Session,
        name: str,
        amount: Decimal,
        source_account_id: int,
        destination_account_id: int,
        target_goal_id: int,
        effective_date: date,
    ) -> int:
        """CF-OP-8: Persist a new automated contribution.

        Args:
            session: The SQLAlchemy session for this operation.
            name: Display label.
            amount: Monthly amount.
            source_account_id: Primary key of the source account.
            destination_account_id: Primary key of the destination account.
            target_goal_id: Primary key of the target goal.
            effective_date: Session effective date.

        Returns:
            Primary key of the newly created contribution.
        """
        contribution = AutomatedContribution(
            name=name,
            date_created=effective_date,
            date_effective=effective_date,
            date_modified=effective_date,
            source_account_id=source_account_id,
            destination_account_id=destination_account_id,
            target_goal_id=target_goal_id,
        )
        contribution.amount.offer_value(effective_date, amount)
        session.add(contribution)
        session.flush()
        return contribution.id

    # ── CF-OP-9 ────────────────────────────────────────────────────────────────

    def update_automated_contribution(
        self,
        session: Session,
        contribution_id: int,
        name: str,
        amount: Decimal,
        source_account_id: int,
        destination_account_id: int,
        target_goal_id: int,
        effective_date: date,
    ) -> None:
        """CF-OP-9: Update all fields of an existing automated contribution.

        Args:
            session: The SQLAlchemy session for this operation.
            contribution_id: Primary key of the contribution to update.
            name: Updated display label.
            amount: New monthly amount.
            source_account_id: Updated source account.
            destination_account_id: Updated destination account.
            target_goal_id: Updated target goal.
            effective_date: Session effective date.

        Raises:
            ValueError: If no contribution with ``contribution_id`` exists.
        """
        contribution = session.get(AutomatedContribution, contribution_id)
        if contribution is None:
            raise ValueError(f"AutomatedContribution {contribution_id!r} not found")
        contribution.name = name
        contribution.source_account_id = source_account_id
        contribution.destination_account_id = destination_account_id
        contribution.target_goal_id = target_goal_id
        contribution.date_modified = effective_date
        contribution.amount.offer_value(effective_date, amount)

    # ── CF-OP-10 ───────────────────────────────────────────────────────────────

    def discard_automated_contribution(
        self, session: Session, contribution_id: int, effective_date: date
    ) -> None:
        """CF-OP-10: Soft-delete an automated contribution.

        Args:
            session: The SQLAlchemy session for this operation.
            contribution_id: Primary key of the contribution to discard.
            effective_date: Session effective date.

        Raises:
            ValueError: If no contribution with ``contribution_id`` exists.
        """
        contribution = session.get(AutomatedContribution, contribution_id)
        if contribution is None:
            raise ValueError(f"AutomatedContribution {contribution_id!r} not found")
        contribution.discard(effective_date)
