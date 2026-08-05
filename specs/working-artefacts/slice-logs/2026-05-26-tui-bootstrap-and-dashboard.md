# Slice: TUI Bootstrap & Dashboard

**Date:** 2026-05-26
**Status:** Complete

## Description

First foray into a running Textual application. Delivers the bootstrap path
(application entry point, database/config initialisation, dependency injection
of services) plus the two screens that gate every other module:

- **Splash** (Flow F-1): shows branding, initialises the database and seed data,
  then transitions to the Dashboard.
- **Dashboard** (Flow F-3): hosts the global `Session Effective Date` widget,
  the live `Amount Left to Invest` readout, and the top-level navigation menu
  to the three modules (placeholders for now) and Quit.

Also generalizes the TUI Principles in the canonical UI spec so subsequent
module slices have a consistent rule-set to build against (color palette, layout
chrome, async/loading discipline, formatting, modal patterns, focus semantics).

## Specification References

### UI Flows to Implement

- [x] `F-1` (Launch / Splash)
- [x] `F-3` (View Dashboard)
- [x] `F-25` (Confirmation Dialog) — partial: only the "Quit?" instance used by
      the Dashboard's `Esc`/`Q` binding. Full reuse for discard flows lands in
      subsequent slices.

### Operations to Implement

- [x] `GEN-OP-1` (Get Amount Left to Invest)

## Dependencies

- [Balance Sheet Service Layer](2026-05-25-balance-sheet-service.md)
- [Domain Model Foundation](2026-05-16-domain-model-foundation.md)

## ADRs

### Referenced
- None

### Created
- [2026-05-27 — Backend: Service Layer Split into Core and Application Sub-layers](../adr/2026-05-27-backend-service-layer-split.md)
  Decisions: `service/` split into `service/core/` (reusable domain operations) and
  `service/application/` (screen-level BFF facades); flat file naming convention;
  entity retrieval must go through the owning core service method; async boundary
  follows actual I/O, not a blanket default.

## TODOs

### Completed
- None

### Created
- None

## Decisions Made

1. **`DateInput` inner message named `DateChanged` not `Changed`**: Textual's
   `Input._watch_value` calls `self.Changed(self, value, validation_result)`,
   dynamically resolving to the most-derived class named `Changed`. A subclass
   `Changed` would receive the wrong arguments. Using `DateChanged` sidesteps
   this.

2. **`DateInput.validate_value` silences `ValueError`**: `MaskedInput.validate_
   value` raises `ValueError` when the proposed value doesn't fit the template
   (e.g. a letter typed while all digits are selected). We override to return
   `self.value` on `ValueError`, making `Input._on_key` treat the operation as a
   no-op rather than crashing the event loop.

3. **`DateInput.on_key` calls `event.stop()` for Escape**: Without `stop()`,
   Escape bubbles to the screen's `Binding("escape", "request_quit")` and shows
   the quit dialog while the user is trying to cancel a date edit. `stop()`
   limits Escape to reverting the field.

4. **`push_screen_wait` replaced with `push_screen` + callback**: Textual 8.x
   requires `push_screen_wait` to run inside a worker. Action handlers run in
   the event-dispatch loop, not a worker. The callback-based form is idiomatic
   and avoids the `NoActiveWorker` error.

5. **`SplashScreen.set_status` guards against `NoMatches`**: The startup worker
   calls `set_status` before `compose()` has run in headless/test mode. Wrapping
   the `query_one` in `try/except` makes status updates best-effort and prevents
   the startup sequence from failing.

6. **Initial focus on first menu button**: `DashboardScreen.on_mount` explicitly
   focuses `#btn-balance-sheet` so the 'q'/'Esc' bindings fire from the outset
   without the user having to Tab away from the date field.

7. **DB init centralized in `personal_finance.db`**: `load_config`,
   `create_db_engine`, and `initialize_database` (including idempotent seed)
   were extracted from `scripts/seed_db.py` into the main package so the app's
   startup worker and the CLI script share the same path.

## Uncertainties

- [x] ~~Splash screen "checking data" semantics~~ — resolved as idempotent seed
      of `Person` / `AccountAssetClass` rows. Migrations not yet in scope.
- [x] ~~Whether unimplemented buttons should be disabled or show a notice~~
      — resolved as "show a warning toast"; disabling removed from scope.

## Handoff Notes

All deliverables complete. The running application:

1. Loads `config.toml`, opens SQLite, initialises schema and seed data on the
   Splash screen.
2. Transitions to the Dashboard showing today's effective date and the
   Amount Left to Invest (computed via GEN-OP-1).
3. Pressing `Q` or `Esc` (when focus is on a menu button) shows a confirmation
   dialog; `Y` exits, `N` returns to the Dashboard.
4. Changing the effective date via the `DateInput` field recomputes the readout.

Test suite: 199 tests, 89% coverage. Ruff and mypy clean.

---

*This slice-log is a working-artefact specification. It is not actively maintained after the slice is complete.*
