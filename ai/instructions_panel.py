"""instructions_panel — cosmetic TIA-style "Instructions" task card (Phase 1).

A right-side HTML rail that mirrors the TIA Portal Instructions task card
(Options / Favorites / Basic instructions tree / Extended / Technology /
Communication / Optional packages). Visual only for now — section headers
collapse, but instructions don't insert yet.
"""

import wx
import wx.html2


# ---- favorite LD glyphs (small inline SVGs, our element style) -------------
def _glyph(inner):
    return (f'<svg viewBox="0 0 34 22" width="34" height="22">{inner}</svg>')


_NO = _glyph('<line x1="0" y1="11" x2="13" y2="11"/><line x1="21" y1="11" x2="34" y2="11"/>'
             '<line x1="13" y1="3" x2="13" y2="19"/><line x1="21" y1="3" x2="21" y2="19"/>')
_NC = _NO + '<line x1="11" y1="20" x2="23" y2="2"/>'
_COIL = _glyph('<line x1="0" y1="11" x2="11" y2="11"/><line x1="23" y1="11" x2="34" y2="11"/>'
               '<path d="M11 3 Q3 11 11 19" fill="none"/><path d="M23 3 Q31 11 23 19" fill="none"/>')
_BOX = _glyph('<rect x="9" y="3" width="16" height="16" rx="2" fill="none"/>'
              '<text x="17" y="15" text-anchor="middle" font-size="9" stroke="none" fill="currentColor">??</text>')
_BR_OPEN = _glyph('<line x1="0" y1="11" x2="34" y2="11"/><line x1="17" y1="11" x2="17" y2="21"/>')
_BR_CLOSE = _glyph('<line x1="0" y1="11" x2="34" y2="11"/><line x1="17" y1="1" x2="17" y2="11"/>')

FAVORITES = [("NO contact", _NO), ("NC contact", _NC), ("Coil", _COIL),
             ("Empty box", _BOX), ("Open branch", _BR_OPEN), ("Close branch", _BR_CLOSE)]

# ---- Basic instructions tree (cosmetic) ------------------------------------
BASIC = [
    ("General", []),
    ("Bit logic operations", []),
    ("Timer operations", []),
    ("Counter operations", []),
    ("Comparator operations", []),
    ("Math functions", []),
    ("Move operations", ["MOVE", "MOVE_BLK", "UMOVE_BLK", "FILL_BLK", "SWAP"]),
    ("Conversion operations", []),
    ("Program control operations", []),
    ("Word logic operations", []),
    ("Shift and rotate", []),
]

_FOLDER = ('<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" '
           'stroke-width="1.2" stroke-linejoin="round"><path d="M2 4.5a1 1 0 011-1h3.2l1.3 1.6H13a1 1 0 '
           '011 1V12a1 1 0 01-1 1H3a1 1 0 01-1-1z"/></svg>')
_BLK = ('<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" '
        'stroke-width="1.2"><rect x="2.5" y="3" width="11" height="10" rx="1.5"/>'
        '<path d="M5 6.5l2 1.5-2 1.5M9 10h2.5" stroke-linecap="round"/></svg>')


def _build_html():
    favs = "".join(
        f'<button class="fav" title="{n}">{g}</button>' for n, g in FAVORITES)

    rows = []
    for name, leaves in BASIC:
        open_cls = " open" if leaves else ""
        rows.append(
            f'<div class="trow folder{open_cls}"><span class="chev">&#9656;</span>'
            f'<span class="ico">{_FOLDER}</span><span class="lbl">{name}</span></div>')
        for lf in leaves:
            rows.append(
                f'<div class="trow leaf"><span class="chev sp"></span>'
                f'<span class="ico">{_BLK}</span><span class="lbl">{lf}</span></div>')
    tree = "".join(rows)

    sections = "".join(
        f'<div class="card collapsed"><div class="chead"><span class="cv">&#9662;</span>'
        f'<span>{t}</span></div><div class="cbody"></div></div>'
        for t in ("Extended instructions", "Technology", "Communication", "Optional packages"))

    return HTML_TEMPLATE.replace("{{FAVS}}", favs).replace("{{TREE}}", tree).replace("{{SECTIONS}}", sections)


