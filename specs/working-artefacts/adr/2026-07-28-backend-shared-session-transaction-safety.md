# Backend: Shared-Session Transaction Safety

**Date:** 2026-07-28
**Status:** Accepted
**Scope:** backend

## Problem

The application creates a single SQLAlchemy `Session` once at startup
(`PersonalFinanceApp._startup()`, `ui/app.py`) and injects that same instance into
`BalanceSheetService`, `GoalService`, and `CashFlowService` — the three core
services in `service/core/`. The session lives for the entire process lifetime,
closed only in `on_unmount()`. This is the "EntityManager shared across the whole
app" pattern from JPA, and it does not translate safely to SQLAlchemy's `Session`.

Every mutating method across the three core services (~40+ call sites) ends with
a bare `self._session.commit()`. There is no `try`/`except`/`rollback()` anywhere
in the service layer, `service/application/`, or `ui/`. UI screens do catch
exceptions broadly (`except Exception as exc:` in `goals.py`, `balance_sheet.py`,
`cash_flow_expenses.py`, etc.) and show error dialogs, but by the layering rules
in the Technical Charter they cannot reach into the service layer to touch
the session directly, and today nothing does.

**Concrete failure mode:** if any `commit()` raises — a constraint violation, a
bad intermediate state, anything — SQLAlchemy marks that session's transaction as
needing rollback. Every subsequent operation through that session (query or
write) then raises `PendingRollbackError` until `rollback()` is called explicitly.
Because the session is a single instance shared by every screen for the life of
the process, one failed operation on any screen poisons every other screen from
that point forward. The only recovery today is restarting the application.

**Constraint that any fix must respect:** `GeneralService.get_amount_left_to_invest`
(`GEN-OP-1`) deliberately relies on the *same* session/identity map staying alive
across several core-service calls within one composite operation.
`BalanceSheetService.list_all_accounts()` prices `ListedSecurityHolding` rows
by setting a transient (never-persisted, per the Technical Charter's Derived
Fields rule) attribute on the in-memory ORM instances; a later call in the same
composite operation, `GoalService.get_total_bank_claim` (via
`GoalBankPortionAutoFill.get_value()` → `InvestmentAccount.get_balance()`), reads
those same instances and depends on the price already being set. This is
documented in [2026-05-27-backend-service-layer-split.md](2026-05-27-backend-service-layer-split.md).
`DashboardService.get_summary` (the application-layer method backing the
dashboard's stats panel) separately calls `BalanceSheetAppService.get_summary`,
which calls `list_all_accounts()` itself — it doesn't require the identity map
to be shared with `get_amount_left_to_invest`, but benefits from it today
(re-pricing an already-priced instance is a no-op via `is_priced()`, so calling
both in the same Dashboard flow costs one round of quote fetches, not two). Any
fix that closes or swaps the session between calls within `get_amount_left_to_invest`
would silently break pricing (holdings would price as `None`/unset again on
the next query), so this cannot be an incidental side effect of the fix — it
must be an explicit, acknowledged part of the design.

## Design

Three candidate designs for the session/transaction lifecycle were evaluated,
plus one enabling change (quote-price caching) that applies regardless of which
was chosen. **Session-per-application-operation** was selected — see "Chosen
Design" below. The other two are kept in this ADR as "Rejected" with their
reasoning, per this repo's ADR conventions (preserve reasoning at time of
decision, not just the outcome).

### Enabler: `CachingQuoteService`

Independent of which session-lifecycle option is chosen, the pricing mechanism
that several service-layer flows depend on is being changed, and it is
documented here first because the Chosen Design below is only viable in light
of it.

Today, "pricing" a `ListedSecurityHolding` means calling
`_price_holding()`, which sets a transient `_unit_price`/`_priced_as_of`
attribute directly on that Python object (`holding.py`,
`ListedSecurityHolding.set_unit_price`/`is_priced`). This is *not* a cache —
it is per-instance memoization. It only avoids a duplicate Yahoo Finance call
when the *same object* (i.e. the same identity-mapped row, within the same
SQLAlchemy session) is priced twice. Once a session is discarded, or a fresh
query returns a different instance for the same row, the memoization is gone and
the price must be re-fetched over the network.

