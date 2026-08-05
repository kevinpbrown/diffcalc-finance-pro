"""Goal core service — domain operations for goal data."""

import asyncio
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet.account import InvestmentAccount
from personal_finance.domain.goals.goal import (
    Goal,
    GoalAssetClassTarget,
    GoalBankPortionAutoFill,
    GoalBankPortionScalar,
    NoGoalValue,
    ScalarGoalValue,
    SimplePVGoalValue,
)
from personal_finance.service.core.balance_sheet_service import BalanceSheetService

__all__ = [
    "GoalService",
]


class GoalService:
    """Domain operations for the Goals module.

    Session-per-application-operation: this service holds no session state.
    Every method that touches the database takes ``session`` as an explicit
    first parameter, supplied by the calling application-service method, which
    owns that session's lifetime and commit/rollback via ``db.transaction()``.
    Methods do not call ``session.commit()`` themselves; they use ``flush()``
    only where a subsequent step in the same call needs a generated primary key.

    Args:
        balance_sheet_service: Core service used to price AutoFill goals'
            allocated investment accounts before evaluating their bank claim.
    """

    def __init__(self, balance_sheet_service: BalanceSheetService) -> None:
        """Store the injected BalanceSheetService."""
        self._balance_sheet = balance_sheet_service

    # ── Queries ────────────────────────────────────────────────────────────────

    def list_active_goals(self, session: Session, as_of: date) -> list[Goal]:
        """Return all goals active as of ``as_of``, ordered by primary key.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for active-state evaluation.

        Returns:
            Active :class:`Goal` rows in insertion order.
        """
        return [g for g in session.query(Goal).all() if g.is_active(as_of)]

    async def get_total_bank_claim(self, session: Session, as_of: date) -> Decimal:
        """Return the sum of all active goal bank-portion claims as of ``as_of``.

        Prices each active AutoFill goal's allocated investment accounts via
        ``BalanceSheetService.price_investment_account`` before evaluating its
        claim, since ``GoalBankPortionAutoFill.get_value()`` reads
        ``InvestmentAccount.get_balance()``, which aggregates holding values
        that are ``None`` until priced. Pricing is cache-backed at the
        ``QuoteService`` layer, so repeated calls across independent sessions
        are cheap — this no longer depends on a prior ``list_all_accounts()``
        call sharing this session's identity map.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for active-state evaluation and value lookup.

        Returns:
            Sum of bank-portion claims across all active goals. Returns
            ``Decimal("0")`` if no active goals have a bank-portion claim.
        """
        goals = session.query(Goal).all()

        accounts_to_price: list[InvestmentAccount] = []
        seen_ids: set[int] = set()
        for goal in goals:
            if not goal.is_active(as_of) or not isinstance(
                goal.bank_portion, GoalBankPortionAutoFill
            ):
                continue
            for acc in goal.allocated_accounts:
                if acc.id not in seen_ids and acc.is_active(as_of):
                    accounts_to_price.append(acc)
                    seen_ids.add(acc.id)

        await asyncio.gather(
            *(self._balance_sheet.price_investment_account(acc, as_of) for acc in accounts_to_price)
        )

        total = Decimal("0")
        for goal in goals:
            if not goal.is_active(as_of):
                continue
            claim = goal.bank_portion.get_value(as_of)
            if claim is not None:
                total += claim
        return total

    def get_goal(self, session: Session, goal_id: int) -> Goal:
        """Return a goal by primary key.

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key to look up.

        Returns:
            The matching :class:`Goal` instance.

        Raises:
            ValueError: If no goal with ``goal_id`` exists.
        """
        return self._get_goal(session, goal_id)

    # ── Mutations ──────────────────────────────────────────────────────────────

    def create_goal(
        self,
        session: Session,
        name: str,
        value_type: Literal["manual", "pv", "none"],
        as_of: date,
        *,
        value: Decimal | None = None,
        future_value: Decimal | None = None,
        start_date: date | None = None,
        maturity_date: date | None = None,
        discount_rate: Decimal | None = None,
    ) -> int:
        """G-OP-2: Persist a new financial goal with the given valuation strategy.

        All new goals are created with a ``GoalBankPortionScalar`` set to $0.
        The user can switch to AutoFill later via G-OP-6.

        Args:
            session: The SQLAlchemy session for this operation.
            name: Display name (must be non-empty after stripping).
            value_type: ``"manual"`` (scalar), ``"pv"`` (present value), or
                ``"none"`` (no target).
            as_of: Session effective date; used as ``date_created`` and as the
                initial timeline entry date for Manual goals that supply a value.
            value: Initial target amount for Manual goals. Ignored for other types.
            future_value: Required for PV goals.
            start_date: Required for PV goals.
            maturity_date: Required for PV goals.
            discount_rate: Required for PV goals (annual rate as a fraction,
                e.g. 0.05 for 5%).

        Returns:
            The primary key of the newly created :class:`Goal`.

        Raises:
            ValueError: If ``name`` is empty or required PV fields are missing.
        """
        name = name.strip()
        if not name:
            raise ValueError("Goal name cannot be empty.")

        if value_type == "manual":
            goal_value: ScalarGoalValue | SimplePVGoalValue | NoGoalValue = ScalarGoalValue()
            if value is not None:
                assert goal_value.value is not None
                goal_value.value.offer_value(as_of, value)
        elif value_type == "pv":
            if any(v is None for v in [future_value, start_date, maturity_date, discount_rate]):
                raise ValueError(
                    "PV goals require future_value, start_date, maturity_date, and discount_rate."
                )
            goal_value = SimplePVGoalValue(
                future_value=future_value,
                start_date=start_date,
                maturity_date=maturity_date,
                discount_rate=discount_rate,
            )
        else:
            goal_value = NoGoalValue()

        bank_portion = GoalBankPortionScalar()
        assert bank_portion.amount is not None
        bank_portion.amount.offer_value(as_of, Decimal("0"))

        goal = Goal(
            name=name,
            date_created=as_of,
            date_effective=as_of,
            goal_value=goal_value,
            bank_portion=bank_portion,
        )
        session.add(goal)
        session.flush()
        return goal.id

    def discard_goal(self, session: Session, goal_id: int, as_of: date) -> None:
        """G-OP-4: Soft-delete a goal and clear its account allocations.

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal to discard.
            as_of: Session effective date to record as the discard date.

        Raises:
            ValueError: If the goal does not exist or discard validation fails.
        """
        goal = self._get_goal(session, goal_id)
        goal.discard(as_of)
        # Detach all allocated accounts (clear the FK on each account).
        for account in list(goal.allocated_accounts):
            account.goal_id = None

    def update_goal_name(self, session: Session, goal_id: int, new_name: str) -> None:
        """Update the display name of a goal.

        This is the name-only portion of G-OP-3. It does not touch the
        GoalValue strategy.

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal to rename.
            new_name: Non-empty replacement name.

        Raises:
            ValueError: If the goal does not exist or ``new_name`` is empty.
        """
        if not new_name.strip():
            raise ValueError("Goal name cannot be empty.")
        goal = self._get_goal(session, goal_id)
        goal.name = new_name

    def update_goal_scalar_value(
        self, session: Session, goal_id: int, new_value: Decimal, as_of: date
    ) -> None:
        """Append a new timeline entry on a ScalarGoalValue target.

        Covers the inline-edit path in F-8 for Manual goals.

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal to update.
            new_value: New target amount.
            as_of: Session effective date for the new timeline entry.

        Raises:
            ValueError: If the goal does not exist or its GoalValue is not a
                ScalarGoalValue.
        """
        goal = self._get_goal(session, goal_id)
        if not isinstance(goal.goal_value, ScalarGoalValue):
            raise ValueError(f"Goal {goal_id} does not use a scalar (Manual) value strategy.")
        assert goal.goal_value.value is not None
        goal.goal_value.value.offer_value(as_of, new_value)

    def update_goal_bank_scalar(
        self, session: Session, goal_id: int, new_amount: Decimal, as_of: date
    ) -> None:
        """Append a new timeline entry on a GoalBankPortionScalar claim.

        Covers the inline-edit path in F-8 for Scalar bank-allocation goals.

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal to update.
            new_amount: New bank claim amount.
            as_of: Session effective date for the new timeline entry.

        Raises:
            ValueError: If the goal does not exist or its bank portion is not
                GoalBankPortionScalar.
        """
        goal = self._get_goal(session, goal_id)
        if not isinstance(goal.bank_portion, GoalBankPortionScalar):
            raise ValueError(f"Goal {goal_id} does not use a scalar bank-allocation strategy.")
        assert goal.bank_portion.amount is not None
        goal.bank_portion.amount.offer_value(as_of, new_amount)

    def switch_bank_portion_to_scalar(self, session: Session, goal_id: int, as_of: date) -> None:
        """Replace AutoFill bank portion with a fresh Scalar at $0.

        Called by G-OP-6 when the user unchecks "Fill difference".

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal.
            as_of: Session effective date for the initial $0 entry.

        Raises:
            ValueError: If the goal does not exist.
        """
        goal = self._get_goal(session, goal_id)
        old_portion = goal.bank_portion
        new_portion = GoalBankPortionScalar()
        assert new_portion.amount is not None
        new_portion.amount.offer_value(as_of, Decimal("0"))
        goal.bank_portion = new_portion
        session.delete(old_portion)
        session.flush()

    def update_goal_value_strategy(
        self,
        session: Session,
        goal_id: int,
        value_type: Literal["manual", "pv", "none"],
        as_of: date,
        *,
        value: Decimal | None = None,
        future_value: Decimal | None = None,
        start_date: date | None = None,
        maturity_date: date | None = None,
        discount_rate: Decimal | None = None,
    ) -> None:
        """G-OP-3: Replace the ``GoalValue`` strategy for a goal.

        Hard-deletes the old ``GoalValue`` row and inserts a new one of the
        requested type (U-1: type changes are hard-delete + re-insert).

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal to update.
            value_type: New value strategy (``"manual"``, ``"pv"``, or ``"none"``).
            as_of: Session effective date; used for the initial timeline entry
                when the new strategy is Manual.
            value: Initial target amount for Manual goals.
            future_value: Required for PV goals.
            start_date: Required for PV goals.
            maturity_date: Required for PV goals.
            discount_rate: Required for PV goals (annual rate as a fraction).

        Raises:
            ValueError: If the goal does not exist or required PV fields are absent.
        """
        goal = self._get_goal(session, goal_id)

        if value_type == "manual":
            new_gv: ScalarGoalValue | SimplePVGoalValue | NoGoalValue = ScalarGoalValue()
            if value is not None:
                assert new_gv.value is not None
                new_gv.value.offer_value(as_of, value)
        elif value_type == "pv":
            if any(v is None for v in [future_value, start_date, maturity_date, discount_rate]):
                raise ValueError(
                    "PV goals require future_value, start_date, maturity_date, and discount_rate."
                )
            new_gv = SimplePVGoalValue(
                future_value=future_value,
                start_date=start_date,
                maturity_date=maturity_date,
                discount_rate=discount_rate,
            )
        else:
            new_gv = NoGoalValue()

        old_gv = goal.goal_value
        goal.goal_value = new_gv
        session.delete(old_gv)
        session.flush()

    def switch_bank_portion_to_autofill(self, session: Session, goal_id: int) -> None:
        """Replace Scalar bank portion with AutoFill.

        Called by G-OP-6 when the user checks "Fill difference".

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal.

        Raises:
            ValueError: If the goal does not exist.
        """
        goal = self._get_goal(session, goal_id)
        old_portion = goal.bank_portion
        goal.bank_portion = GoalBankPortionAutoFill()
        session.delete(old_portion)
        session.flush()

    def update_goal_investment_allocation(
        self, session: Session, goal_id: int, account_ids: list[int]
    ) -> None:
        """G-OP-5: Overwrite the set of allocated investment accounts for a goal.

        Clears ``goal_id`` on any account currently allocated to this goal that
        is absent from ``account_ids``, then sets ``goal_id`` on every account
        in the new list.

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal to update.
            account_ids: New complete set of ``InvestmentAccount`` primary keys
                to allocate to this goal.

        Raises:
            ValueError: If the goal does not exist, an account ID does not exist,
                or an account is already allocated to a *different* active goal.
        """
        goal = self._get_goal(session, goal_id)
        new_id_set = set(account_ids)

        # Validate and collect accounts to assign; raises early on any conflict.
        accounts_to_assign: list[InvestmentAccount] = []
        for acc_id in new_id_set:
            account = session.get(InvestmentAccount, acc_id)
            if account is None:
                raise ValueError(f"InvestmentAccount {acc_id} not found.")
            if account.goal_id is not None and account.goal_id != goal_id:
                raise ValueError(f"Account {account.name!r} is already allocated to another goal.")
            accounts_to_assign.append(account)

        # Clear accounts being removed from this goal.
        for account in list(goal.allocated_accounts):
            if account.id not in new_id_set:
                account.goal_id = None

        # Assign accounts being added to this goal.
        for account in accounts_to_assign:
            account.goal_id = goal_id

    def get_goal_asset_class_targets(
        self, session: Session, goal_id: int, as_of: date
    ) -> dict[int, Decimal]:
        """Return the active asset-class target percentages for a goal.

        G-OP-7 (partial): provides the persisted target side of the allocation matrix.

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal.
            as_of: Effective date for active-state filtering.

        Returns:
            Mapping of ``asset_class_id → targetPercent`` for every active
            ``GoalAssetClassTarget`` row. Returns an empty dict when no targets
            are set.

        Raises:
            ValueError: If no goal with ``goal_id`` exists.
        """
        goal = self._get_goal(session, goal_id)
        return {
            t.asset_class_id: t.target_percent
            for t in goal.asset_class_targets
            if t.is_active(as_of)
        }

    def update_goal_asset_class_targets(
        self,
        session: Session,
        goal_id: int,
        targets: list[tuple[int, Decimal]],
        as_of: date,
    ) -> None:
        """G-OP-8: Overwrite all asset-class targets for a goal.

        Soft-deletes every currently active ``GoalAssetClassTarget`` and inserts
        a fresh record for each ``(asset_class_id, target_percent)`` pair in
        ``targets``. Asset classes absent from ``targets`` end up with no active
        record (implying 0 % going forward).

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key of the goal to update.
            targets: Complete replacement set of ``(asset_class_id, target_percent)``
                pairs. Pairs with ``target_percent == 0`` are written if included
                but need not be if omitted.
            as_of: Session effective date; used as ``date_effective`` on new rows
                and as the discard date for retired rows.

        Raises:
            ValueError: If no goal with ``goal_id`` exists, or if any
                ``asset_class_id`` does not exist in the database.
        """
        goal = self._get_goal(session, goal_id)

        # Validate all asset class IDs up front.
        for ac_id, _ in targets:
            if session.get(AccountAssetClass, ac_id) is None:
                raise ValueError(f"AccountAssetClass {ac_id!r} not found.")

        # Soft-delete existing active targets.
        for existing in goal.asset_class_targets:
            if existing.is_active(as_of):
                existing.discard(as_of)

        # Insert new targets.
        for ac_id, pct in targets:
            session.add(
                GoalAssetClassTarget(
                    goal_id=goal_id,
                    asset_class_id=ac_id,
                    target_percent=pct,
                    date_created=as_of,
                    date_effective=as_of,
                    date_modified=as_of,
                )
            )

    def list_active_asset_classes(self, session: Session, as_of: date) -> list[AccountAssetClass]:
        """Return all AccountAssetClass records active as of ``as_of``, ordered by precedence.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for active-state filtering.

        Returns:
            Asset classes sorted by ``order_precedence`` ascending.
        """
        all_classes: list[AccountAssetClass] = session.query(AccountAssetClass).all()
        return sorted(
            (c for c in all_classes if c.is_active(as_of)),
            key=lambda c: c.order_precedence,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _get_goal(self, session: Session, goal_id: int) -> Goal:
        """Fetch a goal by primary key, raising ValueError if not found.

        Args:
            session: The SQLAlchemy session for this operation.
            goal_id: Primary key to look up.

        Returns:
            The matching :class:`Goal` instance.

        Raises:
            ValueError: If no goal with ``goal_id`` exists.
        """
        goal = session.get(Goal, goal_id)
        if goal is None:
            raise ValueError(f"Goal {goal_id!r} not found.")
        return goal
