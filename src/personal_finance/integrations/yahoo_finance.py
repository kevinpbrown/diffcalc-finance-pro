"""Yahoo Finance implementation of QuoteService via the yfinance library.

Note: yfinance is a synchronous library. All network calls are dispatched to a
thread-pool executor so the asyncio event loop is never blocked.

Integration tests for this provider are marked ``external`` and excluded from
the default test run; this module is excluded from coverage enforcement.
"""

import asyncio
import logging
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf  # type: ignore[import-untyped]

from personal_finance.core.interfaces import QuoteService, QuoteServiceError, SecuritySearchResult

logger = logging.getLogger(__name__)

# Yahoo Finance exchange codes that price securities in CAD.
# Filtering to these codes avoids surfacing USD-priced results until
# currency conversion is added to the application.
#   TOR → Toronto Stock Exchange (TSX)
#   NEO → NEO Exchange
#   VSE → TSX Venture Exchange (Yahoo Finance's internal name for TSXV)
#   CNQ → Canadian Securities Exchange (CSE)
_CAD_EXCHANGES: frozenset[str] = frozenset({"TOR", "NEO", "VSE", "CNQ"})

# Technical charter, Network Security: all external HTTP/HTTPS requests must use
# a timeout (default 10 seconds). Passed explicitly to every yfinance call below
# rather than relying on the library's own defaults, which are not guaranteed to
# stay at 10s across yfinance versions.
_REQUEST_TIMEOUT_SECONDS = 10


class YahooFinanceQuoteService(QuoteService):
    """Quote service backed by the yfinance library.

    Fetches real-time prices for today's date and historical closing prices
    for past dates. All prices are returned in CAD; symbols denominated in other
    currencies must include the appropriate Yahoo Finance suffix (e.g. ``XEQT.TO``
    for TSX-listed securities).
    """

    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:
        """Return the closing price in CAD via yfinance.

        Runs the blocking yfinance call in the default thread-pool executor.

        Args:
            symbol: The ticker symbol (e.g. ``"AAPL"``, ``"XEQT.TO"``).
            as_of: When today's date, returns the most recent available price.
                When a past date, returns the closing price on that date.

        Returns:
            Price per share in CAD.

        Raises:
            QuoteServiceError: If yfinance returns no data or the network call fails.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_price_sync, symbol, as_of)

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        """Return up to five matching securities via the Yahoo Finance search endpoint.

        Runs the blocking yfinance ``Search`` call in the default thread-pool executor.

        Args:
            query: A partial ticker symbol or company name.

        Returns:
            Up to five :class:`SecuritySearchResult` objects ordered by relevance.

        Raises:
            QuoteServiceError: If the network call fails or yfinance raises.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._search_symbols_sync, query)

    def _fetch_price_sync(self, symbol: str, as_of: date) -> Decimal:
        """Synchronous yfinance call; runs in a thread pool.

        Args:
            symbol: The ticker symbol.
            as_of: The effective date for the price lookup.

        Returns:
            Price per share in CAD.

        Raises:
            QuoteServiceError: If yfinance returns no data or raises an exception.
        """
        try:
            ticker = yf.Ticker(symbol)
            if as_of >= date.today():
                hist = ticker.history(period="1d", timeout=_REQUEST_TIMEOUT_SECONDS)
            else:
                hist = ticker.history(
                    start=as_of.isoformat(),
                    end=(as_of + timedelta(days=1)).isoformat(),
                    timeout=_REQUEST_TIMEOUT_SECONDS,
                )
            if hist.empty:
                raise QuoteServiceError(
                    f"No price data returned by Yahoo Finance for symbol={symbol!r} as_of={as_of}"
                )
            return Decimal(str(hist["Close"].iloc[-1]))
        except QuoteServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Yahoo Finance call failed for symbol=%r as_of=%s",
                symbol,
                as_of,
                exc_info=True,
            )
            raise QuoteServiceError(
                f"Yahoo Finance call failed for symbol={symbol!r} as_of={as_of}"
            ) from exc

    def _search_symbols_sync(self, query: str) -> list[SecuritySearchResult]:
        """Synchronous yfinance search call; runs in a thread pool.

        Args:
            query: A partial ticker symbol or company name.

        Returns:
            Up to five :class:`SecuritySearchResult` objects.

        Raises:
            QuoteServiceError: If yfinance raises or returns an unexpected response.
        """
        try:
            search = yf.Search(
                query,
                max_results=5,
                news_count=0,
                lists_count=0,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            results: list[SecuritySearchResult] = []
            for item in search.quotes:
                symbol: str = item.get("symbol", "")
                raw_exchange: str = item.get("exchange", "")
                is_us_unit = symbol.split(".")[0].endswith("-U")
                if not symbol or raw_exchange not in _CAD_EXCHANGES or is_us_unit:
                    continue
                name: str = item.get("shortname") or item.get("longname") or symbol
                exchange: str = item.get("exchDisp") or raw_exchange
                results.append(SecuritySearchResult(symbol=symbol, name=name, exchange=exchange))
                if len(results) == 5:
                    break
            return results
        except Exception as exc:  # noqa: BLE001
            logger.warning("Yahoo Finance search failed for query=%r", query, exc_info=True)
            raise QuoteServiceError(f"Yahoo Finance search failed for query={query!r}") from exc
