# Segmented LD Editor — Design (TIA-style networks as separate segments)

Goal: replace the single-canvas wx ladder view with a **vertical stack of
independent Network segments** like TIA: each network = its own area with a
collapse arrow, `Network N:` title, a Comment line, and its own ladder drawing.
Plus a Block title bar on top.

## Decision: build it as an HTML WebView editor (not native wx)

Why:
- The native Beremiz `LD_Viewer` is one `wx.ScrolledWindow` drawing all elements
  by absolute (x,y). Making true separate segments there means rebuilding the
  layout/hit-testing engine — high effort + the wx/AUI fragility we hit this
  session (segfaults on canvas/notebook restructuring).
- We already render ladders as **animated SVG** in `ai/ladder_html.py`
  (contacts/coils/branches, green-on-energized via `/state`). HTML gives us:
  per-network segments trivially (one `<section>` per network), collapse,
  comments, live monitoring, and full design-system styling — no segfault risk.
- Consistent with sidebar / chat / inspector / toolbar (all HTML).

New module: **`editor/ai/ld_editor_panel.py`** — `LDEditorPanel(wx.Panel)`
hosting a WebView; opened in the work-area tab for LD POUs.

---

## Data model: PLCOpen LD → Networks

A **network** = one `leftPowerRail` + the elements connected through to its
`rightPowerRail`(s). Build a parser `plcopen_ld_to_networks(pou_xml)`:

```
network = {
  index, title, comment,
  rungs: [ { branches:[[contact]…], series_before:[…], series_after:[…],
             coil:{var,negated} | block:{type,inputs,outputs} } ],
}
```

Grouping algorithm (robust): start from each `leftPowerRail`, walk
`connectionPointIn`/`Out` links to collect its sub-graph until `rightPowerRail`.
Pragmatic fallback: group by Y-band (each left rail's Y → next left rail's Y),
since our generator already lays rungs in vertical bands. This is the **inverse
of `add_ladder_rung`** — reuse its rung schema so `ladder_html.py` can render.

`ai/ladder_html.py` already renders a rung list → SVG; extend it to render
**MOVE / function blocks** (boxes with EN/ENO/IN/OUT), which the parser must
emit for `<block>` elements.

---

## UI layout (HTML)

```
┌ Block title:  "program0"            [comment…]            ┐  (sticky top)
├───────────────────────────────────────────────────────────┤
│ ▾  Network 1   <title>                                     │  header bar
│    <comment line>                                          │
│    ┌───────────────────────────────────────────────────┐  │
│    │  ── Start ─ /Stop ─ /Overload ──( Motor )──        │  │  ladder SVG
│    │  ── Motor ─┘  (seal-in branch)                     │  │
│    └───────────────────────────────────────────────────┘  │
├───────────────────────────────────────────────────────────┤
│ ▾  Network 2   …                                           │
│    …                                                       │
└───────────────────────────────────────────────────────────┘
```

- Each network = a `<section class="network">`: header (collapse ▾ + `Network N`
  + editable title) + comment row + ladder SVG box.
- Block title bar pinned at top (block name + comment).
- Design tokens from `DESIGN.md` (light, amber accent, GRID_LINE separators).
- Empty state when POU has no rungs.

---

## Live monitoring

Reuse `ai/sim_bridge.py` (`/state` at 127.0.0.1:8765). On simulate, subscribe
the POU's variables; the SVG colours energized contacts/coils/wires green at
10 Hz (already implemented in `ladder_html.py`). Toggle from the editor toolbar
(Monitoring button we already have).

---

## Integration with the work area (the risky part)

Editors are created in `IDEFrame.EditProjectElement` by body type
(Viewer / LD_Viewer / TextViewer). Add: **if body == "LD" and AI available →
`LDEditorPanel`** instead of `LD_Viewer`.

`LDEditorPanel` must **duck-type the EditorPanel interface** the tab system calls
(`GetTagName, IsViewing, IsDebugging, IsModified, CheckSaveBeforeClosing, Save,
SaveAs, ResetBuffer, RefreshView, SetMode, GetTitle, GetIcon`). Lesson from this
session: a missing method or a broken import silently breaks the whole UI — so:
- implement all stubs + a `__getattr__` no-op safety net,
- **feature-flag** `USE_HTML_LD` with graceful fallback to native `LD_Viewer`,
- keep imports isolated so a failure can't disable other AI panels.

Re-render on change: poll the controller / hook the agent's edit tools so the
segments refresh after the agent modifies the POU.

---

## Editing scope — phased

- **Phase 1 (render + read):** parse → segmented SVG render, collapse, block
  title, network titles/comments (stored), live monitoring. Editing of *logic*
  stays with the agent (`add_ladder_rung`, `add_ladder_move_rung`). ← start here.
- **Phase 2 (light inline edit):** rename a tag, toggle contact NO↔NC, toggle
  coil negate, delete an element → write back via PLCOpen tools.
- **Phase 3 (full edit):** click/drag from the Instructions task card to insert
  contacts/coils/boxes; add/move networks.

## Where to store network title/comment

PLCOpen LD has no native "network" object (flat power rails). Options:
1. **`<comment>` graphic elements** placed at each network header (Beremiz
   renders these) — portable, lives in `plc.xml`.
2. **Sidecar** keyed by network index in `beremiz.xml`/project metadata.
→ Propose **(1)** (comment elements) so titles/comments travel with the program.

---

## Risks & mitigations
- Editor-swap breaks the tab system → duck-type fully + feature-flag + fallback.
- PLCOpen connectivity parsing edge cases → start with Y-band grouping (matches
  our generator), refine to graph-walk.
- Keeping in sync with agent edits → re-render on controller change / after tool
  calls.
- Save semantics: Phase 1 is read-render of `plc.xml`; saving stays through the
  existing controller (no separate write path) until Phase 2.

## Build order
1. `plcopen_ld_to_networks` parser (+ unit-test like `_test_move_rung.py`).
2. Extend `ladder_html.py` to render MOVE/function blocks.
3. `LDEditorPanel` (HTML, segments, block title, collapse, comments) — read-only.
4. Wire into `EditProjectElement` behind `USE_HTML_LD`, with fallback.
5. Live monitoring via `sim_bridge`.
6. Phase 2 inline edits; Phase 3 instruction drag-in.
