"""ChatPanel — single WebView chat with the input embedded inside the HTML
so the whole panel can be styled top-to-bottom (no native text-input chrome
showing through). JS posts user messages back to Python via WebView's
script message handler. Python pushes assistant text + tool events into
the page via RunScript.
"""

import json
import sys
import threading

import wx
import wx.html2

from ai.agent import Agent
from ai.tools import Tools
from ai.sim_bridge import Bridge, BRIDGE_HOST, BRIDGE_PORT, load_elevator_page
from ai.hmi_autogen import auto_generate as auto_generate_hmi

print("[plc-cursor] AI chat panel loaded", file=sys.stderr)


ELEVATOR_VAR_MAP = {
    "CarPosition":  "car_position",
    "MotorUp":      "motor_up",
    "MotorDown":    "motor_down",
    "DoorOpen":     "door_open",
    "AtFloor1":     "at_floor_1",
    "AtFloor2":     "at_floor_2",
    "AtFloor3":     "at_floor_3",
    "Request1":     "request1",
    "Request2":     "request2",
    "Request3":     "request3",
}


def _match_elevator_vars(idx_map):
    matched = []
    lowered = {p.split(".")[-1].lower(): p for p in idx_map.keys()}
    for suffix, friendly in ELEVATOR_VAR_MAP.items():
        path = lowered.get(suffix.lower())
        if path:
            matched.append((path, friendly))
    return matched


class _MainThreadTools:
    def __init__(self, real_tools):
        self._real = real_tools
        self.ctr = real_tools.ctr

    def dispatch(self, name, arguments):
        holder = {}
        done = threading.Event()

        def on_main():
            try:
                holder["value"] = self._real.dispatch(name, arguments)
            except Exception as exc:
                holder["value"] = {"error": f"main-thread dispatch raised: {exc}"}
            finally:
                done.set()

        wx.CallAfter(on_main)
        if not done.wait(timeout=180):
            return {"error": "tool dispatch timed out after 180s"}
        return holder["value"]


# ----------------------------------------------------------------------------
# Cursor-inspired chat UI — fully HTML/CSS/JS inside one WebView.
# ----------------------------------------------------------------------------

