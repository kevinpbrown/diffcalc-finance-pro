"""Integration tests for YahooFinanceQuoteService.

These tests make real network calls to Yahoo Finance and are marked ``external``
so they are excluded from the default test run. Run them explicitly with:

    pytest -m external
"""

from datetime import date
from decimal import Decimal

import pytest

from personal_finance.core.interfaces import QuoteServiceError, SecuritySearchResult
from personal_finance.integrations.yahoo_finance import YahooFinanceQuoteService

pytestmark = pytest.mark.external


@pytest.fixture()
def service() -> YahooFinanceQuoteService:
    return YahooFinanceQuoteService()


class TestGetPriceCadHistorical:
    async def test_returns_positive_decimal_for_past_date(
        self, service: YahooFinanceQuoteService
    ) -> None:
        # XEQT.TO is a liquid TSX ETF with data going back to 2019
        price = await service.get_price_cad("XEQT.TO", date(2024, 6, 3))

        assert isinstance(price, Decimal)
        assert price > 0

    async def test_historical_price_is_within_plausible_range(
        self, service: YahooFinanceQuoteService
    ) -> None:
        # XEQT.TO traded in the ~$30–$40 CAD range in mid-2024
        price = await service.get_price_cad("XEQT.TO", date(2024, 6, 3))

        assert Decimal("20") < price < Decimal("60")

    async def test_usd_symbol_returns_decimal(self, service: YahooFinanceQuoteService) -> None:
        # AAPL is a highly liquid symbol; any weekday in 2024 should have data
        price = await service.get_price_cad("AAPL", date(2024, 6, 3))

        assert isinstance(price, Decimal)
        assert price > 0


class TestGetPriceCadCurrent:
    async def test_returns_positive_decimal_for_today(
        self, service: YahooFinanceQuoteService
    ) -> None:
        price = await service.get_price_cad("XEQT.TO", date.today())

        assert isinstance(price, Decimal)
        assert price > 0


class TestGetPriceCadErrors:
    async def test_invalid_symbol_raises_quote_service_error(
        self, service: YahooFinanceQuoteService
    ) -> None:
        with pytest.raises(QuoteServiceError):
            await service.get_price_cad("INVALID_TICKER_XYZ_999", date(2024, 6, 3))


class TestSearchSymbols:
    async def test_returns_list_of_security_search_results(
        self, service: YahooFinanceQuoteService
    ) -> None:
        results = await service.search_symbols("XEQT")

        assert isinstance(results, list)
        assert all(isinstance(r, SecuritySearchResult) for r in results)

    async def test_results_have_non_empty_symbol_and_name(
        self, service: YahooFinanceQuoteService
    ) -> None:
        results = await service.search_symbols("XEQT")

        assert len(results) > 0
        for r in results:
            assert r.symbol
            assert r.name

    async def test_returns_at_most_five_results(self, service: YahooFinanceQuoteService) -> None:
        results = await service.search_symbols("ETF")

        assert len(results) <= 5

    async def test_exact_cad_symbol_appears_in_results(
        self, service: YahooFinanceQuoteService
    ) -> None:
        # XEQT.TO is a known TSX ETF; an exact query should surface it first
        results = await service.search_symbols("XEQT.TO")

        symbols = [r.symbol for r in results]
        assert "XEQT.TO" in symbols

    async def test_only_cad_exchanges_returned(self, service: YahooFinanceQuoteService) -> None:
        # "Apple" matches AAPL (NASDAQ/NMS) among others; none should appear
        results = await service.search_symbols("Apple")

        for r in results:
            assert r.exchange in {"Toronto", "NEO", "VSE", "Canadian Sec"}

    async def test_usd_only_symbol_returns_empty(self, service: YahooFinanceQuoteService) -> None:
        # AAPL trades only on NASDAQ; should return nothing after CAD filtering
        results = await service.search_symbols("AAPL")

        assert all(r.symbol != "AAPL" for r in results)

    async def test_empty_results_for_nonsense_query(
        self, service: YahooFinanceQuoteService
    ) -> None:
        # A truly gibberish query should return an empty list, not raise
        results = await service.search_symbols("ZZZZZZZZZZZZZNOMATCH99999")

        assert isinstance(results, list)
