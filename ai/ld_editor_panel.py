"""ld_editor_panel — segmented HTML LD editor (TIA-style).

Renders an LD POU as a vertical stack of independent **Network segments**
(header + comment + ladder SVG), reading the PLCOpen geometry via ld_parse.
A WebView panel opened in the work-area tab for LD POUs (behind a feature flag,
with fallback to the native LD_Viewer). Read-only render for now — logic is
authored by the AI agent; live monitoring + inline editing come later.
"""

import sys

import wx
import wx.html2

from ai.ld_parse import parse_ld_networks


INK = "#1c1e24"
LABEL = "#20222a"
ADDR = "#2f6f9c"


def _esc(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _wire(points):
    if len(points) < 2:
        return ""
    d = " ".join("%d,%d" % (x, y) for x, y in points)
    return f'<polyline points="{d}" fill="none" stroke="{INK}" stroke-width="2"/>'


def _contact(e):
    x, y, w, h = e["x"], e["y"], e["w"] or 30, e["h"] or 20
    cy = y + h // 2
    b1, b2 = x + 11, x + w - 11
    s = []
    s.append(f'<line x1="{x}" y1="{cy}" x2="{b1}" y2="{cy}" stroke="{INK}" stroke-width="2"/>')
    s.append(f'<line x1="{b2}" y1="{cy}" x2="{x+w}" y2="{cy}" stroke="{INK}" stroke-width="2"/>')
    s.append(f'<line x1="{b1}" y1="{y}" x2="{b1}" y2="{y+h}" stroke="{INK}" stroke-width="2"/>')
    s.append(f'<line x1="{b2}" y1="{y}" x2="{b2}" y2="{y+h}" stroke="{INK}" stroke-width="2"/>')
    if e["negated"]:
        s.append(f'<line x1="{b1}" y1="{y+h}" x2="{b2}" y2="{y}" stroke="{INK}" stroke-width="1.5"/>')
    if e["var"]:
        s.append(f'<text x="{x+w//2}" y="{y-4}" text-anchor="middle" font-size="11" fill="{LABEL}">{_esc(e["var"])}</text>')
    return "".join(s)


def _coil(e):
    x, y, w, h = e["x"], e["y"], e["w"] or 30, e["h"] or 20
    cy = y + h // 2
    s = []
    s.append(f'<line x1="{x}" y1="{cy}" x2="{x+8}" y2="{cy}" stroke="{INK}" stroke-width="2"/>')
    s.append(f'<line x1="{x+w-8}" y1="{cy}" x2="{x+w}" y2="{cy}" stroke="{INK}" stroke-width="2"/>')
    s.append(f'<path d="M {x+8} {y+2} Q {x-3} {cy} {x+8} {y+h-2}" fill="none" stroke="{INK}" stroke-width="2"/>')
    s.append(f'<path d="M {x+w-8} {y+2} Q {x+w+3} {cy} {x+w-8} {y+h-2}" fill="none" stroke="{INK}" stroke-width="2"/>')
    if e["negated"]:
        s.append(f'<line x1="{x+8}" y1="{y+h}" x2="{x+w-8}" y2="{y}" stroke="{INK}" stroke-width="1.5"/>')
    if e["var"]:
        s.append(f'<text x="{x+w//2}" y="{y-4}" text-anchor="middle" font-size="11" fill="{LABEL}">{_esc(e["var"])}</text>')
    return "".join(s)


def _rail(e):
    x, y, h = e["x"], e["y"], e["h"] or 20
    return f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+h}" stroke="{INK}" stroke-width="3"/>'


def _block(e):
    x, y, w, h = e["x"], e["y"], e["w"] or 90, e["h"] or 100
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="#f1f3f7" stroke="{INK}" stroke-width="1.5"/>']
    s.append(f'<text x="{x+w//2}" y="{y+14}" text-anchor="middle" font-size="11" font-weight="700" fill="{LABEL}">{_esc(e["btype"])}</text>')
    for p in e["ports"]:
        px, py = x + p["rx"], y + p["ry"]
        if p["dir"] == "in":
            s.append(f'<line x1="{px-8}" y1="{py}" x2="{px}" y2="{py}" stroke="{INK}" stroke-width="2"/>')
            s.append(f'<text x="{px+4}" y="{py+4}" font-size="9" fill="{LABEL}">{_esc(p["name"])}</text>')
        else:
            s.append(f'<line x1="{px}" y1="{py}" x2="{px+8}" y2="{py}" stroke="{INK}" stroke-width="2"/>')
            s.append(f'<text x="{px-4}" y="{py+4}" text-anchor="end" font-size="9" fill="{LABEL}">{_esc(p["name"])}</text>')
    return "".join(s)