CHAT_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
 :root {
   --bg: #f6f7f9;
   --bg-elev: #ffffff;
   --bg-input: #ffffff;
   --line: #d2d5dc;
   --line-soft: #e4e6ea;
   --ink: #20222a;
   --ink-2: #4a4d56;
   --dim: #8a8d96;
   --accent: #de8c1e;       /* industrial amber — Siemens-ish (darker for light bg) */
   --accent-dark: #a8650f;
   --ok: #2e9e44;
   --err: #c82828;
   --user-bg: #fbecd6;      /* warm light bubble for user message */
   --user-ink: #5a3d18;
   --user-border: #e6c89a;
 }
 * { box-sizing: border-box; }
 html, body {
   margin: 0; padding: 0; height: 100%; overflow: hidden;
   background: var(--bg); color: var(--ink);
   font: 13.5px/1.5 -apple-system, "SF Pro Text", Helvetica, Arial, sans-serif;
   -webkit-font-smoothing: antialiased;
 }

 /* ===== Top bar ============================================== */
 #topbar {
   display: flex; align-items: center; padding: 8px 12px;
   border-bottom: 1px solid var(--line-soft);
   user-select: none; gap: 10px;
 }
 #topbar .title {
   display: flex; align-items: center; gap: 8px;
   font-weight: 500; font-size: 13.5px; color: var(--ink);
 }
 #topbar .title svg { width: 16px; height: 16px; opacity: .85; }
 #topbar .status {
   display: flex; align-items: center; gap: 6px;
   font-size: 12px; color: var(--dim); flex: 1;
   font-family: ui-monospace, "SF Mono", Menlo, monospace;
 }
 #topbar .status .dot {
   width: 8px; height: 8px; border-radius: 50%;
   background: var(--dim); transition: background .2s;
 }
 #topbar .status.working .dot {
   background: var(--accent);
   animation: pulse 1.1s ease-in-out infinite;
 }
 #topbar .status.working .label { color: var(--accent); }
 @keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .35 } }
 #topbar .actions { display: flex; gap: 4px; }
 #topbar .actions button {
   background: transparent; border: 0; padding: 5px; border-radius: 5px;
   color: var(--ink-2); cursor: pointer; line-height: 0;
 }
 #topbar .actions button:hover { background: var(--bg-elev); color: var(--ink); }
 #topbar .actions svg { width: 14px; height: 14px; }

 /* ===== Layout =============================================== */
 #app { display: flex; flex-direction: column; height: 100vh; }
 #messages {
   flex: 1; overflow-y: auto; padding: 14px 14px 4px 14px;
   scroll-behavior: smooth;
 }
 #composer { padding: 8px 10px 12px 10px; }

 /* ===== Empty state ========================================== */
 .empty {
   color: var(--dim); text-align: center; padding: 16vh 18px 0;
   font-size: 13px;
 }
 .empty .logo {
   width: 42px; height: 42px; margin: 0 auto 16px; border-radius: 11px;
   background: linear-gradient(135deg, var(--accent), var(--accent-dark));
   display: flex; align-items: center; justify-content: center; color: #fff;
   box-shadow: 0 4px 14px rgba(222,140,30,.28);
 }
 .empty .logo svg { width: 22px; height: 22px; }
 .empty h2 { color: var(--ink); font-weight: 600; font-size: 18px;
             margin: 0 0 7px; letter-spacing: -.2px; }
 .empty .sub { font-size: 12.5px; color: var(--dim); margin: 0 auto 24px;
               max-width: 320px; line-height: 1.55; }
 .examples { display: flex; flex-direction: column; gap: 8px;
             max-width: 360px; margin: 0 auto; text-align: left; }
 .examples .lbl { font-size: 10px; letter-spacing: .9px; color: var(--dim);
                  text-transform: uppercase; margin: 0 0 2px 2px; }
 .example {
   display: flex; align-items: center; gap: 11px; padding: 11px 13px;
   background: var(--bg-elev); border: 1px solid var(--line);
   border-radius: 11px; cursor: pointer; font-size: 12.5px; color: var(--ink-2);
   transition: border-color .12s, box-shadow .12s, transform .06s;
 }
 .example:hover { border-color: var(--accent); color: var(--ink);
                  box-shadow: 0 2px 10px rgba(0,0,0,.05); }
 .example:active { transform: scale(.99); }
 .example .ico { flex: 0 0 16px; color: var(--accent); display: inline-flex; }
 .example .arrow { margin-left: auto; color: var(--dim); opacity: 0;
                   transition: opacity .12s; }
 .example:hover .arrow { opacity: 1; }

 /* ===== Messages ============================================= */
 .msg { margin: 12px 0; display: flex; gap: 9px; align-items: flex-start; }
 .msg.user { justify-content: flex-end; }
 .msg .avatar {
   flex: 0 0 22px; width: 22px; height: 22px; border-radius: 50%;
   display: flex; align-items: center; justify-content: center;
   font-size: 10px; font-weight: 600; letter-spacing: -.2px; color: #fff;
   margin-top: 1px;
 }
 .msg.ai   .avatar { background: linear-gradient(135deg, var(--accent), var(--accent-dark)); }
 .msg.user .avatar { background: #4a4d54; order: 2; }

 .msg .bubble {
   max-width: 88%; padding: 7px 11px; border-radius: 10px;
   white-space: pre-wrap; word-wrap: break-word; line-height: 1.5;
 }
 .msg.ai   .bubble { background: transparent; color: var(--ink); padding-left: 0; padding-right: 0; }
 .msg.user .bubble { background: var(--user-bg); color: var(--user-ink); border: 1px solid var(--user-border); border-bottom-right-radius: 3px; }

 /* ===== Tool calls (collapsed by default, click to expand) === */
 .tools { margin: 4px 0 4px 31px; }
 .tool {
   display: flex; align-items: center; gap: 7px;
   font: 11.5px/1.5 ui-monospace, "SF Mono", Menlo, monospace;
   color: var(--dim); padding: 1.5px 0;
 }
 .tool .icon {
   flex: 0 0 14px; display: inline-flex; align-items: center; justify-content: center;
   font-size: 11px; color: var(--accent);
 }
 .tool.pending .icon::after {
   content: ''; width: 9px; height: 9px; border-radius: 50%;
   border: 1.5px solid var(--accent); border-top-color: transparent;
   animation: spin .8s linear infinite;
 }
 .tool.ok  .icon { color: var(--ok); }
 .tool.err .icon { color: var(--err); }
 .tool .name { color: var(--ink-2); }
 .tool .args { color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 1; }
 .tool .timing { color: var(--dim); font-size: 10.5px; opacity: .7; }
 @keyframes spin { to { transform: rotate(360deg) } }

 /* ===== Banners (system / error / log) ====================== */
 .banner { margin: 8px 0; padding: 7px 11px; border-radius: 7px;
           font-size: 12px; line-height: 1.5; }
 .banner.system { color: var(--ok);   background: rgba(103,217,122,.06); border: 1px solid rgba(103,217,122,.18); }
 .banner.error  { color: var(--err);  background: rgba(255,120,120,.08); border: 1px solid rgba(255,120,120,.25); }
 .banner.log    { color: var(--dim);  background: var(--bg-elev); font: 11px ui-monospace, monospace; }

 /* ===== Typing indicator ===================================== */
 .typing { display: flex; align-items: center; gap: 8px; color: var(--dim);
           font-size: 12px; margin: 6px 0 6px 31px; }
 .typing .dots span { display: inline-block; width: 4px; height: 4px;
   border-radius: 50%; background: var(--dim); margin-right: 3px;
   animation: blink 1.2s infinite both; }
 .typing .dots span:nth-child(2) { animation-delay: .2s; }
 .typing .dots span:nth-child(3) { animation-delay: .4s; }
 @keyframes blink { 0%,80%,100% { opacity: .25 } 40% { opacity: 1 } }

 /* ===== Composer (input card) ================================ */
 .card {
   background: var(--bg-input);
   border: 1px solid var(--line);
   border-radius: 12px;
   padding: 10px 12px 8px 12px;
   transition: border-color .15s;
 }
 .card:focus-within { border-color: var(--accent); }
 .card textarea {
   width: 100%; min-height: 44px; max-height: 200px;
   background: transparent; border: 0; outline: 0; resize: none;
   color: var(--ink); font: 13.5px/1.5 -apple-system, "SF Pro Text", Helvetica, sans-serif;
   padding: 0;
 }
 .card textarea::placeholder { color: var(--dim); }
 .card .row {
   display: flex; align-items: center; justify-content: space-between;
   margin-top: 6px;
 }
 .card .left, .card .right { display: flex; align-items: center; gap: 6px; }
 .pill {
   display: inline-flex; align-items: center; gap: 4px;
   background: var(--bg-elev); border: 1px solid var(--line);
   color: var(--ink-2); font-size: 11.5px;
   padding: 3px 8px; border-radius: 999px;
   cursor: default;
 }
 .pill .caret { color: var(--dim); font-size: 9px; }
 .send-btn {
   background: var(--accent); border: 0; padding: 0;
   width: 40px; height: 40px; border-radius: 50%; color: #1a1206;
   cursor: pointer; display: flex; align-items: center; justify-content: center;
   box-shadow: 0 1px 6px rgba(240,161,58,.25);
   transition: background .1s, transform .06s;
 }
 .send-btn:hover { background: #ffae3e; }
 .send-btn:active { transform: scale(.93); }
 .send-btn.stop {
   background: #3a1c1c; color: #ff9e9e;
   border: 1px solid #ff7878; box-shadow: none;
 }
 .send-btn.stop:hover { background: #4a2424; color: #ffbcbc; }
 .send-btn.stop::before {
   content: ''; width: 11px; height: 11px; background: #ff7878;
   border-radius: 2px;
 }
 .send-btn:disabled { cursor: not-allowed; opacity: .6; }
 .send-btn svg { width: 17px; height: 17px; }

 /* scrollbar */
 ::-webkit-scrollbar { width: 8px; height: 8px; }
 ::-webkit-scrollbar-track { background: transparent; }
 ::-webkit-scrollbar-thumb { background: var(--line); border-radius: 4px; }
 ::-webkit-scrollbar-thumb:hover { background: #3a3d45; }
</style>
</head>
<body>
<div id="app">

  <div id="topbar">
    <div class="title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <rect x="6" y="6" width="12" height="12" rx="1"/>
        <line x1="3" y1="9"  x2="6"  y2="9"/>  <line x1="3" y1="12" x2="6"  y2="12"/>
        <line x1="3" y1="15" x2="6"  y2="15"/>
        <line x1="18" y1="9"  x2="21" y2="9"/> <line x1="18" y1="12" x2="21" y2="12"/>
        <line x1="18" y1="15" x2="21" y2="15"/>
      </svg>
      PLC Agent
    </div>
    <div id="status" class="status">
      <span class="dot"></span><span class="label">idle</span>
    </div>
    <div class="actions">
      <button title="New conversation" onclick="newChat()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
      </button>
      <button title="Clear" onclick="clearChat()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
        </svg>
      </button>
    </div>
  </div>

  <div id="messages"></div>

  <div id="composer">
    <div class="card">
      <textarea id="input" placeholder="Describe a machine, a control loop, an HMI behaviour…" rows="2"></textarea>
      <div class="row">
        <div class="left"></div>
        <div class="right">
          <button id="send" class="send-btn" title="Send" onclick="submit()">
            <svg class="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 2L11 13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const messages = $('messages');
const input = $('input');
const sendBtn = $('send');

function postToHost(msg) {
  try { window.bridge.postMessage(JSON.stringify(msg)); }
  catch (e) { console.error('host bridge unavailable', e); }
}

const EXAMPLES = [
  "3-section conveyor with emergency stop and a parts counter",
  "5-floor elevator with top-down call priority",
  "oven with PID temperature control for a chocolate line",
];
function emptyHTML(){
  const chip = '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/><rect x="7" y="7" width="10" height="10" rx="2"/></svg>';
  let ex = '';
  for (const e of EXAMPLES){
    ex += '<div class="example" data-text="'+e.replace(/"/g,'&quot;')+'" onclick="useExample(this)">'+chip+
          '<span>'+e+'</span><span class="arrow">&rarr;</span></div>';
  }
  return '<div id="empty" class="empty">'+
    '<div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6v6H9z"/><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/></svg></div>'+
    '<h2>PLC Agent</h2>'+
    '<div class="sub">Describe a machine in plain language — the agent generates ST / LD / FBD, compiles it, and simulates the plant.</div>'+
    '<div class="examples"><div class="lbl">Try an example</div>'+ex+'</div>'+
    '</div>';
}
function useExample(el){
  const t = el.getAttribute('data-text') || el.textContent.trim();
  input.value = t; input.focus();
  input.style.height = 'auto'; input.style.height = input.scrollHeight + 'px';
}
function showEmpty(){ messages.innerHTML = emptyHTML(); }

function hideEmpty(){ const e = $('empty'); if (e) e.remove(); }
function scrollBot(){ requestAnimationFrame(() => { messages.scrollTop = messages.scrollHeight; }); }

function addMessage(role, text){
  const b = $('busy'); if (b) b.remove();
  hideEmpty();
  const m = document.createElement('div'); m.className = 'msg ' + role;
  const av = document.createElement('div'); av.className = 'avatar';
  av.textContent = role === 'user' ? 'You' : 'AI';
  const bub = document.createElement('div'); bub.className = 'bubble';
  bub.textContent = text;
  m.appendChild(av); m.appendChild(bub);
  messages.appendChild(m);
  scrollBot();
}

// Append text to the most-recent AI bubble or start a new one.
function appendAi(text){
  const last = messages.lastElementChild;
  if (last && last.classList && last.classList.contains('msg') && last.classList.contains('ai')) {
    last.querySelector('.bubble').appendChild(document.createTextNode(text));
  } else {
    addMessage('ai', text);
  }
  scrollBot();
}

// Track in-flight tool rows so we can replace the spinner with ok/err
// when the result comes back. Keyed by tool name; FIFO (oldest first).
const pendingTools = new Map();

function _toolGroup() {
  let group = messages.lastElementChild;
  if (!group || !group.classList || !group.classList.contains('tools')) {
    group = document.createElement('div'); group.className = 'tools';
    messages.appendChild(group);
  }
  return group;
}

function addToolPending(name, args) {
  hideEmpty();
  const group = _toolGroup();
  const row = document.createElement('div');
  row.className = 'tool pending';
  row.dataset.startedAt = Date.now();
  const icon = document.createElement('span'); icon.className = 'icon';
  const nm = document.createElement('span'); nm.className = 'name'; nm.textContent = name;
  const a = document.createElement('span'); a.className = 'args'; a.textContent = args;
  const t = document.createElement('span'); t.className = 'timing'; t.textContent = '…';
  row.appendChild(icon); row.appendChild(nm); row.appendChild(a); row.appendChild(t);
  group.appendChild(row);
  if (!pendingTools.has(name)) pendingTools.set(name, []);
  pendingTools.get(name).push(row);
  scrollBot();
}

function resolveTool(name, ok, output) {
  hideEmpty();
  const queue = pendingTools.get(name) || [];
  const row = queue.shift();
  if (row) {
    if (queue.length === 0) pendingTools.delete(name);
    row.classList.remove('pending');
    row.classList.add(ok ? 'ok' : 'err');
    const icon = row.querySelector('.icon');
    icon.textContent = ok ? '✓' : '✗';
    row.querySelector('.args').textContent = output;
    const elapsed = ((Date.now() - Number(row.dataset.startedAt)) / 1000).toFixed(1);
    row.querySelector('.timing').textContent = elapsed + 's';
  } else {
    // No matching call (shouldn't happen, but keep a fallback line)
    const group = _toolGroup();
    const row2 = document.createElement('div');
    row2.className = 'tool ' + (ok ? 'ok' : 'err');
    row2.innerHTML = `<span class="icon">${ok ? '✓' : '✗'}</span>
                      <span class="name">${escapeHTML(name)}</span>
                      <span class="args">${escapeHTML(output)}</span>`;
    group.appendChild(row2);
  }
  scrollBot();
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function addBanner(kind, text){
  hideEmpty();
  const d = document.createElement('div'); d.className = 'banner ' + kind;
  d.textContent = text;
  messages.appendChild(d);
  scrollBot();
}

function showBusy(){
  hideEmpty();
  if ($('busy')) return;
  const b = document.createElement('div');
  b.id = 'busy'; b.className = 'typing';
  b.innerHTML = "<span>AI is working</span><span class='dots'><span></span><span></span><span></span></span>";
  messages.appendChild(b); scrollBot();
}
function hideBusy(){ const b = $('busy'); if (b) b.remove(); }

function setBusy(busy){
  const label = sendBtn.querySelector('.send-label');
  const icon = sendBtn.querySelector('.send-icon');
  if (busy) {
    sendBtn.disabled = false;       // keep enabled so user can click Stop
    sendBtn.classList.add('stop');
    sendBtn.onclick = stopAgent;
    if (label) label.textContent = 'Stop';
    if (icon) icon.style.display = 'none';
    setStatus(true, 'thinking');
  } else {
    sendBtn.disabled = false;
    sendBtn.classList.remove('stop');
    sendBtn.onclick = submit;
    if (label) label.textContent = 'Send';
    if (icon) icon.style.display = '';
    setStatus(false, 'idle');
    // Any tool rows still spinning when the agent finishes — mark abandoned.
    for (const [name, queue] of pendingTools.entries()) {
      for (const row of queue) {
        row.classList.remove('pending');
        row.classList.add('err');
        const icon = row.querySelector('.icon');
        if (icon) icon.textContent = '✗';
        row.querySelector('.args').textContent = '(no result returned)';
      }
    }
    pendingTools.clear();
  }
  if (busy) showBusy(); else hideBusy();
}

function setStatus(working, text) {
  const s = document.getElementById('status');
  if (!s) return;
  s.classList.toggle('working', !!working);
  const lbl = s.querySelector('.label');
  if (lbl) lbl.textContent = text;
}

function setStatusText(text) {
  const s = document.getElementById('status');
  if (!s) return;
  const lbl = s.querySelector('.label');
  if (lbl) lbl.textContent = text;
}

function clearChat(){
  showEmpty();
  postToHost({type: 'clear'});
}
function newChat(){ clearChat(); }

function submit(){
  const text = input.value.trim();
  if (!text || sendBtn.disabled) return;
  input.value = '';
  postToHost({type: 'submit', text: text});
}

function stopAgent(){
  postToHost({type: 'stop'});
  setStatusText('stopping…');
}

// Enter to send, Shift+Enter for newline. ⌘/Ctrl+Enter also sends.
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault(); submit();
  }
});
// Auto-grow textarea up to max-height.
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(200, input.scrollHeight) + 'px';
});
if (!messages.children.length) showEmpty();
input.focus();
</script>
</body></html>
"""


class ChatPanel(wx.Panel):
    def __init__(self, parent, project_controller_getter):
        super().__init__(parent)
        self._get_ctr = project_controller_getter
        self._agent = None
        self._busy = False
        self._webview_ready = False
        self._pending_calls = []

        self.SetBackgroundColour(wx.Colour(246, 247, 249))

        self.webview = wx.html2.WebView.New(self)
        self.webview.EnableContextMenu(False)
        # JS-to-Python bridge: window.bridge.postMessage(json) from page → here.
        self.webview.AddScriptMessageHandler("bridge")
        self.webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, self._on_webview_loaded)
        self.webview.Bind(wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, self._on_js_message)
        self.webview.SetPage(CHAT_HTML, "")

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.webview, proportion=1, flag=wx.EXPAND)
        self.SetSizer(sizer)

    # ---- WebView bridge -------------------------------------------------

    def _on_webview_loaded(self, _event):
        self._webview_ready = True
        for call in self._pending_calls:
            self._run(call)
        self._pending_calls = []

    def _run(self, expr):
        # JS try/catch: LOADED can fire before the page script defines its
        # functions (WKWebView race) — guard so it never throws a dialog.
        try:
            self.webview.RunScript("try{" + expr + "}catch(e){}")
        except Exception:
            pass

    def _js(self, expr):
        if self._webview_ready:
            self._run(expr)
        else:
            self._pending_calls.append(expr)

    def _on_js_message(self, event):
        raw = event.GetString()
        try:
            msg = json.loads(raw)
        except Exception:
            return
        if msg.get("type") == "submit":
            self._submit(msg.get("text", "").strip())
        elif msg.get("type") == "stop":
            if self._agent is not None:
                self._agent.abort()
        elif msg.get("type") == "clear":
            # Drop conversation state; next user turn starts fresh context.
            if self._agent is not None:
                self._agent.messages = []

    # ---- agent lifecycle -------------------------------------------------

    def _ensure_agent(self):
        ctr = self._get_ctr()
        if ctr is None:
            return None
        if self._agent is None or self._agent.tools.ctr is not ctr:
            tools = Tools(
                ctr,
                logger=lambda m: wx.CallAfter(self._append_log, m + "\n"),
                on_hmi_request=lambda html, matched, caption: wx.CallAfter(
                    self._setup_custom_hmi, html, matched, caption),
            )
            gui_tools = _MainThreadTools(tools)
            self._agent = Agent(
                gui_tools,
                on_event=lambda kind, payload: wx.CallAfter(self._on_agent_event, kind, payload),
            )
        return self._agent

    def _setup_custom_hmi(self, html, matched_vars, caption):
        """Agent called set_hmi → tear down old bridge, spin up new one with the
        provided HTML and watch list, point WebView at it."""
        frame = wx.GetTopLevelParent(self)
        hmi = getattr(frame, "HMIPanel", None)
        ctr = self._get_ctr()
        if hmi is None or ctr is None:
            return
        if not matched_vars:
            self._append_system("HMI request had no resolvable variables — ignored")
            return
        self._tear_down_bridge()
        try:
            bridge = Bridge(ctr, matched_vars, html)
            bridge.start()
            self._bridge = bridge
            url = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/"
            hmi.load_url(url)
            self._show_hmi_tab(frame, hmi, caption=caption or "HMI View")
            self._append_system(
                f"Custom HMI ready · '{caption}' · watching {len(matched_vars)} variables")
        except Exception as exc:
            self._js(f"addBanner('error', {json.dumps('⚠ HMI bridge failed: ' + str(exc))})")

    def _on_agent_event(self, kind, payload):
        if kind == "assistant_text":
            self._js(f"appendAi({json.dumps(payload)})")
        elif kind == "tool_call":
            self._js(f"addToolPending({json.dumps(payload['name'])}, "
                     f"{json.dumps(_summarize(payload['input']))})")
            self._js(f"setStatusText({json.dumps('running ' + payload['name'])})")
        elif kind == "tool_result":
            out = payload.get("output", {})
            ok = (isinstance(out, dict) and out.get("ok") in (True, None)
                  and "error" not in out)
            self._js(f"resolveTool({json.dumps(payload['name'])}, "
                     f"{'true' if ok else 'false'}, "
                     f"{json.dumps(_summarize(out))})")
            self._js(f"setStatusText('thinking')")
            self._maybe_refresh_hmi(payload)
        elif kind == "error":
            self._js(f"addBanner('error', {json.dumps('⚠ ' + str(payload))})")
        elif kind == "done":
            self._busy = False
            self._js("setBusy(false)")

    def _append_log(self, msg):
        self._js(f"addBanner('log', {json.dumps(msg.rstrip())})")

    def _append_system(self, msg):
        self._js(f"addBanner('system', {json.dumps(msg)})")

    # ---- input flow (called from JS bridge) ------------------------------

    def _submit(self, text):
        if not text or self._busy:
            return
        agent = self._ensure_agent()
        if agent is None:
            self._js(f"addBanner('error', {json.dumps('⚠ No project open. Open or create a project first.')})")
            return
        self._js(f"addMessage('user', {json.dumps(text)})")
        self._busy = True
        self._js("setBusy(true)")

        def worker():
            try:
                agent.send(text)
            finally:
                wx.CallAfter(self._on_agent_event, "done", None)

        threading.Thread(target=worker, daemon=True, name="plc-cursor-agent").start()

    # ---- HMI bridging ----------------------------------------------------

    def _maybe_refresh_hmi(self, payload):
        name = payload.get("name")
        if name == "stop_simulation":
            self._tear_down_bridge()
            return
        if name != "start_simulation":
            return
        if not payload.get("output", {}).get("ok"):
            return
        # Deterministic auto-HMI: after every successful start_simulation
        # we inspect the live debug variables and either build an elevator
        # visual (if the project looks like one) or a generic dashboard.
        # The agent's set_hmi tool can still override later if it wants
        # a customized view.
        wx.CallLater(400, self._auto_build_hmi)

    def _auto_build_hmi(self):
        ctr = self._get_ctr()
        if ctr is None:
            return
        idx_map = getattr(ctr, "_IECPathToIdx", {}) or {}
        if not idx_map:
            return
        try:
            html, watch_vars, caption = auto_generate_hmi(idx_map)
        except Exception as exc:
            self._js(f"addBanner('error', {json.dumps('⚠ auto-HMI failed: ' + str(exc))})")
            return
        # Resolve friendly names → full IECPaths.
        lowered = {p.split('.')[-1].lower(): p for p in idx_map.keys()}
        matched = []
        for name in watch_vars:
            full = lowered.get(name.lower())
            if full:
                matched.append((full, name))
        if not matched:
            return
        self._setup_custom_hmi(html, matched, caption)

    def _show_hmi_tab(self, frame, hmi, caption):
        tabs = getattr(frame, "TabsOpened", None)
        if tabs is None:
            return
        for i in range(tabs.GetPageCount()):
            if tabs.GetPage(i) is hmi:
                tabs.SetSelection(i)
                hmi.Show()
                return
        if hmi.GetParent() is not tabs:
            hmi.Reparent(tabs)
        hmi.Show()
        tabs.AddPage(hmi, caption, select=True)

    def _hide_hmi_tab(self, frame, hmi):
        tabs = getattr(frame, "TabsOpened", None)
        if tabs is None:
            return
        for i in range(tabs.GetPageCount()):
            if tabs.GetPage(i) is hmi:
                tabs.RemovePage(i)
                hmi.Hide()
                return

    def _tear_down_bridge(self):
        bridge = getattr(self, "_bridge", None)
        if bridge is not None:
            try:
                bridge.stop()
            except Exception:
                pass
            self._bridge = None
        frame = wx.GetTopLevelParent(self)
        hmi = getattr(frame, "HMIPanel", None)
        if hmi is not None:
            self._hide_hmi_tab(frame, hmi)


def _summarize(obj):
    s = repr(obj) if not isinstance(obj, str) else obj
    return s if len(s) < 160 else s[:157] + "…"
