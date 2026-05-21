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


# shared stroke styling — round caps/joins for a clean, modern look
_W = 'stroke-width="2"'
_WB = 'stroke-width="2.6"'           # contact bars / rails
_CAP = 'stroke-linecap="round" stroke-linejoin="round"'
_FONT = 'font-family="-apple-system,&apos;SF Pro Text&apos;,&apos;Segoe UI&apos;,sans-serif"'


def _wire(points):
    if len(points) < 2:
        return ""
    d = " ".join("%d,%d" % (x, y) for x, y in points)
    return f'<polyline points="{d}" fill="none" stroke="{INK}" {_W} {_CAP}/>'


def _name(cx, top, text):
    return (f'<text x="{cx}" y="{top}" text-anchor="middle" font-size="12" '
            f'font-weight="600" fill="{LABEL}" {_FONT}>{_esc(text)}</text>')


def _grp(eid, kind, body, hit):
    """Wrap an element's symbol in a clickable group (color via currentColor so
    hover/selection can recolour it); `hit` is an invisible click target."""
    return (f'<g class="el" data-id="{eid}" data-kind="{kind}">'
            f'<rect x="{hit[0]}" y="{hit[1]}" width="{hit[2]}" height="{hit[3]}" '
            f'fill="transparent"/>{body}</g>')


def _contact(e):
    # clean bare IEC symbol: leads + two vertical bars, optional NC slash
    x, y, w, h = e["x"], e["y"], e["w"] or 30, e["h"] or 20
    cy = y + h // 2
    b1, b2 = x + 9, x + w - 9
    s = [
        f'<line x1="{x}" y1="{cy}" x2="{b1}" y2="{cy}" stroke="currentColor" {_W} {_CAP}/>',
        f'<line x1="{b2}" y1="{cy}" x2="{x+w}" y2="{cy}" stroke="currentColor" {_W} {_CAP}/>',
        f'<line x1="{b1}" y1="{y}" x2="{b1}" y2="{y+h}" stroke="currentColor" {_WB} {_CAP}/>',
        f'<line x1="{b2}" y1="{y}" x2="{b2}" y2="{y+h}" stroke="currentColor" {_WB} {_CAP}/>',
    ]
    if e["negated"]:   # diagonal slash through both bars (NC)
        s.append(f'<line x1="{b1-3}" y1="{y+h+3}" x2="{b2+3}" y2="{y-3}" '
                 f'stroke="currentColor" {_WB} {_CAP}/>')
    label = _name(x + w // 2, y - 7, e["var"]) if e["var"] else ""
    return _grp(e["id"], "contact", "".join(s), (x, y - 4, w, h + 8)) + label


def _coil(e):
    # clean bare IEC symbol: leads + two arcs ( )
    x, y, w, h = e["x"], e["y"], e["w"] or 30, e["h"] or 20
    cy = y + h // 2
    lx, rx = x + 8, x + w - 8
    s = [
        f'<line x1="{x}" y1="{cy}" x2="{lx}" y2="{cy}" stroke="currentColor" {_W} {_CAP}/>',
        f'<line x1="{rx}" y1="{cy}" x2="{x+w}" y2="{cy}" stroke="currentColor" {_W} {_CAP}/>',
        f'<path d="M {lx} {y-1} Q {x-2} {cy} {lx} {y+h+1}" fill="none" stroke="currentColor" {_WB} {_CAP}/>',
        f'<path d="M {rx} {y-1} Q {x+w+2} {cy} {rx} {y+h+1}" fill="none" stroke="currentColor" {_WB} {_CAP}/>',
    ]
    if e["negated"]:
        s.append(f'<line x1="{lx}" y1="{y+h}" x2="{rx}" y2="{y}" stroke="currentColor" {_W} {_CAP}/>')
    label = _name(x + w // 2, y - 7, e["var"]) if e["var"] else ""
    return _grp(e["id"], "coil", "".join(s), (x, y - 4, w, h + 8)) + label


def _rail(e):
    x, y, h = e["x"], e["y"], e["h"] or 20
    return f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+h}" stroke="{INK}" stroke-width="3" {_CAP}/>'


def _block(e):
    x, y, w, h = e["x"], e["y"], e["w"] or 90, e["h"] or 100
    s = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#eef1f6" '
        f'stroke="{INK}" stroke-width="1.6"/>',
        f'<rect x="{x}" y="{y}" width="{w}" height="20" rx="6" fill="#e0e4ec" stroke="none"/>',
        f'<rect x="{x}" y="{y+12}" width="{w}" height="8" fill="#e0e4ec" stroke="none"/>',
        f'<line x1="{x}" y1="{y+20}" x2="{x+w}" y2="{y+20}" stroke="{INK}" stroke-width="1"/>',
        f'<text x="{x+w//2}" y="{y+14}" text-anchor="middle" font-size="11.5" '
        f'font-weight="700" fill="{LABEL}" {_FONT}>{_esc(e["btype"])}</text>',
    ]
    for p in e["ports"]:
        px, py = x + p["rx"], y + p["ry"]
        if p["dir"] == "in":
            s.append(f'<line x1="{px-9}" y1="{py}" x2="{px}" y2="{py}" stroke="{INK}" {_W} {_CAP}/>')
            s.append(f'<text x="{px+5}" y="{py+3.5}" font-size="9.5" fill="{LABEL}" {_FONT}>{_esc(p["name"])}</text>')
        else:
            s.append(f'<line x1="{px}" y1="{py}" x2="{px+9}" y2="{py}" stroke="{INK}" {_W} {_CAP}/>')
            s.append(f'<text x="{px-5}" y="{py+3.5}" text-anchor="end" font-size="9.5" fill="{LABEL}" {_FONT}>{_esc(p["name"])}</text>')
    return "".join(s)