def _var_box(e):
    x, y, w, h = e["x"], e["y"], e["w"] or 80, e["h"] or 30
    cy = y + h // 2
    s = []
    if e["kind"] == "invar":
        s.append(f'<line x1="{x+w}" y1="{cy}" x2="{x+w+8}" y2="{cy}" stroke="{INK}" stroke-width="2"/>')
    else:
        s.append(f'<line x1="{x-8}" y1="{cy}" x2="{x}" y2="{cy}" stroke="{INK}" stroke-width="2"/>')
    s.append(f'<text x="{x+w//2}" y="{cy+4}" text-anchor="middle" font-size="10" fill="{ADDR}">{_esc(e["var"])}</text>')
    return "".join(s)


def render_network_svg(net):
    pad, top = 12, 20
    vb_w, vb_h = net["w"] + pad * 2, net["h"] + top + pad
    parts = []
    # wires first (connections), then symbols
    for e in net["elements"]:
        for wpts in e["wires"]:
            parts.append(_wire(wpts))
    for e in net["elements"]:
        k = e["kind"]
        if k == "contact":
            parts.append(_contact(e))
        elif k == "coil":
            parts.append(_coil(e))
        elif k in ("leftrail", "rightrail"):
            parts.append(_rail(e))
        elif k == "block":
            parts.append(_block(e))
        elif k in ("invar", "outvar"):
            parts.append(_var_box(e))
    inner = "".join(parts)
    return (f'<svg class="ld" viewBox="{-pad} {-top} {vb_w} {vb_h}" '
            f'width="{vb_w}" height="{vb_h}" xmlns="http://www.w3.org/2000/svg">{inner}</svg>')


HEAD = r"""<!doctype html><html><head><meta charset="utf-8"><style>
  :root{--bg:#fcfcfc;--head:#e6e8ec;--line:#d2d5dc;--ink:#20222a;--dim:#8a8d96;--accent:#de8c1e;}
  *{box-sizing:border-box;} html,body{margin:0;height:100%;background:var(--bg);
    font:12.5px -apple-system,"SF Pro Text","Segoe UI",sans-serif;color:var(--ink);}
  #title{display:flex;align-items:center;gap:8px;padding:8px 12px;background:#eef0f3;
    border-bottom:1px solid var(--line);font-weight:600;position:sticky;top:0;z-index:2;}
  #title .cmt{color:var(--dim);font-weight:400;}
  .network{border-bottom:1px solid var(--line);}
  .nhead{display:flex;align-items:center;gap:8px;padding:5px 12px;background:var(--head);
    border-top:1px solid var(--line);border-bottom:1px solid var(--line);cursor:pointer;}
  .nhead .tab{width:3px;height:14px;background:var(--accent);border-radius:1px;}
  .nhead .ttl{font-weight:600;}
  .nhead .name{color:var(--dim);font-weight:400;}
  .nhead .chev{margin-left:auto;color:var(--dim);font-size:10px;transition:transform .12s;}
  .network.collapsed .chev{transform:rotate(-90deg);}
  .ncomment{padding:3px 14px;color:var(--dim);font-size:11.5px;}
  .nbody{padding:10px 14px 16px;overflow-x:auto;background:
    radial-gradient(circle, #d7dae1 1px, transparent 1px); background-size:14px 14px;}
  .network.collapsed .nbody, .network.collapsed .ncomment{display:none;}
  svg.ld{display:block;}
  .empty{color:var(--dim);text-align:center;padding:40px;}
</style></head><body><div id="root"></div>
<script>
  function render(state){
    const r=document.getElementById('root');
    if(!state||!state.networks||!state.networks.length){
      r.innerHTML='<div id="title">'+(state&&state.block?state.block:'(block)')+'</div>'+
        '<div class="empty">No networks. Ask the PLC Agent to add ladder logic.</div>';return;}
    let h='<div id="title">'+esc(state.block)+'<span class="cmt">'+esc(state.comment||'')+'</span></div>';
    state.networks.forEach(n=>{
      h+='<div class="network"><div class="nhead"><span class="tab"></span>'+
         '<span class="ttl">Network '+(n.index+1)+'</span>'+
         (n.title?'<span class="name">'+esc(n.title)+'</span>':'')+
         '<span class="chev">&#9662;</span></div>'+
         '<div class="ncomment">'+(n.comment?esc(n.comment):'Comment')+'</div>'+
         '<div class="nbody">'+n.svg+'</div></div>';
    });
    r.innerHTML=h;
    r.querySelectorAll('.nhead').forEach(el=>el.addEventListener('click',()=>
      el.parentNode.classList.toggle('collapsed')));
  }
  function esc(s){return (s==null?'':(''+s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
</script></body></html>"""


