# Frontend Decision: Visual Polish — Contrast, Whitespace, and a Centralized Palette

**Date:** 2026-08-05
**Status:** Accepted and implemented
**Scope:** frontend

## Problem

The app's visual identity is intentionally nostalgic of 90s-era DOS TUIs (Novell NetWare, IBM Classroom LAN
Administration System). That identity should stay, but two areas fall short of "sharp by modern standards":

1. **Contrast of blues.** `netware.tcss` and per-screen `DEFAULT_CSS` blocks lean on a narrow band of the blue
   channel (`#000080` screen background, `#0000aa` panel fill, `#000066` nav-pane fill) with almost no luminance
   or hue separation between them. Measured against WCAG's relative-luminance contrast formula:
   - Panel fill vs. screen background: **1.20:1** — indistinguishable except by border.
   - Unfocused input border (`#555588`) vs. screen background: **2.1:1** — well under the 3:1 floor for
     non-text UI components (WCAG 1.4.11), which is why fields are nearly invisible until focused.
   - Nav-pane divider (`#333388`) vs. nav-pane fill (`#000066`): **1.6:1**.
   - Dim account/nav labels (`#888888`) vs. screen background: **4.07:1** — just under the 4.5:1 body-text floor.
   - Splash "Press Enter to skip" hint (`#555555`) vs. screen background: **1.98:1** — a genuine bug, not a
     style choice; the hint is nearly unreadable.
   - Manual-entry placeholder dashes in the holding table (`#555555`, `investment_editor.py`): same 1.98:1
     bug, same root color.
   - Balance Sheet account-name labels (`#555577`, `AccountRow.acct-name`) and the equivalent dim static values
     in `AddHoldingDialog` (`.acd-static-dim`): **2.10:1** — a third, distinct near-invisible "dim gray"
     found during implementation, alongside `#888888` and `#555555`.
   - The Household Cash Flow report's empty-state text (`.cfr-empty`, `#666666`): **2.79:1** — another bug
     found during implementation, same family as the two above.
   - What already works and must not change: white text on navy (16:1), the `#0055cc` focus/selected fill with
     white text (6.97:1), gold borders, and warning red `#ff4444` (4.70:1).
2. **Whitespace.** Confirmed in `dashboard.py`: `DashboardScreen` is `align: center middle`, and the three
   stacked blocks (date row, stats panel, menu) add `margin-bottom: 2` and `margin-bottom: 3` on top of that
   centering — five extra blank rows stitched between three already-short, already-centered blocks. This is
   the main source of the sparse look on the dashboard.
3. **Duplicated color literals.** The same raw hex values (`#aaaaaa` alone appears in 12+ files) are hand-copied
   into every screen's `DEFAULT_CSS`, so a palette change today means a 17-file grep-and-replace, and the next
   one will too.

## Design

### Token table

