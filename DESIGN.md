# plc-cursor — Design System

The reference for how plc-cursor looks and feels. **Adhere to this for every UI
change.** Goal: a modern, professional, light, TIA-Portal-grade industrial IDE —
not a half-dark/half-90s-wx patchwork.

---

## 1. Principles

1. **Light, single coherent surface.** One light theme everywhere. No dark
   islands, no leftover native-wx greys, no black 1px borders/grippers.
2. **Modern flat.** No 3D bevels, no gradient "folder" tabs, no emoji icons, no
   sparse oversized buttons. Flat surfaces, thin rules, tasteful spacing.
3. **Retina-crisp, always.** Every rendered bitmap/icon is authored at 2× and
   tagged `SetScaleFactor(2.0)`. Never ship a blurry 1× asset. (See `MEMORY`.)
4. **HTML for rich panels.** Inspector, sidebar, chat, HMI are HTML WebViews —
   easy to make modern and consistent. Native wx is for the editor canvas and
   menus only.
5. **TIA-Portal mental model.** Networks, Properties/Info/Diagnostics inspector,
   icon-only engineering toolbar with tooltips, symbolic/absolute addressing.
6. **The agent authors content.** Variables, ladder, HMI are produced by the AI
   agent — UI surfaces visualise, they don't force manual low-level editing.

---

## 2. Colour palette

Single source of truth: **`editor/ide_theme.py`** (wx) and the `:root` blocks of
the HTML panels (keep them in sync with these values).

| Token | Hex | Use |
|---|---|---|
| `CHROME_BG` | `#E2E5EA` | toolbars, AUI dock, tab chrome, frame bg |
| `PANEL_BG` | `#EEF0F3` | panel chrome behind controls |
| `SURFACE` | `#FCFCFD` | cells, rows, active tab, canvas-ish surfaces |
| `ROW_ALT` | `#F4F5F8` | zebra row |
| `GRID_LINE` | `#D2D5DC` | cell rules, borders |
| `BORDER` / `--line` | `#C6CAD2` / `#D2D5DC` | dividers |
| `HEADER_BG` | `#E0E3E8` | table headers |
| `INK` | `#20222A` | primary text |
| `INK_DIM` | `#70747C` | secondary text |
| `ACCENT` | `#DE8C1E` | industrial amber — selection, active tab underline, focus, logo |
| `CANVAS_BG` | `#FCFCFC` | ladder canvas (black ink on white, like Siemens) |
| `--ok` | `#2E9E44` | success / RUN |
| `--err` | `#C8392B` | error / STOP |
| `--warn` | `#B9791A` | warning |

Ladder element ink lives in `graphics/GraphicCommons.py`: near-black
`#1C1E24` strokes on white `#FCFCFC` paper.

**Never** introduce a new hardcoded colour in a widget — reference `ide_theme`
(wx) or a `:root` var (HTML). Audit for stray dark literals (`30,33,39`,
`13,14,16`, `#0d0e10`, `wx.BLACK`) — they create dark islands.

---

## 3. Toolbar

- **Custom HTML toolbar** (`editor/ai/toolbar_panel.py`), a WebView docked top —
  NOT a native `wx.ToolBar` (macOS fights us on bottom divider, icon/label
  colour and sizing; the wx Menu/Editor/Status toolbars are hidden).
- Buttons = **custom vector icons** (`editor/ai/toolbar_icons.py`,
  Lucide/Feather style, 24×24 viewBox, 2px round stroke) inlined as SVG, **22px**,
  with a **caption under each** (`--dim`, hover → `--ink`). Run = green
  `#2E9E44`, Stop = red `#C8392B`.
- Panel `HEIGHT ≈ 72px`; bg `CHROME_BG`; hover `#d3d7de`; thin `--line` group
  separators. Inline "Search in project" field on the right.
- Groups: File · Edit · Undo/Redo · Build · Online/Run · Deploy · Debug.
- Clicks post `{action}` over the `bridge` script channel → dispatched in
  `BeremizIDE._on_toolbar_action` to frame handlers / ProjectController methods.
  Disabled actions are dimmed when no project is open (`setEnabled`).
- Add a new tool: extend `GROUPS` in `toolbar_panel.py` (+ an icon path in
  `toolbar_icons.py`) and map the action in `_on_toolbar_action`.

---

## 4. Tabs & panels

- AUI notebooks use flat art; the bottom inspector hides its AUI tab bar
  (`SetTabCtrlHeight(0)`) and uses its **own flat HTML tabs** (active = bold ink
  + amber underline).
- **Bottom inspector** = one HTML panel, three sections:
  - **Properties** — sub-tabs General · IO tags · System constants · Texts.
  - **Info** — compile/build messages (errors red, warnings amber) + search
    results. Console/PLC Log are teed in here, not as separate native tabs.
  - **Diagnostics** — connection · operating mode (RUN/STOP LED) · target · status.
- HTML panel chrome: `--bg` light, thin `--line` dividers, system font stack
  (`-apple-system, "SF Pro Text", "Segoe UI", …`), 12.5px base.

---

## 5. Typography & spacing

- UI font: system stack. Mono (console/addresses): `ui-monospace, "SF Mono", Menlo`.
- Base 12.5–13.5px; headers 17–18px/600; uppercase micro-labels 10–11px with
  `.6–.9px` letter-spacing in `--dim`.
- Tables: 6px header padding, 5px cell padding, zebra rows, sticky header.

---

## 6. Process checklist (every UI change)

1. Pull colours from `ide_theme` / `:root` — no new literals.
2. Bitmaps authored at 2× and tagged HiDPI; composed content vertically centred.
3. After changing code, **relaunch the app yourself** (`run.sh`) and verify.
4. Watch for regressions: dark 1px borders/grippers, blurry icons, sparse
   toolbars, dark islands, emoji icons.
5. Keep `ide_theme.py` and HTML `:root` palettes in sync.
