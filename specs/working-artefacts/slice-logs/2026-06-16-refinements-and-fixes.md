# Slice: Refinements and Fixes

**Date:** 2026-06-16
**Status:** In progress

## Description

Incremental polish and bug fixes after the Cash Flow module reached feature-complete status. Each item is a targeted, self-contained fix — no new functionality.

## Specification References

### UI Flows to Implement

No new flows. Fixes are within existing flows.

- [x] `F-13` — Expense summary panel constrained to right pane only (not full-width)
- [x] `F-14` — "Average monthly expenses" and all contribution amounts shown as deductions (negative format)
- [x] `F-14` — Automated contribution labels indented under "Automated contributions:" header
- [x] `F-13` / `F-14` — Enter on left nav (Expenses / Household Cash Flow selected) focuses first right-pane element

### Dashboard Redesign

- [x] Splash screen — skippable by pressing Enter; "Press Enter to skip" hint shown below status line
- [x] Dashboard navigation — DOS/NetWare-style bordered menu box replacing plain buttons:
  - "Available Options" title with separator rule
  - Arrow-key navigation within the ListView
  - Highlight hidden when focus is outside the menu; dark navy bar (`#000080`) when focused
  - Bold white item text
- [x] Dashboard layout — Session Effective Date field with visible gap between label and input;
  Amount Left to Invest, Current Net Worth, and Total Net Worth grouped in a bordered stats panel
  (`#stats-container`) below the date row, consistent with Balance Sheet definitions
- [x] Dashboard stats — backed by new `GEN-OP-2` (`GeneralService.get_dashboard_summary`) which
  prices all securities once then computes all three values; exposed via `DashboardService.get_summary`

### Operations to Implement

None.

### Infrastructure

- [x] Startup database backup — on each launch, copy the live DB to `<data_dir>/backups/personal_finance_YYYYMMDD_HHMMSS.db`; retain 30 most recent; failures log a warning and do not block startup.

### Goals Screen Refinements

