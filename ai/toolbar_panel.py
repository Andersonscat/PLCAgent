"""toolbar_panel — fully custom HTML toolbar (WebView), replacing the native
wx.ToolBar (which on macOS fights us on the bottom divider, icon colour, label
colour and button sizing).

A compact, modern, light engineering toolbar: grouped icon buttons with hover
states and tooltips + an inline project search. Clicking a button posts
{action: "..."} to the host over the `bridge` script-message channel; the IDE
maps the action to a frame handler or a ProjectController method.
"""

import json
import sys

import wx
import wx.html2

from ai.toolbar_icons import _ICONS, _COLORED, _FILLED


# Toolbar layout: list of groups; each item = (action, icon, label, tooltip).
GROUPS = [
    [("new", "tool_new", "New", "New project"),
     ("open", "tool_open", "Open", "Open project"),
     ("save", "tool_save", "Save", "Save"),
     ("print", "tool_print", "Print", "Print")],
    [("cut", "tool_cut", "Cut", "Cut"),
     ("copy", "tool_copy", "Copy", "Copy"),
     ("paste", "tool_paste", "Paste", "Paste"),
     ("delete", "tool_delete", "Delete", "Delete")],
    [("undo", "tool_undo", "Undo", "Undo"),
     ("redo", "tool_redo", "Redo", "Redo")],
    [("build", "tool_verify", "Verify", "Compile / verify"),
     ("clean", "tool_clean", "Clean", "Clean build"),
     ("ieccode", "tool_ieccode", "IEC", "Show generated IEC code")],
    [("connect", "tool_online", "Online", "Go online"),
     ("transfer", "tool_download", "Download", "Download to PLC"),
     ("run", "tool_run", "Run", "Run (simulate)"),
     ("stop", "tool_stop", "Stop", "Stop"),
     ("disconnect", "tool_offline", "Offline", "Go offline")],
    [("generate", "tool_generate", "Generate", "Generate for OpenPLC Runtime"),
     ("upload", "tool_upload", "Upload", "Upload to Arduino PLC")],
    [("debug", "tool_debug", "Debug", "Live debug")],
]


def _svg(icon, size=18):
    inner = _ICONS.get(icon, "")
    color = _COLORED.get(icon, "#3A3D45")
    filled = icon in _FILLED
    fill = color if filled else "none"
    stroke = "none" if filled else color
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{inner}</svg>')


def _build_html():
    btns = []
    for gi, group in enumerate(GROUPS):
        if gi:
            btns.append('<div class="sep"></div>')
        for action, icon, label, tip in group:
            btns.append(
                f'<button class="tb" data-a="{action}" title="{tip}">'
                f'<span class="ic">{_svg(icon)}</span>'
                f'<span class="lb">{label}</span></button>')
    buttons_html = "".join(btns)
    return r"""<!doctype html><html><head><meta charset="utf-8"><style>
  :root { --bg:#E2E5EA; --ink:#3A3D45; --dim:#5b5e66; --hover:#d3d7de; --line:#c6cad2; }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--bg); overflow:hidden;
    font:12px -apple-system,"SF Pro Text","Segoe UI",sans-serif; -webkit-user-select:none; }
  #bar { display:flex; align-items:center; height:100%; padding:0 8px; gap:0; }
  .tb { display:flex; flex-direction:column; align-items:center; justify-content:center;
    gap:2px; min-width:44px; height:42px; border:0; background:transparent;
    border-radius:7px; cursor:pointer; padding:3px 5px; transition:background .1s; }
  .tb .ic { display:flex; align-items:center; justify-content:center; height:18px; }
  .tb .lb { font-size:9.5px; color:var(--dim); white-space:nowrap; line-height:1; }
  .tb:hover { background:var(--hover); }
  .tb:hover .lb { color:var(--ink); }
  .tb:active { transform:scale(.94); }
  .sep { width:1px; height:26px; background:var(--line); margin:0 6px; flex:0 0 auto; }
  #search { margin-left:auto; display:flex; align-items:center; gap:6px;
    background:#fff; border:1px solid var(--line); border-radius:7px; padding:5px 10px;
    min-width:190px; }
  #search:focus-within { border-color:#de8c1e; }
  #search svg { flex:0 0 13px; }
  #search input { border:0; outline:0; background:transparent; font-size:12.5px;
    color:#20222a; width:100%; }
  #search input::placeholder { color:#8a8d96; }
</style></head><body>
  <div id="bar">""" + buttons_html + r"""
    <div id="search">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#8a8d96" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input id="q" placeholder="Search in project" />
    </div>
  </div>
<script>
  function post(m){ try{ window.bridge.postMessage(JSON.stringify(m)); }catch(e){} }
  document.querySelectorAll(".tb").forEach(b =>
    b.addEventListener("click", () => post({action: b.dataset.a})));
  const q = document.getElementById("q");
  q.addEventListener("keydown", e => {
    if (e.key === "Enter" && q.value.trim()) post({action:"search", q:q.value.trim()});
  });
  function setEnabled(map){
    document.querySelectorAll(".tb").forEach(b => {
      const on = map[b.dataset.a];
      b.style.opacity = (on === false) ? .35 : 1;
      b.style.pointerEvents = (on === false) ? "none" : "auto";
    });
  }
</script></body></html>"""


class ToolbarPanel(wx.Panel):
    """Custom HTML engineering toolbar. `on_action(action, payload)` is called
    on the main thread when a button is clicked or a search is submitted."""

    HEIGHT = 52

    def __init__(self, parent, on_action):
        super().__init__(parent)
        self._on_action = on_action
        self.SetBackgroundColour(wx.Colour(226, 229, 234))
        self.SetMinSize(wx.Size(-1, self.HEIGHT))
        self.SetMaxSize(wx.Size(-1, self.HEIGHT))

        self.webview = wx.html2.WebView.New(self)
        self.webview.EnableContextMenu(False)
        try:
            self.webview.AddScriptMessageHandler("bridge")
        except Exception:
            pass
        self.webview.Bind(wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, self._on_msg)
        self.webview.SetPage(_build_html(), "")

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.webview, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def _on_msg(self, event):
        try:
            msg = json.loads(event.GetString())
        except Exception:
            return
        action = msg.get("action")
        if not action:
            return
        try:
            self._on_action(action, msg)
        except Exception as exc:
            print(f"[toolbar] action {action!r} failed: {exc}", file=sys.stderr)
