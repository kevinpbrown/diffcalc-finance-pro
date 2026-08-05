"""Balance Sheet application service — BFF for the Balance Sheet Summary screen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from personal_finance.core.interfaces import SecuritySearchResult  # re-exported for UI layer
from personal_finance.db import transaction
from personal_finance.domain.balance_sheet.account import (
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,  # re-exported for UI layer
    SimpleAccount,
    SimpleAccountCategory,  # re-exported for UI layer
)
from personal_finance.domain.balance_sheet.holding import (
    ExactHolding,
    ListedSecurityHolding,
)
from personal_finance.service.core.balance_sheet_service import BalanceSheetService

__all__ = [
    "AccountAssetClassOption",
    "AccountClassification",
    "AccountDetail",
    "AccountSummaryRow",
    "AllocationInput",
    "BalanceSheetAppService",
    "BalanceSheetSection",
    "BalanceSheetSummary",
    "HoldingRow",
    "InvestmentDetails",
    "InvestmentRegistration",
    "PersonOption",
    "SecuritySearchResult",
    "SimpleAccountCategory",
]


@dataclass(frozen=True)
class PersonOption:
    """A person selectable as an account owner in the UI.

    Attributes:
        id: Database primary key.
        name: Display name.
    """

    id: int
    name: str


@dataclass(frozen=True)
class AccountDetail:
    """Full account metadata for pre-populating the account edit dialog (F-5).

    Attributes:
        account_id: Database primary key.
        name: Current display name.
        is_long_term: True when the classification is LONG_TERM; False for CURRENT.
        is_investment: True when the underlying account is an InvestmentAccount.
        is_asset: True when classified as an asset; False for liabilities.
        simple_category: Subcategory for simple accounts; None for investment accounts.
        investment_registration: Registration type for investment accounts; None for simple.
        owner_ids: Primary keys of the account's current owners.
    """

    account_id: int
    name: str
    is_long_term: bool
    is_investment: bool
    is_asset: bool
    simple_category: SimpleAccountCategory | None
    investment_registration: InvestmentRegistration | None
    owner_ids: list[int]


@dataclass(frozen=True)
class AccountSummaryRow:
    """A single account entry for the Balance Sheet Summary screen.

    Attributes:
        account_id: Database primary key.
        name: Display name.
        balance: Effective balance as of the query date, or None if unpriceable.
        is_investment: True when the underlying account is an InvestmentAccount.
    """

    account_id: int
    name: str
    balance: Decimal | None
    is_investment: bool


@dataclass(frozen=True)
class BalanceSheetSection:
    """One of the four grouping sections on the Balance Sheet Summary screen.

    Attributes:
        label: Human-readable section title (e.g., "Current Assets").
        accounts: Ordered list of account rows belonging to this section.
        total: Sum of all non-None account balances in this section.
    """

    label: str
    accounts: list[AccountSummaryRow]
    total: Decimal


@dataclass(frozen=True)
class BalanceSheetSummary:
    """Full data contract for the Balance Sheet Summary screen (BS-OP-1).

    Attributes:
        current_assets: Accounts classified as ASSET_CURRENT.
        long_term_assets: Accounts classified as ASSET_LONG_TERM.
        current_liabilities: Accounts classified as LIABILITY_CURRENT.
        long_term_liabilities: Accounts classified as LIABILITY_LONG_TERM.
        current_net_worth: current_assets.total − current_liabilities.total.
        total_net_worth: (current + long-term assets) − (current + long-term liabilities).
        as_of: The effective date used for all balance lookups.
    """

    current_assets: BalanceSheetSection
    long_term_assets: BalanceSheetSection
    current_liabilities: BalanceSheetSection
    long_term_liabilities: BalanceSheetSection
    current_net_worth: Decimal
    total_net_worth: Decimal
    as_of: date


@dataclass(frozen=True)
class AllocationInput:
    """A single asset-class allocation entry for holding creation or update.

    Attributes:
        asset_class_id: Primary key of the AccountAssetClass.
        percent: Percentage allocated (0–100). All inputs for a holding must sum to 100.
    """

    asset_class_id: int
    percent: Decimal


@dataclass(frozen=True)
class AccountAssetClassOption:
    """An asset class selectable in allocation forms.

    Attributes:
        id: Database primary key.
        name: Display name (e.g. "US Equity").
    """

    id: int
    name: str


@dataclass(frozen=True)
class HoldingRow:
    """A single holding entry for the Investment Editor screen (BS-OP-6).

    Attributes:
        holding_id: Database primary key.
        holding_type: ``"listed"`` for a ListedSecurityHolding; ``"exact"`` for
            an ExactHolding.
        name: Display name. Editable for exact; read-only for listed (from API).
        symbol: Ticker symbol. Non-None only for listed holdings.
        quantity: Current quantity as of the query date. Non-None only for listed.
        unit_price: Injected price per share. Non-None only for listed, after pricing.
        total: Computed market value (unit_price × quantity for listed; exact amount
            for manual). May be None if pricing failed.
        total_allocation_percent: Sum of active HoldingAssetClassAllocation
            percentages as of the query date.
    """

    holding_id: int
    holding_type: Literal["listed", "exact"]
    name: str
    symbol: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    total: Decimal | None
    total_allocation_percent: Decimal


@dataclass(frozen=True)
class InvestmentDetails:
    """Full data contract for the Investment Editor screen (BS-OP-6).

    Attributes:
        account_id: Database primary key.
        account_name: Display name of the investment account.
        cash_balance: Uninvested cash as of the query date, or None if no entry exists.
        holdings: Active holdings in insertion order.
        as_of: The effective date used for all lookups.
    """

    account_id: int
    account_name: str
    cash_balance: Decimal | None
    holdings: list[HoldingRow]
    as_of: date


class BalanceSheetAppService:
    """Screen-level facade for the Balance Sheet Summary screen.

    Delegates persistence to BalanceSheetService (core). Exists to enforce the
    rule that UI screens import only from ``service/application/``.

    Owns the session lifetime for every public method (session-per-application-operation):
    each method opens one session via ``db.transaction()`` for its whole body and
    passes it into every core-service call it makes.

    Args:
        core: The injected BalanceSheetService instance.
        session_factory: Session factory used to open one session per public method.
    """

    def __init__(self, core: BalanceSheetService, session_factory: sessionmaker[Session]) -> None:
        """Store the injected core service and session factory."""
        self._core = core
        self._session_factory = session_factory

    async def get_summary(self, as_of: date) -> BalanceSheetSummary:
        """BS-OP-1: Return the full balance sheet summary for ``as_of``.

        Args:
            as_of: Effective date for balance lookups and active-state evaluation.

        Returns:
            A populated :class:`BalanceSheetSummary`.
        """
        with transaction(self._session_factory) as session:
            accounts = await self._core.list_all_accounts(session, as_of)

            def _row(account: object) -> AccountSummaryRow:
                from personal_finance.domain.balance_sheet.account import Account

                a: Account = account  # type: ignore[assignment]
                return AccountSummaryRow(
                    account_id=a.id,
                    name=a.name,
                    balance=a.get_balance(as_of),
                    is_investment=isinstance(a, InvestmentAccount),
                )

            def _section(label: str, classification: AccountClassification) -> BalanceSheetSection:
                rows = [_row(a) for a in accounts if a.classification == classification]
                total = sum(
                    (r.balance for r in rows if r.balance is not None),
                    Decimal("0"),
                )
                return BalanceSheetSection(label=label, accounts=rows, total=total)

            ca = _section("Current Assets", AccountClassification.ASSET_CURRENT)
            la = _section("Long-Term Assets", AccountClassification.ASSET_LONG_TERM)
            cl = _section("Current Liabilities", AccountClassification.LIABILITY_CURRENT)
            ll = _section("Long-Term Liabilities", AccountClassification.LIABILITY_LONG_TERM)

            return BalanceSheetSummary(
                current_assets=ca,
                long_term_assets=la,
                current_liabilities=cl,
                long_term_liabilities=ll,
                current_net_worth=ca.total - cl.total,
                total_net_worth=(ca.total + la.total) - (cl.total + ll.total),
                as_of=as_of,
            )

    def get_account_detail(self, account_id: int) -> AccountDetail:
        """BS-OP-3 (read): Return editable metadata for pre-populating the account edit dialog.

        Args:
            account_id: Primary key of the account.

        Returns:
            An :class:`AccountDetail` suitable for pre-populating the edit dialog.

        Raises:
            ValueError: If the account does not exist.
        """
        with transaction(self._session_factory) as session:
            account = self._core.get_account_detail(session, account_id)
            return AccountDetail(
                account_id=account.id,
                name=account.name,
                is_long_term=account.classification.is_long_term(),
                is_investment=isinstance(account, InvestmentAccount),
                is_asset=account.classification.is_asset(),
                simple_category=account.type if isinstance(account, SimpleAccount) else None,
                investment_registration=(
                    account.investment_registration
                    if isinstance(account, InvestmentAccount)
                    else None
                ),
                owner_ids=[o.id for o in account.owners],
            )

    def update_account_metadata(
        self,
        account_id: int,
        name: str,
        is_long_term: bool,
        simple_category: SimpleAccountCategory | None,
        investment_registration: InvestmentRegistration | None,
        owner_ids: list[int],
    ) -> None:
        """BS-OP-3: Update the editable metadata of an account.

        The asset/liability dimension of the classification is preserved from the
        account's current state; only the current/long-term dimension is changed.

        Args:
            account_id: Primary key of the account.
            name: New display name.
            is_long_term: True for a LONG_TERM classification; False for CURRENT.
            simple_category: New subcategory (simple accounts only).
            investment_registration: New registration type (investment accounts only).
            owner_ids: New list of owner Person primary keys. Must be non-empty.

        Raises:
            ValueError: If the account does not exist, ``owner_ids`` is empty,
                or any owner is not found.
        """
        with transaction(self._session_factory) as session:
            core_detail = self._core.get_account_detail(session, account_id)
            if core_detail.classification.is_asset():
                classification = (
                    AccountClassification.ASSET_LONG_TERM
                    if is_long_term
                    else AccountClassification.ASSET_CURRENT
                )
            else:
                classification = (
                    AccountClassification.LIABILITY_LONG_TERM
                    if is_long_term
                    else AccountClassification.LIABILITY_CURRENT
                )
            self._core.update_account_metadata(
                session,
                account_id=account_id,
                name=name,
                classification=classification,
                simple_category=simple_category,
                investment_registration=investment_registration,
                owner_ids=owner_ids,
            )

    def get_persons(self) -> list[PersonOption]:
        """Return all active persons as selectable options for account ownership.

        Returns:
            Ordered list of :class:`PersonOption` objects.
        """
        with transaction(self._session_factory) as session:
            return [PersonOption(id=p.id, name=p.name) for p in self._core.list_persons(session)]

    def create_account(
        self,
        name: str,
        classification: AccountClassification,
        nature: Literal["simple", "investment"],
        simple_category: SimpleAccountCategory | None,
        investment_registration: InvestmentRegistration | None,
        owner_ids: list[int],
        as_of: date,
    ) -> int:
        """BS-OP-2: Create a new Simple or Investment account.

        Args:
            name: Display name for the new account.
            classification: Balance sheet quadrant (e.g., ASSET_CURRENT).
            nature: ``"simple"`` for a SimpleAccount, ``"investment"`` for an
                InvestmentAccount.
            simple_category: Required when ``nature == "simple"``.
            investment_registration: Required when ``nature == "investment"``.
            owner_ids: Primary keys of one or more owning Persons.
            as_of: Session effective date; becomes ``date_effective`` on the account.

        Returns:
            The database primary key of the newly created account.
        """
        with transaction(self._session_factory) as session:
            return self._core.create_account(
                session,
                name=name,
                classification=classification,
                nature=nature,
                simple_category=simple_category,
                investment_registration=investment_registration,
                owner_ids=owner_ids,
                as_of=as_of,
            )

    def discard_account(self, account_id: int, as_of: date) -> None:
        """BS-OP-4: Soft-delete an account as of the given effective date.

        Args:
            account_id: Primary key of the account to discard.
            as_of: Session effective date to record as the discard date.
        """
        with transaction(self._session_factory) as session:
            self._core.discard_account(session, account_id, as_of)

    def update_simple_account_balance(
        self, account_id: int, as_of: date, new_balance: Decimal
    ) -> None:
        """BS-OP-5: Append a new balance entry for the given effective date.

        Args:
            account_id: Primary key of the SimpleAccount.
            as_of: Effective date for the new balance entry.
            new_balance: The updated monetary balance.
        """
        with transaction(self._session_factory) as session:
            self._core.update_simple_account_balance(session, account_id, as_of, new_balance)

    def update_uninvested_cash_balance(
        self, account_id: int, as_of: date, new_balance: Decimal
    ) -> None:
        """BS-OP-7: Append a new uninvested cash balance entry.

        Args:
            account_id: Primary key of the InvestmentAccount.
            as_of: Effective date for the new balance entry.
            new_balance: The updated uninvested cash amount.
        """
        with transaction(self._session_factory) as session:
            self._core.update_uninvested_cash_balance(session, account_id, as_of, new_balance)

    def update_holding_name(self, holding_id: int, new_name: str) -> None:
        """Rename a holding.

        Args:
            holding_id: Primary key of the holding to rename.
            new_name: Replacement display name.
        """
        with transaction(self._session_factory) as session:
            self._core.update_holding_name(session, holding_id, new_name)

    def discard_holding(self, holding_id: int, as_of: date) -> None:
        """BS-OP-11: Soft-delete a holding.

        Args:
            holding_id: Primary key of the holding to discard.
            as_of: Effective date to record as the discard date.
        """
        with transaction(self._session_factory) as session:
            self._core.discard_holding(session, holding_id, as_of)

    def update_holding_exact_amount(
        self, holding_id: int, as_of: date, new_amount: Decimal
    ) -> None:
        """BS-OP-9: Append a new amount entry for an ExactHolding.

        Args:
            holding_id: Primary key of the ExactHolding.
            as_of: Effective date for the new amount entry.
            new_amount: The updated monetary value.
        """
        with transaction(self._session_factory) as session:
            self._core.update_holding_exact_amount(session, holding_id, as_of, new_amount)

    def update_holding_listed_quantity(
        self, holding_id: int, as_of: date, new_quantity: Decimal
    ) -> None:
        """BS-OP-10: Append a new quantity entry for a ListedSecurityHolding.

        Args:
            holding_id: Primary key of the ListedSecurityHolding.
            as_of: Effective date for the new quantity entry.
            new_quantity: The updated share count. Must be positive.
        """
        with transaction(self._session_factory) as session:
            self._core.update_holding_listed_quantity(session, holding_id, as_of, new_quantity)

    async def get_investment_details(self, account_id: int, as_of: date) -> InvestmentDetails:
        """BS-OP-6: Return full investment account details for the editor screen.

        Fetches the account, prices all listed security holdings via the quote
        service, then assembles a flat :class:`InvestmentDetails` DTO for the UI.

        Args:
            account_id: Primary key of the InvestmentAccount.
            as_of: Effective date for balance lookups, active-state evaluation, and
                price fetching.

        Returns:
            A populated :class:`InvestmentDetails`.

        Raises:
            ValueError: If the account does not exist.
            QuoteServiceError: If pricing any listed holding fails.
        """
        with transaction(self._session_factory) as session:
            account = await self._core.get_investment_account_details(session, account_id, as_of)
            rows: list[HoldingRow] = []
            for c in account.holdings:
                if not c.is_active(as_of):
                    continue
                total = c.get_value(as_of)
                active_allocs = [a for a in c.allocations if a.is_active(as_of)]
                total_pct = sum((a.percent_allocated for a in active_allocs), Decimal("0"))
                if isinstance(c, ListedSecurityHolding):
                    rows.append(
                        HoldingRow(
                            holding_id=c.id,
                            holding_type="listed",
                            name=c.name,
                            symbol=c.symbol,
                            quantity=c.quantity.latest_value_as_of(as_of),
                            unit_price=c.unit_price,
                            total=total,
                            total_allocation_percent=total_pct,
                        )
                    )
                elif isinstance(c, ExactHolding):
                    rows.append(
                        HoldingRow(
                            holding_id=c.id,
                            holding_type="exact",
                            name=c.name,
                            symbol=None,
                            quantity=None,
                            unit_price=None,
                            total=total,
                            total_allocation_percent=total_pct,
                        )
                    )

            return InvestmentDetails(
                account_id=account.id,
                account_name=account.name,
                cash_balance=account.cash_balance.latest_value_as_of(as_of),
                holdings=rows,
                as_of=as_of,
            )

    def get_asset_classes(self, as_of: date) -> list[AccountAssetClassOption]:
        """Return all active asset classes as UI-friendly options.

        Args:
            as_of: Effective date for active-state filtering.

        Returns:
            Ordered list of :class:`AccountAssetClassOption` objects.
        """
        with transaction(self._session_factory) as session:
            return [
                AccountAssetClassOption(id=ac.id, name=ac.name)
                for ac in self._core.list_active_asset_classes(session, as_of)
            ]

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        """BS-OP-13: Search for matching securities via the quote provider.

        Args:
            query: Partial ticker symbol or company name.

        Returns:
            Up to five matching :class:`SecuritySearchResult` objects, or an empty list.

        Raises:
            QuoteServiceError: If the provider fails or the network call times out.
        """
        return await self._core.search_symbols(query)

    async def get_unit_price(self, symbol: str, as_of: date) -> Decimal:
        """Fetch the current unit price for a single symbol.

        Args:
            symbol: Ticker symbol.
            as_of: Effective date for the price lookup.

        Returns:
            Price per share in CAD.

        Raises:
            QuoteServiceError: If the provider fails for this symbol.
        """
        return await self._core.get_unit_price(symbol, as_of)

    def add_holding(
        self,
        account_id: int,
        holding_type: Literal["listed", "exact"],
        name: str,
        as_of: date,
        symbol: str | None,
        initial_quantity: Decimal | None,
        initial_amount: Decimal | None,
        allocations: list[AllocationInput],
    ) -> int:
        """BS-OP-8: Add a listed or exact holding to an investment account.

        Args:
            account_id: Primary key of the target InvestmentAccount.
            holding_type: ``"listed"`` or ``"exact"``.
            name: Display name.
            as_of: Session effective date.
            symbol: Ticker symbol (listed only).
            initial_quantity: Initial share count (listed only; must be positive).
            initial_amount: Initial monetary value (exact only).
            allocations: Allocation inputs that must sum to 100%.

        Returns:
            Primary key of the newly created holding.
        """
        with transaction(self._session_factory) as session:
            return self._core.add_holding(
                session,
                account_id=account_id,
                holding_type=holding_type,
                name=name,
                as_of=as_of,
                symbol=symbol,
                initial_quantity=initial_quantity,
                initial_amount=initial_amount,
                allocations=[(a.asset_class_id, a.percent) for a in allocations],
            )

    def get_holding_allocations(self, holding_id: int, as_of: date) -> dict[int, Decimal]:
        """Return active asset-class allocations for a holding as {asset_class_id: percent}.

        Args:
            holding_id: Primary key of the holding.
            as_of: Effective date for active-state filtering.

        Returns:
            Mapping of asset_class_id → percent_allocated for all active allocations.
        """
        with transaction(self._session_factory) as session:
            return self._core.get_holding_allocations(session, holding_id, as_of)

    def update_holding_asset_allocation(
        self,
        holding_id: int,
        as_of: date,
        allocations: list[AllocationInput],
    ) -> None:
        """BS-OP-12: Overwrite the asset allocations for a holding.

        Args:
            holding_id: Primary key of the holding.
            as_of: Session effective date.
            allocations: New allocation inputs that must sum to 100%.
        """
        with transaction(self._session_factory) as session:
            self._core.update_holding_asset_allocation(
                session,
                holding_id=holding_id,
                as_of=as_of,
                allocations=[(a.asset_class_id, a.percent) for a in allocations],
            )