def _var_box(e):
    x, y, w, h = e["x"], e["y"], e["w"] or 80, e["h"] or 30
    cy = y + h // 2
    s = []
    if e["kind"] == "invar":
        s.append(f'<line x1="{x+w}" y1="{cy}" x2="{x+w+8}" y2="{cy}" stroke="{INK}" {_W} {_CAP}/>')
    else:
        s.append(f'<line x1="{x-8}" y1="{cy}" x2="{x}" y2="{cy}" stroke="{INK}" {_W} {_CAP}/>')
    s.append(f'<text x="{x+w//2}" y="{cy+4}" text-anchor="middle" font-size="10.5" '
             f'font-weight="600" fill="{ADDR}" {_FONT}>{_esc(e["var"])}</text>')
    return "".join(s)


def render_network_svg(net):
    pad, top = 14, 24
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
    scale = 1.3
    return (f'<svg class="ld" viewBox="{-pad} {-top} {vb_w} {vb_h}" '
            f'width="{int(vb_w * scale)}" height="{int(vb_h * scale)}" '
            f'xmlns="http://www.w3.org/2000/svg">{inner}</svg>')


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
  .nbody{padding:16px 16px 20px;min-height:150px;overflow:auto;background:
    radial-gradient(circle, #d7dae1 1px, transparent 1px); background-size:16px 16px;}
  .network.collapsed .nbody, .network.collapsed .ncomment,
  .network.collapsed .resizer{display:none;}
  .resizer{height:9px;cursor:ns-resize;position:relative;border-bottom:1px solid var(--line);}
  .resizer::after{content:"";position:absolute;left:50%;bottom:2px;width:36px;height:3px;
    border-radius:2px;background:var(--line);transform:translateX(-50%);}
  .resizer:hover::after{background:var(--accent);}
  svg.ld{display:block;}
  .el{color:#1c1e24;cursor:pointer;}
  .el:hover{color:var(--accent);}
  .el.sel{color:var(--accent);}
  .el.sel .selbox{display:block;}
  .empty{color:var(--dim);text-align:center;padding:40px;}
</style></head><body><div id="root"></div>
<script>
  if(!window._h){window._h={};}   // user-set network body heights, by index
  if(!window._c){window._c={};}   // collapsed state, by index
  function esc(s){return (s==null?'':(''+s)).replace(/[&<>]/g,function(c){return ({'&':'&amp;','<':'&lt;','>':'&gt;'})[c];});}
  function post(m){try{window.bridge.postMessage(JSON.stringify(m));}catch(e){}}
  function bindHandlers(r){
    var els=r.querySelectorAll('.el');
    for(var k=0;k<els.length;k++){
      els[k].addEventListener('click',function(e){
        e.stopPropagation();
        var was=this.classList.contains('sel');
        var all=document.querySelectorAll('.el.sel');
        for(var m=0;m<all.length;m++){all[m].classList.remove('sel');}
        if(!was){this.classList.add('sel');}
        post({type:'select',id:+this.getAttribute('data-id'),kind:this.getAttribute('data-kind')});
      });
      els[k].addEventListener('dblclick',function(e){
        e.stopPropagation();
        if(this.getAttribute('data-kind')==='contact'){
          post({type:'toggle_neg',id:+this.getAttribute('data-id')});
        }
      });
    }
    var heads=r.querySelectorAll('.nhead');
    for(var i=0;i<heads.length;i++){
      heads[i].addEventListener('click',function(){
        var net=this.parentNode; net.classList.toggle('collapsed');
        window._c[net.getAttribute('data-i')]=net.classList.contains('collapsed');
      });
    }
    var grips=r.querySelectorAll('.resizer');
    for(var j=0;j<grips.length;j++){
      grips[j].addEventListener('mousedown',function(e){
        e.preventDefault();
        var net=this.parentNode, body=net.querySelector('.nbody');
        var startY=e.clientY, startH=body.offsetHeight, key=net.getAttribute('data-i');
        body.style.minHeight='0';
        function mv(ev){var nh=Math.max(50,startH+(ev.clientY-startY));
          body.style.height=nh+'px'; window._h[key]=nh;}
        function up(){document.removeEventListener('mousemove',mv);
          document.removeEventListener('mouseup',up); document.body.style.userSelect='';}
        document.body.style.userSelect='none';
        document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
      });
    }
  }
  function render(state){
    var r=document.getElementById('root');
    try{
      if(!state||!state.networks||!state.networks.length){
        r.innerHTML='<div id="title">'+esc((state&&state.block)||'(block)')+'</div>'+
          '<div class="empty">No networks. Ask the PLC Agent to add ladder logic.</div>';
        return;
      }
      var h='<div id="title">'+esc(state.block)+'<span class="cmt">'+esc(state.comment||'')+'</span></div>';
      for(var i=0;i<state.networks.length;i++){
        var n=state.networks[i];
        var coll=window._c[n.index]?' collapsed':'';
        var hh=window._h[n.index];
        var st=hh?(' style="height:'+hh+'px;min-height:0"'):'';
        h+='<div class="network'+coll+'" data-i="'+n.index+'"><div class="nhead"><span class="tab"></span>'+
           '<span class="ttl">Network '+(n.index+1)+'</span>'+
           (n.title?'<span class="name">'+esc(n.title)+'</span>':'')+
           '<span class="chev">&#9662;</span></div>'+
           '<div class="ncomment">'+(n.comment?esc(n.comment):'Comment')+'</div>'+
           '<div class="nbody"'+st+'>'+(n.svg||'')+'</div>'+
           '<div class="resizer"></div></div>';
      }
      r.innerHTML=h;
      bindHandlers(r);
    }catch(err){
      r.innerHTML='<div id="title">render error</div>'+
        '<pre style="color:#b00020;padding:12px;white-space:pre-wrap">'+esc(''+err)+'</pre>';
    }
  }
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
        try:
            self.webview.AddScriptMessageHandler("bridge")
        except Exception:
            pass
        self.webview.Bind(wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, self._on_msg)
        self.webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, self._on_loaded)
        self.webview.SetPage(HEAD, "")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.webview, 1, wx.EXPAND)
        self.SetSizer(sizer)

        # Don't depend solely on EVT_WEBVIEW_LOADED (unreliable on WKWebView):
        # mark ready after a short delay as a fallback.
        wx.CallLater(700, self._force_ready)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda e: self.RefreshView(), self._timer)
        self._timer.Start(1500)

    # ---- rendering ----
    def _force_ready(self):
        self._ready = True
        self._last_json = None   # DOM may have reset → force a render
        self.RefreshView()

    def _on_loaded(self, _e):
        # WKWebView can fire LOADED twice (about:blank then content); each load
        # resets the DOM, so always force a re-render.
        self._ready = True
        self._last_json = None
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

    def _get_ld(self):
        block = self._pou_name()
        project = self.Controler.GetProject() if hasattr(self.Controler, "GetProject") else getattr(self.Controler, "Project", None)
        pou = project.getpou(block) if project is not None else None
        if pou is None:
            return None
        body = pou.getbody()
        if isinstance(body, list):
            body = body[0] if body else None
        return body.getcontent() if body is not None else None

    def _on_msg(self, evt):
        import json
        try:
            msg = json.loads(evt.GetString())
        except Exception:
            return
        if msg.get("type") == "toggle_neg":
            self._toggle_negated(msg.get("id"))

    def _toggle_negated(self, eid):
        if eid is None:
            return
        try:
            ld = self._get_ld()
            if ld is None:
                return
            for el in ld:
                tag = (getattr(el, "tag", "") or "").split("}")[-1]
                if tag in ("contact", "coil") and el.getlocalId() == eid:
                    el.setnegated(not bool(el.getnegated()))
                    break
            else:
                return
            try:
                self.Controler.BufferProject()
            except Exception:
                pass
            self._last_json = None
            self.RefreshView()
        except Exception as exc:
            print("[ld] toggle failed: %r" % exc, file=sys.stderr)

    def RefreshView(self, *a, **k):
        if not self._ready:
            return
        try:
            data = self._gather()
        except Exception as exc:
            print("[ld] _gather raised: %r" % exc, file=sys.stderr)
            return
        if data == getattr(self, "_last_json", None):
            return   # unchanged → keep DOM (preserve resize/collapse state)
        self._last_json = data
        try:
            self.webview.RunScript("try{render(" + data + ")}catch(e){document.body.innerHTML='<pre>'+e+'</pre>'}")
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