This is why `GeneralService.get_amount_left_to_invest` (`GEN-OP-1`) calls
`BalanceSheetService.list_all_accounts(as_of)` up front (`general_service.py:57`)
before calling `GoalService.get_total_bank_claim`: `GoalBankPortionAutoFill.get_value()`
walks `goal.allocated_accounts` and calls `InvestmentAccount.get_balance()`, which
needs those holdings already priced. Investigating this closely surfaced two
corrections worth recording:

- Of `get_amount_left_to_invest`'s three downstream calls, only `get_total_bank_claim`
  actually needs pricing — `get_total_bank_balance` and `get_total_current_liability_balance`
  query `SimpleAccount` only and never touch `InvestmentAccount`/holdings.
  Pre-pricing the *entire household's* investment accounts via `list_all_accounts()`
  to serve one narrower downstream need is broader than necessary.
- `BalanceSheetService.get_total_by_classification` carries the same kind of
  documented "must be called after `list_all_accounts`" ordering dependency
  (`balance_sheet_service.py:129-130`), but has no production caller today — it is
  a landmine for whoever wires it up next, not yet a live bug.

The fix is to replace per-instance memoization with a real cache in the
`QuoteService` implementation, decoupling pricing correctness from session/object
identity entirely:

- Add `CachingQuoteService`, a decorator implementing the existing `QuoteService`
  ABC (`core/interfaces.py`) and wrapping any other `QuoteService` (in practice,
  `YahooFinanceQuoteService`). Cache key: `(symbol, as_of)`.
- **Historical quotes** (`as_of < today` at fetch time) are end-of-day closes and
  never change — cache them for the life of the process, no expiry.
- **Same-day quotes** (`as_of == today`) can move intraday — cache them with a
  configurable TTL. Default 5 minutes.
- The TTL must not be hard-coded: add `same_day_quote_ttl_seconds` under
  `[settings]` in `config.toml`, alongside the existing
  `amount_left_to_invest_cushion`, per the Technical Charter's
  Configuration-Over-Code rule for numeric tunables. `CachingQuoteService` takes
  the TTL as a constructor argument; `ui/app.py` reads it from config and wires
  it in, the same way `amount_left_to_invest_cushion` is read and passed to
  `GeneralService` today.
- `search_symbols` is unaffected — only `get_price_cad` is cached.
- Known edge case, not solved here: a same-day cache entry does not
  self-invalidate if the wall-clock date rolls over past midnight during a
  long-running session. Given this is a desktop app with short sessions, this is
  accepted as a known limitation rather than engineered around.