class LDEditorPanel(wx.Panel):
    """Segmented HTML LD editor. Duck-types EditorPanel so the work-area tab
    system can host it (GetTagName/IsViewing/Save/RefreshView/...)."""

    def __init__(self, parent, tagname, window, controler, debug=False, instancepath=""):
        super().__init__(parent, style=wx.BORDER_NONE)
        self.TagName = tagname
        self.ParentWindow = window
        self.Controler = controler
        self.Debug = debug
        self.Icon = None
        self._ready = False
        self.SetBackgroundColour(wx.Colour(252, 252, 252))

        try:
            self.webview = wx.html2.WebView.New(self, style=wx.BORDER_NONE)
        except Exception:
            self.webview = wx.html2.WebView.New(self)
        try:
            self.webview.SetWindowStyleFlag(wx.BORDER_NONE)
            self.SetWindowStyleFlag(wx.BORDER_NONE)
        except Exception:
            pass
        self.webview.EnableContextMenu(False)
        self.webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, self._on_loaded)
        self.webview.SetPage(HEAD, "")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.webview, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda e: self.RefreshView(), self._timer)
        self._timer.Start(1500)

    # ---- rendering ----
    def _on_loaded(self, _e):
        self._ready = True
        self.RefreshView()

    def _pou_name(self):
        t = self.TagName or ""
        return t.split("::")[-1] if "::" in t else t

    def _gather(self):
        import json
        block = self._pou_name()
        networks = []
        try:
            project = self.Controler.GetProject() if hasattr(self.Controler, "GetProject") else getattr(self.Controler, "Project", None)
            pou = project.getpou(block) if project is not None else None
            ld = None
            if pou is not None:
                body = pou.getbody()
                if isinstance(body, list):
                    body = body[0] if body else None
                if body is not None:
                    ld = body.getcontent()
            if ld is not None:
                for net in parse_ld_networks(ld):
                    net["svg"] = render_network_svg(net)
                    net.pop("elements", None)
                    networks.append(net)
        except Exception as exc:
            print(f"[ld-editor] parse failed: {exc}", file=sys.stderr)
        return json.dumps({"block": block, "comment": "", "networks": networks})

    def RefreshView(self, *a, **k):
        if not self._ready:
            return
        try:
            self.webview.RunScript("try{render(" + self._gather() + ")}catch(e){}")
        except Exception:
            pass

    # ---- EditorPanel-compatible stubs ----
    def GetTagName(self):
        return self.TagName

    def SetTagName(self, tagname):
        self.TagName = tagname

    def IsViewing(self, tagname):
        return self.TagName == tagname

    def IsDebugging(self):
        return False

    def IsModified(self):
        return False

    def GetBufferState(self):
        return False, False

    def GetConfNodeMenuItems(self):
        return []

    def RefreshConfNodeMenu(self, menu):
        pass

    def HasNoModel(self):
        return False

    def GetScale(self):
        return 0

    def GetInstancePath(self, *a, **k):
        return ""

    def CheckSaveBeforeClosing(self, *a, **k):
        return True

    def RefreshScaling(self, *a, **k):
        pass

    def GetTitle(self):
        return ".".join(self.TagName.split("::")[1:]) if "::" in self.TagName else self.TagName

    def GetIcon(self):
        return self.Icon

    def SetIcon(self, icon):
        self.Icon = icon

    def Select(self):
        try:
            self.ParentWindow.EditProjectElement(None, self.GetTagName(), True)
        except Exception:
            pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None
