# plc-cursor — TIA-Portal Integration Plan (Design & Structure)

Scope: **design, tabs, layout, file/project structure.** Functionality & content
(instruction behaviour, editing semantics, simulation) are **out of scope here**
— discussed separately. Follow `DESIGN.md` for all visuals.

Target mental model = TIA Portal: a single light shell with a left **project
tree**, a central **work area** of editor tabs, a bottom **Inspector**
(Properties/Info/Diagnostics), a right **task-card rail** (Instructions/Testing/
Libraries/Add-Ins), a top **toolbar**, and a **status bar**.

---

## Phase 0 — Baseline (DONE)

Light theme, custom HTML toolbar, HTML project-tree sidebar, HTML unified
Inspector (own bottom pane), HTML work-area empty state, custom vector icons,
subtle 1px section separators, dark-chrome/borders removed. Codified in `DESIGN.md`.

---

## Phase 1 — Tabs system (the core of this plan)

Three distinct tab surfaces, one consistent visual language (flat, light, amber
active-underline; see DESIGN.md §4).

1. **Work-area editor tabs** (open blocks)
   - Today: native `AuiNotebook` (`TabsOpened`) with `AuiSimpleTabArt` (angled
     "folder" tabs — dated).
   - Plan: flat modern tab strip — square tabs, light, active = white + amber
     underline, hover, middle-click/× close, language badge (ST/LD/FBD) per tab.
   - Approach A (low risk): custom `AuiTabArt` subclass drawing flat tabs.
     Approach B (max control): thin HTML tab-bar header above the editor canvas
     that drives `TabsOpened` page selection. → **decide A vs B.**
   - Files: `IDEFrame.py` (notebook art), optional `ai/tabbar_panel.py`.

2. **Inspector tabs** — DONE (HTML Properties/Info/Diagnostics + sub-tabs). Keep
   as the reference style for the others.

3. **Right task-card rail** (Instructions / Testing / Libraries / Add-Ins)
   - Design only here (content later): a thin vertical rail of collapsible
     cards on the right, TIA-style rotated labels, expand/collapse, remembers
     state. The active card slides open as a panel.
   - Files: new `ai/taskcard_rail.py` (HTML WebView rail) docked Right.
   - **Content** of each card (the instruction catalogue etc.) is deferred.

**Acceptance:** all tabs (work area, inspector, task cards) share one flat light
style; no angled/3D tabs anywhere; opening/closing editor tabs is smooth.

---

## Phase 2 — File system & project structure

Goal: a TIA-like project tree and lifecycle on top of our transparent on-disk
format (no need to copy TIA's opaque object DB).

1. **On-disk format (keep, document):**
   ```
   ProjectName/
     beremiz.xml   ← project config (target, build)
     plc.xml       ← PLCOpen TC6 XML (types: dataTypes + pous; instances)
     *.st          ← optional ST sources
     build/        ← generated C / binary (gitignore)
   ```
   - Treat the **folder** as "the project" (like TIA's `.apXX` folder).
   - Optional: single-file **archive** (`.plcz` = zip of the folder) for
     New/Open/share — analogous to TIA `.zapXX`.

2. **Project tree ↔ PLCOpen mapping** (one clean model the sidebar renders):
   | Tree node | Backing PLCOpen / controller |
   |---|---|
   | Device root | project (single resource/config) |
   | Program blocks → POUs | `<pou pouType=…>` + body language |
   | PLC tags → Default tag table | located `<variable address=…>` |
   | PLC data types | `<dataTypes>` |
   | Resources | `<configurations>/<resource>` |
   - Sidebar (`ai/sidebar_panel.py`) already renders this; formalize a single
     `project_model` dict the sidebar + inspector both consume.

3. **Lifecycle UX (design + wire to existing controller):**
   - **New / Open / Save / Save As / Recent** — already in toolbar; ensure
     modern dialogs and a Recent-projects list.
   - **Add new block** (modal exists) → refine to TIA "Add new block" (name,
     type OB/FB/FC/Program, language). **Add new device** — placeholder.
   - **Context actions** on tree nodes: open, rename, delete, duplicate
     (right-click menu, HTML).
   - Double-click node → opens editor tab in work area (wire to
     `EditProjectElement`).

4. **Layout persistence:** remember panel sizes / collapsed task cards / open
   tabs across restarts (extend the perspective save we already re-capture).

**Acceptance:** tree mirrors TIA hierarchy; New/Open/Save round-trips the folder;
double-click opens a tab; add/rename/delete work from the tree.

---

## Phase 3 — Shell polish

- **Status bar** (bottom): project · target CPU · online/RUN state · scan —
  light, thin, TIA-like (replaces the current wx status bar styling).
- **Portal vs Project view** (optional): a task-oriented start screen
  ("Create / Open / Describe to the agent") vs the full IDE. Low priority.
- **Detach/resize** panels with light sashes (already 1px GRID_LINE); verify
  drag works and min-sizes are sane.

---

## Phase 4 — Design hardening (sweep)

- Audit every remaining native wx surface for dark/90s remnants: menus,
  modal dialogs, `wx.grid` tables, tree controls, scrollbars.
- Enforce `ide_theme` tokens / HTML `:root` everywhere; delete stray literals.
- Verify Retina-crispness of every rendered bitmap (2× rule).

---

## Sequencing & risk

1. **Phase 1.1 (editor tabs)** — highest visible impact, contained. Decide A/B.
2. **Phase 2.2–2.3 (tree model + lifecycle)** — unblocks everything content-side.
3. **Phase 1.3 (task-card rail shell)** — sets the stage for the Instructions
   catalogue (content later).
4. **Phase 3 / 4** — polish, do last.

## Decisions (locked)

- **Editor tabs:** custom `AuiTabArt` subclass (Approach A) — flat light tabs on
  the existing `TabsOpened` notebook. Lowest risk, editors keep working.
- **On-disk format:** keep the transparent project **folder** + add single-file
  **`.plcz`** archive (zip of the folder) for New/Open/share — TIA `.zap` analogue.
- **Task-card rail:** ship **all four** shells (Instructions / Testing /
  Libraries / Add-Ins) as empty collapsible cards; content filled later.

These are design/structure only; instruction behaviour & content come later.
