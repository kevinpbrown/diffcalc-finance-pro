"""Cash flow application service — BFF for the Cash Flow screens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from personal_finance.db import transaction
from personal_finance.domain.cash_flow.expense import (
    HouseholdExpenseClassification,
    HouseholdExpenseFrequency,
    HouseholdExpenseSource,
)
from personal_finance.service.core.cash_flow_service import CashFlowService
from personal_finance.service.core.goal_service import GoalService

__all__ = [
    "AccountOption",
    "CashFlowAppService",
    "ContributionRow",
    "ExpenseRow",
    "ExpenseSummaryData",
    "ExpensesViewData",
    "GoalContributionLine",
    "GoalOption",
    "PersonNavItem",
    "PersonProfileFormData",
    "ReportViewData",
    "RrspDeductionLine",
]

_D0 = Decimal("0")


@dataclass(frozen=True)
class ExpenseRow:
    """One active household expense for the F-13 right pane.

    Attributes:
        expense_id: Primary key of the HouseholdExpense.
        name: Display label.
        amount: Monthly amount as of the session effective date.
        source: Payment source (BANK / CREDIT / OTHER).
        frequency: Recurrence (REGULAR / IRREGULAR).
        classification: Group (HOME / AUTO / OTHER).
    """

    expense_id: int
    name: str
    amount: Decimal
    source: HouseholdExpenseSource
    frequency: HouseholdExpenseFrequency
    classification: HouseholdExpenseClassification


@dataclass(frozen=True)
class ExpenseSummaryData:
    """Cross-tab totals for the F-13 summary table (all monthly amounts).

    Attributes:
        bank_regular: Total of BANK × REGULAR expenses.
        bank_irregular: Total of BANK × IRREGULAR expenses.
        credit_regular: Total of CREDIT × REGULAR expenses.
        credit_irregular: Total of CREDIT × IRREGULAR expenses.
        other_regular: Total of OTHER × REGULAR expenses.
        other_irregular: Total of OTHER × IRREGULAR expenses.
    """

    bank_regular: Decimal
    bank_irregular: Decimal
    credit_regular: Decimal
    credit_irregular: Decimal
    other_regular: Decimal
    other_irregular: Decimal


@dataclass(frozen=True)
class ExpensesViewData:
    """All data needed to render the F-13 expenses screen.

    Attributes:
        home: Active HOME expenses in insertion order.
        auto: Active AUTO expenses in insertion order.
        other: Active OTHER expenses in insertion order.
        summary: Cross-tab totals.
    """

    home: list[ExpenseRow]
    auto: list[ExpenseRow]
    other: list[ExpenseRow]
    summary: ExpenseSummaryData


@dataclass(frozen=True)
class PersonNavItem:
    """One person entry in the cash flow left-nav pane.

    Attributes:
        profile_id: Primary key of the ``PersonalCashFlowProfile``.
        person_id: Primary key of the associated ``Person``.
        person_name: Display name shown in the nav pane.
    """

    profile_id: int
    person_id: int
    person_name: str


@dataclass(frozen=True)
class GoalOption:
    """One entry in the RRSP goal dropdown.

    Attributes:
        goal_id: Primary key of the ``Goal``.
        name: Display name of the goal.
    """

    goal_id: int
    name: str


@dataclass(frozen=True)
class AccountOption:
    """One entry in the account dropdowns (From / To account in F-15).

    Attributes:
        account_id: Primary key of the ``Account``.
        name: Display name of the account.
    """

    account_id: int
    name: str


@dataclass(frozen=True)
class ContributionRow:
    """One automated contribution row for the F-14 report and F-15 dialog.

    Attributes:
        contribution_id: Primary key of the ``AutomatedContribution``.
        name: Display label.
        amount: Monthly amount as of the session effective date.
        source_account_id: Primary key of the source account.
        destination_account_id: Primary key of the destination account.
        target_goal_id: Primary key of the target goal.
    """

    contribution_id: int
    name: str
    amount: Decimal
    source_account_id: int
    destination_account_id: int
    target_goal_id: int


@dataclass(frozen=True)
class RrspDeductionLine:
    """One 'Less Automated RRSP for <Name>' line in the F-14 gross-to-net reconciliation.

    Only emitted for persons whose ``(auto_rrsp_deducted + rrsp_matched) > 0``.

    Attributes:
        person_name: Name of the person.
        monthly_amount: ``(auto_rrsp_deducted + rrsp_matched) / 12``.
    """

    person_name: str
    monthly_amount: Decimal


@dataclass(frozen=True)
class GoalContributionLine:
    """One row in the F-14 Goal Contributions (Annualized) table.

    Aggregates all contributions (RRSP + automated) targeting the same goal.

    Attributes:
        goal_name: Display name of the goal.
        annual_amount: Total annual contributions to this goal.
    """

    goal_name: str
    annual_amount: Decimal


@dataclass(frozen=True)
class ReportViewData:
    """All data needed to render the F-14 Household Cash Flow Report.

    Attributes:
        gross_monthly: Total household monthly gross income (sum / 12).
        rrsp_deduction_lines: Per-person RRSP deduction lines (only when > 0).
        taxes_other_monthly: Implicit remainder: gross_monthly - sum(rrsp) - net_monthly.
        net_monthly: Total household monthly net (take-home) income (sum / 12).
        avg_monthly_expenses: Sum of all active household expense amounts.
        contributions: Active automated contributions in insertion order.
        total_monthly_retained: net_monthly - avg_monthly_expenses - sum(contributions).
        total_annual_retained: total_monthly_retained * 12.
        total_net_bonus: Sum of net_bonus across all persons (annual).
        final_annual_retained: total_annual_retained + total_net_bonus.
        gross_annual_total: Sum of gross_annual_income across all persons.
        goal_contributions: Annualized contributions per goal, sorted by goal name.
    """

    gross_monthly: Decimal
    rrsp_deduction_lines: list[RrspDeductionLine]
    taxes_other_monthly: Decimal
    net_monthly: Decimal
    avg_monthly_expenses: Decimal
    contributions: list[ContributionRow]
    total_monthly_retained: Decimal
    total_annual_retained: Decimal
    total_net_bonus: Decimal
    final_annual_retained: Decimal
    gross_annual_total: Decimal
    goal_contributions: list[GoalContributionLine]


@dataclass(frozen=True)
class PersonProfileFormData:
    """Data contract for the F-12 right-pane person profile form.

    All monetary values are annual figures (as stored in the database).
    The F-14 report divides them by 12 for monthly display.

    Attributes:
        profile_id: Primary key of the ``PersonalCashFlowProfile``.
        person_id: Primary key of the ``Person``.
        person_name: Display name of the person.
        gross_annual_income: Annual gross income as of the effective date.
        net_annual_income: Annual net (take-home) income as of the effective date.
        gross_bonus: Annual gross bonus as of the effective date.
        net_bonus: Annual net bonus as of the effective date.
        auto_rrsp_deducted: Annual RRSP deducted from payroll as of the effective date.
        rrsp_matched: Annual employer RRSP match as of the effective date.
        auto_rrsp_goal_id: Goal that RRSP contributions target, or ``None``.
        auto_rrsp_goal_name: Display name of that goal, or ``None``.
    """

    profile_id: int
    person_id: int
    person_name: str
    gross_annual_income: Decimal
    net_annual_income: Decimal
    gross_bonus: Decimal
    net_bonus: Decimal
    auto_rrsp_deducted: Decimal
    rrsp_matched: Decimal
    auto_rrsp_goal_id: int | None
    auto_rrsp_goal_name: str | None


class CashFlowAppService:
    """Application service (BFF) for the Cash Flow module screens.

    Owns the session lifetime for every public method (session-per-application-operation):
    each method opens one session via ``db.transaction()`` for its whole body and
    passes it into every core-service call it makes.

    Args:
        cash_flow_service: Core service for cash flow domain operations.
        goal_service: Core service used for goal dropdown population.
        session_factory: Session factory used to open one session per public method.
    """

    def __init__(
        self,
        cash_flow_service: CashFlowService,
        goal_service: GoalService,
        session_factory: sessionmaker[Session],
    ) -> None:
        """Store injected core services and session factory."""
        self._cf = cash_flow_service
        self._goals = goal_service
        self._session_factory = session_factory

    # ── CF-OP-1: Get Person Profiles ───────────────────────────────────────────

    def get_person_nav_items(self) -> list[PersonNavItem]:
        """CF-OP-1 support: return persons for the left-nav pane.

        Returns:
            One :class:`PersonNavItem` per person, in person insertion order.
        """
        with transaction(self._session_factory) as session:
            return [
                PersonNavItem(
                    profile_id=p.id,
                    person_id=p.person.id,
                    person_name=p.person.name,
                )
                for p in self._cf.list_person_profiles(session)
            ]

    def get_person_profile_form_data(self, profile_id: int, as_of: date) -> PersonProfileFormData:
        """Return the form data for the selected person's profile.

        Args:
            profile_id: Primary key of the ``PersonalCashFlowProfile`` to load.
            as_of: Session effective date for EffectiveAmount lookups.

        Returns:
            A :class:`PersonProfileFormData` ready for the F-12 right pane.

        Raises:
            ValueError: If no profile with ``profile_id`` exists.
        """
        with transaction(self._session_factory) as session:
            profile = next(
                (p for p in self._cf.list_person_profiles(session) if p.id == profile_id),
                None,
            )
            if profile is None:
                raise ValueError(f"PersonalCashFlowProfile {profile_id!r} not found")

            return PersonProfileFormData(
                profile_id=profile.id,
                person_id=profile.person.id,
                person_name=profile.person.name,
                gross_annual_income=profile.gross_annual_income.latest_value_as_of(as_of) or _D0,
                net_annual_income=profile.net_annual_income.latest_value_as_of(as_of) or _D0,
                gross_bonus=profile.gross_bonus.latest_value_as_of(as_of) or _D0,
                net_bonus=profile.net_bonus.latest_value_as_of(as_of) or _D0,
                auto_rrsp_deducted=profile.auto_rrsp_deducted.latest_value_as_of(as_of) or _D0,
                rrsp_matched=profile.rrsp_matched.latest_value_as_of(as_of) or _D0,
                auto_rrsp_goal_id=profile.auto_rrsp_goal_id,
                auto_rrsp_goal_name=profile.auto_rrsp_goal.name if profile.auto_rrsp_goal else None,
            )

    def get_goal_options(self, as_of: date) -> list[GoalOption]:
        """Return active goals for the RRSP goal dropdown.

        Args:
            as_of: Session effective date for active-state evaluation.

        Returns:
            One :class:`GoalOption` per active goal, in insertion order.
        """
        with transaction(self._session_factory) as session:
            return [
                GoalOption(goal_id=g.id, name=g.name)
                for g in self._goals.list_active_goals(session, as_of)
            ]

    # ── CF-OP-2: Update Person Profile ─────────────────────────────────────────

    def update_person_profile(
        self,
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
        """CF-OP-2: Persist updated income and RRSP values for a person.

        Args:
            profile_id: Primary key of the profile to update.
            effective_date: Date from which the new values take effect.
            gross_annual_income: Annual gross income.
            net_annual_income: Annual net (take-home) income.
            gross_bonus: Annual gross bonus.
            net_bonus: Annual net bonus.
            auto_rrsp_deducted: Annual RRSP deducted from payroll.
            rrsp_matched: Annual employer RRSP match.
            auto_rrsp_goal_id: Goal that RRSP contributions target.

        Raises:
            ValueError: Propagated from :class:`CashFlowService` on invariant violations.
        """
        with transaction(self._session_factory) as session:
            self._cf.update_person_profile(
                session,
                profile_id=profile_id,
                effective_date=effective_date,
                gross_annual_income=gross_annual_income,
                net_annual_income=net_annual_income,
                gross_bonus=gross_bonus,
                net_bonus=net_bonus,
                auto_rrsp_deducted=auto_rrsp_deducted,
                rrsp_matched=rrsp_matched,
                auto_rrsp_goal_id=auto_rrsp_goal_id,
            )

    # ── CF-OP-3: Get Expenses View Data ────────────────────────────────────────

    def get_expenses_view_data(self, as_of: date) -> ExpensesViewData:
        """CF-OP-3: Return all active expenses grouped by classification, with summary.

        Args:
            as_of: Session effective date.

        Returns:
            :class:`ExpensesViewData` ready for the F-13 right pane.
        """
        with transaction(self._session_factory) as session:
            expenses = self._cf.list_household_expenses(session, as_of)

            rows = [
                ExpenseRow(
                    expense_id=e.id,
                    name=e.name,
                    amount=e.amount.latest_value_as_of(as_of) or _D0,
                    source=e.source,
                    frequency=e.frequency,
                    classification=e.classification,
                )
                for e in expenses
            ]

            home = [r for r in rows if r.classification == HouseholdExpenseClassification.HOME]
            auto = [r for r in rows if r.classification == HouseholdExpenseClassification.AUTO]
            other = [r for r in rows if r.classification == HouseholdExpenseClassification.OTHER]

            summary = self._compute_summary(rows)
            return ExpensesViewData(home=home, auto=auto, other=other, summary=summary)

    def _compute_summary(self, rows: list[ExpenseRow]) -> ExpenseSummaryData:
        def _total(src: HouseholdExpenseSource, freq: HouseholdExpenseFrequency) -> Decimal:
            return sum(
                (r.amount for r in rows if r.source == src and r.frequency == freq),
                _D0,
            )

        return ExpenseSummaryData(
            bank_regular=_total(HouseholdExpenseSource.BANK, HouseholdExpenseFrequency.REGULAR),
            bank_irregular=_total(HouseholdExpenseSource.BANK, HouseholdExpenseFrequency.IRREGULAR),
            credit_regular=_total(HouseholdExpenseSource.CREDIT, HouseholdExpenseFrequency.REGULAR),
            credit_irregular=_total(
                HouseholdExpenseSource.CREDIT, HouseholdExpenseFrequency.IRREGULAR
            ),
            other_regular=_total(HouseholdExpenseSource.OTHER, HouseholdExpenseFrequency.REGULAR),
            other_irregular=_total(
                HouseholdExpenseSource.OTHER, HouseholdExpenseFrequency.IRREGULAR
            ),
        )

    # ── CF-OP-4: Create Expense ────────────────────────────────────────────────

    def create_expense(
        self,
        name: str,
        amount: Decimal,
        classification: HouseholdExpenseClassification,
        source: HouseholdExpenseSource,
        frequency: HouseholdExpenseFrequency,
        as_of: date,
    ) -> int:
        """CF-OP-4: Create a new household expense.

        Args:
            name: Display label (must be non-empty after stripping).
            amount: Monthly amount.
            classification: HOME, AUTO, or OTHER.
            source: BANK, CREDIT, or OTHER.
            frequency: REGULAR or IRREGULAR.
            as_of: Session effective date.

        Returns:
            Primary key of the newly created expense.

        Raises:
            ValueError: If ``name`` is empty.
        """
        name = name.strip()
        if not name:
            raise ValueError("Expense name cannot be empty.")
        with transaction(self._session_factory) as session:
            return self._cf.create_household_expense(
                session,
                name=name,
                amount=amount,
                classification=classification,
                source=source,
                frequency=frequency,
                effective_date=as_of,
            )

    # ── CF-OP-5: Update Expense ────────────────────────────────────────────────

    def update_expense(
        self,
        expense_id: int,
        name: str,
        amount: Decimal,
        classification: HouseholdExpenseClassification,
        source: HouseholdExpenseSource,
        frequency: HouseholdExpenseFrequency,
        as_of: date,
    ) -> None:
        """CF-OP-5: Update all fields of an existing expense.

        Args:
            expense_id: Primary key of the expense to update.
            name: Updated display label (must be non-empty after stripping).
            amount: New monthly amount.
            classification: Updated classification.
            source: Updated payment source.
            frequency: Updated recurrence.
            as_of: Session effective date.

        Raises:
            ValueError: If ``name`` is empty or expense not found.
        """
        name = name.strip()
        if not name:
            raise ValueError("Expense name cannot be empty.")
        with transaction(self._session_factory) as session:
            self._cf.update_household_expense(
                session,
                expense_id=expense_id,
                name=name,
                amount=amount,
                classification=classification,
                source=source,
                frequency=frequency,
                effective_date=as_of,
            )

    def update_expense_amount(
        self,
        expense_id: int,
        amount: Decimal,
        as_of: date,
    ) -> None:
        """CF-OP-5 (inline amount only): Record a new temporal amount.

        Args:
            expense_id: Primary key of the expense to update.
            amount: New monthly amount.
            as_of: Session effective date.

        Raises:
            ValueError: If expense not found.
        """
        with transaction(self._session_factory) as session:
            self._cf.update_household_expense_amount(
                session,
                expense_id=expense_id,
                amount=amount,
                effective_date=as_of,
            )

    # ── CF-OP-6: Discard Expense ───────────────────────────────────────────────

    def discard_expense(self, expense_id: int, as_of: date) -> None:
        """CF-OP-6: Soft-delete a household expense.

        Args:
            expense_id: Primary key of the expense to discard.
            as_of: Session effective date.

        Raises:
            ValueError: If expense not found.
        """
        with transaction(self._session_factory) as session:
            self._cf.discard_household_expense(session, expense_id=expense_id, effective_date=as_of)

    # ── CF-OP-7: Get Report View Data ──────────────────────────────────────────

    def get_account_options(self, as_of: date) -> list[AccountOption]:
        """Return active accounts for the From/To account dropdowns in F-15.

        Args:
            as_of: Session effective date.

        Returns:
            One :class:`AccountOption` per active account, in insertion order.
        """
        with transaction(self._session_factory) as session:
            return [
                AccountOption(account_id=a.id, name=a.name)
                for a in self._cf.list_accounts(session, as_of)
            ]

    def get_bank_account_options(self, as_of: date) -> list[AccountOption]:
        """Return active bank (SimpleAccount / BANK) accounts for the 'From' dropdown in F-15.

        Args:
            as_of: Session effective date.

        Returns:
            One :class:`AccountOption` per active bank account, in insertion order.
        """
        from personal_finance.domain.balance_sheet.account import (  # noqa: PLC0415
            SimpleAccount,
            SimpleAccountCategory,
        )

        with transaction(self._session_factory) as session:
            return [
                AccountOption(account_id=a.id, name=a.name)
                for a in self._cf.list_accounts(session, as_of)
                if isinstance(a, SimpleAccount) and a.type == SimpleAccountCategory.BANK
            ]

    def get_investment_account_options(self, as_of: date) -> list[AccountOption]:
        """Return active investment accounts for the 'To' dropdown in F-15.

        Args:
            as_of: Session effective date.

        Returns:
            One :class:`AccountOption` per active investment account, in insertion order.
        """
        from personal_finance.domain.balance_sheet.account import InvestmentAccount  # noqa: PLC0415

        with transaction(self._session_factory) as session:
            return [
                AccountOption(account_id=a.id, name=a.name)
                for a in self._cf.list_accounts(session, as_of)
                if isinstance(a, InvestmentAccount)
            ]

    def get_report_view_data(self, as_of: date) -> ReportViewData:
        """CF-OP-7: Build the complete data payload for the F-14 report screen.

        Args:
            as_of: Session effective date.

        Returns:
            :class:`ReportViewData` ready for the F-14 right pane.
        """
        with transaction(self._session_factory) as session:
            profiles = self._cf.list_person_profiles(session)

            _D12 = Decimal("12")
            gross_annual_total = sum(
                (p.gross_annual_income.latest_value_as_of(as_of) or _D0 for p in profiles),
                _D0,
            )
            net_annual_total = sum(
                (p.net_annual_income.latest_value_as_of(as_of) or _D0 for p in profiles),
                _D0,
            )
            gross_monthly = gross_annual_total / _D12
            net_monthly = net_annual_total / _D12

            # Per-person RRSP deduction lines (only when combined RRSP > 0)
            rrsp_deduction_lines: list[RrspDeductionLine] = []
            for p in profiles:
                deducted = p.auto_rrsp_deducted.latest_value_as_of(as_of) or _D0
                matched = p.rrsp_matched.latest_value_as_of(as_of) or _D0
                total_rrsp = deducted + matched
                if total_rrsp > _D0:
                    rrsp_deduction_lines.append(
                        RrspDeductionLine(
                            person_name=p.person.name,
                            monthly_amount=total_rrsp / _D12,
                        )
                    )

            sum_rrsp_monthly = sum((ln.monthly_amount for ln in rrsp_deduction_lines), _D0)
            taxes_other_monthly = gross_monthly - sum_rrsp_monthly - net_monthly

            # Expenses
            expenses = self._cf.list_household_expenses(session, as_of)
            avg_monthly_expenses = sum(
                (e.amount.latest_value_as_of(as_of) or _D0 for e in expenses),
                _D0,
            )

            # Automated contributions
            raw_contribs = self._cf.list_automated_contributions(session, as_of)
            contributions = [
                ContributionRow(
                    contribution_id=c.id,
                    name=c.name,
                    amount=c.amount.latest_value_as_of(as_of) or _D0,
                    source_account_id=c.source_account_id,
                    destination_account_id=c.destination_account_id,
                    target_goal_id=c.target_goal_id,
                )
                for c in raw_contribs
            ]
            sum_contributions = sum((c.amount for c in contributions), _D0)

            total_monthly_retained = net_monthly - avg_monthly_expenses - sum_contributions
            total_annual_retained = total_monthly_retained * _D12

            total_net_bonus = sum(
                (p.net_bonus.latest_value_as_of(as_of) or _D0 for p in profiles),
                _D0,
            )
            final_annual_retained = total_annual_retained + total_net_bonus

            # Goal contributions (annualized): RRSP amounts are already annual
            goal_totals: dict[str, Decimal] = {}
            for p in profiles:
                deducted = p.auto_rrsp_deducted.latest_value_as_of(as_of) or _D0
                matched = p.rrsp_matched.latest_value_as_of(as_of) or _D0
                total_rrsp = deducted + matched
                if total_rrsp > _D0 and p.auto_rrsp_goal:
                    goal_name = p.auto_rrsp_goal.name
                    goal_totals[goal_name] = goal_totals.get(goal_name, _D0) + total_rrsp

            for c_raw in raw_contribs:
                goal_name = c_raw.target_goal.name
                monthly = c_raw.amount.latest_value_as_of(as_of) or _D0
                goal_totals[goal_name] = goal_totals.get(goal_name, _D0) + monthly * _D12

            goal_contributions = [
                GoalContributionLine(goal_name=name, annual_amount=amount)
                for name, amount in sorted(goal_totals.items())
            ]

            return ReportViewData(
                gross_monthly=gross_monthly,
                rrsp_deduction_lines=rrsp_deduction_lines,
                taxes_other_monthly=taxes_other_monthly,
                net_monthly=net_monthly,
                avg_monthly_expenses=avg_monthly_expenses,
                contributions=contributions,
                total_monthly_retained=total_monthly_retained,
                total_annual_retained=total_annual_retained,
                total_net_bonus=total_net_bonus,
                final_annual_retained=final_annual_retained,
                gross_annual_total=gross_annual_total,
                goal_contributions=goal_contributions,
            )

    # ── CF-OP-8: Create Automated Contribution ─────────────────────────────────

    def create_automated_contribution(
        self,
        name: str,
        amount: Decimal,
        source_account_id: int,
        destination_account_id: int,
        target_goal_id: int,
        as_of: date,
    ) -> int:
        """CF-OP-8: Create a new automated contribution.

        Args:
            name: Display label (must be non-empty after stripping).
            amount: Monthly amount.
            source_account_id: Primary key of the source account.
            destination_account_id: Primary key of the destination account.
            target_goal_id: Primary key of the target goal.
            as_of: Session effective date.

        Returns:
            Primary key of the newly created contribution.

        Raises:
            ValueError: If ``name`` is empty.
        """
        name = name.strip()
        if not name:
            raise ValueError("Contribution name cannot be empty.")
        with transaction(self._session_factory) as session:
            return self._cf.create_automated_contribution(
                session,
                name=name,
                amount=amount,
                source_account_id=source_account_id,
                destination_account_id=destination_account_id,
                target_goal_id=target_goal_id,
                effective_date=as_of,
            )

    # ── CF-OP-9: Update Automated Contribution ─────────────────────────────────

    def update_automated_contribution(
        self,
        contribution_id: int,
        name: str,
        amount: Decimal,
        source_account_id: int,
        destination_account_id: int,
        target_goal_id: int,
        as_of: date,
    ) -> None:
        """CF-OP-9: Update all fields of an existing automated contribution.

        Args:
            contribution_id: Primary key of the contribution to update.
            name: Updated display label (must be non-empty after stripping).
            amount: New monthly amount.
            source_account_id: Updated source account.
            destination_account_id: Updated destination account.
            target_goal_id: Updated target goal.
            as_of: Session effective date.

        Raises:
            ValueError: If ``name`` is empty or contribution not found.
        """
        name = name.strip()
        if not name:
            raise ValueError("Contribution name cannot be empty.")
        with transaction(self._session_factory) as session:
            self._cf.update_automated_contribution(
                session,
                contribution_id=contribution_id,
                name=name,
                amount=amount,
                source_account_id=source_account_id,
                destination_account_id=destination_account_id,
                target_goal_id=target_goal_id,
                effective_date=as_of,
            )

    # ── CF-OP-10: Discard Automated Contribution ───────────────────────────────

    def discard_automated_contribution(self, contribution_id: int, as_of: date) -> None:
        """CF-OP-10: Soft-delete an automated contribution.

        Args:
            contribution_id: Primary key of the contribution to discard.
            as_of: Session effective date.

        Raises:
            ValueError: If contribution not found.
        """
        with transaction(self._session_factory) as session:
            self._cf.discard_automated_contribution(
                session, contribution_id=contribution_id, effective_date=as_of
            )
