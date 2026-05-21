# plc-cursor — Master Plan: Look & Work like Siemens TIA Portal

Roadmap to make plc-cursor **look** (design) and **work** (functionality) like TIA
Portal, on top of OpenPLC/Beremiz + PLCOpen XML + the AI agent. Follow
`DESIGN.md` for visuals.

Legend: ✅ done · 🟡 partial · ⬜ to do · ❌ not applicable to a soft-PLC.

---

## 0. Principles & hard constraints (learned this session)

1. **HTML WebView panels are the safe, controllable surface.** Toolbar,
   sidebar, chat, inspector, work-area empty-state are all HTML — modern,
   themeable, no native quirks.
2. **Do NOT restructure the central `AuiNotebook` or subclass C++ `AuiTabArt`.**
   Both segfault wxPython on this macOS build (verified twice). Editor tabs stay
   on `AuiSimpleTabArt`.
3. **Keep AI panel imports clean.** A broken import in the `if _AI_AVAILABLE`
   block silently disables ALL HTML panels → native Beremiz UI resurfaces.
4. **The agent authors content** (POUs, ladder, variables) via tools
   (`add_ladder_rung`, `add_ladder_move_rung`, `add_pou_variable`, …). UI
   surfaces visualise and lightly edit; the heavy authoring is the agent.
5. **Restart + verify after every change** (run.sh); watch the log for
   tracebacks/segfaults.

---

## 1. Foundation & design system — ✅ DONE

Light theme (`ide_theme.py`), custom HTML toolbar (`ai/toolbar_panel.py`) with
custom vector icons (`ai/toolbar_icons.py`), HTML project-tree sidebar
(`ai/sidebar_panel.py`), unified HTML inspector (`ai/inspector_panel.py`), HTML
chat (`ai/chat_panel.py`), white work-area empty state, subtle separators.
Codified in `DESIGN.md`.

---

## 2. Project tree ("Devices") — design ✅ / function 🟡

Full TIA hierarchy is rendered: project → device (`Config0 [Soft PLC]`) →
all sections + Add-new actions + collapse/expand toolbar.

**Make nodes functional (open something on click).** Priority order:

| Node | Action when clicked | Feasibility |
|---|---|---|
| Program blocks → POU | open editor tab | ✅ done |
| Add new block | new-POU modal | ✅ done |
| PLC tags → Default tag table | open a **tag table** editor (Name/Type/Address/Comment, editable) | 🟡 have data |
| Device configuration | form: runtime target + I/O address map | 🟡 partial |
| Online & diagnostics | jump to inspector Diagnostics / connect | 🟡 |
| Watch and force tables | open a **watch table** (live values + force) | 🟡 have bridge/force |
| PLC data types | list/edit UDTs (`<dataTypes>`) | 🟡 when present |
| Program info | compile summary (size, #POU, #tags, call tree) | 🟡 |
| Resources → Config0.Res0 | show/edit task↔program instances | 🟡 |
| Software units, Technology objects, External source files, Online backups, Traces, OPC UA, Web applications, Device proxy data, PLC supervisions & alarms, PLC alarm text lists, Local modules | TIA-specific — keep as **empty folders** (placeholders) like TIA shows them | ❌/later |

Also ⬜: right-click context menu (open / rename / delete / duplicate),
double-click semantics, multi-device note (we have one soft-PLC).

---

## 3. LD graphical editor — TIA-grade (biggest design+function area)

TIA editor layers (analysed): path bar · toolbar · **Block interface** ·
**Block title + comment** · **Networks (number + title + comment)** · ladder
content · status bar.

**Design (on our canvas):**
- ⬜ **Networks**: number each rung (`Network 1:`), with an editable **title**
  and **comment** line above it (most recognizable TIA element).
- ⬜ **Block title** + comment bar at the top of the LD view.
- 🟡 **Block interface**: collapsible variable strip (we currently hide it for
  LD — could re-add as a TIA-style collapsible bar).
- 🟡 editor toolbar: add insert-network, comments on/off, symbolic↔absolute
  address toggle (we have Monitoring/Zoom/Compile).

**Function:**
- ✅ render contacts/coils/boxes/branches from PLCOpen; MOVE block tool.
- ⬜ symbolic ↔ absolute address display toggle (`"Start"` ↔ `%IX0.0`).
- ⬜ live **monitoring** colouring (green energized) — wire the sim bridge to the
  wx canvas (HMI ladder already does this in HTML).
- ⬜ hand-insert elements is optional (agent-authored is primary).

Start here: **numbered networks + title/comment + block title** — pure canvas
drawing, high TIA-fidelity, no AUI risk.

---

## 4. Inspector window (Properties / Info / Diagnostics) — design ✅ / function 🟡

- ✅ structure + flat tabs; General + IO tags read live.
- ⬜ **Properties → General** reflects the *selected* object (POU / tag / device),
  not just the active editor.
- ⬜ **IO tags** editable (rename/retype/address/comment) writing back to PLCOpen.
- 🟡 **Info**: build/compile messages teed in; ⬜ add cross-references + clickable
  search results (jump to location).
- 🟡 **Diagnostics**: wire real PLC/sim status (RUN/STOP, scan, connection).

---

## 5. Instructions task card (right rail) — ⬜

TIA right panel: Favorites · Basic · Extended · Technology · Communication.
- ⬜ HTML rail shell (collapsible cards) — design only first.
- ⬜ **Basic instructions** catalogue (Bit logic, Timers `TON/TOF`, Counters,
  Compare, Math, Move, Convert, Word logic, Shift) — backed by matiec stdlib.
- ⬜ Click/drag an instruction → insert via agent tools (`add_ladder_*`) into the
  active LD POU. (Drag-drop onto wx canvas is hard; start with click-to-append.)
- ❌ Extended/Technology/Communication = Siemens-specific; show as empty shells.

---

## 6. Editor tabs — 🟡 (constrained)

Keep **`AuiSimpleTabArt`** (flat light). Custom C++ tab art / HTML-bar wrapping
the central notebook **segfault** → do not attempt again. Acceptable as-is.

---

## 7. File system / project lifecycle — design 🟡 / function ⬜

- on-disk: keep transparent folder (`beremiz.xml` + `plc.xml` PLCOpen + `*.st` +
  `build/`); folder = "project" (TIA `.apXX` analogue).
- ⬜ single-file **`.plcz`** archive (zip) for New/Open/share (TIA `.zap`).
- ⬜ lifecycle UX: New / Open / Save / Save As / Recent (toolbar wired);
  Add new block (✅), ⬜ Add new device (placeholder), ⬜ rename/delete/duplicate
  from the tree.
- ⬜ persist panel layout / open tabs across restarts.

---

## 8. Sequencing (recommended)

1. **LD networks: number + title + comment + block title** (§3) — highest
   TIA-fidelity, self-contained canvas work.
2. **PLC tags table** + **Watch table** (§2/§4) — real, useful, data exists.
3. **Inspector wiring**: selection-aware Properties, editable IO tags, Info
   cross-refs (§4).
4. **Live monitoring colouring** on the LD canvas (§3).
5. **Instructions rail shell + Basic catalogue** (§5).
6. **Lifecycle: `.plcz` + rename/delete + layout persistence** (§7).
7. Polish: status bar, context menus, address toggle.

Each step: design first (HTML/canvas), then wire to PLCOpen/agent, restart+verify.
Avoid the central-notebook / native-AUI restructuring that caused regressions.
