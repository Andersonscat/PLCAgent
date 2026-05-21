# Instructions Panel (TIA "Instructions task card") — Implementation Plan

Add the right-side **Instructions** rail: a searchable catalogue of LD
instructions (Favorites + Basic categories) that you **click to insert** into the
active LD POU. Backed by matiec's IEC 61131-3 stdlib; inserts via agent tools.

## Surface & layout

- New HTML WebView panel **`ai/instructions_panel.py`** (`InstructionsPanel`),
  same pattern as sidebar / inspector / chat (safe, themeable).
- Dock as a **Right AUI pane** ("InstructionsPane"), stacked/tabbed with the
  existing ChatPane (right side), vertical caption "Instructions" like TIA.
  Adding an AUI pane is low-risk (we already run several) — NOT a notebook
  restructure (that segfaults — see [[project_plc_cursor_tabs_segfault]]).
- Design tokens from `DESIGN.md` (light, amber accent, collapsible cards).

## Catalogue (data model)

Static catalogue in `ai/instructions_catalog.py` — only what matiec actually
compiles, grouped like TIA:

- **Favorites:** NO contact, NC contact, Coil, Set/Reset coil, empty Box, branch.
- **Basic instructions:**
  - Bit logic — contact NO/NC, coil, set/reset (`S`/`R`), `SR`/`RS`, edge `P`/`N`
  - Timers — `TON`, `TOF`, `TP`, `TONR`
  - Counters — `CTU`, `CTD`, `CTUD`
  - Comparators — `EQ NE GT LT GE LE`
  - Math — `ADD SUB MUL DIV MOD ABS MIN MAX LIMIT SQRT`
  - Move — `MOVE` (have), `SEL`, `MUX`
  - Conversion — `*_TO_*`, `TRUNC`, `REAL_TO_INT`
  - Word logic — `AND OR XOR NOT`, `SHL SHR ROL ROR`
- **Extended / Technology / Communication:** Siemens-specific → shown as
  collapsed/empty sections (only expose what matiec supports, if any).

Each entry: `{id, label, category, kind: 'contact'|'coil'|'block', block_type,
icon}`.

## Interaction — click to insert

Click an instruction → bridge message `{type:'insert', id}` → host inserts into
the **active LD POU** via tools, then re-renders the LD editor + sidebar.

- Contacts / coils / MOVE: reuse `add_ladder_rung` / `add_ladder_move_rung`
  (append a new rung).
- Timers / counters / comparators / math: **new generic tool**
  `add_ladder_block_rung(pou, block_type, en_var=None, inputs={}, outputs={})`
  — generalises `add_ladder_move_rung` to any matiec FB/function (EN/ENO + ports).
- v1 = **append a new network**; v2 = insert at the **selected element**
  (we already have element selection in the HTML editor); v3 = drag-and-drop.

## Phases

1. **Rail shell** (HTML): Options bar (search), Favorites, Basic categories as
   collapsible cards — matching TIA. Catalogue rendered, search filters,
   sections collapse. **No insert yet.** Dock the right pane.
2. **Insert — LD basics:** click NO/NC/Coil/MOVE → append a rung via existing
   tools; refresh editor. Wire the bridge + active-POU resolution.
3. **Generic block tool:** `add_ladder_block_rung` for timers/counters/
   comparators/math; insert those from the catalogue.
4. **Position-aware insert:** insert at the selected element/network (use the
   editor's selection); then drag-and-drop from rail → network.
5. Polish: favorites pinning, instruction tooltips/help, version labels.

## Open questions
- Active-POU resolution: track the focused `LDEditorPanel` (the tab system knows
  the selected page) → its TagName. Confirm how to get the active editor.
- Pane placement: tabbed with chat vs its own thin rail. Default: tabbed right.

## Risks
- AUI right pane add — low risk (existing panes), but verify no layout regression.
- New `add_ladder_block_rung` must place EN/ENO + data ports correctly (mirror
  `add_ladder_move_rung`, which works) and pass matiec compile.
- Keep imports isolated (a broken import disables all AI panels).

## Build order
1. `instructions_catalog.py` (data) + `instructions_panel.py` (shell) + dock.
2. Bridge + active-POU + insert for basics (reuse tools).
3. `add_ladder_block_rung` tool + wire timers/counters/etc.
4. Position-aware insert; drag-drop.

---

# Phase 1 — DONE. Functionality strategy (what next, in order)

## What the shell has now (all cosmetic)
- Header buttons (collapse/expand all, collapse pane) — **non-functional**.
- Options: **search field** (no filtering yet), filter/view toggles (cosmetic).
- **Favorites**: 6 LD glyphs (NO, NC, Coil, Box, branch open/close) — non-functional.
- **Basic instructions** tree: 11 folders; only *Move operations* has real leaf
  entries; collapse/expand works; leaves don't insert.
- Bottom sections (Extended/Technology/Communication/Optional) pinned — empty.

## Guiding strategy
1. **Lowest-risk, highest-value first.** Search & plumbing before any model edit.
2. **Insert a whole new network** first (self-contained, always compiles) — defer
   in-rung insertion (hard) to later.
3. **Reuse the proven path** (`add_ladder_move_rung`) — generalise it, don't invent.
4. **Only list instructions matiec actually compiles** — every insert must build.
5. The **agent stays the power-path**; the panel is quick-insert for common items.

## Sequenced phases

### Phase 2a — Plumbing + Search (no model edits, zero risk) ← START HERE
- Make the **search field filter** the tree/favorites live (pure JS).
- Wire the **bridge** (panel → host messages).
- **Active-POU resolution**: read the selected editor tab; if it's an
  `LDEditorPanel`, insertion is enabled; otherwise show instructions dimmed +
  a hint "open an LD block". (No inserts yet — just the enabled/disabled state.)
- Hover highlight + tooltips on instructions.

### Phase 2b — First real insert: blocks → new network
- Generalise `add_ladder_move_rung` → **`add_ladder_block_rung(pou, block_type,
  en_var, inputs, outputs)`** for any matiec FB/function.
- Fill the catalogue with **real, compilable** blocks per category:
  Timers `TON/TOF/TP`, Counters `CTU/CTD/CTUD`, Compare `EQ/NE/GT/LT/GE/LE`,
  Math `ADD/SUB/MUL/DIV`, Move `MOVE`.
- Click a block leaf → append a **new network** with that block (EN from a
  contact, ENO→rail, ports with placeholder tags) → refresh editor + sidebar.

### Phase 2c — Bit-logic basics (contacts / coils)
- Favorites NO/NC/Coil → append a new rung scaffold (contact → coil with
  placeholder tags). Decide names (auto `tag1`, editable inline later).

### Phase 3 — Position-aware insert
- Use the HTML editor's **element selection** (already built) to insert into an
  existing rung at the chosen spot (series/parallel), and add contacts to rungs.

### Phase 4 — Drag-and-drop from the rail onto a network.

### Phase 5 — Favorites pinning, instruction tooltips/help, version labels.

## Key decisions / risks
- **Insertion semantics:** start *new-network* (simple, valid); in-rung later.
- **matiec coverage:** verify each catalogue block compiles (test like
  `_test_move_rung.py`) before exposing it.
- **No LD open:** disable inserts gracefully with a hint.
- **Refresh:** after insert, bump `_last_json=None` + `RefreshView()` on the
  active editor, and refresh the sidebar.
