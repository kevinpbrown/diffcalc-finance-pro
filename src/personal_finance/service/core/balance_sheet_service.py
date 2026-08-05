"""Balance Sheet core service — domain operations for balance sheet data."""

import asyncio
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from personal_finance.core.interfaces import QuoteService, SecuritySearchResult
from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.balance_sheet.account import (
    Account,
    AccountClassification,
    InvestmentAccount,
    InvestmentRegistration,
    SimpleAccount,
    SimpleAccountCategory,
)
from personal_finance.domain.balance_sheet.holding import (
    ExactHolding,
    HoldingAssetClassAllocation,
    InvestmentAccountHolding,
    ListedSecurityHolding,
)
from personal_finance.domain.person import Person


class BalanceSheetService:
    """Domain operations for the Balance Sheet module.

    The service is the single entry point for all balance sheet operations from
    the application service layer, and is responsible for pricing listed
    security holdings before returning account data to callers.

    Session-per-application-operation: this service holds no session state.
    Every method that touches the database takes ``session`` as an explicit
    first parameter, supplied by the calling application-service method, which
    owns that session's lifetime and commit/rollback via ``db.transaction()``.
    Methods do not call ``session.commit()`` themselves; they use ``flush()``
    only where a subsequent step in the same call needs a generated primary key.

    Args:
        quote_service: Provider used to fetch market prices for listed securities.
    """

    def __init__(self, quote_service: QuoteService) -> None:
        """Store the injected quote service."""
        self._quote_service = quote_service

    async def list_all_accounts(self, session: Session, as_of: date) -> list[Account]:
        """Return accounts active as of ``as_of``, with listed security holdings fully priced.

        Each active ``ListedSecurityHolding`` inside any ``InvestmentAccount``
        will have its transient computed value injected before the list is returned.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for balance lookups and active-state evaluation.
                Accounts discarded on or before this date are excluded.

        Returns:
            ``Account`` rows that were active as of ``as_of``.

        Raises:
            QuoteServiceError: If the price provider fails for any active listed
                security holding. The operation is aborted; no partial results
                are returned.
            ValueError: If any active holding violates the quantity invariant
                (no non-zero quantity entry covering its active period).
        """
        all_accounts: list[Account] = session.query(Account).all()
        accounts = [a for a in all_accounts if a.is_active(as_of)]
        investment_accounts = [a for a in accounts if isinstance(a, InvestmentAccount)]
        await asyncio.gather(
            *(self._price_listed_securities(account, as_of) for account in investment_accounts)
        )
        return accounts

    def get_total_bank_balance(self, session: Session, as_of: date) -> Decimal:
        """Return the sum of all active BANK account balances as of ``as_of``.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for balance lookups and active-state evaluation.

        Returns:
            Sum of balances across all active BANK accounts. Returns ``Decimal("0")``
            if no accounts exist or none have a balance entry as of ``as_of``.
        """
        accounts = (
            session.query(SimpleAccount)
            .filter(SimpleAccount.type == SimpleAccountCategory.BANK)
            .all()
        )
        total = Decimal("0")
        for account in accounts:
            if not account.is_active(as_of):
                continue
            balance = account.get_balance(as_of)
            if balance is not None:
                total += balance
        return total

    def get_total_current_liability_balance(self, session: Session, as_of: date) -> Decimal:
        """Return the sum of all active current-liability account balances as of ``as_of``.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for balance lookups and active-state evaluation.

        Returns:
            Sum of balances across all active ``LIABILITY_CURRENT`` accounts.
            Returns ``Decimal("0")`` if no such accounts exist.
        """
        accounts = (
            session.query(SimpleAccount)
            .filter(SimpleAccount.classification == AccountClassification.LIABILITY_CURRENT)
            .all()
        )
        total = Decimal("0")
        for account in accounts:
            if not account.is_active(as_of):
                continue
            balance = account.get_balance(as_of)
            if balance is not None:
                total += balance
        return total

    def get_total_by_classification(
        self, session: Session, as_of: date, classification: AccountClassification
    ) -> Decimal:
        """Sum all active account balances for the given balance sheet classification.

        Queries across all Account subtypes (SimpleAccount, InvestmentAccount, …).
        Callers must ensure any active ``InvestmentAccount`` in scope has already
        been priced within this same ``session`` (e.g. via ``list_all_accounts``
        or ``price_investment_account``) before calling this, since holding
        pricing is transient, in-memory state that does not survive a session
        boundary.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for balance lookups and active-state evaluation.
            classification: Balance sheet quadrant to sum.

        Returns:
            Sum of balances across all active accounts in the given classification.
            Returns ``Decimal("0")`` if no such accounts exist.
        """
        accounts = session.query(Account).filter(Account.classification == classification).all()
        total = Decimal("0")
        for account in accounts:
            if not account.is_active(as_of):
                continue
            balance = account.get_balance(as_of)
            if balance is not None:
                total += balance
        return total

    def discard_account(self, session: Session, account_id: int, as_of: date) -> None:
        """BS-OP-4: Soft-delete an account as of the given effective date.

        Args:
            session: The SQLAlchemy session for this operation.
            account_id: Primary key of the account to discard.
            as_of: Session effective date to record as the discard date.

        Raises:
            ValueError: If the account does not exist or discard validation fails.
        """
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id!r} not found")
        account.discard(as_of)

    def get_account_detail(self, session: Session, account_id: int) -> Account:
        """BS-OP-3 (read): Return the domain object for an account.

        Args:
            session: The SQLAlchemy session for this operation.
            account_id: Primary key of the account.

        Returns:
            The :class:`Account` (or concrete subclass) for the given ID.

        Raises:
            ValueError: If the account does not exist.
        """
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id!r} not found")
        return account

    def update_account_metadata(
        self,
        session: Session,
        account_id: int,
        name: str,
        classification: AccountClassification,
        simple_category: SimpleAccountCategory | None,
        investment_registration: InvestmentRegistration | None,
        owner_ids: list[int],
    ) -> None:
        """BS-OP-3: Update the editable metadata of an account.

        The account's nature (simple vs. investment) is immutable after creation
        and is not changed by this operation.

        Args:
            session: The SQLAlchemy session for this operation.
            account_id: Primary key of the account.
            name: New display name.
            classification: New balance sheet quadrant.
            simple_category: New subcategory (SimpleAccount only; ignored for investment accounts).
            investment_registration: New registration type (InvestmentAccount only).
            owner_ids: New list of owner Person primary keys. Must be non-empty.

        Raises:
            ValueError: If the account does not exist, ``owner_ids`` is empty,
                or any owner ID is not found.
        """
        if not owner_ids:
            raise ValueError("At least one owner_id is required")
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id!r} not found")
        owners: list[Person] = []
        for oid in owner_ids:
            person = session.get(Person, oid)
            if person is None:
                raise ValueError(f"Person {oid!r} not found")
            owners.append(person)
        account.name = name
        account.classification = classification
        account.owners = owners
        account.date_modified = date.today()
        if isinstance(account, SimpleAccount) and simple_category is not None:
            account.type = simple_category
        elif isinstance(account, InvestmentAccount) and investment_registration is not None:
            account.investment_registration = investment_registration

    def update_simple_account_balance(
        self, session: Session, account_id: int, effective_date: date, new_balance: Decimal
    ) -> None:
        """BS-OP-5: Append a new balance entry for a SimpleAccount.

        Args:
            session: The SQLAlchemy session for this operation.
            account_id: Primary key of the SimpleAccount.
            effective_date: The date from which the new balance is in effect.
            new_balance: The replacement monetary balance.

        Raises:
            ValueError: If the account does not exist or is not a SimpleAccount.
        """
        account = session.get(SimpleAccount, account_id)
        if account is None:
            raise ValueError(f"SimpleAccount {account_id!r} not found")
        account.balance.offer_value(effective_date, new_balance)

    def list_persons(self, session: Session) -> list[Person]:
        """Return all Person rows in the database.

        Args:
            session: The SQLAlchemy session for this operation.

        Returns:
            All :class:`Person` records, in insertion order.
        """
        return list(session.query(Person).all())

    def create_account(
        self,
        session: Session,
        name: str,
        classification: AccountClassification,
        nature: Literal["simple", "investment"],
        simple_category: SimpleAccountCategory | None,
        investment_registration: InvestmentRegistration | None,
        owner_ids: list[int],
        as_of: date,
    ) -> int:
        """BS-OP-2: Persist a new Simple or Investment account.

        Args:
            session: The SQLAlchemy session for this operation.
            name: Display name for the new account.
            classification: Balance sheet quadrant (ASSET_CURRENT etc.).
            nature: ``"simple"`` for a :class:`SimpleAccount`, ``"investment"`` for
                an :class:`InvestmentAccount`.
            simple_category: Required when ``nature == "simple"``; ignored otherwise.
            investment_registration: Required when ``nature == "investment"``; ignored
                otherwise.
            owner_ids: Primary keys of one or more :class:`Person` owners.
            as_of: Session effective date; becomes ``date_effective`` on the account.

        Returns:
            The database primary key of the newly created account.

        Raises:
            ValueError: If any owner ID is not found, if ``owner_ids`` is empty, or
                if a required discriminator (``simple_category`` /
                ``investment_registration``) is missing.
        """
        if not owner_ids:
            raise ValueError("At least one owner_id is required")

        owners: list[Person] = []
        for oid in owner_ids:
            person = session.get(Person, oid)
            if person is None:
                raise ValueError(f"Person {oid!r} not found")
            owners.append(person)

        today = date.today()
        account: Account
        if nature == "simple":
            if simple_category is None:
                raise ValueError("simple_category is required for a SimpleAccount")
            account = SimpleAccount(
                name=name,
                classification=classification,
                type=simple_category,
                owners=owners,
                date_created=today,
                date_effective=as_of,
                date_modified=today,
            )
        else:
            if investment_registration is None:
                raise ValueError("investment_registration is required for an InvestmentAccount")
            account = InvestmentAccount(
                name=name,
                classification=classification,
                investment_registration=investment_registration,
                owners=owners,
                date_created=today,
                date_effective=as_of,
                date_modified=today,
            )

        session.add(account)
        session.flush()
        assert account.id is not None
        return account.id

    async def get_investment_account_details(
        self, session: Session, account_id: int, as_of: date
    ) -> InvestmentAccount:
        """BS-OP-6: Return a fully-priced InvestmentAccount with all active holdings.

        Fetches market prices for all active ``ListedSecurityHolding`` records
        inside the account before returning, so callers can call ``get_value(as_of)``
        on any holding without a separate pricing step.

        Args:
            session: The SQLAlchemy session for this operation.
            account_id: Primary key of the InvestmentAccount.
            as_of: Effective date for active-state filtering and price lookups.

        Returns:
            The ``InvestmentAccount`` with listed security holdings priced.

        Raises:
            ValueError: If no InvestmentAccount with ``account_id`` exists.
            QuoteServiceError: If the price provider fails for any listed holding.
        """
        account = session.get(InvestmentAccount, account_id)
        if account is None:
            raise ValueError(f"InvestmentAccount {account_id!r} not found")
        await self._price_listed_securities(account, as_of)
        return account

    def update_uninvested_cash_balance(
        self, session: Session, account_id: int, effective_date: date, new_balance: Decimal
    ) -> None:
        """BS-OP-7: Append a new cash balance entry for an InvestmentAccount.

        Args:
            session: The SQLAlchemy session for this operation.
            account_id: Primary key of the InvestmentAccount.
            effective_date: The date from which the new balance is in effect.
            new_balance: The replacement uninvested cash amount.

        Raises:
            ValueError: If the account does not exist.
        """
        account = session.get(InvestmentAccount, account_id)
        if account is None:
            raise ValueError(f"InvestmentAccount {account_id!r} not found")
        account.cash_balance.offer_value(effective_date, new_balance)

    def update_holding_name(self, session: Session, holding_id: int, new_name: str) -> None:
        """Rename an existing active holding.

        Args:
            session: The SQLAlchemy session for this operation.
            holding_id: Primary key of the holding to rename.
            new_name: Replacement display name.

        Raises:
            ValueError: If the holding does not exist.
        """
        holding = session.get(InvestmentAccountHolding, holding_id)
        if holding is None:
            raise ValueError(f"Holding {holding_id!r} not found")
        holding.name = new_name

    def discard_holding(self, session: Session, holding_id: int, as_of: date) -> None:
        """BS-OP-11: Soft-delete a holding as of the given effective date.

        Args:
            session: The SQLAlchemy session for this operation.
            holding_id: Primary key of the holding to discard.
            as_of: Effective date to record as the discard date.

        Raises:
            ValueError: If the holding does not exist.
        """
        holding = session.get(InvestmentAccountHolding, holding_id)
        if holding is None:
            raise ValueError(f"Holding {holding_id!r} not found")
        holding.discard(as_of)

    def update_holding_exact_amount(
        self, session: Session, holding_id: int, effective_date: date, new_amount: Decimal
    ) -> None:
        """BS-OP-9: Append a new amount entry for an ExactHolding.

        Args:
            session: The SQLAlchemy session for this operation.
            holding_id: Primary key of the ExactHolding.
            effective_date: The date from which the new amount is in effect.
            new_amount: The replacement monetary value.

        Raises:
            ValueError: If the holding does not exist or is not an ExactHolding.
        """
        holding = session.get(ExactHolding, holding_id)
        if holding is None:
            raise ValueError(f"ExactHolding {holding_id!r} not found")
        holding.amount.offer_value(effective_date, new_amount)

    def update_holding_listed_quantity(
        self, session: Session, holding_id: int, effective_date: date, new_quantity: Decimal
    ) -> None:
        """BS-OP-10: Append a new quantity entry for a ListedSecurityHolding.

        Args:
            session: The SQLAlchemy session for this operation.
            holding_id: Primary key of the ListedSecurityHolding.
            effective_date: The date from which the new quantity is in effect.
            new_quantity: The replacement share count. Must be positive.

        Raises:
            ValueError: If the holding does not exist, is not a
                ListedSecurityHolding, or ``new_quantity`` is not positive.
        """
        holding = session.get(ListedSecurityHolding, holding_id)
        if holding is None:
            raise ValueError(f"ListedSecurityHolding {holding_id!r} not found")
        if new_quantity <= 0:
            raise ValueError(f"Quantity must be positive; got {new_quantity}")
        holding.quantity.offer_value(effective_date, new_quantity)

    def list_active_asset_classes(self, session: Session, as_of: date) -> list[AccountAssetClass]:
        """Return all AccountAssetClass records active as of ``as_of``.

        Args:
            session: The SQLAlchemy session for this operation.
            as_of: Effective date for active-state filtering.

        Returns:
            Asset classes ordered by ``order_precedence``.
        """
        all_classes: list[AccountAssetClass] = session.query(AccountAssetClass).all()
        return sorted(
            (c for c in all_classes if c.is_active(as_of)),
            key=lambda c: c.order_precedence,
        )

    def add_holding(
        self,
        session: Session,
        account_id: int,
        holding_type: Literal["listed", "exact"],
        name: str,
        as_of: date,
        symbol: str | None,
        initial_quantity: Decimal | None,
        initial_amount: Decimal | None,
        allocations: list[tuple[int, Decimal]],
    ) -> int:
        """BS-OP-8: Add a holding to an investment account.

        Args:
            session: The SQLAlchemy session for this operation.
            account_id: Primary key of the target InvestmentAccount.
            holding_type: ``"listed"`` for a ListedSecurityHolding;
                ``"exact"`` for an ExactHolding.
            name: Display name.
            as_of: Session effective date; used for timeline and Discardable fields.
            symbol: Ticker symbol (required when ``holding_type == "listed"``).
            initial_quantity: Initial share count (required for listed; must be positive).
            initial_amount: Initial monetary value (required for exact).
            allocations: ``(asset_class_id, percent)`` pairs that must sum to 100.

        Returns:
            The primary key of the newly created holding.

        Raises:
            ValueError: If the account is not found, required fields are missing,
                initial_quantity is not positive, or allocations do not sum to 100.
        """
        account = session.get(InvestmentAccount, account_id)
        if account is None:
            raise ValueError(f"InvestmentAccount {account_id!r} not found")

        total_pct = sum(pct for _, pct in allocations)
        if total_pct != Decimal("100"):
            raise ValueError(f"Allocations must sum to 100%; got {total_pct}")

        if holding_type == "listed":
            if not symbol:
                raise ValueError("Listed holdings require a symbol")
            if initial_quantity is None or initial_quantity <= 0:
                raise ValueError("Listed holdings require a positive initial_quantity")
            holding: InvestmentAccountHolding = ListedSecurityHolding(
                investment_account_id=account_id,
                name=name,
                symbol=symbol,
                date_created=as_of,
                date_effective=as_of,
                date_modified=as_of,
            )
            holding.quantity.offer_value(as_of, initial_quantity)  # type: ignore[attr-defined]
        else:
            if initial_amount is None:
                raise ValueError("Exact holdings require an initial_amount")
            holding = ExactHolding(
                investment_account_id=account_id,
                name=name,
                date_created=as_of,
                date_effective=as_of,
                date_modified=as_of,
            )
            holding.amount.offer_value(as_of, initial_amount)

        session.add(holding)
        session.flush()

        for asset_class_id, pct in allocations:
            session.add(
                HoldingAssetClassAllocation(
                    holding_id=holding.id,
                    asset_class_id=asset_class_id,
                    percent_allocated=pct,
                    date_created=as_of,
                    date_effective=as_of,
                    date_modified=as_of,
                )
            )

        return holding.id

    def get_holding_allocations(
        self, session: Session, holding_id: int, as_of: date
    ) -> dict[int, Decimal]:
        """Return active asset-class allocations for a holding as {asset_class_id: percent}.

        Args:
            session: The SQLAlchemy session for this operation.
            holding_id: Primary key of the holding.
            as_of: Effective date for active-state filtering.

        Returns:
            Mapping of asset_class_id → percent_allocated for all active allocations.
            Returns an empty dict if the holding is not found.
        """
        holding = session.get(InvestmentAccountHolding, holding_id)
        if holding is None:
            return {}
        return {
            alloc.asset_class_id: alloc.percent_allocated
            for alloc in holding.allocations
            if alloc.is_active(as_of)
        }

    def update_holding_asset_allocation(
        self,
        session: Session,
        holding_id: int,
        as_of: date,
        allocations: list[tuple[int, Decimal]],
    ) -> None:
        """BS-OP-12: Overwrite the asset allocations for a holding.

        Discards all currently active ``HoldingAssetClassAllocation`` records
        then inserts a fresh set with ``date_effective = as_of``.

        Args:
            session: The SQLAlchemy session for this operation.
            holding_id: Primary key of the holding to update.
            as_of: Session effective date.
            allocations: ``(asset_class_id, percent)`` pairs that must sum to 100.

        Raises:
            ValueError: If the holding is not found or allocations don't sum to 100.
        """
        holding = session.get(InvestmentAccountHolding, holding_id)
        if holding is None:
            raise ValueError(f"Holding {holding_id!r} not found")

        total_pct = sum(pct for _, pct in allocations)
        if total_pct != Decimal("100"):
            raise ValueError(f"Allocations must sum to 100%; got {total_pct}")

        for alloc in holding.allocations:
            if alloc.is_active(as_of):
                alloc.discard(as_of)

        for asset_class_id, pct in allocations:
            session.add(
                HoldingAssetClassAllocation(
                    holding_id=holding_id,
                    asset_class_id=asset_class_id,
                    percent_allocated=pct,
                    date_created=as_of,
                    date_effective=as_of,
                    date_modified=as_of,
                )
            )

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        """BS-OP-13: Search for matching securities via the quote provider.

        Args:
            query: Partial ticker symbol or company name.

        Returns:
            Up to five matching :class:`SecuritySearchResult` objects.

        Raises:
            QuoteServiceError: If the provider fails or the network call times out.
        """
        return await self._quote_service.search_symbols(query)

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
        return await self._quote_service.get_price_cad(symbol, as_of)

    async def price_investment_account(self, account: InvestmentAccount, as_of: date) -> None:
        """Inject market prices for all active listed security holdings in ``account``.

        A convenience wrapper around the private ``_price_listed_securities``
        helper, exposed so other core services (e.g. ``GoalService``) can price
        allocated accounts without going through a full account fetch. Takes no
        session: it operates purely on the in-memory ``account`` object plus the
        injected quote service, and the underlying ``QuoteService`` is expected
        to be cache-backed so repeated calls across independent sessions are
        cheap.

        Args:
            account: The investment account whose listed holdings need pricing.
            as_of: Effective date for active-state filtering and price lookup.

        Raises:
            QuoteServiceError: If the price provider fails for any holding.
            ValueError: If any holding violates the quantity invariant.
        """
        await self._price_listed_securities(account, as_of)

    async def _price_listed_securities(self, account: InvestmentAccount, as_of: date) -> None:
        """Fetch and inject prices for all active listed security holdings.

        Args:
            account: The investment account to process.
            as_of: Effective date; used for active-state filtering and price lookup.
        """
        active_listed = [
            c
            for c in account.holdings
            if isinstance(c, ListedSecurityHolding) and c.is_active(as_of)
        ]
        await asyncio.gather(*(self._price_holding(c, as_of) for c in active_listed))

    async def _price_holding(self, holding: ListedSecurityHolding, as_of: date) -> None:
        """Fetch the market price per share and inject it into the holding.

        Args:
            holding: The listed security holding to price.
            as_of: Effective date for the quantity validation and price lookup.

        Raises:
            ValueError: If the holding has no positive quantity entry as of ``as_of``.
            QuoteServiceError: If the price provider fails for this symbol.
        """
        if holding.is_priced(as_of):
            return
        holding.validate_quantity(as_of)
        price = await self._quote_service.get_price_cad(holding.symbol, as_of)
        holding.set_unit_price(as_of, price)
