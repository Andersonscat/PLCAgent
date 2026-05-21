"""HMIPanel — embedded browser pane that renders the running project's
SVG HMI (or any URL/HTML we feed it).

Lives as an AUI dock pane in IDEFrame, alongside the chat panel. When the
agent starts a simulation that has SVG HMI configured, the WebView is
pointed at Beremiz's HMI HTTP/WebSocket endpoint and the elevator (or
whatever the SVG depicts) animates in real time from PLC variable values.
"""

import sys
import wx
import wx.html2


PLACEHOLDER_HTML = """<!doctype html>
<html><head><meta charset='utf-8'><title>HMI</title>
<style>
 body { margin:0; background:#1e1e22; color:#cfcfcf;
        font-family:-apple-system,Helvetica,Arial,sans-serif;
        display:flex; align-items:center; justify-content:center;
        height:100vh; text-align:center; }
 .box { max-width:380px; }
 h2 { font-weight:500; margin:0 0 12px; color:#8ce0a0; }
 p  { font-size:13px; line-height:1.5; color:#9c9c9c; }
 code { background:#2a2a30; padding:2px 6px; border-radius:3px;
        color:#dcb87a; font-size:12px; }
</style></head><body><div class='box'>
<h2>AI HMI</h2>
<p>This panel shows the project's SVG HMI once the simulation is running.</p>
<p>Ask the agent to <code>start_simulation</code> with an SVG HMI configured,
   or load any URL via the dev bar above.</p>
</div></body></html>"""


class HMIPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)

        # Dev URL bar — useful during integration, can be hidden later.
        self.url_input = wx.TextCtrl(self, value="", style=wx.TE_PROCESS_ENTER)
        self.url_input.SetHint("http://localhost:8008  (or any URL/file://)")
        self.url_input.Bind(wx.EVT_TEXT_ENTER, self._on_url_enter)
        self.go_btn = wx.Button(self, label="Go", size=(48, -1))
        self.go_btn.Bind(wx.EVT_BUTTON, self._on_url_enter)
        self.reload_btn = wx.Button(self, label="⟳", size=(36, -1))
        self.reload_btn.Bind(wx.EVT_BUTTON, lambda _e: self.webview.Reload())

        try:
            self.webview = wx.html2.WebView.New(self)
        except Exception as exc:
            self.webview = None
            print(f"[plc-cursor] WebView init failed: {exc}", file=sys.stderr)

        sizer = wx.BoxSizer(wx.VERTICAL)
        bar = wx.BoxSizer(wx.HORIZONTAL)
        bar.Add(self.url_input, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=2)
        bar.Add(self.go_btn, flag=wx.RIGHT, border=2)
        bar.Add(self.reload_btn)
        sizer.Add(bar, flag=wx.EXPAND | wx.ALL, border=2)
        if self.webview is not None:
            sizer.Add(self.webview, proportion=1, flag=wx.EXPAND)
        else:
            err = wx.StaticText(self, label="wx.html2.WebView unavailable on this system.")
            sizer.Add(err, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        self.SetSizer(sizer)

        self.show_placeholder()
        print("[plc-cursor] HMI panel loaded", file=sys.stderr)

    # ---- public API used by chat / agent / start_simulation hook --------

    def show_placeholder(self):
        if self.webview is not None:
            self.webview.SetPage(PLACEHOLDER_HTML, "")

    def load_url(self, url):
        if self.webview is None:
            return
        self.url_input.SetValue(url)
        self.webview.LoadURL(url)

    def load_html(self, html, base_url=""):
        if self.webview is not None:
            self.webview.SetPage(html, base_url)

    # ---- TabsOpened (Beremiz editor notebook) compatibility -----------
    # When HMIPanel lives as a page in self.TabsOpened, Beremiz's event
    # handlers call these methods expecting an EditorPanel-like object.
    # We return safe defaults so the IDE keeps working when the HMI tab
    # is selected.

    HMI_TAGNAME = "@HMI"

    def IsDebugging(self):
        return False

    def IsModified(self):
        return False

    def ResetBuffer(self):
        pass

    def CheckSaveBeforeClosing(self, _title=None):
        return True

    def GetTagName(self):
        return self.HMI_TAGNAME

    def SetTagName(self, _tagname):
        pass

    def RefreshView(self, **_kwargs):
        pass

    def Find(self, _direction, _params):
        pass

    def GetInstancePath(self):
        return ""

    def GetBufferState(self):
        # (can_undo, can_redo) — no buffer for the HMI tab.
        return (False, False)

    def HasNoModel(self):
        # Don't get auto-closed by CloseTabsWithoutModel.
        return False

    def Undo(self):
        pass

    def Redo(self):
        pass

    def Save(self):
        pass

    def SaveAs(self):
        pass

    def GetConfNodeMenuItems(self):
        return []

    def SetMode(self, _mode):
        pass

    def GetMode(self):
        return 0

    def __getattr__(self, name):
        # Beremiz refreshes Edit menu / toolbar by calling many methods on
        # whatever the current TabsOpened page is, assuming EditorPanel API.
        # Rather than enumerate every single one (Search/Find/Replace, debug
        # navigation, breakpoints, etc.) and crash one at a time, return a
        # safe no-op for any unknown attribute. Real wx.Panel methods take
        # precedence (this only fires on AttributeError from normal lookup).
        if name.startswith("__") and name.endswith("__"):
            # Don't swallow dunder lookups — they're framework-internal.
            raise AttributeError(name)

        def _noop(*_args, **_kwargs):
            return None
        return _noop

    def load_for_running_sim(self, project_controller):
        """Auto-discover the SVG HMI URL from the running project and
        load it. Falls back to common defaults so the user can still
        try a URL if confnode introspection misses."""
        url = _discover_svghmi_url(project_controller)
        if url:
            self.load_url(url)
            return url
        self.load_html(_NO_HMI_HTML, "")
        return None

    # ---- internal -------------------------------------------------------

    def _on_url_enter(self, _event):
        url = self.url_input.GetValue().strip()
        if url:
            self.webview.LoadURL(url)


_NO_HMI_HTML = """<!doctype html><html><head><style>
 body{margin:0;background:#1e1e22;color:#cfcfcf;font-family:-apple-system,Helvetica,Arial,sans-serif;
      display:flex;align-items:center;justify-content:center;height:100vh;text-align:center}
 .box{max-width:420px} h2{color:#e0bd6c;font-weight:500} p{font-size:13px;color:#9c9c9c;line-height:1.5}
 code{background:#2a2a30;padding:2px 6px;border-radius:3px;color:#dcb87a;font-size:12px}
</style></head><body><div class='box'>
<h2>No SVG HMI in this project</h2>
<p>Add an SVG HMI confnode to a Resource (right-click <code>Res0 → Add → SVGHMI</code>),
   put your SVG file in the resulting <code>name@svghmi/</code> folder,
   then run the simulation again.</p>
<p>Or type a URL above to load any page (e.g. <code>http://localhost:8008/svghmi</code>).</p>
</div></body></html>"""


def _discover_svghmi_url(ctr):
    """Walk the ProjectController's child confnode tree looking for SVGHMI
    nodes. Returns the first URL found, or None if none configured."""
    if ctr is None:
        return None
    try:
        children = ctr.IterChildren() if hasattr(ctr, "IterChildren") else []
    except Exception:
        children = []
    return _find_svghmi_recursive(children)


def _find_svghmi_recursive(children):
    for child in children:
        cls = type(child).__name__
        if cls == "SVGHMI" and hasattr(child, "get_SVGHMI_options"):
            try:
                opts = child.get_SVGHMI_options()
                return opts.get("url")
            except Exception:
                pass
        if hasattr(child, "IterChildren"):
            try:
                url = _find_svghmi_recursive(child.IterChildren())
                if url:
                    return url
            except Exception:
                pass
    return None
