"""Shared color palette tokens for the NetWare-inspired UI theme.

Centralizes the hex values referenced across screen ``DEFAULT_CSS`` blocks and
inline Rich markup styles, so a palette change is a one-file edit instead of a
grep across every screen. Textual's ``$variable`` CSS substitution does not
propagate across separate CSS sources (``netware.tcss`` vs. a screen's own
``DEFAULT_CSS`` string are parsed independently against the same variable
snapshot), so these are plain Python constants: import them and interpolate
into ``DEFAULT_CSS`` f-strings or Rich ``style=`` strings.

See ``specs/working-artefacts/adr/2026-08-05-frontend-visual-polish.md`` for
the WCAG contrast rationale behind each value.

``netware.tcss`` cannot import these (it is a static file loaded via
``CSS_PATH``, not a Python string) — its few structural-color rules
(``Input``/``Select`` borders, ``.dialog`` fill) carry the same literal values
by hand and are commented to keep in sync with this module.
"""

from __future__ import annotations

#: Panel/chrome surfaces (bordered boxes, dialogs, title bars) — one step
#: brighter than the screen background they sit on. Deliberately a modest
#: lift (not a full 3:1 jump): white borders remain the primary hierarchy
#: signal, this is a secondary depth cue that preserves the dark NetWare fill.
PANEL_FILL = "#1a1ab0"

#: Unfocused input/select borders, structural nav-pane dividers, and panel
#: boundary rules (border-top/border-right). 3:1+ against both #000080 and
#: #000066 — previously #555588/#333388, which fell to ~2:1-1.6:1.
BORDER_STRUCTURAL = "#6666cc"

#: Unselected nav items, dim account/category names, blocked list rows.
#: Previously #888888 (4.07:1, just under the 4.5:1 body-text floor) and
#: #555577 (2.10:1); both unified into this one blue-grey tone (5.93:1).
TEXT_DIM = "#9a9ad6"

#: Lowest tier of the text-emphasis ladder (primary > secondary > dim >
#: hint): splash "Press Enter to skip", manual-entry "-" placeholders.
#: Previously #555555 (1.98:1, a genuine legibility bug). Intentionally
#: below the 4.5:1 body-text AA floor at 4.01:1 -- it is the bottom rung,
#: not body text, analogous to how most design systems place placeholder/
#: disabled text below the body-text floor.
TEXT_HINT = "#7a7ab3"

#: Tertiary in-content separators (Rule widgets, decorative divider lines)
#: ONLY -- never buttons, primary text, or monetary values. Previously
#: #333388 for this specific role (1.6:1); distinct from BORDER_STRUCTURAL,
#: which covers load-bearing pane-split/panel-boundary borders.
ACCENT_CYAN = "#00aaaa"