Textual's `$variable` substitution is resolved per-CSS-source against a single snapshot (`Stylesheet._variables`,
populated once from `App.get_css_variables()`); a `$name: value;` declared inside `netware.tcss` is **not**
visible to a different source (e.g. a screen's own `DEFAULT_CSS` string) — confirmed by reading
`textual/css/stylesheet.py` and `textual/css/parse.py`. Built-in Textual theme variables (e.g.
`$footer-foreground`, already used in `SplitFooter`) work everywhere because the App seeds them into that one
shared snapshot; a custom value declared inline in a `.tcss` file does not get fed back into it.

**Mechanism actually used (amended from the original "shared CSS classes" proposal):** plain Python constants
in a new `personal_finance.ui.palette` module, imported and interpolated into each screen/widget's `DEFAULT_CSS`
f-string. This was chosen over shared CSS classes for two reasons discovered during implementation: (1) several
of the duplicated colors are Rich `style=` strings on programmatically-rendered `Text` content (e.g. the Cash
Flow nav-pane's dim item color, the Profiles-list divider), which a CSS class cannot reach at all; a Python
constant can supply both. (2) `.panel`/`.panel--title` — the existing shared-class precedent this ADR meant to
extend — turned out to be dead code (defined in `netware.tcss`, never applied via `classes=` anywhere), so there
was no live pattern to extend without first wiring it up screen-by-screen, a larger and riskier change than a
constants module for the same one-source-of-truth outcome. `netware.tcss` itself (a static file, not a Python
string) keeps literal values with a `/* palette.X */` comment on each line, by hand, since it cannot import the
module.

| Token (`palette.py` constant) | Old value(s) | New value | Role | Contrast after |
|---|---|---|---|---|
| App/Screen background (unchanged) | `#000080` | unchanged | App/screen background | — |
| `PANEL_FILL` | `#0000aa` | `#1a1ab0` | Panel/card/dialog/title-bar fill, and every other chrome surface previously sharing the `#0000aa` literal (buttons, footer, loading indicator, select overlay, dashboard menu/stats panels) | 1.39:1 vs. screen — deliberate modest lift only; see "Why not push panel fill to 3:1" below. White borders remain the primary hierarchy signal. |
| Nav-pane fill (unchanged) | `#000066` | unchanged | Recessed left-nav pane fill | — |
| Focus/selected fill (`Input:focus`, `#0055cc`, unchanged) | `#0055cc` | unchanged | Focused input / selected row | 6.97:1 — already correct |
| Primary borders (unchanged) | `#ffffff` | unchanged | Primary panel/dialog/button borders | 16:1 — already correct |
| `BORDER_STRUCTURAL` | `#555588`, `#333388` | `#6666cc` | Unfocused input/select borders, load-bearing nav-pane split borders (`border-right`) and panel-boundary borders (`border-top`) | 3.30:1 vs. screen bg, 3.64:1 vs. nav-pane fill |
| Gold border (`GoldBorderDisplay`, unchanged) | `#ffd700`/`#aa8800` | unchanged | Investment / read-only cell borders | already correct |
| Primary text (unchanged) | `#ffffff` | unchanged | Primary values, titles | 16:1 |
| Secondary text / `Label` (unchanged) | `#aaaaaa` | unchanged | Labels, column headers, secondary values | 6.89:1 — already correct |
| `TEXT_DIM` | `#888888`, `#555577` | `#9a9ad6` | Unselected nav items, dim account/category names, blocked list rows — two distinct near-duplicate "dim gray" values unified into one | 5.93:1 (was 4.07:1 and 2.10:1 respectively, both below AA) |
| `TEXT_HINT` | `#555555`, `#666666` | `#7a7ab3` | Lowest-tier hint/placeholder/empty-state text: splash skip-hint, manual-entry `–` placeholders, Cash Flow report empty state — two distinct values unified | 4.01:1 (was 1.98:1 and 2.79:1 respectively). Intentionally below the 4.5:1 body-text floor — this is the bottom of the emphasis ladder by design, one step below `TEXT_DIM`, analogous to how most design systems place disabled/placeholder text below body-text AA. |
| `ACCENT_CYAN` | `#333388` (divider role only) | `#00aaaa` | Decorative in-content `Rule`/divider separators **only** — see bounded site list below | 5.59:1 vs. screen bg |
| Danger (`#ff4444`/`#aa0000`/`#ff5555`, unchanged) | unchanged | unchanged | Warnings/errors | 4.70:1 — already correct |

**Why not push panel fill to a full 3:1?** With the screen background fixed at `#000080` (luminance 0.0156), a
true 3:1 panel fill would require luminance ≈0.147 — a genuinely light blue, not a "richer navy." That would
break the moody, dark NetWare aesthetic the app is going for. White borders already give every panel a real
16:1 edge; the panel-fill change here is a secondary depth cue, not the hierarchy mechanism. Structural
*borders and dividers* (which have no white-border escape hatch) get the full 3:1+ treatment instead.
`DashboardScreen`'s own root background is deliberately left at its pre-existing `#0000aa` (not lifted to
`PANEL_FILL`) — it is that screen's *screen tier* (its one-off, slightly-lighter-than-`#000080` base), not a
panel sitting on top of a screen; lifting it would collapse it into its own panels' new fill and reintroduce
the blending problem this ADR fixes, just one shade lighter.

**Accent cyan — bounded site list** (per repo convention of not letting new UI language sprawl beyond what's
requested): applies only to decorative, non-load-bearing `Rule`/separator content within the Cash Flow module,
all previously the low-contrast `#333388`:
- The `"─" * 16` profile-list divider under "Profiles" in `cash_flow.py`.
- The `#cfp-separator-1`/`#cfp-separator-2` `Rule`s in the Person Profile view.
- The `.cfr-sep` `Rule`s in the Household Cash Flow report.

Explicitly **not** cyan: the `border-right` nav-pane split (`base.py`/`goal_allocation.py`) and the
`_ExpenseSummaryWidget` `border-top` — both are load-bearing structural boundaries (same role as an unfocused
input border), not decorative separators, so they take `BORDER_STRUCTURAL` instead. The original draft of this
ADR lumped these two categories together for `goal_allocation.py`/`base.py`; this amendment draws the line
explicitly. No other element (buttons, primary text, monetary values) changes hue. If a future slice wants
cyan elsewhere, that's a new decision, not an extension of this one.

### Whitespace — Dashboard

- Change `DashboardScreen` from `align: center middle` to `align: center top` with an explicit `margin-top`
  (small, e.g. 2–3 rows) — closer to how NetWare/Classroom LAN menu screens actually sat (anchored, not
  floating mid-screen), and removes the dead air above/below on tall terminals.
- Reduce `#dash-fields { margin-bottom: 2; }` and `#stats-container { margin-bottom: 3; }` substantially
  (exact values tuned live via `tmux capture-pane` against the reference screenshots, per existing slice
  convention — not fixed a priori in this ADR).
- Balance Sheet / dialog row height (`height: 3` bordered inputs) is inherent to bordered `Input`/`MoneyInput`
  boxes (border-top + content + border-bottom), not extra margin; no stray `margin-bottom` was found between
  rows in `AccountRow`, `CreateGoalDialog`, or `GoalValueForm`. No spacing change proposed there — flagged as
  an open question below in case a live pass turns up something a static code read didn't.

## Implementation Approach

1. Add `personal_finance/ui/palette.py` with the five new constants (`PANEL_FILL`, `BORDER_STRUCTURAL`,
   `TEXT_DIM`, `TEXT_HINT`, `ACCENT_CYAN`), each documented with its role and the WCAG rationale.
2. Update `netware.tcss`'s own structural-color rules (`Input`/`Select` borders, `.dialog`/`.panel`/
   `.panel--title` fill, `Button`/`Footer`/`LoadingIndicator`/`SelectOverlay`/`SelectAccountsDialog` fills) to
   the new literal values by hand, each with a `/* palette.X */` sync comment.
