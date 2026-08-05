"""Abstract base classes for all third-party integrations.

All concrete provider implementations must subclass the ABCs defined here and
be injected via constructor rather than instantiated directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class QuoteServiceError(Exception):
    """Raised when a quote provider cannot return a price.

    Signals a provider-level failure (network error, timeout, no data for the
    requested symbol or date). Callers should surface this to the user rather
    than silently treating the holding as unpriced.
    """


@dataclass(frozen=True)
class SecuritySearchResult:
    """A single result from a symbol search query.

    Attributes:
        symbol: The ticker symbol (e.g. ``"AAPL"``, ``"XEQT.TO"``).
        name: The security's display name (e.g. ``"Apple Inc."``).
        exchange: The exchange on which the security is listed (e.g. ``"NASDAQ"``).
    """

    symbol: str
    name: str
    exchange: str


class QuoteService(ABC):
    """Abstract interface for fetching security market prices and searching symbols.

    Implementations are expected to be async-safe; long-running network calls
    must not block the asyncio event loop.
    """

    @abstractmethod
    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:
        """Return the price per share in CAD as of the given date.

        When ``as_of`` is today's date, returns the most recent available price.
        When ``as_of`` is a past date, returns the closing price on that date.

        Args:
            symbol: The ticker symbol (e.g. ``"AAPL"``, ``"XEQT.TO"``).
            as_of: The effective date for the price lookup.

        Returns:
            Price per share in CAD.

        Raises:
            QuoteServiceError: If the provider fails or returns no data for the
                requested symbol and date (network error, timeout, unknown symbol,
                no trading data on that date, etc.).
        """

    @abstractmethod
    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        """Return up to five matching securities for the given search query.

        Args:
            query: A partial ticker symbol or company name (e.g. ``"XEQT"`` or
                ``"Apple"``).

        Returns:
            Up to five :class:`SecuritySearchResult` objects ordered by relevance.
            Returns an empty list when no matches are found.

        Raises:
            QuoteServiceError: If the provider fails or the network call times out.
        """