- [x] "No goal" placeholder (Goal column, no-target goals) horizontally centered instead of left-aligned. Scoped via a
  `gr-goal-empty` class added only to the no-target `F6OpenableField`, so `content-align: center middle` targets just
  that instance's `GoldBorderDisplay` — applying it screen-wide would have broken the `$`-alignment crop logic in
  `GoldBorderDisplay.render_line`/`MoneyInput.render_line` for every monetary cell (those assume left-aligned base
  rendering; see new gotcha #9 in `ui/README.md`).
- [x] `$` sign misalignment between gold-bordered read-only cells (`GoldBorderDisplay`, padding `0 1`) and editable
  scalar cells (`MoneyInput`, inheriting Textual's default `Input` padding `0 2`) — added `padding: 0 1` to
  `MoneyInput`'s own `DEFAULT_CSS` so both cell types have the same border+padding inset. Fixes the same misalignment
  in Balance Sheet (`is_investment` rows use `GoldBorderDisplay`, others `MoneyInput`, in the same column).
- [x] Follow-up regression from the above: `balance_sheet.py`'s `.acct-balance-readonly` class had its own
  `padding: 0 2` override — a screen-specific compensation for `MoneyInput`'s *old* default padding (`0 2`), added
  when `GoldBorderDisplay`'s default (`0 1`) didn't match it. Once `MoneyInput`'s default became `0 1`, that leftover
  override reintroduced the identical 1-column `$` misalignment in the opposite direction on the Balance Sheet
  screen. Removed the override; both widgets now share the same default padding with no per-screen compensation
  needed. Checked `investment_editor.py` and `cash_flow_report.py` for the same pattern — neither pairs
  `GoldBorderDisplay` and `MoneyInput` in the same column, so no equivalent fix was needed there.
- [x] Second follow-up: the section-total row's `.bs-total-amount` (`$ 39,804.00`, a plain `Static`, no border) had
  `padding-right: 3` — tuned to match the *old* combined border+padding inset (border `1` + padding-right `2` = `3`)
  shared by `MoneyInput` and (via the just-removed override) `GoldBorderDisplay`. With both now at padding `0 1`
  (inset `1 + 1 = 2`), changed `padding-right` to `2` so the totals' cents line up with the input/gold-border columns
  above. Verified at the character level (`tmux capture-pane`): the final digit of every amount — bordered inputs and
  both section totals — now lands in the same column.
- [x] Third follow-up: with cents aligned, the `$` sign on the section-total rows was still one column too far right.
  Cause: `.bs-total-amount` has no border and no left padding, so (unlike `MoneyInput`/`GoldBorderDisplay`, which pin
  `$` to a fixed column via their `render_line` crop logic) its `$` position is purely a function of the *length* of
  the right-aligned string. The format string built `"$ " + total:>13` (15 chars); right-aligned in an 18-wide area
  (box width `20` − `padding-right: 2`), its `$` landed 1 column right of the bordered cells' pinned `$` column.
  Widened the numeric field from `:>13` to `:>14` — the 1-char-longer string's *start* (where `$` sits) shifts one
  column left under right-alignment while its *end* (last digit) stays anchored, so cents stayed correct and `$` is
  now flush with the bordered columns too. Verified both column positions (`$` and last digit) via `tmux capture-pane`
  across every row in both sections.

### Goal Allocation View Refinements

- [x] Actual $ column (`goal_allocation.py`, `_AllocationRow`/`_AllocationHeaders`/`_AllocationTotalsRow`) reformatted
  to pin `$` at a fixed left column with digits right-justified in a field sized for the largest expected value
  (`$ 9,999,999`), matching the input-box convention elsewhere: `_fmt_amt` now returns `f"$ {value:>9,.0f}"` (fixed
  11 chars). Applies to both the per-row cells and the Total row (both call the same `_fmt_amt`). Column CSS switched
  from `content-align: right` (relying on incidental left-blank-padding for the Target→Actual$ gap) to
  `content-align: left` with the fixed-width string doing its own internal right-justification — this dropped the
  gap after the Target box, so added explicit `margin-left: 1` to `.ar-actual-amt`/`.ah-actual-amt`/`.atr-actual-amt`
  to restore it. Verified column-exact alignment (`$` and last digit both landing in the same column across every
  row and the total, for both a single-value goal and a goal with 8 varied-magnitude rows) via `tmux capture-pane`.
- [x] Actual % column rounded to the nearest tenth of a percent with the decimal place always shown (new
  `_fmt_actual_pct`, `f"{value:.1f}%"`), replacing the trailing-zero-stripped `_fmt_pct` for this column only.
  `_fmt_pct` itself is untouched and still used for the Target-sum total and the over-100% warning banner — neither
  was mentioned in the request, so left as-is.
- [x] Brought `.ah-actual-amt` and `.ah-actual-pct` (the two headers touched by this change) into conformance with
  the canonical "column headers are always left-aligned" rule (`ui/README.md`) by dropping their
  `content-align: right middle`. `.ah-diff` (Difference header) has the same pre-existing violation but was out of
  scope — noted below as a handoff item rather than fixed silently.
- [x] Reduced `.ar-name`/`.ah-name`/`.atr-name` `min-width` from 12 to 10 to give the 1fr Name column a little more
  room to yield to the wider Actual $ column, per the request ("Name column can be shrunk a bit"). In practice the
  1fr sizing absorbed the +2 width change automatically; the lower floor is headroom for narrower terminals, not a
  visible change at normal widths.

### Visual Polish (Contrast & Whitespace)

- [x] Centralize duplicated color literals into `personal_finance.ui.palette` (`PANEL_FILL`,
  `BORDER_STRUCTURAL`, `TEXT_DIM`, `TEXT_HINT`, `ACCENT_CYAN`), interpolated into `DEFAULT_CSS`
  f-strings and Rich `style=` strings across every touched screen/widget. Amended from the
  original "shared CSS classes" ADR proposal — Rich inline styles can't be reached by a CSS
  class, and the `.panel`/`.panel--title` precedent turned out to be dead code (see ADR).
- [x] Raised contrast of structural borders/dividers (`#555588`/`#333388` → `BORDER_STRUCTURAL`
  `#6666cc`, load-bearing pane-split/panel-boundary borders only) and dim/hint text (`#888888`,
  `#555577` → `TEXT_DIM` `#9a9ad6`; `#555555`, `#666666` → `TEXT_HINT` `#7a7ab3`) per the WCAG
  analysis in the ADR. The `#555577` and `#666666` sources were additional near-duplicate
  contrast bugs found during implementation, not in the original screenshot pass.
- [x] Modest lift to panel fill (`#0000aa` → `PANEL_FILL` `#1a1ab0`) for a secondary depth cue,
  applied uniformly to every surface sharing that literal (title bars, dialogs, buttons, footer,
  loading indicator, select overlays, dashboard panels) except `DashboardScreen`'s own root
  background, deliberately left as its screen-tier value. White borders remain the primary
  layering mechanism.
- [x] Fixed splash "Press Enter to skip" hint, holding-table manual-entry `–` placeholder,
  balance-sheet/`AddHoldingDialog` dim-label, and Cash Flow report empty-state contrast bugs
  (all fell out of the `TEXT_DIM`/`TEXT_HINT` swap above).
- [x] Introduced `ACCENT_CYAN` (`#00aaaa`), scoped only to decorative in-content `Rule`/divider
  sites in the Cash Flow module (four sites) — never load-bearing structural borders.
- [x] Dashboard: changed `align: center middle` → `align: center top` with `margin-top: 3`;
  reduced the `margin-bottom: 2`/`3` stack to `1` between the date row, stats panel, and menu.
- [x] Updated `ui/README.md` with a "Color Palette" convention section and gotcha #10 on
  Textual's per-source `$variable` scoping.
- [x] Live-verified via `tmux capture-pane`: Dashboard now renders anchored near the top with
  the tightened margins (no more large dead-air gaps); Balance Sheet renders correctly with
  intact alignment. Confirmed `TEXT_DIM` and `BORDER_STRUCTURAL` are actually reaching the
  terminal by decoding the raw 24-bit-downsampled-to-256-color ANSI codes in the capture back to
  RGB and matching them against the new hex values (the `PANEL_FILL` bg change is too subtle a
  luminance step — by design, see ADR — to distinguish from the old value once quantized to
  256 colors in this headless environment; verified instead via the `Stylesheet` parse checks
  below). `pytest` (429 passed), `ruff check`/`ruff format --check`, and `mypy` all run on every
  touched file: all clean except pre-existing, unrelated issues already present on `main` before
  this slice (3 pre-existing `E501` lines, 9 pre-existing `mypy` errors, and pre-existing
  `ruff format` non-compliance in several files' untouched code — confirmed identical via a
  `git stash` diff, not introduced by this work).

## Dependencies

- [2026-06-09-cash-flow.md](2026-06-09-cash-flow.md) — Cash Flow module (feature-complete baseline)

## ADRs

### Referenced
- None.

### Created
- [2026-08-05-frontend-visual-polish.md](../adr/2026-08-05-frontend-visual-polish.md) —
  WCAG-driven audit of the NetWare/Classroom-LAN-inspired palette found several structural
  colors (unfocused input borders, nav-pane dividers, dim/hint text) sitting well under the
  3:1/4.5:1 contrast floors, plus a genuinely near-invisible splash hint (`#555555`, 1.98:1).
  **Proposed:** centralize the palette into shared semantic classes in `netware.tcss`
  (extending the existing `.value--readonly`/`.panel--title` pattern, since Textual's
  `$variable` substitution does not propagate across CSS sources); raise structural
  border/divider and dim/hint text contrast; a deliberate, modest-only lift to panel fill
  (full 3:1 would require a genuinely light blue, breaking the dark NetWare identity — white
  borders stay the primary hierarchy signal); a bounded two-site introduction of an
  `.accent-cyan` token for tertiary dividers; and a Dashboard layout change from
  `align: center middle` to an anchored `align: center top` with tightened inter-block margins.
  Not yet implemented.
- [2026-07-28-backend-shared-session-transaction-safety.md](../adr/2026-07-28-backend-shared-session-transaction-safety.md) —
  shared app-lifetime SQLAlchemy `Session` has no rollback-on-error handling
  anywhere in the service layer; a failed `commit()` poisons the session for
  every screen until restart. **Accepted and implemented:** session-per-application-operation
  (each `service/application/` method owns a per-call session via `db.transaction()`;
  core services take `session` as an explicit parameter, no longer call
  `commit()`/`rollback()` themselves) plus `CachingQuoteService`, a
  `QuoteService` decorator that caches by `(symbol, as_of)` (indefinite for
  past dates, `same_day_quote_ttl_seconds`-bounded for today) so pricing
  correctness no longer depends on session identity. `GoalService` now takes
  an injected `BalanceSheetService` and prices AutoFill goals' allocated
  accounts itself in `get_total_bank_claim`; `GeneralService.get_amount_left_to_invest`
  no longer pre-sweeps `list_all_accounts()`. All core/application service
  files and their test suites updated; 417 tests passing, mypy/ruff clean on
  touched files.

## Decisions Made

- Current Net Worth = current assets − current liabilities; Total Net Worth = all assets − all liabilities (same definitions as the Balance Sheet screen).
- Dashboard stats use a single `get_dashboard_summary` call to price securities once across all three values.

## Uncertainties

- [x] Which option in [2026-07-28-backend-shared-session-transaction-safety.md](../adr/2026-07-28-backend-shared-session-transaction-safety.md)
  to adopt for the shared-session transaction-safety fix — resolved:
  session-per-application-operation.

### Modal UX

- [x] F10 in any `ModalDialogMixin` dialog — presses the first enabled `variant="primary"` button; no-ops if the button is absent or disabled. Implemented in `ModalDialogMixin.on_key` (`dialogs.py`).

## Handoff Notes

- The session-per-application-operation refactor touched every method in
  `service/core/` and `service/application/` plus their test suites, but did
  **not** change any UI screen — application-service public method signatures
  are unchanged, so `ui/screens/*` needed no edits. This was verified via unit
  tests and a full module import check, but the running TUI itself was not
  manually smoke-tested end-to-end as part of this change; worth a manual
  pass (`.venv/bin/personal-finance`) before considering this fully verified.
- `BalanceSheetService.get_total_by_classification` still carries no
  production caller (flagged in the ADR as a landmine) — if a future slice
  wires it up, it must price its own accounts explicitly (e.g. via
  `price_investment_account`) rather than assuming a prior `list_all_accounts()`
  call in the same session, since that assumption no longer holds under
  session-per-application-operation.
- Existing service-layer test suites now depend on a `StaticPool`-backed
  in-memory SQLite fixture pattern (`engine` fixture shared by `db_session`
  and `session_factory`) to let a test's own fixture-setup session and an
  application service's independently-opened session see each other's data.
  Follow this pattern for any new `service/application/` test file.
- `_AllocationHeaders .ah-diff` (Difference column header, `goal_allocation.py`) still right-aligns its
  `content-align`, violating the canonical "column headers are always left-aligned" rule in `ui/README.md`. Left
  as-is because the Difference column's formatting/width wasn't part of this slice's request — a future slice
  touching that column should fix it then.
- Discovered while implementing the visual-polish ADR: running a blanket `ruff format <file>` across a whole
  file can move a trailing `# type: ignore[...]` comment onto a different physical line than the one mypy
  attributes the suppressed error to, when reformatting collapses/re-wraps a multi-line statement — this
  silently turns a working suppression into an unsuppressed error plus an "unused ignore" (hit once in
  `goal_allocation.py`, `get_goals_for_allocation_view`). Also, several files in `ui/screens/` already carried
  pre-existing `ruff format` non-compliance and `mypy` errors on `main` before this slice (confirmed via
  `git stash` diffs) — `ruff format`ting a whole touched file bundles that unrelated pre-existing debt into the
  diff. Going forward, prefer hand-matching ruff's style on just the new/changed lines over running
  `ruff format <file>` on a file with pre-existing formatting debt; if a blanket format is run, re-diff against
  the pre-edit file to confirm every hunk is one you intended, and re-run `mypy` afterward specifically for
  this failure mode.
