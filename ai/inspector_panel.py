"""inspector_panel — unified TIA-Portal-style bottom inspector, rendered as a
single light HTML WebView with its own flat tab bar (no AUI folder tabs, no
native wx widgets). One panel, three sections:

  Properties — General | IO tags | System constants | Texts
  Info       — compile / build messages and project-search results (the log
               text is teed in from the IDE's LogPseudoFile; search results
               are pushed from the IDE's search)
  Diagnostics— online / run state of the PLC

Properties + Diagnostics are refreshed by polling the project controller a
couple times a second; Info is push-driven via append_log()/set_search().
"""

import json
import sys

import wx
import wx.html2


UNIFIED_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><style>
  :root {
    --bg: #f6f7f9; --bg-elev: #ffffff; --line: #d2d5dc; --line-soft: #e8eaee;
    --ink: #20222a; --ink-2: #4a4d56; --dim: #8a8d96; --accent: #de8c1e;
    --head: #eef0f3; --row-alt: #f4f5f7; --ok: #2e9e44; --err: #c8392b;
    --warn: #b9791a;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--ink);
    font: 12.5px/1.5 -apple-system, "SF Pro Text", "Segoe UI", Helvetica, sans-serif;
    -webkit-font-smoothing: antialiased; }
  #app { display: flex; flex-direction: column; height: 100vh; }

  /* flat top tab bar */
  #tabs { display: flex; align-items: stretch; gap: 0; background: var(--bg);
    border-bottom: 1px solid var(--line); padding: 0 6px; flex: 0 0 auto; }
  .tab { padding: 9px 16px 8px; font-size: 12.5px; color: var(--dim);
    cursor: pointer; user-select: none; border-bottom: 2px solid transparent;
    margin-bottom: -1px; }
  .tab:hover { color: var(--ink-2); }
  .tab.active { color: var(--ink); font-weight: 600; border-bottom-color: var(--accent); }
  .tab .badge { margin-left: 6px; font-size: 10px; font-weight: 600;
    background: var(--err); color: #fff; border-radius: 8px; padding: 0 5px; }

  /* sub-tabs (Properties) */
  #subtabs { display: flex; gap: 2px; padding: 6px 10px 0; background: var(--bg);
    border-bottom: 1px solid var(--line-soft); flex: 0 0 auto; }
  .subtab { padding: 4px 11px; font-size: 11.5px; color: var(--ink-2); cursor: pointer;
    border: 1px solid transparent; border-bottom: none; border-radius: 6px 6px 0 0; }
  .subtab:hover { background: var(--bg-elev); }
  .subtab.active { background: var(--bg-elev); color: var(--ink); font-weight: 600;
    border-color: var(--line-soft); position: relative; top: 1px; }

  #scroll { flex: 1; overflow: auto; }
  .pad { padding: 10px 14px; }

  .form-row { display: flex; gap: 10px; padding: 4px 0; }
  .form-row .k { color: var(--dim); min-width: 140px; }
  .form-row .v { color: var(--ink); font-weight: 500; }

  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; background: var(--head); color: var(--ink-2); font-weight: 600;
    padding: 6px 10px; border: 1px solid var(--line); position: sticky; top: 0; }
  td { padding: 5px 10px; border: 1px solid var(--line-soft); }
  tr:nth-child(even) td { background: var(--row-alt); }
  td.addr { font-family: ui-monospace, monospace; color: var(--accent); }
  td.type { font-family: ui-monospace, monospace; color: var(--ink-2); }

  .empty { color: var(--dim); padding: 30px 8px; text-align: center; }

  /* Info log */
  #infolog { font: 12px/1.55 ui-monospace, "SF Mono", Menlo, monospace;
    padding: 8px 12px; white-space: pre-wrap; word-break: break-word; }
  .logline { padding: 1px 0; color: var(--ink-2); }
  .logline.err { color: var(--err); }
  .logline.warn { color: var(--warn); }
  .search-block { padding: 8px 12px; border-bottom: 1px solid var(--line-soft); }
  .search-block h4 { margin: 0 0 6px; font-size: 11px; text-transform: uppercase;
    letter-spacing: .6px; color: var(--dim); font-weight: 600; }
  .hit { padding: 4px 8px; border-radius: 6px; cursor: pointer; }
  .hit:hover { background: var(--bg-elev); }
  .hit .where { color: var(--accent); font-weight: 600; }
  .hit .txt { color: var(--ink-2); font-family: ui-monospace, monospace; }

  .led { display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    margin-right: 7px; vertical-align: middle; }
  .led.on { background: var(--ok); } .led.off { background: #b9bcc4; }
</style></head><body>
<div id="app">
  <div id="tabs">
    <div class="tab active" data-t="properties">Properties</div>
    <div class="tab" data-t="info">Info <span class="badge" id="infoBadge" style="display:none"></span></div>
    <div class="tab" data-t="diagnostics">Diagnostics</div>
  </div>
  <div id="subtabs" style="display:none">
    <div class="subtab active" data-s="general">General</div>
    <div class="subtab" data-s="iotags">IO tags</div>
    <div class="subtab" data-s="sysconst">System constants</div>
    <div class="subtab" data-s="texts">Texts</div>
  </div>
  <div id="scroll"><div class="pad"><div class="empty">No project open.</div></div></div>
</div>
<script>
  let STATE = null, TAB = "properties", SUB = "general";
  let SEARCH = null, LOG = [];
  const $ = id => document.getElementById(id);
  const scrollBox = $("scroll");
  function esc(s){ return (s==null?"":(""+s)).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

  document.querySelectorAll(".tab").forEach(el => el.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    el.classList.add("active"); TAB = el.dataset.t;
    $("subtabs").style.display = (TAB === "properties") ? "flex" : "none";
    draw();
  }));
  document.querySelectorAll(".subtab").forEach(el => el.addEventListener("click", () => {
    document.querySelectorAll(".subtab").forEach(t => t.classList.remove("active"));
    el.classList.add("active"); SUB = el.dataset.s; draw();
  }));

  function drawProperties(){
    if (!STATE){ return '<div class="empty">No project open.</div>'; }
    if (SUB === "general"){
      const g = STATE.general || {};
      return '<div class="pad">'+
        row("Project", g.project)+ row("Selected block", g.pou || "—")+
        row("Type", g.pou_type || "—")+ row("Language", g.lang || "—")+
        row("Program blocks", g.pou_count)+ row("Tags (variables)", g.var_count)+
        '</div>';
    }
    if (SUB === "iotags"){
      const rows = STATE.iotags || [];
      if (!rows.length) return '<div class="empty">No tags declared.</div>';
      let h = '<table><thead><tr><th>Name</th><th>Type</th><th>Address</th><th>Tag table</th><th>Comment</th></tr></thead><tbody>';
      for (const r of rows)
        h += '<tr><td>'+esc(r.name)+'</td><td class="type">'+esc(r.type)+'</td><td class="addr">'+esc(r.address||'')+
             '</td><td>'+esc(r.table||'Default tag table')+'</td><td>'+esc(r.comment||'')+'</td></tr>';
      return h + '</tbody></table>';
    }
    if (SUB === "sysconst"){
      const rows = STATE.sysconst || [];
      if (!rows.length) return '<div class="empty">No system constants.</div>';
      let h = '<table><thead><tr><th>Name</th><th>Type</th><th>Value</th></tr></thead><tbody>';
      for (const r of rows) h += '<tr><td>'+esc(r.name)+'</td><td class="type">'+esc(r.type)+'</td><td>'+esc(r.value)+'</td></tr>';
      return h + '</tbody></table>';
    }
    return '<div class="empty">No project texts.</div>';
  }
  function row(k, v){ return '<div class="form-row"><div class="k">'+esc(k)+'</div><div class="v">'+esc(v)+'</div></div>'; }

  function drawInfo(){
    let h = '';
    if (SEARCH && SEARCH.length){
      h += '<div class="search-block"><h4>Search results</h4>';
      for (const s of SEARCH)
        h += '<div class="hit"><span class="where">'+esc(s.where)+'</span> &nbsp;<span class="txt">'+esc(s.text)+'</span></div>';
      h += '</div>';
    }
    if (LOG.length){
      h += '<div id="infolog">';
      for (const l of LOG) h += '<div class="logline '+esc(l.lvl||'')+'">'+esc(l.text)+'</div>';
      h += '</div>';
    }
    if (!h) h = '<div class="empty">No messages. Compile or search to see output here.</div>';
    return h;
  }

  function drawDiagnostics(){
    const d = STATE && STATE.diag;
    if (!d) return '<div class="empty">No project open.</div>';
    return '<div class="pad">'+
      '<div class="form-row"><div class="k">Connection</div><div class="v"><span class="led '+(d.online?'on':'off')+'"></span>'+(d.online?'Online':'Offline')+'</div></div>'+
      '<div class="form-row"><div class="k">Operating mode</div><div class="v"><span class="led '+(d.running?'on':'off')+'"></span>'+esc(d.mode||'STOP')+'</div></div>'+
      '<div class="form-row"><div class="k">Target</div><div class="v">'+esc(d.target||'—')+'</div></div>'+
      '<div class="form-row"><div class="k">Status</div><div class="v">'+esc(d.status||'—')+'</div></div>'+
      '</div>';
  }

  function draw(){
    let html;
    if (TAB === "properties") html = drawProperties();
    else if (TAB === "info") html = drawInfo();
    else html = drawDiagnostics();
    scrollBox.innerHTML = html;
    if (TAB === "info"){ const il = $("infolog"); if (il) scrollBox.scrollTop = scrollBox.scrollHeight; }
  }

  // ---- host API ----
  function render(state){ STATE = state; if (TAB !== "info") draw(); else draw(); }
  function appendLog(text, lvl){
    for (const ln of (""+text).split("\n")) { if (ln.length) LOG.push({text: ln, lvl: lvl||''}); }
    if (LOG.length > 2000) LOG = LOG.slice(-2000);
    if (lvl === "err") { const b=$("infoBadge"); b.style.display='inline-block'; b.textContent=(parseInt(b.textContent||"0")||0)+1; }
    if (TAB === "info") draw();
  }
  function clearLog(){ LOG = []; SEARCH = null; const b=$("infoBadge"); b.style.display='none'; b.textContent=''; if (TAB==="info") draw(); }
  function setSearch(items){ SEARCH = items || []; TAB = "info";
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.t==="info"));
    $("subtabs").style.display = "none"; draw(); }