HTML_TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
  :root{--bg:#eef0f3;--surface:#fcfcfd;--chrome:#e2e5ea;--line:#d2d5dc;
        --ink:#20222a;--dim:#7c808a;--accent:#de8c1e;}
  *{box-sizing:border-box;} html,body{margin:0;height:100%;background:var(--bg);
    font:12.5px -apple-system,"SF Pro Text","Segoe UI",sans-serif;color:var(--ink);
    overflow:hidden;}
  #wrap{display:flex;flex-direction:column;height:100%;}
  #header{display:flex;align-items:center;padding:9px 12px;background:var(--chrome);
    border-bottom:1px solid var(--line);font-weight:700;font-size:13.5px;}
  #header .sp{flex:1;}
  #header .hbtn{width:22px;height:22px;border-radius:5px;color:var(--dim);
    display:inline-flex;align-items:center;justify-content:center;cursor:default;}
  #header .hbtn:hover{background:#d3d7de;color:var(--ink);}
  #options{display:flex;align-items:center;gap:6px;padding:7px 10px;background:var(--bg);
    border-bottom:1px solid var(--line);}
  #search{flex:1;height:26px;border:1px solid var(--line);border-radius:6px;
    padding:0 9px;background:var(--surface);font-size:12px;color:var(--ink);outline:none;}
  #search:focus{border-color:var(--accent);}
  .obtn{width:26px;height:26px;border:1px solid var(--line);border-radius:6px;
    background:var(--surface);color:var(--dim);cursor:default;display:inline-flex;
    align-items:center;justify-content:center;}
  .obtn:hover{color:var(--ink);}
  #header,#options{flex:0 0 auto;}
  .favcard{flex:0 0 auto;}
  .basiccard{flex:1 1 auto;display:flex;flex-direction:column;min-height:0;}
  .basiccard.collapsed{flex:0 0 auto;}
  .basiccard>.cbody{flex:1 1 auto;overflow-y:auto;min-height:0;}
  #bottom{flex:0 0 auto;}
  .card{border-bottom:1px solid var(--line);}
  .chead{display:flex;align-items:center;gap:8px;padding:7px 12px;background:var(--chrome);
    font-weight:600;cursor:pointer;user-select:none;}
  .chead .cv{color:var(--dim);font-size:10px;transition:transform .12s;}
  .card.collapsed .cv{transform:rotate(-90deg);}
  .card.collapsed .cbody{display:none;}
  .cbody{background:var(--surface);}
  .favs{display:flex;flex-wrap:wrap;gap:6px;padding:10px 12px;}
  .fav{width:46px;height:34px;border:1px solid var(--line);border-radius:7px;
    background:var(--surface);color:var(--ink);cursor:pointer;display:inline-flex;
    align-items:center;justify-content:center;}
  .fav svg{stroke:currentColor;stroke-width:2;fill:none;stroke-linecap:round;}
  .fav:hover{border-color:var(--accent);color:var(--accent);background:#fff7ec;}
  .colhead{display:flex;padding:4px 12px;color:var(--dim);font-size:11px;
    border-bottom:1px solid var(--line);background:var(--bg);}
  .trow{display:flex;align-items:center;gap:7px;padding:4px 12px;cursor:default;
    color:var(--ink);}
  .trow:hover{background:#eef2f8;}
  .trow.leaf{padding-left:30px;color:#3a3e47;}
  .trow .chev{width:10px;color:var(--dim);font-size:9px;transition:transform .12s;}
  .trow.folder.open .chev{transform:rotate(90deg);}
  .trow .chev.sp{visibility:hidden;}
  .trow .ico{color:var(--accent);display:inline-flex;}
  .trow.leaf .ico{color:var(--dim);}
  .trow .lbl{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
</style></head><body><div id="wrap">
  <div id="header"><span>Instructions</span><span class="sp"></span>
    <span class="hbtn" title="Collapse all">&#8863;</span>
    <span class="hbtn" title="Expand all">&#8862;</span>
    <span class="hbtn" title="Collapse pane">&#9656;</span></div>
  <div id="options">
    <input id="search" placeholder="Search instructions…">
    <span class="obtn" title="Filter">&#9776;</span>
    <span class="obtn" title="List view">&#9783;</span>
  </div>
  <div class="card favcard"><div class="chead"><span class="cv">&#9662;</span><span>Favorites</span></div>
    <div class="cbody"><div class="favs">{{FAVS}}</div></div></div>
  <div class="card basiccard"><div class="chead"><span class="cv">&#9662;</span><span>Basic instructions</span></div>
    <div class="cbody"><div class="colhead">Name</div>{{TREE}}</div></div>
  <div id="bottom">{{SECTIONS}}</div>
</div>
<script>
  document.querySelectorAll('.chead').forEach(function(h){
    h.addEventListener('click',function(){h.parentNode.classList.toggle('collapsed');});
  });
  document.querySelectorAll('.trow.folder').forEach(function(f){
    f.addEventListener('click',function(){f.classList.toggle('open');
      var n=f.nextElementSibling;
      while(n&&n.classList.contains('leaf')){n.style.display=f.classList.contains('open')?'flex':'none';n=n.nextElementSibling;}
    });
  });
</script></body></html>"""


class InstructionsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundColour(wx.Colour(0xEE, 0xF0, 0xF3))
        try:
            self.web = wx.html2.WebView.New(self, style=wx.BORDER_NONE)
        except Exception:
            self.web = wx.html2.WebView.New(self)
        try:
            self.web.EnableContextMenu(False)
        except Exception:
            pass
        self.web.SetPage(_build_html(), "")
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(self.web, 1, wx.EXPAND)
        self.SetSizer(s)
