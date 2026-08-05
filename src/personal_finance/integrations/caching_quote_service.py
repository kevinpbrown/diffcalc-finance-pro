"""Caching decorator for QuoteService implementations.

Decouples pricing correctness from SQLAlchemy session/object identity: prices
are cached by (symbol, as_of) rather than memoized as a transient attribute on
a single ORM instance, so repeated pricing calls across independent sessions
are cheap instead of triggering redundant network calls.

@adr specs/working-artefacts/adr/2026-07-28-backend-shared-session-transaction-safety.md
"""

import time
from datetime import date
from decimal import Decimal

from personal_finance.core.interfaces import QuoteService, SecuritySearchResult

_DEFAULT_SAME_DAY_TTL_SECONDS = 300.0


class CachingQuoteService(QuoteService):
    """Caches ``get_price_cad`` results by ``(symbol, as_of)``.

    Historical quotes (``as_of`` before today at fetch time) are end-of-day
    closes and never change, so they are cached for the life of the process.
    Same-day quotes can move intraday, so they are cached with a configurable
    TTL. ``search_symbols`` is passed straight through, uncached.

    Args:
        wrapped: The underlying ``QuoteService`` to fetch prices from on a
            cache miss.
        same_day_ttl_seconds: How long a same-day price stays cached before
            it is re-fetched. Read from ``settings.same_day_quote_ttl_seconds``
            in ``config.toml``.
    """

    def __init__(
        self,
        wrapped: QuoteService,
        same_day_ttl_seconds: float = _DEFAULT_SAME_DAY_TTL_SECONDS,
    ) -> None:
        """Store the wrapped service, TTL, and an empty cache."""
        self._wrapped = wrapped
        self._same_day_ttl_seconds = same_day_ttl_seconds
        self._cache: dict[tuple[str, date], tuple[Decimal, float | None]] = {}

    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:
        """Return a cached price when available and unexpired, else fetch and cache it.

        Args:
            symbol: The ticker symbol.
            as_of: The effective date for the price lookup.

        Returns:
            Price per share in CAD.

        Raises:
            QuoteServiceError: Propagated from the wrapped service on a cache miss.
        """
        key = (symbol, as_of)
        cached = self._cache.get(key)
        if cached is not None:
            price, expires_at = cached
            if expires_at is None or time.monotonic() < expires_at:
                return price

        price = await self._wrapped.get_price_cad(symbol, as_of)
        expires_at = None if as_of < date.today() else time.monotonic() + self._same_day_ttl_seconds
        self._cache[key] = (price, expires_at)
        return price

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        """Delegate directly to the wrapped service; search results are not cached.

        Args:
            query: A partial ticker symbol or company name.

        Returns:
            Up to five matching :class:`SecuritySearchResult` objects.
        """
        return await self._wrapped.search_symbols(query)