</script></body></html>"""


class UnifiedInspectorPanel(wx.Panel):
    """Single bottom inspector: Properties | Info | Diagnostics (all HTML)."""

    def __init__(self, parent, project_controller_getter, active_pou_getter=None):
        super().__init__(parent)
        self._get_ctr = project_controller_getter
        self._get_active_pou = active_pou_getter
        self._ready = False
        self._last_json = None
        self._pending = []   # log lines queued before the page is ready
        self.SetBackgroundColour(wx.Colour(246, 247, 249))

        self.webview = wx.html2.WebView.New(self)
        self.webview.EnableContextMenu(False)
        self.webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, self._on_loaded)
        self.webview.SetPage(UNIFIED_HTML, "")

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.webview, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._refresh, self._timer)
        self._timer.Start(1500)

    # ---- lifecycle ----
    def _on_loaded(self, _e):
        self._ready = True
        for text, lvl in self._pending:
            self._run(f"appendLog({json.dumps(text)},{json.dumps(lvl)})")
        self._pending = []
        self._refresh()

    def _run(self, script):
        # Wrap in JS try/catch: EVT_WEBVIEW_LOADED can fire before the page's
        # script has defined render()/appendLog() (WKWebView race), and an
        # unguarded call would raise a "Can't find variable" error dialog. The
        # next poll tick re-renders once the page is ready.
        try:
            self.webview.RunScript("try{" + script + "}catch(e){}")
        except Exception:
            pass

    # ---- properties + diagnostics polling ----
    def _refresh(self, _e=None):
        try:
            state = self._gather()
        except Exception as exc:
            state = None
            print(f"[inspector] gather failed: {exc}", file=sys.stderr)
        if not self._ready:
            return
        payload = json.dumps(state)
        if payload == self._last_json:
            return
        self._last_json = payload
        self._run(f"render({payload})")

    def force_refresh(self):
        self._refresh()

    # ---- Info: push API ----
    def append_log(self, text, style=None):
        if not text:
            return
        lvl = ""
        if style == 1:               # LogPseudoFile red_white = warning
            lvl = "warn"
        elif style == 2:             # red_yellow = error
            lvl = "err"
        if not self._ready:
            self._pending.append((text, lvl))
            return
        self._run(f"appendLog({json.dumps(text)},{json.dumps(lvl)})")

    def clear_log(self):
        if self._ready:
            self._run("clearLog()")

    def set_search(self, items):
        if self._ready:
            self._run(f"setSearch({json.dumps(items)})")

    def show_info(self):
        if self._ready:
            self._run("document.querySelector('.tab[data-t=\"info\"]').click()")

    # ---- data ----
    def _gather(self):
        ctr = self._get_ctr()
        if ctr is None:
            return None
        project = ctr.GetProject() if hasattr(ctr, "GetProject") else getattr(ctr, "Project", None)
        pou_names = []
        try:
            pou_names = list(ctr.GetProjectPouNames())
        except Exception:
            pass
        active = None
        if self._get_active_pou:
            try:
                active = self._get_active_pou()
            except Exception:
                active = None
        if active is None and pou_names:
            active = pou_names[0]
        pou_type = lang = None
        if active:
            try:
                pou_type = ctr.GetPouType(active)
            except Exception:
                pass
            try:
                lang = ctr.GetPouBodyType(active)
            except Exception:
                pass
        iotags = self._collect_tags(ctr, project, pou_names)
        general = {
            "project": (ctr.GetProjectName() if hasattr(ctr, "GetProjectName") else None) or "(unnamed)",
            "pou": active, "pou_type": pou_type, "lang": lang,
            "pou_count": len(pou_names), "var_count": len(iotags),
        }
        return {"general": general, "iotags": iotags, "sysconst": [],
                "diag": self._diag(ctr)}

    def _collect_tags(self, ctr, project, pou_names):
        tags = []
        if project is None:
            return tags
        scope_ok = {"inputVars", "outputVars", "localVars", "inOutVars", "externalVars"}
        for name in pou_names:
            try:
                pou = project.getpou(name)
            except Exception:
                pou = None
            if pou is None:
                continue
            try:
                iface = pou.getinterface()
            except Exception:
                iface = None
            if iface is None:
                continue
            for block in iface.iter():
                if (getattr(block, "tag", "") or "").split("}")[-1] not in scope_ok:
                    continue
                for v_el in block.iter():
                    if (getattr(v_el, "tag", "") or "").split("}")[-1] != "variable":
                        continue
                    vtype = "?"
                    type_el = v_el.find("{*}type") if hasattr(v_el, "find") else None
                    if type_el is not None and len(type_el):
                        first = type_el[0]
                        tname = (getattr(first, "tag", "") or "").split("}")[-1]
                        vtype = (first.get("name") or "derived") if tname == "derived" else (tname or "?")
                    tags.append({
                        "name": v_el.get("name") or "", "type": vtype,
                        "address": v_el.get("address") or "", "comment": "",
                        "table": "Default tag table",
                    })
        return tags

    def _diag(self, ctr):
        online = running = False
        mode, status = "STOP", "—"
        try:
            st = ctr.GetPLCStatus() if hasattr(ctr, "GetPLCStatus") else None
            if st:
                status = str(st)
                running = status.lower() in ("started", "running")
                online = status.lower() not in ("disconnected", "", "none")
                mode = "RUN" if running else "STOP"
        except Exception:
            pass
        target = "—"
        try:
            target = ctr.GetProjectName() or "—"
        except Exception:
            pass
        return {"online": online, "running": running, "mode": mode,
                "target": target, "status": status}