3. Screen-by-screen sweep, converting each touched `DEFAULT_CSS` to an f-string and importing the relevant
   constant(s): `dashboard.py`, `base.py` (`TwoPaneScreen` — covers every screen built on it), `goal_allocation.py`,
   `investment_editor.py`, `goals.py`, `balance_sheet.py`, `balance_sheet_dialogs.py`, `cash_flow.py`,
   `cash_flow_expenses.py`, `cash_flow_report.py`, `goal_dialogs.py`, `splash.py`, `summary_bar.py`,
   `split_footer.py`. Rich `style=` string sites (nav-pane dim text, decorative dividers) get the same constant
   interpolated directly, no CSS involved.
   - Dashboard anchoring (`align: center middle` → `align: center top` + `margin-top: 3` on `#dash-inner`) and
     margin tightening (`margin-bottom: 2`→`1`, `margin-bottom: 3`→`1`).
   - Splash hint, holding-table placeholder, balance-sheet dim-label, and Cash Flow empty-state fixes all
     fall out of the `TEXT_DIM`/`TEXT_HINT` swap in step 3, not separate patches.
4. Sanity-checked every touched `DEFAULT_CSS` block by feeding it through `textual.css.stylesheet.Stylesheet`
   directly (catches f-string brace-escaping mistakes a plain `ast.parse` can't) plus a full-module import
   check across the touched files.
5. Update `ui/README.md`: a "Color Palette" section documenting the `palette.py` convention, and gotcha #10 on
   Textual's per-source (non-cross-file) `$variable` scoping.
6. Remaining: run `pytest`/`ruff`/`mypy` per the technical charter's slice-closure gate, and live-verify
   the running app via `tmux capture-pane` against the 10 reference screenshots before considering this closed.

## Decisions and Open Questions

- **Decision (amended during implementation):** Centralize via a plain Python constants module
  (`personal_finance.ui.palette`) interpolated into `DEFAULT_CSS` f-strings and Rich `style=` strings, not
  shared CSS classes. The original proposal (extend the `.value--readonly`/`.panel--title` shared-class
  pattern) turned out to have two problems on inspection: `.panel`/`.panel--title` were dead code (never
  applied via `classes=`), so there was no live pattern to extend; and several duplicated colors are Rich
  inline styles on programmatically-rendered text, which a CSS class cannot reach at all. Cross-file `$variable`
  sharing remains unsupported by Textual's per-source parsing model either way.
- **Decision:** Panel-fill contrast gets a modest lift only (1.20:1 → 1.39:1); structural borders/dividers get
  the full 3:1+ treatment. White borders remain the primary layering mechanism — this preserves the dark,
  saturated NetWare identity rather than lightening it into a pastel blue. `PANEL_FILL` was applied to every
  surface that previously shared the literal `#0000aa` value for the same chrome role (title bars across all
  module screens, dashboard's stats/menu panels and menu-list items, buttons, the footer, the loading indicator,
  select overlays, and the Select-Accounts dialog's list), not just `.dialog` — except `DashboardScreen`'s own
  root background, deliberately left unchanged (see "Why not push panel fill to 3:1" above).
- **Decision:** `TEXT_HINT` intentionally lands at 4.01:1, below the 4.5:1 body-text AA floor — it is the
  lowest tier of a four-step text hierarchy (primary → secondary → dim → hint), and its predecessor values
  (1.98:1, 2.79:1) were genuine legibility bugs, not a deliberate design choice being preserved.
- **Decision:** Two additional near-duplicate "dim gray" bugs (`#555577`, `#666666`) were found during
  implementation and folded into `TEXT_DIM`/`TEXT_HINT` respectively, per the "fold in bonus fixes" scope
  decision — same contrast-bug family as `#888888`/`#555555`, just missed in the initial screenshot pass.
- **Decision:** Dashboard moves from `align: center middle` to `align: center top` plus tightened inter-block
  margins (`margin-bottom: 2`→`1`, `margin-bottom: 3`→`1`, `margin-top: 3` added on `#dash-inner`).
- **Decision:** Accent cyan (`#00aaaa`) is scoped to decorative `Rule`/divider content only (four sites across
  Cash Flow), never load-bearing structural borders (nav-pane splits, panel boundaries) — see the corrected
  bounded site list above.
- **Resolved:** Exact Dashboard margin/anchor values were set directly in this pass (not deferred) since they
  were simple, low-risk numeric tunings; still worth a live `tmux capture-pane` check against the reference
  screenshot as a final sanity pass.
- **Open:** Whether any bordered-row (Balance Sheet, dialogs) spacing needs tightening beyond what a static
  code read found — a live pass may surface something the CSS alone didn't show. No stray `margin-bottom` was
  found between rows in `AccountRow`, `CreateGoalDialog`, or `GoalValueForm`, so none was changed.
- **Open:** `_AllocationHeaders .ah-diff` right-aligned header (flagged as a pre-existing violation of the
  "column headers are always left-aligned" rule in a prior slice, `2026-06-16-refinements-and-fixes.md`) is
  out of scope for this ADR — it's a layout/alignment issue, not a color or spacing one.

---

*This ADR is a working-artefact specification. It is not actively maintained after the decision is implemented.*
