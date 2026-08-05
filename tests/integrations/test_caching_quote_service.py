"""Tests for CachingQuoteService."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

import personal_finance.integrations.caching_quote_service as caching_module
from personal_finance.core.interfaces import QuoteService, SecuritySearchResult
from personal_finance.integrations.caching_quote_service import CachingQuoteService


class _CountingQuoteService(QuoteService):
    """Records every get_price_cad call so tests can assert on cache hits/misses."""

    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices
        self.calls: list[tuple[str, date]] = []
        self.search_calls: list[str] = []

    async def get_price_cad(self, symbol: str, as_of: date) -> Decimal:
        self.calls.append((symbol, as_of))
        return self._prices[symbol]

    async def search_symbols(self, query: str) -> list[SecuritySearchResult]:
        self.search_calls.append(query)
        return [SecuritySearchResult(symbol="AAPL", name="Apple Inc.", exchange="NASDAQ")]


_YESTERDAY = date.today() - timedelta(days=1)
_TODAY = date.today()


class TestHistoricalQuotes:
    async def test_second_call_is_a_cache_hit(self) -> None:
        wrapped = _CountingQuoteService({"AAPL": Decimal("100")})
        svc = CachingQuoteService(wrapped)

        await svc.get_price_cad("AAPL", _YESTERDAY)
        await svc.get_price_cad("AAPL", _YESTERDAY)

        assert wrapped.calls == [("AAPL", _YESTERDAY)]

    async def test_cache_hit_never_expires_regardless_of_ttl(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wrapped = _CountingQuoteService({"AAPL": Decimal("100")})
        svc = CachingQuoteService(wrapped, same_day_ttl_seconds=1)

        await svc.get_price_cad("AAPL", _YESTERDAY)

        fake_now = {"t": 0.0}
        monkeypatch.setattr(caching_module.time, "monotonic", lambda: fake_now["t"])
        fake_now["t"] = 100_000.0  # far beyond any TTL

        await svc.get_price_cad("AAPL", _YESTERDAY)

        assert wrapped.calls == [("AAPL", _YESTERDAY)]

    async def test_different_dates_are_independent_cache_entries(self) -> None:
        wrapped = _CountingQuoteService({"AAPL": Decimal("100")})
        svc = CachingQuoteService(wrapped)

        await svc.get_price_cad("AAPL", _YESTERDAY)
        await svc.get_price_cad("AAPL", _YESTERDAY - timedelta(days=1))

        assert len(wrapped.calls) == 2


class TestSameDayQuotes:
    async def test_second_call_within_ttl_is_a_cache_hit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_now = {"t": 1_000.0}
        monkeypatch.setattr(caching_module.time, "monotonic", lambda: fake_now["t"])
        wrapped = _CountingQuoteService({"AAPL": Decimal("100")})
        svc = CachingQuoteService(wrapped, same_day_ttl_seconds=60)

        await svc.get_price_cad("AAPL", _TODAY)
        fake_now["t"] += 30  # within TTL
        await svc.get_price_cad("AAPL", _TODAY)

        assert wrapped.calls == [("AAPL", _TODAY)]

    async def test_call_after_ttl_elapses_refetches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_now = {"t": 1_000.0}
        monkeypatch.setattr(caching_module.time, "monotonic", lambda: fake_now["t"])
        wrapped = _CountingQuoteService({"AAPL": Decimal("100")})
        svc = CachingQuoteService(wrapped, same_day_ttl_seconds=60)

        await svc.get_price_cad("AAPL", _TODAY)
        fake_now["t"] += 61  # past TTL
        await svc.get_price_cad("AAPL", _TODAY)

        assert wrapped.calls == [("AAPL", _TODAY), ("AAPL", _TODAY)]

    async def test_default_ttl_is_five_minutes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_now = {"t": 1_000.0}
        monkeypatch.setattr(caching_module.time, "monotonic", lambda: fake_now["t"])
        wrapped = _CountingQuoteService({"AAPL": Decimal("100")})
        svc = CachingQuoteService(wrapped)

        await svc.get_price_cad("AAPL", _TODAY)
        fake_now["t"] += 299
        await svc.get_price_cad("AAPL", _TODAY)
        assert wrapped.calls == [("AAPL", _TODAY)]

        fake_now["t"] += 2
        await svc.get_price_cad("AAPL", _TODAY)
        assert wrapped.calls == [("AAPL", _TODAY), ("AAPL", _TODAY)]


class TestSearchSymbols:
    async def test_delegates_and_is_not_cached(self) -> None:
        wrapped = _CountingQuoteService({})
        svc = CachingQuoteService(wrapped)

        await svc.search_symbols("AAPL")
        await svc.search_symbols("AAPL")

        assert wrapped.search_calls == ["AAPL", "AAPL"]
