"""ide_theme — single light palette for the whole editor UI.

The IDE reads as one coherent light tool (TIA-Portal-like): light panel
chrome, white cell/canvas surfaces, dark ink. This module drives the wx
panels — the variable table, ladder canvas, console, project tree, and
the toolbar/AUI chrome (CHROME_BG).

Colours are exposed as wx.Colour (for widgets) and as #RRGGBB hex
strings (for Scintilla StyleSetSpec, which only takes hex). The ladder
*element* colours (black contacts/coils on white) live separately in
graphics/GraphicCommons.py as ELEMENT_INK / *_BRUSH, because that
package is imported with `*` everywhere and shouldn't depend on us.
"""

import wx


def _c(r, g, b):
    return wx.Colour(r, g, b)


def _hex(r, g, b):
    return "#%02X%02X%02X" % (r, g, b)


# --- surfaces & rules -------------------------------------------------------
PANEL_BG     = _c(238, 240, 243)   # panel chrome behind controls
SURFACE      = _c(252, 252, 253)   # primary cell / row background (near-white)
ROW_ALT      = _c(244, 245, 248)   # zebra-striped alternate row
GRID_LINE    = _c(210, 213, 220)   # cell rules
BORDER       = _c(198, 202, 210)

# --- chrome (toolbars, AUI dock background, sashes) -------------------------
CHROME_BG    = _c(226, 229, 234)   # light gray toolbar / dock chrome

# --- table header -----------------------------------------------------------
HEADER_BG    = _c(224, 227, 232)   # raised header bar
HEADER_FG    = _c(60, 64, 72)      # dark, slightly muted

# --- text -------------------------------------------------------------------
INK          = _c(32, 34, 40)      # primary text
INK_DIM      = _c(112, 116, 124)   # secondary text

# --- accent & selection -----------------------------------------------------
ACCENT       = _c(222, 140, 30)    # industrial amber (shared with chrome)
SELECT_BG    = _c(198, 220, 250)   # light blue selection
SELECT_FG    = _c(20, 30, 46)

# --- ladder canvas ----------------------------------------------------------
CANVAS_BG       = _c(252, 252, 252)
CANVAS_GRID_DOT = _c(206, 209, 216)
CANVAS_BORDER   = _c(190, 194, 202)

# --- console (Scintilla — hex strings) --------------------------------------
CONSOLE_BG_HEX   = _hex(246, 247, 249)
CONSOLE_FG_HEX   = _hex(40, 44, 52)
CONSOLE_ERR_HEX  = _hex(200, 40, 40)     # red on light
CONSOLE_WARN_HEX = _hex(255, 244, 214)   # light amber highlight
CONSOLE_BG       = _c(246, 247, 249)     # for the LogViewer (PLC Log) panel


def style_grid(grid):
    """Apply the dark look to a wx.grid.Grid (used by CustomGrid)."""
    grid.SetDefaultCellBackgroundColour(SURFACE)
    grid.SetDefaultCellTextColour(INK)
    grid.SetGridLineColour(GRID_LINE)
    grid.SetSelectionBackground(SELECT_BG)
    grid.SetSelectionForeground(SELECT_FG)
    grid.SetLabelBackgroundColour(HEADER_BG)
    grid.SetLabelTextColour(HEADER_FG)
    grid.SetColLabelSize(34)
    grid.SetDefaultRowSize(34)
    try:
        # area below the last row / empty corner
        grid.SetBackgroundColour(PANEL_BG)
    except Exception:
        pass
    grid.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                         wx.FONTWEIGHT_NORMAL))
    grid.SetLabelFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                              wx.FONTWEIGHT_BOLD))


def row_base_colours(row):
    """Default (bg, fg) for a data cell, with zebra striping by row parity."""
    return (SURFACE if row % 2 == 0 else ROW_ALT), INK


def style_tree(tree):
    """Apply the dark look to a tree control (project / search results)."""
    try:
        tree.SetBackgroundColour(PANEL_BG)
        tree.SetForegroundColour(INK)
    except Exception:
        pass
