"""Goals application service — BFF for the Goals screens."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from personal_finance.db import transaction
from personal_finance.domain.asset_class import AccountAssetClass, BuiltInAssetClassId
from personal_finance.domain.balance_sheet.account import InvestmentAccount
from personal_finance.domain.goals.goal import (
    GoalBankPortionAutoFill,
    NoGoalValue,
    ScalarGoalValue,
    SimplePVGoalValue,
)
from personal_finance.service.core.balance_sheet_service import BalanceSheetService
from personal_finance.service.core.goal_service import GoalService

__all__ = [
    "GoalAllocationData",
    "GoalAllocationRow",
    "GoalAppService",
    "GoalListItem",
    "GoalSummaryRow",
    "GoalsSummary",
    "GoalValueParams",
    "InvestmentAccountOption",
]


@dataclass(frozen=True)
class InvestmentAccountOption:
    """One row in SelectAccountsDialog (F-10).

    Attributes:
        account_id: Database primary key of the investment account.
        name: Display name of the account.
        balance: Current balance as of the effective date, or ``None`` if
            the account is unpriced (no holding prices available).
        is_selected: ``True`` when the account is currently allocated to the
            goal being edited.
        blocking_goal_name: Name of the *other* active goal this account is
            assigned to, or ``None`` when the account is free or already
            belongs to the goal being edited.
    """

    account_id: int
    name: str
    balance: Decimal | None
    is_selected: bool
    blocking_goal_name: str | None


@dataclass(frozen=True)
class GoalValueParams:
    """Pre-fill data for ``GoalValueDialog`` / ``GoalValueForm``.

    This is a screen-level DTO owned by the application service layer.
    Its shape is driven by what the form widget needs to display.

    Attributes:
        goal_type: Current strategy type (``"manual"``, ``"pv"``, or ``"none"``).
        manual_value: Current scalar target for Manual goals; ``None`` when no
            timeline entry exists yet.
        future_value: Future value for PV goals.
        start_date: Savings start date for PV goals.
        maturity_date: Maturity date for PV goals.
        discount_rate: Annual discount rate as a fraction for PV goals.
    """

    goal_type: Literal["manual", "pv", "none"]
    manual_value: Decimal | None = field(default=None)
    future_value: Decimal | None = field(default=None)
    start_date: date | None = field(default=None)
    maturity_date: date | None = field(default=None)
    discount_rate: Decimal | None = field(default=None)


@dataclass(frozen=True)
class GoalSummaryRow:
    """Data for a single row in the Goals List screen (F-8).

    Attributes:
        goal_id: Database primary key.
        name: Display name.
        goal_type: ``"manual"`` (ScalarGoalValue, editable inline),
            ``"pv"`` (SimplePVGoalValue, read-only), or
            ``"none"`` (NoGoalValue, read-only).
        goal_target: Calculated target amount, or ``None`` for ``"none"`` goals.
        investment_allocation: Sum of balances for all allocated investment
            accounts as of the effective date. Unpriced accounts contribute $0.
        bank_allocation: Amount claimed from bank accounts; $0 when the
            Scalar timeline has no entry yet.
        is_autofill: ``True`` when the goal uses AutoFill bank strategy.
        difference: ``investment_allocation + bank_allocation - goal_target``,
            or ``None`` when ``goal_target`` is ``None``.
            Positive means total allocations exceed the goal (surplus);
            negative means allocations fall short of the goal (deficit).
    """

    goal_id: int
    name: str
    goal_type: Literal["manual", "pv", "none"]
    goal_target: Decimal | None
    investment_allocation: Decimal
    bank_allocation: Decimal
    is_autofill: bool
    difference: Decimal | None


@dataclass(frozen=True)
class GoalsSummary:
    """Aggregated data for the Goals List screen (F-8).

    Attributes:
        rows: One entry per active goal, in insertion order.
        overclaim_amount: Positive amount by which total bank claims exceed
            available bank balances, or ``None`` when there is no overclaim.
        total_bank_balance: The sum of all active BANK account balances as of
            the query date. Exposed so the screen can maintain an incremental
            running total for live overclaim updates without re-querying.
    """

    rows: list[GoalSummaryRow]
    overclaim_amount: Decimal | None
    total_bank_balance: Decimal


@dataclass(frozen=True)
class GoalListItem:
    """One row in the left pane of GoalAllocationView (F-11b).

    Attributes:
        goal_id: Database primary key.
        name: Display name.
        target_sum_exceeds_100: ``True`` when the sum of active target percentages
            for this goal exceeds 100%, triggering the ``[!]`` indicator.
    """

    goal_id: int
    name: str
    target_sum_exceeds_100: bool


@dataclass(frozen=True)
class GoalAllocationRow:
    """One asset-class row in the right pane of GoalAllocationView (F-11b).

    Attributes:
        asset_class_id: Database primary key of the AccountAssetClass.
        asset_class_name: Display name.
        target_percent: Persisted target percentage (0 when no record exists).
        actual_percent: Computed percentage of total goal value in this class.
        difference_percent: ``actual_percent − target_percent``.
        difference_amount: ``difference_percent × total_value``.
    """

    asset_class_id: int
    asset_class_name: str
    target_percent: Decimal
    actual_percent: Decimal
    difference_percent: Decimal
    difference_amount: Decimal


@dataclass(frozen=True)
class GoalAllocationData:
    """Right-pane data contract for GoalAllocationView (F-11b).

    Attributes:
        goal_id: Database primary key of the selected goal.
        goal_name: Display name shown in the right-pane header.
        rows: One entry per active AccountAssetClass, in order_precedence order.
        total_value: Total allocated value (investments + bank portion). Used by
            the UI to recompute difference_amount when target inputs change.
    """

    goal_id: int
    goal_name: str
    rows: list[GoalAllocationRow]
    total_value: Decimal


class GoalAppService:
    """Application service (BFF) for the Goals module screens.

    Each UI screen must interact only with its own application service. This
    class fans out to :class:`GoalService` and :class:`BalanceSheetService`
    as needed.

    Owns the session lifetime for every public method (session-per-application-operation):
    each method opens one session via ``db.transaction()`` for its whole body and
    passes it into every core-service call it makes.

    Args:
        goal_service: Core service for goal domain operations.
        balance_sheet_service: Core service used for bank-balance queries and
            pricing allocated investment accounts.
        session_factory: Session factory used to open one session per public method.
    """

    def __init__(
        self,
        goal_service: GoalService,
        balance_sheet_service: BalanceSheetService,
        session_factory: sessionmaker[Session],
    ) -> None:
        """Store injected core services and session factory."""
        self._goals = goal_service
        self._bs = balance_sheet_service
        self._session_factory = session_factory

    # ── G-OP-1: Get Goals Summary ──────────────────────────────────────────────

    async def get_goals_summary(self, as_of: date) -> GoalsSummary:
        """G-OP-1: Build the full goals list data contract for F-8.

        Prices all allocated investment accounts concurrently, then computes
        investment allocations, bank claims, goal targets, and the overclaim flag.

        Args:
            as_of: Session effective date for all balance and active-state lookups.

        Returns:
            A :class:`GoalsSummary` ready for the screen to render.
        """
        with transaction(self._session_factory) as session:
            goals = self._goals.list_active_goals(session, as_of)

            # Gather all unique allocated investment accounts that need pricing.
            accounts_to_price: list[InvestmentAccount] = []
            seen_ids: set[int] = set()
            for goal in goals:
                for acc in goal.allocated_accounts:
                    if isinstance(acc, InvestmentAccount) and acc.id not in seen_ids:
                        if acc.is_active(as_of):
                            accounts_to_price.append(acc)
                            seen_ids.add(acc.id)

            await asyncio.gather(
                *(self._bs.price_investment_account(acc, as_of) for acc in accounts_to_price)
            )

            rows: list[GoalSummaryRow] = []
            total_bank_claims = Decimal("0")

            for goal in goals:
                # Determine goal type label.
                if isinstance(goal.goal_value, ScalarGoalValue):
                    goal_type: Literal["manual", "pv", "none"] = "manual"
                elif isinstance(goal.goal_value, NoGoalValue):
                    goal_type = "none"
                else:
                    goal_type = "pv"

                goal_target = goal.goal_value.calculate_target(as_of)

                # Sum active allocated investment account balances; treat None as $0.
                inv_alloc = Decimal("0")
                for acc in goal.allocated_accounts:
                    if acc.is_active(as_of):
                        bal = acc.get_balance(as_of)
                        if bal is not None:
                            inv_alloc += bal

                is_autofill = isinstance(goal.bank_portion, GoalBankPortionAutoFill)
                bank_raw = goal.bank_portion.get_value(as_of)
                bank_alloc = bank_raw if bank_raw is not None else Decimal("0")
                total_bank_claims += bank_alloc

                if goal_target is not None:
                    difference: Decimal | None = inv_alloc + bank_alloc - goal_target
                else:
                    difference = None

                rows.append(
                    GoalSummaryRow(
                        goal_id=goal.id,
                        name=goal.name,
                        goal_type=goal_type,
                        goal_target=goal_target,
                        investment_allocation=inv_alloc,
                        bank_allocation=bank_alloc,
                        is_autofill=is_autofill,
                        difference=difference,
                    )
                )

            # Overclaim check: compare total bank claims against available bank balance.
            bank_balance = self._bs.get_total_bank_balance(session, as_of)
            overclaim = total_bank_claims - bank_balance
            overclaim_amount: Decimal | None = overclaim if overclaim > Decimal("0") else None

            return GoalsSummary(
                rows=rows,
                overclaim_amount=overclaim_amount,
                total_bank_balance=bank_balance,
            )

    # ── G-OP-2: Create Goal ────────────────────────────────────────────────────

    def create_goal(
        self,
        name: str,
        value_type: str,
        as_of: date,
        *,
        value: Decimal | None = None,
        future_value: Decimal | None = None,
        start_date: date | None = None,
        maturity_date: date | None = None,
        discount_rate: Decimal | None = None,
    ) -> int:
        """G-OP-2: Persist a new financial goal.

        Args:
            name: Display name for the goal.
            value_type: ``"manual"``, ``"pv"``, or ``"none"``.
            as_of: Session effective date.
            value: Initial scalar target for Manual goals.
            future_value: Future value for PV goals.
            start_date: Savings start date for PV goals.
            maturity_date: Maturity date for PV goals.
            discount_rate: Annual discount rate as a fraction for PV goals.

        Returns:
            The primary key of the newly created goal.
        """
        with transaction(self._session_factory) as session:
            return self._goals.create_goal(
                session,
                name=name,
                value_type=value_type,  # type: ignore[arg-type]
                as_of=as_of,
                value=value,
                future_value=future_value,
                start_date=start_date,
                maturity_date=maturity_date,
                discount_rate=discount_rate,
            )

    # ── Inline-edit proxies ────────────────────────────────────────────────────

    def discard_goal(self, goal_id: int, as_of: date) -> None:
        """G-OP-4: Soft-delete a goal.

        Args:
            goal_id: Primary key of the goal to discard.
            as_of: Session effective date.
        """
        with transaction(self._session_factory) as session:
            self._goals.discard_goal(session, goal_id, as_of)

    def update_goal_name(self, goal_id: int, new_name: str) -> None:
        """Update the name of a goal (name-only portion of G-OP-3).

        Args:
            goal_id: Primary key of the goal.
            new_name: Non-empty replacement name.
        """
        with transaction(self._session_factory) as session:
            self._goals.update_goal_name(session, goal_id, new_name)

    def update_goal_scalar_value(self, goal_id: int, new_value: Decimal, as_of: date) -> None:
        """Append a new target entry for a Manual goal (inline G-OP-3).

        Args:
            goal_id: Primary key of the goal.
            new_value: New target amount.
            as_of: Session effective date.
        """
        with transaction(self._session_factory) as session:
            self._goals.update_goal_scalar_value(session, goal_id, new_value, as_of)

    def update_goal_bank_scalar(self, goal_id: int, new_amount: Decimal, as_of: date) -> None:
        """Append a new bank-claim entry for a Scalar-strategy goal (inline G-OP-6).

        Args:
            goal_id: Primary key of the goal.
            new_amount: New bank claim amount.
            as_of: Session effective date.
        """
        with transaction(self._session_factory) as session:
            self._goals.update_goal_bank_scalar(session, goal_id, new_amount, as_of)

    def get_goal_value_params(self, goal_id: int, as_of: date) -> GoalValueParams:
        """Build the pre-fill DTO for ``GoalValueDialog`` from the goal's domain state.

        Args:
            goal_id: Primary key of the goal.
            as_of: Effective date for reading the current scalar value on Manual goals.

        Returns:
            A :class:`GoalValueParams` with the goal's current valuation strategy fields.

        Raises:
            ValueError: If the goal does not exist.
        """
        with transaction(self._session_factory) as session:
            goal = self._goals.get_goal(session, goal_id)
            gv = goal.goal_value
            if isinstance(gv, ScalarGoalValue):
                return GoalValueParams(
                    goal_type="manual",
                    manual_value=gv.calculate_target(as_of),
                )
            elif isinstance(gv, SimplePVGoalValue):
                return GoalValueParams(
                    goal_type="pv",
                    future_value=gv.future_value,
                    start_date=gv.start_date,
                    maturity_date=gv.maturity_date,
                    discount_rate=gv.discount_rate,
                )
            else:
                return GoalValueParams(goal_type="none")

    def update_goal_value_strategy(
        self,
        goal_id: int,
        value_type: str,
        as_of: date,
        *,
        value: Decimal | None = None,
        future_value: Decimal | None = None,
        start_date: date | None = None,
        maturity_date: date | None = None,
        discount_rate: Decimal | None = None,
    ) -> None:
        """G-OP-3: Replace the ``GoalValue`` strategy for a goal.

        Args:
            goal_id: Primary key of the goal to update.
            value_type: New value strategy (``"manual"``, ``"pv"``, or ``"none"``).
            as_of: Session effective date.
            value: Initial target amount for Manual goals.
            future_value: Required for PV goals.
            start_date: Required for PV goals.
            maturity_date: Required for PV goals.
            discount_rate: Required for PV goals (annual rate as a fraction).
        """
        with transaction(self._session_factory) as session:
            self._goals.update_goal_value_strategy(
                session,
                goal_id,
                value_type,  # type: ignore[arg-type]
                as_of,
                value=value,
                future_value=future_value,
                start_date=start_date,
                maturity_date=maturity_date,
                discount_rate=discount_rate,
            )

    def switch_bank_to_scalar(self, goal_id: int, as_of: date) -> None:
        """G-OP-6: Replace AutoFill bank portion with a $0 Scalar.

        Args:
            goal_id: Primary key of the goal.
            as_of: Session effective date for the initial entry.
        """
        with transaction(self._session_factory) as session:
            self._goals.switch_bank_portion_to_scalar(session, goal_id, as_of)

    def switch_bank_to_autofill(self, goal_id: int) -> None:
        """G-OP-6: Replace Scalar bank portion with AutoFill.

        Args:
            goal_id: Primary key of the goal.
        """
        with transaction(self._session_factory) as session:
            self._goals.switch_bank_portion_to_autofill(session, goal_id)

    # ── G-OP-5: Update Goal Investment Allocation ──────────────────────────────

    async def get_investment_accounts_for_dialog(
        self, goal_id: int, as_of: date
    ) -> list[InvestmentAccountOption]:
        """Build the account selection list for SelectAccountsDialog (F-10).

        Fetches and prices all active investment accounts via
        :class:`BalanceSheetService`, then annotates each with selection state
        relative to ``goal_id`` and the name of any blocking goal.

        Args:
            goal_id: Primary key of the goal being edited.
            as_of: Session effective date for balance lookups and active-state
                evaluation.

        Returns:
            One :class:`InvestmentAccountOption` per active investment account,
            in the order returned by :meth:`BalanceSheetService.list_all_accounts`.
        """
        with transaction(self._session_factory) as session:
            all_accounts = await self._bs.list_all_accounts(session, as_of)
            inv_accounts = [a for a in all_accounts if isinstance(a, InvestmentAccount)]

            # Build goal_id → name map for blocked-account labels.
            goals = self._goals.list_active_goals(session, as_of)
            goal_name_map: dict[int, str] = {g.id: g.name for g in goals}

            result: list[InvestmentAccountOption] = []
            for account in inv_accounts:
                balance = account.get_balance(as_of)
                is_selected = account.goal_id == goal_id
                blocking_goal_name: str | None = None
                if account.goal_id is not None and account.goal_id != goal_id:
                    blocking_goal_name = goal_name_map.get(account.goal_id, "Unknown goal")
                result.append(
                    InvestmentAccountOption(
                        account_id=account.id,
                        name=account.name,
                        balance=balance,
                        is_selected=is_selected,
                        blocking_goal_name=blocking_goal_name,
                    )
                )
            return result

    def update_goal_investment_allocation(self, goal_id: int, account_ids: list[int]) -> None:
        """G-OP-5: Overwrite the allocated investment accounts for a goal.

        Args:
            goal_id: Primary key of the goal to update.
            account_ids: New complete set of ``InvestmentAccount`` primary keys.

        Raises:
            ValueError: If any account is assigned to a different active goal.
        """
        with transaction(self._session_factory) as session:
            self._goals.update_goal_investment_allocation(session, goal_id, account_ids)

    # ── G-OP-7/8: Goal Allocation View ────────────────────────────────────────

    def get_goals_for_allocation_view(self, as_of: date) -> list[GoalListItem]:
        """Build the left-pane data for GoalAllocationView (F-11b).

        No pricing is needed — only goal names and target sums.

        Args:
            as_of: Session effective date.

        Returns:
            One :class:`GoalListItem` per active goal, in insertion order.
        """
        with transaction(self._session_factory) as session:
            goals = self._goals.list_active_goals(session, as_of)
            items: list[GoalListItem] = []
            for goal in goals:
                target_sum = sum(
                    (t.target_percent for t in goal.asset_class_targets if t.is_active(as_of)),
                    Decimal("0"),
                )
                items.append(
                    GoalListItem(
                        goal_id=goal.id,
                        name=goal.name,
                        target_sum_exceeds_100=target_sum > Decimal("100"),
                    )
                )
            return items

    async def get_goal_allocation_data(self, goal_id: int, as_of: date) -> GoalAllocationData:
        """G-OP-7: Build the right-pane data for GoalAllocationView (F-11b).

        Prices all allocated investment accounts concurrently, then computes
        actual vs target asset-class percentages.

        Actual percentage formula per asset class:
        - ``total_value = Σ(investment_account_balances) + bank_portion_value``
        - Holding values are distributed by their ``HoldingAssetClassAllocation``
          weights; uninvested cash within each account counts 100% as Cash.
        - ``GoalBankPortion`` value counts 100% as Cash (``BuiltInAssetClassId.CASH``).
        - When ``total_value == 0``, all actual percentages are 0%.

        Args:
            goal_id: Primary key of the goal.
            as_of: Session effective date for all balance and active-state lookups.

        Returns:
            A :class:`GoalAllocationData` ready for the screen to render.

        Raises:
            ValueError: If no goal with ``goal_id`` exists.
        """
        with transaction(self._session_factory) as session:
            goal = self._goals.get_goal(session, goal_id)

            # Price all allocated investment accounts concurrently.
            accounts_to_price = [
                acc
                for acc in goal.allocated_accounts
                if isinstance(acc, InvestmentAccount) and acc.is_active(as_of)
            ]
            await asyncio.gather(
                *(self._bs.price_investment_account(acc, as_of) for acc in accounts_to_price)
            )

            # Accumulate actual values per asset class.
            class_values: dict[int, Decimal] = defaultdict(Decimal)
            total_value = Decimal("0")
            _D100 = Decimal("100")

            for acc in goal.allocated_accounts:
                if not isinstance(acc, InvestmentAccount) or not acc.is_active(as_of):
                    continue

                # Uninvested cash within the account → Cash asset class.
                uninvested = acc.cash_balance.latest_value_as_of(as_of) or Decimal("0")
                class_values[int(BuiltInAssetClassId.CASH)] += uninvested
                total_value += uninvested

                # Holding values distributed by HoldingAssetClassAllocation.
                for holding in acc.holdings:
                    if not holding.is_active(as_of):
                        continue
                    c_val = holding.get_value(as_of) or Decimal("0")
                    total_value += c_val
                    for alloc in holding.allocations:
                        if alloc.is_active(as_of):
                            class_values[alloc.asset_class_id] += (
                                c_val * alloc.percent_allocated / _D100
                            )

            # Bank portion → Cash asset class.
            bank_val = goal.bank_portion.get_value(as_of)
            if bank_val is None:
                bank_val = Decimal("0")
            class_values[int(BuiltInAssetClassId.CASH)] += bank_val
            total_value += bank_val

            # Fetch persisted target percentages.
            persisted_targets = self._goals.get_goal_asset_class_targets(session, goal_id, as_of)

            # Build one row per active asset class.
            asset_classes: list[AccountAssetClass] = self._goals.list_active_asset_classes(
                session, as_of
            )
            rows: list[GoalAllocationRow] = []
            for ac in asset_classes:
                target_pct = persisted_targets.get(ac.id, Decimal("0"))
                if total_value > Decimal("0"):
                    actual_pct = (
                        class_values.get(ac.id, Decimal("0")) / total_value * _D100
                    ).quantize(Decimal("0.01"))
                else:
                    actual_pct = Decimal("0")
                diff_pct = actual_pct - target_pct
                diff_amt = diff_pct / _D100 * total_value
                rows.append(
                    GoalAllocationRow(
                        asset_class_id=ac.id,
                        asset_class_name=ac.name,
                        target_percent=target_pct,
                        actual_percent=actual_pct,
                        difference_percent=diff_pct,
                        difference_amount=diff_amt,
                    )
                )

            return GoalAllocationData(
                goal_id=goal_id,
                goal_name=goal.name,
                rows=rows,
                total_value=total_value,
            )

    def update_goal_asset_class_targets(
        self,
        goal_id: int,
        targets: list[tuple[int, Decimal]],
        as_of: date,
    ) -> None:
        """G-OP-8: Overwrite all asset-class targets for a goal.

        Args:
            goal_id: Primary key of the goal to update.
            targets: Complete replacement set of ``(asset_class_id, target_percent)``
                pairs.
            as_of: Session effective date.

        Raises:
            ValueError: If the goal or any asset class ID does not exist.
        """
        with transaction(self._session_factory) as session:
            self._goals.update_goal_asset_class_targets(session, goal_id, targets, as_of)
