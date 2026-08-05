# Deferred Refactor: Controlled-Component Form for `CashFlowPersonProfileView`

**Captured:** 2026-06-11 (during the Cash Flow slice, F-12)
**Status:** Deferred — fixes landed; refactor not started.
**Affected:** `src/personal_finance/ui/screens/cash_flow.py`, `src/personal_finance/ui/widgets/inputs.py`, potentially `src/personal_finance/ui/screens/base.py` (shared with `GoalAllocationView`).

## Symptom that prompted this

A run of recurring, same-shaped bugs on the F-12 person profile form:

- `Select.BLANK` vs `Select.NULL` `TypeError` on empty goal selection.
- Both Auto RRSP fields resetting to `0.00` when switching profiles.
- Focus jumping to the contribution field on left-pane navigation.
- Same-item goal re-selection not auto-advancing focus.
- Auto RRSP match displaying `0.00` on first load only (correct after navigating away and back).

Each was patched individually (`_loading` flag → `prevent()` → `call_after_refresh` → `has_focus` gating). All fixes are in and tests pass.

## Root cause (one cause, many symptoms)

The form's event handlers serve **double duty**: `on_input_changed`, `on_select_changed`, and the `expanded` watcher all fire both when **the user acts** and when **our own code mutates widgets** (loading a profile, `Select.set_options`, widget construction). The handlers cannot distinguish the two, so each bug was fixed by adding another guard to suppress the programmatic case.

Contributing factors:
- **No single source of truth.** Widget state is mutated imperatively from ~4 places, and the progressive-enable rule (match enabled iff goal selected AND contribution > 0) is re-derived independently in each. When two paths disagree on ordering, a bug appears.
- **Phantom construction events.** `Input(value="0.00")` posts an `Input.Changed` at construction (`Input.__init__` runs `self.value = value`). It is queued pre-mount and processed after the load worker finishes, outrunning timing guards. `prevent()` does not catch it (posted outside the prevent block, only *processed* later). This is the first-load-only match-zeroing bug.

See memory `project-textual-gotchas` items #8 (Select.NULL vs BLANK) and #9 (phantom Input.Changed / has_focus gating) for the Textual-level details.

## Proposed refactor

Make the form a **controlled component over an explicit view-model**. Three moves:

1. **One state object, one render method.** A `_FormState` dataclass (extend or wrap `PersonProfileFormData`) carries the editable values and exposes the derivation rules as pure properties:
   ```python
   @property
   def contribution_enabled(self) -> bool: return self.goal_id is not None
   @property
   def match_enabled(self) -> bool: return self.contribution_enabled and self.contribution > 0
   ```
   A single `_render(state)` sets **every** widget from `state`, wrapped in `prevent(...)`. Loading = set state + render. The enable/disable rule lives in exactly one place.

2. **Gate every user-event handler on `has_focus`, uniformly.** Focus is the reliable "the user did this" signal and is immune to event *ordering* (unlike `_loading`, which a queued event can outrun). With a clean `_render`, `_loading` and most `prevent()` calls can then be deleted.

3. **Stop inputs lying at construction.** Add a `SilentNumericInput` (subclass of `RightAlignedNumericInput`) that sets its initial value via `set_reactive(Input.value, ...)` in `__init__` — no watcher, no event. Kills the entire phantom-construction-event class for every screen, not just F-12.

Net effect: handlers shrink to "update state, call `_render`," and the timing-guard zoo disappears.

## Scope / sequencing notes

- This is `TwoPaneScreen`-shaped work: `GoalAllocationView` shares the same left-nav + right-form pattern and the same latent issues, so the controlled-form pattern and `SilentNumericInput` should be designed to be reused by both.
- Touches a screen that was mid-slice when captured. Treat as its own focused change, **not** folded into bug-fix commits.
- Low risk to defer: current behaviour is correct and tested; this is about preventing the *next* bug, not fixing a live one.
