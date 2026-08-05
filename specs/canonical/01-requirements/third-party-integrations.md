# Third-Party Integrations

This document defines external APIs and services the system depends on, documenting the API contract, required usage patterns, and constraints imposed on the implementation.

## Financial Data Providers

### FD-1: Security Price Lookup & Symbol Search
**Purpose:** Fetch current market prices for equities, ETFs, mutual funds, and other securities to revalue investment holdings, and provide a typeahead autocomplete for accurate ticker entry.

**Provider:**
- **Yahoo Finance** (via `yfinance` Python library and public autocomplete endpoints) - free, no API key required.

**Required Capabilities:**
- Perform typeahead symbol search via the public Yahoo Finance search endpoint to retrieve valid symbols, exchange names, and quote types.
- Lookup price by standard Yahoo symbol (e.g., "AAPL", "VTI", "XEQT.TO").
- Return current price in CAD.
- Support for common exchanges (NYSE, NASDAQ, TSX).
- Fallback to previous close if real-time price unavailable.

**Integration Constraints:**
- The system must not block the UI thread while fetching prices or performing autocomplete searches; use asynchronous calls or background threads.
- Prices should be cached locally for at least 24 hours to reduce API calls. Autocomplete results may be cached based on the search string.
- The user must be able to disable automatic price updates via configuration.
- Provider failures (network errors, timeouts, no data) must **surface to the UI** as a `QuoteServiceError`, not be silently swallowed. The UI shall show a user-friendly message (e.g., "Price update temporarily unavailable") when this occurs.

**API Contract (Abstract):**
```python
class QuoteServiceError(Exception):
    """Raised when the provider cannot return a price for any reason."""

@dataclass(frozen=True)
class SecuritySearchResult:
    symbol: str   # ticker symbol, e.g. "XEQT.TO"
    name: str     # display name, e.g. "iShares Core Equity ETF Portfolio"
    exchange: str # exchange name, e.g. "Toronto"

class QuoteService(ABC):
    async def get_price_cad(symbol: str, as_of: date) -> Decimal:
        """Return price per share in CAD. Raises QuoteServiceError on any failure."""

    async def search_symbols(query: str) -> list[SecuritySearchResult]:
        """Return up to five matching results ordered by relevance.
        Returns an empty list when no matches are found."""
```

## Implementation Guidelines

### General Principles
1. **Dependency Injection:** Third-party integrations shall be accessed through abstract interfaces, allowing easy mocking or swapping of providers.
2. **Fail-fast on pricing failure:** A missing or unavailable price is not silently dropped. `get_price_cad` raises `QuoteServiceError`; the service propagates it; the UI catches it and shows a clear error. No holding is ever silently unpriced.
3. **Rate Limiting & Caching:** Respect provider rate limits; implement local caching to minimize external calls.

### Security Requirements
- Network requests must validate TLS certificates.
- The application shall not transmit any personal financial data to third parties; only publicly traded ticker symbols are sent to the pricing provider.

### Error Handling
- Network timeouts shall be set appropriately (e.g., 10 seconds for price lookups).
- Provider errors shall be logged at WARNING level with enough context to diagnose.
- The UI shall show a user-friendly message (e.g., "Price update temporarily unavailable") when an integration fails.

### Testing
- Integration tests for third-party providers shall be marked as "slow" or "external" and excluded from default test runs.
- Mock implementations of all provider interfaces shall be provided for unit testing.
- The test suite must verify that the system behaves correctly when providers return errors or malformed data.
