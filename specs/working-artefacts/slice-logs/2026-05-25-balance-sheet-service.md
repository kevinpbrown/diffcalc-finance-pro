# Slice: Balance Sheet Service Layer

**Date:** 2026-05-25
**Status:** Completed

## Description

Implements the first vertical slice of the service layer for the Balance Sheet module.
Introduces `BalanceSheetService` with `list_all_accounts(as_of)` as the entry point,
along with the `QuoteService` ABC and a Yahoo Finance stub for pricing listed securities.

The key design challenge in this slice is that `ListedSecurityHolding.get_value()`
cannot resolve a price without an external market data call. This slice introduces a
transient "stuffing" pattern: the service fetches prices and injects them into the domain
objects before returning them to the caller. The domain objects remain unaware of any
external provider.

## Specification References

### UI Flows to Implement

N/A — no UI flows are in scope for this slice.

### Operations to Implement

- [ ] `BS-OP-1` — Get Balance Sheet Summary (partial: `list_all_accounts` is the data foundation)
- [ ] `BS-OP-6` — Get Investment Account Details (the pricing infrastructure built here is its prerequisite)

## Dependencies

- [Domain Model Foundation](2026-05-16-domain-model-foundation.md)

## ADRs

### Referenced
- None

### Created
- None

## TODOs

### Completed
- None

### Created
- None

## Decisions Made

- **Transient stuffing pattern** — `ListedSecurityHolding` gains two Python-only
  (non-mapped) transient fields: `_priced_as_of` and `_precomputed_value`. The service
  calls `set_computed_value(as_of, value)` after fetching prices; subsequent `get_value(as_of)`
  calls return the injected value. If `get_value` is called with a date that doesn't match
  `_priced_as_of`, a `ValueError` is raised to catch programming errors early.
  SQLAlchemy `@reconstructor` initialises the transient fields to `None` on DB load.

- **`QuoteService` ABC in `core.interfaces`** — follows the technical charter's
  requirement that all third-party integrations be accessed via ABCs in `core.interfaces`.
  Concrete implementations live in `src/personal_finance/integrations/`.

- **`YahooFinanceQuoteService` is a stub** — the Yahoo Finance implementation wraps
  `yfinance` in a thread-pool executor to avoid blocking the asyncio event loop.
  It is excluded from coverage enforcement (integrations are integration-tested separately).

- **Async-first service** — `BalanceSheetService` methods are `async`. Concurrent price
  fetches for multiple holdings use `asyncio.gather`. Single-security accounts still
  benefit from the non-blocking async call chain.

- **Abort-on-pricing-failure** — `QuoteServiceError` propagates unhandled out of
  `list_all_accounts`; no partial results are returned. `YahooFinanceQuoteService` logs a
  warning before raising so the failure is visible in logs without caller intervention.

- **`quantity` stays scalar** — `ListedSecurityHolding.quantity` is not yet temporal.
  The service uses the current scalar directly. BS-OP-10 notes this is an open design choice;
  if temporal quantity history becomes a requirement, it will be converted to an
  `EffectiveAmount` timeline.

- **`QuoteService.search_symbols` deferred** — the third-party-integrations spec
  (`FD-1`) declares `search_symbols` as part of the `QuoteService` ABC, but only
  `get_price_cad` is implemented in this slice. BS-OP-13 ("Search Securities") is
  out of scope; adding a mock now would bake in a poorly-thought-out shape. The
  method will be added to the ABC when BS-OP-13 is implemented, alongside a real
  Yahoo Finance autocomplete call and any UI typeahead requirements.

## Uncertainties

- [x] `yfinance` currency handling — deferred. All securities in scope are assumed to be
  CAD-denominated (TSX-listed with `.TO` suffix). USD-listed securities and FX conversion
  are out of base scope; if added in a future slice, `get_price_cad` will need a conversion
  step.
- [x] `list_all_accounts` active filtering — resolved: the service filters accounts at the
  service layer using `account.is_active(as_of)`. Discarded accounts are excluded from the
  result; callers receive only accounts active as of the requested effective date.

## Handoff Notes

- `BalanceSheetService.list_all_accounts` is the data foundation for `BS-OP-1`. The
  remaining aggregation logic (grouping by classification, totals) belongs in the next slice.
- `YahooFinanceQuoteService._fetch_price_sync` is a stub — no caching, no FX conversion,
  no rate limiting. These are required per the third-party integrations spec and must be
  addressed before production use.
- Next recommended slice: Balance Sheet summary aggregation + read-only TUI screen (BS-OP-1).

---

*This slice-log is a working-artefact specification. It is not actively maintained after the slice is complete.*