With pricing now cheap and idempotent to repeat regardless of session or object
identity, the service layer can afford to call pricing explicitly wherever it's
actually needed, instead of relying on one up-front sweep and hoping downstream
code runs in the same session afterward. Concretely: `GoalService` gains an
injected `BalanceSheetService` dependency (permitted today — the Technical
Charter already allows `goals` to depend on `balance_sheet`, and "core
services may call other core services"), and `get_total_bank_claim` prices each
AutoFill goal's `allocated_accounts` itself via the existing public
`BalanceSheetService.price_investment_account()` — never the private
`_price_listed_securities()`, preserving the encapsulation `service/core/README.md`
already documents ("retrieve/enrich through the owning core service's public
method, not by reaching around it"). `get_total_bank_claim` becomes `async` as a
result, consistent with the existing "async iff it awaits something" convention
from [2026-05-27-backend-service-layer-split.md](2026-05-27-backend-service-layer-split.md).
`GeneralService.get_amount_left_to_invest` no longer needs to pre-price the whole
household up front; each call prices exactly what it needs, and the cache absorbs
any overlap between calls.

### Chosen Design: Session-per-application-operation

The initial draft of this ADR proposed a "session-per-operation" option (below,
kept as **Rejected: naive session-per-core-service-call**) scoped as a
mechanical swap: inject a `sessionmaker` into each core service instead of a
live `Session`, and have each core-service *method* open and close its own
session. A follow-up audit — checking every `relationship(...)` declaration
across `domain/` and every place the `service/application/` layer reads a
relationship off an object returned from `service/core/` — found that shape
unsafe, for a reason independent of the pricing constraint above.

**Audit finding:** none of the ~25 `relationship(...)` declarations in `domain/`
set `lazy=`, and no query anywhere in the codebase uses `joinedload`/`selectinload`.
Every relationship is lazily loaded on first attribute access, which requires an
attached, open session. `service/application/` methods routinely read
relationships on objects returned from `service/core/` calls *after* that call
has returned — this is how the existing DTO-building pattern works, and it was
always safe only because the session never closed. Concrete, currently-working
call sites that would break under a naive per-core-method session:

- `BalanceSheetAppService.get_summary` (`balance_sheet_app_service.py:240`) —
  `_row()` calls `a.get_balance(as_of)` on a `SimpleAccount`, reading
  `self.balance`; `list_all_accounts()` never touches `.balance` (it only primes
  `InvestmentAccount.holdings` for pricing).
- `BalanceSheetAppService.get_account_detail` (`balance_sheet_app_service.py:292`)
  — reads `account.owners` after `get_account_detail()` has already returned.
- `BalanceSheetAppService` holding/allocation views (`balance_sheet_app_service.py:483-521`)
  — read `account.holdings`, `holding.allocations`, `.quantity`, `.cash_balance`.
- `GoalAppService` (`goal_app_service.py:230,256,579,591,596,601,606`) — reads
  `goal.allocated_accounts`, `goal.goal_value`, `goal.bank_portion`,
  `goal.asset_class_targets`, `acc.cash_balance`, `acc.holdings`,
  `holding.allocations`.
- `CashFlowAppService` (`cash_flow_app_service.py:281-318,606-676`) — reads
  `profile.person`, all five `PersonalCashFlowProfile` income relationships,
  `profile.auto_rrsp_goal`, and `AutomatedContribution.source_account`/`target_goal`.

This is systemic, not a corner case confined to `GEN-OP-1` — it's a property of
how the app is structured (core services return ORM entities; application
services shape them into DTOs one call later), which the permanently-open
session made invisible.

**The corrected design** keeps everything session-per-operation was meant to
achieve, but draws the session boundary one layer up: at the *public
application-service method*, not the core-service method. Each public method in
`service/application/` opens one session for its entire body and passes that
same session into every core-service call it makes:

```python
# service/application/balance_sheet_app_service.py
async def get_summary(self, as_of: date) -> BalanceSheetSummary:
    with self._session_factory() as session:
        accounts = await self._core.list_all_accounts(session, as_of)
        ...  # DTO construction reads relationships here, session still open
        return BalanceSheetSummary(...)
```

Core services stop storing `self._session` at construction; every core-service
method takes `session: Session` as an explicit first parameter, supplied by the
caller. This is a larger mechanical change than the naive form (every method in
all three core services gains a parameter, not just the constructor), but it is
still fundamentally "session per unit of work" — the unit of work is now
correctly scoped to "one user-initiated action" (the granularity that actually
matters), not to an internal implementation call. It still eliminates the
permanent shared session and its identity map, still contains a failure to the
one operation that caused it, and it resolves the lazy-loading problem because
the session stays open for exactly as long as the relationship reads that
already happen naturally during DTO construction need it.

Nested application-service-to-application-service calls (e.g. `DashboardService.get_summary`
calling into `BalanceSheetAppService.get_summary`) each simply open their own
independent session — this is safe because each public application-service
method is already self-contained (queries, prices, and builds its DTO before
returning), so it never needs objects from a sibling call's session. Pricing
consistency across independent sessions is what `CachingQuoteService` (above)
is for — it replaces identity-map sharing as the mechanism that makes repeated
pricing cheap and idempotent.

### Rejected: Guarded-transaction wrapper (Option 1 — minimal diff)

Keep the single long-lived `Session` exactly as it is today. Add a small
`transaction()` context manager (e.g. in `db.py`, alongside the existing engine
helpers) that every mutating core-service method uses in place of a bare
`self._session.commit()`:

```python
@contextmanager
def transaction(session: Session) -> Iterator[None]:
    try:
        yield
        session.commit()
    except Exception:
        session.rollback()
        raise
```

Every `self._session.commit()` call site becomes `with transaction(self._session): ...`
around the mutation. On any exception the session is rolled back to a clean,
reusable state before the exception propagates up to the UI's existing
`except Exception` handlers, which already show an error dialog.

This does not remove the shared-mutable-session pattern — it makes it
self-healing after every individual unit of work. It has no effect on the
GEN-OP-1/GEN-OP-2 pricing flows, since the session identity and lifetime are
unchanged.

### Rejected: naive session-per-core-service-call

Inject a `sessionmaker` into each core service instead of a live `Session`, and
have each *core-service* method open and close its own session for the
duration of that call — the mechanical, minimal-thought version of "session per
operation":

```python
def update_account_metadata(self, ...) -> None:
    with self._session_factory() as session:
        account = session.get(Account, account_id)
        ...
        session.commit()
```

This was the initial candidate for "Option 2" and was first evaluated against
only the pricing constraint (resolved by `CachingQuoteService` — see above).
The full audit documented under **Chosen Design** found a second, larger
problem: `service/application/` routinely reads lazy relationships on objects
*after* the core-service call that produced them has already returned, and
every relationship in `domain/` is lazily loaded with no eager-loading anywhere
in the codebase. Closing the session inside the core-service method detaches
those objects before the application-service layer's existing DTO-building
code runs, which would raise `DetachedInstanceError` across all three modules
(concrete call sites listed above), not just in the two pricing-dependent
flows. Rejected in this exact form; the session boundary needed to move up to
the application-service method instead, which is what "Chosen Design" does.

### Rejected: Unit-of-Work at the application-service boundary, permanent session (Option 3)

Core services stop calling `commit()` internally (they may still `flush()` when
they need a generated primary key mid-method, e.g. `BalanceSheetService.add_holding`).
The long-lived `Session` and its identity map are preserved exactly as today, so
the GEN-OP-1/GEN-OP-2 pricing flows are unaffected. Transaction control moves to
`service/application/` — the layer that already represents "one user-initiated
action" (a single screen's button press or form submit) — using the same
`transaction()` helper from Option 1, but invoked once per application-service
method around whatever sequence of core-service calls it makes:

```python
# service/application/balance_sheet_app_service.py
def rename_account(self, account_id: int, name: str) -> None:
    with transaction(self._session):
        self._balance_sheet.update_account_metadata_no_commit(account_id, name, ...)
```

This centralizes transaction boundaries at one layer instead of scattering
`commit()` through 40+ core-service methods, and makes "what is one atomic unit
of work" an explicit, visible decision at the application-service call site
rather than an implicit property of wherever `commit()` happens to be called.
It correctly identified *where* the transaction boundary belongs — the
application-service method — which is why the Chosen Design above keeps that
part. It's rejected in this exact form only because it kept the single
app-lifetime `Session` and identity map, which is the specific pattern this
ADR exists to remove; the Chosen Design gets the same transaction-boundary
placement without the permanent session.

## Implementation Approach

### `CachingQuoteService` (not deferred — applies regardless of the session-lifecycle option)

1. Add `same_day_quote_ttl_seconds` under `[settings]` in `config.toml` (default
   `300`), next to `amount_left_to_invest_cushion`.
2. Add `CachingQuoteService` (new file, e.g.
   `integrations/caching_quote_service.py`) implementing `QuoteService`, wrapping
   an injected `QuoteService` and caching `get_price_cad(symbol, as_of)` by
   `(symbol, as_of)` — indefinite for `as_of < today`, TTL-bounded for
   `as_of == today`.
3. Wire it in `ui/app.py`: `quote_service = CachingQuoteService(YahooFinanceQuoteService(), same_day_ttl_seconds=cushion_config_value)`, reading the TTL from `load_config()` the same way `amount_left_to_invest_cushion` is read today.
4. Inject `BalanceSheetService` into `GoalService.__init__`; update
   `get_total_bank_claim` to price each AutoFill goal's `allocated_accounts` via
   `BalanceSheetService.price_investment_account()` before reading
   `bank_portion.get_value()`. Mark it `async`.
5. Remove the now-unnecessary `list_all_accounts()` pre-priming call from
   `GeneralService.get_amount_left_to_invest` once step 4 lands, since
   `get_total_bank_claim` prices its own dependencies.
6. Add test coverage: same symbol/date priced twice returns a cached value
   without a second provider call (mock/spy on the wrapped `QuoteService`); a
   same-day entry expires and re-fetches after the TTL elapses; a
   historical-date entry never expires within a test run.

### Session/transaction-safety fix — Session-per-application-operation

1. Add `create_session_factory(engine) -> sessionmaker` to `db.py`, alongside
   `create_db_engine`. `ui/app.py` constructs it once at startup instead of a
   single `Session(engine)`.
2. Rework all three core services (`BalanceSheetService`, `GoalService`,
   `CashFlowService`): remove `self._session` from `__init__`; add
   `session: Session` as an explicit first parameter to every public and
   private method that currently uses `self._session`. Non-session
   dependencies (`quote_service`, etc.) remain constructor-injected.
3. Rework every public method in `service/application/` (`BalanceSheetAppService`,
   `GoalAppService`, `CashFlowAppService`, `DashboardService`) to open
   `with self._session_factory() as session:` at the top of the method body and
   thread that `session` into every core-service call it makes. Application
   services hold the injected `sessionmaker`, not a live session.
4. Add the `transaction()` context manager from the Rejected Option 1 section
   above (commit on success, rollback + re-raise on exception) and use it
   inside every application-service method that mutates, wrapping the
   sequence of core-service calls it makes within its own session block. Pure
   read methods commit is unnecessary; they just need the session open for the
   read.
5. Update `service/core/README.md` and `service/application/README.md` to
   document the new signature convention: core-service methods take `session`
   as a parameter; application-service methods own the `sessionmaker` and the
   transaction boundary.
6. Update every core-service and application-service test fixture: replace
   `with Session(engine) as session: svc = XService(session)` with a
   `sessionmaker` fixture, calling service methods with an explicit session
   (core-service tests) or letting the application service open its own
   (application-service tests, which can now test real session-per-call
   behavior instead of a fixture-provided one).
7. Add regression test coverage for the original bug: force an exception
   during a mutating application-service call (e.g. a constraint violation)
   and assert (a) that call's session was rolled back, and (b) a subsequent,
   unrelated application-service call succeeds without needing to recreate
   anything at the app level — this is the direct regression test for "one
   failure poisons the whole app until restart."
8. Audit `service/core/goal_service.py` methods that perform `delete()` +
   `flush()` + `commit()` in sequence (`switch_bank_portion_to_scalar`,
   `switch_bank_portion_to_autofill`, `update_goal_value_strategy`) to confirm
   they behave correctly wrapped in the new per-call session + `transaction()`
   boundary.
9. Run the full test suite (`.venv/bin/pytest`) after the change.

### Specs and documentation to update as part of this work

- `config.toml` — add `settings.same_day_quote_ttl_seconds`.
- `specs/canonical/technical-charter.md` — add `same_day_quote_ttl_seconds`
  to the Configuration-Over-Code list of numeric tunables (alongside
  `amount_left_to_invest_cushion`).
- `src/personal_finance/service/core/README.md` — document (a) the new
  `GoalService → BalanceSheetService` dependency and the "call the public
  `price_investment_account()`, never the private `_price_listed_securities()`"
  rule, and (b) that core-service methods take `session: Session` as an
  explicit parameter rather than holding one at construction. While editing,
  the `## Services` list here is already stale (missing `goal_service.py` and
  `cash_flow_service.py`) — fix it in the same pass.
- `src/personal_finance/service/application/README.md` — document that
  application services own the injected `sessionmaker` and are the transaction
  boundary (open a session per public method, commit/rollback via
  `transaction()`).
- `specs/canonical/02-operations/service-operations.md` — `GEN-OP-1`'s
  description currently implies (via the code it maps to) a household-wide
  pre-pricing step; update it to reflect that pricing happens per-goal inside
  `GoalService` instead.

## Decisions and Open Questions

- **Decision:** Adopt `CachingQuoteService`, a `QuoteService`-implementing
  decorator caching `get_price_cad` by `(symbol, as_of)` — indefinitely for
  `as_of < today`, TTL-bounded for `as_of == today`. This decision is made
  regardless of which session-lifecycle option below is chosen; it stands on
  its own merits (removes accidental coupling between pricing correctness and
  session/object identity) and is a prerequisite for session-per-operation
  (in any form) being viable at all.
- **Decision:** The same-day TTL is configurable, not hard-coded — `settings.same_day_quote_ttl_seconds`
  in `config.toml`, default `300` (5 minutes), per the Technical Charter's
  Configuration-Over-Code rule for numeric tunables.
- **Decision:** Pricing moves from "one up-front sweep the caller must
  remember to run first" to "each core-service method prices exactly what it
  needs, via the public `BalanceSheetService.price_investment_account()`."
  Concretely, `GoalService` gains an injected `BalanceSheetService` dependency
  and `get_total_bank_claim` prices its own `allocated_accounts`. This
  resolves the `GEN-OP-1` cross-call ordering dependency that originally
  disqualified Option 2, without changing `GEN-OP-1`'s observable output.
- **Decision:** Adopt **session-per-application-operation**. Each public
  `service/application/` method opens its own session (via an injected
  `sessionmaker`) and holds it for its entire body; core services take
  `session: Session` as an explicit per-call parameter instead of storing one
  at construction. This was chosen over the naive "session opens/closes inside
  each core-service method" form after an audit found the naive form breaks
  lazy-relationship loading across essentially every read path in the app
  (concrete evidence in "Chosen Design" above) — not just the two pricing-order
  dependencies originally considered. It was chosen over keeping the
  permanent app-lifetime session (Rejected Option 3) because that still leaves
  the exact "EntityManager shared across the whole app" pattern this ADR
  exists to remove, just with rollback added.
- **Open:** Should the `transaction()` helper live in `db.py` next to
  `create_db_engine`/`initialize_database`, or in a new `service/core/` module,
  given the Technical Charter's file-naming rule against generic
  filenames?
- **Open:** `DashboardService.get_summary` composes `GeneralService` and
  `BalanceSheetAppService`, each now opening its own independent session. Both
  currently self-contained (verified above), so this is believed safe, but the
  general pattern — should a nested application-service-to-application-service
  call ever be allowed to share the caller's session instead of always opening
  its own? — hasn't been needed yet and is left unresolved until a case
  actually requires it.
- **Open:** Is a 5-minute default same-day TTL the right value? Chosen as a
  reasonable starting point for a personal desktop app (not a trading tool);
  revisit if it proves too stale or too chatty against Yahoo Finance in
  practice.
- **Decision:** Whichever session-lifecycle option is chosen, the fix must not
  change the observable *output* of `GEN-OP-1`/`GEN-OP-2` — only the mechanism
  by which pricing correctness is achieved (cache instead of session identity)
  is changing.

---

**Supersedes:** —
**Superseded by:** —

---

*This ADR is a working-artefact specification. It is not actively maintained after the decision is implemented.*
