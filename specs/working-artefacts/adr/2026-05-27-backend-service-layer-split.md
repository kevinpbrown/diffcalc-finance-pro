# Backend: Service Layer Split into Core and Application Sub-layers

**Date:** 2026-05-27
**Status:** Accepted
**Scope:** backend

## Problem

The `service/` layer currently mixes two distinct kinds of responsibility, which
will cause problems as more UI screens are added:

1. **Core (domain) operations** — business logic that maps to domain concepts and
   could serve any consumer (test harness, future CLI, second TUI screen). Example:
   `BalanceSheetService.list_all_accounts`, which fetches, filters, and prices
   accounts regardless of how any screen chooses to display them. The formula for
   Amount Left to Invest (`Σ bank − Σ liabilities − Σ goal claims − cushion`) is
   also a domain calculation, even though it currently lives in `DashboardService`.

2. **Application-level aggregation** — logic that exists solely to fulfil a
   specific screen's data contract. Example: the Dashboard screen's readout, which
   calls the Amount Left to Invest formula and hands the result to the widget. This
   is a thin orchestration concern, not business logic.

Today both kinds live at the same level with no structural signal about which is
which. As more screens arrive there is a real risk that:

- UI-specific aggregation logic gets duplicated across screens.
- Domain operations accumulate screen-specific assumptions that make them
  unsuitable for reuse.
- Tests of domain operations become entangled with UI-only concerns.

The parallel in web development is the split between a domain API (stable,
reusable) and a BFF (Backend For Frontend — aggregation layer tuned to a specific
client's needs).

## Design

Split `service/` into two sub-layers:

```
service/
  core/                        ← Core Services: reusable domain operations
    balance_sheet_service.py
    general_service.py         ← GEN-OP-* operations (cross-cutting domain logic)
    cash_flow_service.py       (future)
    goals_service.py           (future)
  application/                 ← Application Services (BFF): screen-level aggregation
    dashboard_service.py
    balance_sheet_service.py   (future)
    ...
```

### Classifying services

A service belongs in `service/core/` if:
- Removing Textual from the project would leave it meaningful and independently
  testable.
- It maps to a named domain operation in the service-operations spec (`BS-OP-*`,
  `CF-OP-*`, `GOAL-OP-*`, `GEN-OP-*`).
- It contains no knowledge of how a specific screen presents or filters its output.

A service belongs in `service/application/` if:
- It exists to fulfil the data contract of a specific screen.
- It is UI-specific: it aggregates, proxies, or reshapes core service output for
  presentation. Logic of this kind has no meaning outside the UI context.

Core services may call other core services. Application services may call core
services. Neither may call application services. UI screens must only import from
`service/application/`.

### Current mapping

| Current class / location | Proposed location |
|---|---|
| `BalanceSheetService` — `service/balance_sheet/service.py` | `service/core/balance_sheet_service.py` |
| `DashboardService.get_amount_left_to_invest` (formula) | `service/core/general_service.py` → new `GeneralService` |
| `DashboardService` (screen orchestration) — `service/general/service.py` | `service/application/dashboard_service.py` (thin proxy to `GeneralService`) |

### GEN-OP-* operations

Cross-cutting domain operations (those prefixed `GEN-OP` in the spec) belong in
`service/core/general_service.py` as a `GeneralService` class. The formula for
Amount Left to Invest is business logic; any screen that needs it calls
`GeneralService` via its application service. The Dashboard's application service
is therefore a one-line proxy — that is intentional and acceptable.

### File naming

All service files are named `<module>_service.py` directly inside `service/core/`
or `service/application/` — no further subdirectory nesting. This is consistent
with the file-naming convention in the Coding Standards section of the Technical
Charter.

## Implementation Approach

1. Create `service/core/` and `service/application/` packages with `__init__.py`
   and `README.md` files.
2. Move `BalanceSheetService` from `service/balance_sheet/service.py` to
   `service/core/balance_sheet_service.py`. Update all imports.
3. Extract the Amount Left to Invest formula from `DashboardService` into a new
   `GeneralService` class at `service/core/general_service.py`.
4. Replace `service/general/service.py` with a thin `DashboardService` at
   `service/application/dashboard_service.py` that delegates to `GeneralService`.
5. Update the TUI startup code (dependency injection in `personal_finance/__init__`
   or app entry point) to instantiate the new class locations.
6. Delete the now-empty `service/balance_sheet/`, `service/general/`, and
   `service/cash_flow/` subdirectories.
7. Update `service/README.md` to describe the two-sub-layer structure.
8. Update the Technical Charter to reflect the new directory layout, the
   classification rule, and the file-naming convention (covered by separate
   charter amendment in this ADR).
9. Run the full test suite; fix any broken imports. No business-logic changes in
   this refactor.

## Decisions and Open Questions

- **Decision:** Sub-layer names are `service/core/` (domain operations) and
  `service/application/` (screen-level aggregation). `core` avoids the naming
  collision that `domain` would create against the `domain/` layer. `application`
  is the standard DDD term for services that orchestrate domain logic for a
  specific use-case.

- **Decision:** `GEN-OP-*` operations belong in `service/core/general_service.py`.
  Amount Left to Invest is domain business logic; the Dashboard application service
  proxies it. A proxy with no added logic is an acceptable cost of maintaining the
  sub-layer boundary.

- **Decision:** Module-level subdirectory nesting inside `service/core/` and
  `service/application/` is prohibited. Each service is a single flat file named
  `<module>_service.py`.

- **Decision:** Filenames must be representative of their primary content.
  Generic filenames (`service.py`, `utils.py`, `helpers.py`) are not permitted
  anywhere in the project. A file containing multiple related classes is acceptable
  when all classes share a clear single subject (e.g. `holding.py`); a generic
  catch-all name is not. This will be codified in the Technical Charter as a
  non-negotiable coding standard.

- **Decision:** UI screens must only import from `service/application/`. Direct
  imports from `service/core/` in the UI layer are prohibited.

- **Decision:** Entity retrieval within the service layer must go through the owning core
  service method, not directly through `session.query()`. Core service methods may perform
  post-load enrichment (e.g. `BalanceSheetService.list_all_accounts()` injects market
  prices into `ListedSecurityHolding` transient fields). Bypassing that method with a
  raw session query silently omits the enrichment, causing downstream reads of computed
  fields to return `None` and producing incorrect results. Concretely:
  `GeneralService.get_amount_left_to_invest()` calls `BalanceSheetService.list_all_accounts()`
  before computing because `GoalBankPortionAutoFill` reads `InvestmentAccount.get_balance()`,
  which aggregates holding values that are only populated after pricing. This is why
  `get_amount_left_to_invest` is async even though the formula itself is pure arithmetic.

- **Decision:** Service methods (core and application) are `async` if and only if
  they `await` something. There is no blanket default-async rule. Rationale: in
  Python, forgetting to `await` a coroutine is a loud, immediate error
  (`RuntimeWarning: coroutine was never awaited`), not a silent bug as in
  JavaScript. The defensive value of pre-emptive `async` is therefore low, while
  the costs are real: Ruff flags `async def` with no `await` (`RUF029`),
  `pytest-asyncio` requires per-test decoration or global config, and the
  sync/async boundary is harder to cross than in Node. Promoting a sync method to
  async later is a trivial, loud change — one keyword and `await` at each call
  site.

---

**Supersedes:** —
**Superseded by:** —

---

*This ADR is a working-artefact specification. It is not actively maintained after the decision is implemented.*
