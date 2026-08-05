# service/core

Core (domain) services: reusable business logic operations that map directly to
the named operations in the service-operations spec (`BS-OP-*`, `CF-OP-*`,
`GOAL-OP-*`, `GEN-OP-*`).

These services must be independently testable without Textual and must contain no
knowledge of how any specific screen presents their output.

## Services

- **`balance_sheet_service.py`** — `BS-OP-*` operations (list and price accounts).
- **`goal_service.py`** — `G-OP-*` operations (goal domain logic).
- **`cash_flow_service.py`** — `CF-OP-*` operations (cash flow domain logic).
- **`general_service.py`** — `GEN-OP-*` cross-cutting operations (e.g. Amount Left to Invest).

## Key Constraints

- No imports from `service/application/` or the `ui/` layer.
- No screen-specific filtering or output shaping.
- Async only where I/O is genuinely async (network calls via injected providers).

## Session ownership (session-per-application-operation)

Core services hold **no session state**. Every method that touches the
database takes `session: Session` as an explicit first parameter, supplied by
the calling application-service method — never store a session on `self` or
accept one in `__init__`. Core-service methods must not call
`session.commit()` or `session.rollback()`; only `flush()` where a later step
in the same method needs a generated primary key. The application-service
layer owns the session's lifetime and commit/rollback via `db.transaction()`.
See `service/application/README.md` and
`specs/working-artefacts/adr/2026-07-28-backend-shared-session-transaction-safety.md`
for the full rationale.

`GoalService` is constructed with an injected `BalanceSheetService` (permitted:
`goals` may depend on `balance_sheet`, and core services may call other core
services) so `get_total_bank_claim` can price AutoFill goals' allocated
accounts itself via `BalanceSheetService.price_investment_account()` — call
the public method, never the private `_price_listed_securities()`. Pricing is
cache-backed at the `QuoteService` layer (`CachingQuoteService`), so repeated
pricing calls across independent sessions are cheap; correctness no longer
depends on sharing a session's identity map across calls.

## Retrieval discipline

Always retrieve entities through the core service method that owns them, not directly via
`session.query()`. Core service methods may perform post-load enrichment — for example,
`BalanceSheetService.list_all_accounts()` injects market prices into
`ListedSecurityHolding` instances before returning them. A raw session query bypasses
that enrichment silently: callers receive objects whose computed fields are `None`, and any
downstream logic that reads those fields will either error or produce incorrect results.

If a service method needs entities that belong to another module's core service, it must
call that service's method. If no suitable method exists yet, add one rather than falling
back to a direct session query.
