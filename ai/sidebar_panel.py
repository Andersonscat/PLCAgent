"""SidebarPanel — modern WebView-based replacement for Beremiz's legacy
project tree + variables panel.

Renders project structure (POUs, resources) and variables of the currently
selected POU in a single dark HTML sidebar. Polls ProjectController every
2 seconds; pushes incremental updates to the page via RunScript. Click on
a POU posts back to Python which calls IDEFrame.EditProjectElement to
open it in the central editor.
"""

import json
import sys

import wx
import wx.html2


print("[plc-cursor] Sidebar panel loaded", file=sys.stderr)


SIDEBAR_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
 :root {
   --bg: #f6f7f9;
   --bg-elev: #eef0f3;
   --bg-hover: #e9ebef;
   --bg-selected: #fdebcf;
   --line: #d2d5dc;
   --ink: #20222a;
   --ink-2: #4a4d56;
   --dim: #8a8d96;
   --accent: #de8c1e;
   --accent-dim: #a8650f;
   --ok: #2e9e44;
   --guide: #d7dae1;
 }
 * { box-sizing: border-box; }
 html, body {
   margin: 0; padding: 0; height: 100%; overflow: hidden;
   background: var(--bg); color: var(--ink);
   font: 13px/1.45 -apple-system, "SF Pro Text", Helvetica, Arial, sans-serif;
   -webkit-font-smoothing: antialiased;
   user-select: none;
 }

 #header {
   padding: 9px 12px 8px;
   background: var(--bg-elev);
   border-bottom: 1px solid var(--line);
 }
 #header .ptitle { color: var(--ink); font-weight: 600; font-size: 13.5px; }
 #tabrow {
   display: flex; align-items: flex-end; justify-content: space-between;
   padding: 0 8px; background: var(--bg);
   border-bottom: 1px solid var(--line);
 }
 #tabrow .dtab {
   padding: 6px 14px 7px; font-size: 12px; color: var(--ink);
   border: 1px solid var(--line); border-bottom: none;
   border-radius: 6px 6px 0 0; background: var(--bg-elev);
   position: relative; top: 1px; font-weight: 600;
 }
 .treebtns { display: flex; gap: 2px; padding-bottom: 4px; }
 .treebtn {
   width: 24px; height: 22px; border: 0; background: transparent;
   border-radius: 5px; color: var(--dim); cursor: pointer; padding: 0;
   display: inline-flex; align-items: center; justify-content: center;
 }
 .treebtn svg { width: 15px; height: 15px; }
 .treebtn:hover { background: var(--bg-hover); color: var(--ink); }
 .treebtn:active { transform: scale(.92); }

 #content { height: calc(100vh - 78px); overflow-y: auto; padding: 4px 0 16px 0; }

 .section { margin-top: 8px; }
 .section-header {
   display: flex; align-items: center; justify-content: space-between;
   padding: 8px 14px 4px 14px;
   font-size: 10.5px; color: var(--dim);
   text-transform: uppercase; letter-spacing: .8px;
 }
 .section-header .count { color: var(--dim); opacity: .7; }

 .item {
   display: flex; align-items: center; gap: 8px;
   padding: 5px 14px; cursor: pointer;
   transition: background .08s;
 }
 .item:hover { background: var(--bg-hover); }
 .item.selected { background: var(--bg-selected); }
 .item .name { color: var(--ink); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
 .item.selected .name { color: var(--accent); }

 .lang-badge {
   display: inline-flex; align-items: center; justify-content: center;
   width: 21px; height: 13px; border-radius: 3px;
   font: 700 7.5px ui-monospace, "SF Mono", Menlo, monospace;
   letter-spacing: .2px; color: #1a1206;
   flex-shrink: 0;
 }
 .lang-badge.ST  { background: #ff8c52; }
 .lang-badge.LD  { background: #67d97a; color: #0a1f10; }
 .lang-badge.FBD { background: #6ab0ff; color: #06182c; }
 .lang-badge.SFC { background: #c987ff; color: #1a0a2e; }
 .lang-badge.IL  { background: #888;    color: #1a1a1a; }

 .pou-type {
   font-size: 9px; color: var(--dim); padding: 0 3px;
   border: 1px solid var(--line); border-radius: 3px; flex-shrink: 0;
 }

 /* Variables */
 .var {
   display: flex; align-items: center; gap: 8px;
   padding: 4px 14px;
   font: 12px/1.4 ui-monospace, "SF Mono", Menlo, monospace;
 }
 .var:hover { background: var(--bg-hover); }
 .var .scope-dot {
   width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
 }
 .scope-dot.input    { background: #ff5252; }
 .scope-dot.output   { background: #6ab0ff; }
 .scope-dot.local    { background: #c987ff; }
 .scope-dot.external { background: #ffa726; }
 .scope-dot.inout    { background: #ffeb3b; }

 .var .name { color: var(--ink-2); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
 .var .type {
   color: var(--dim); font-size: 10.5px; padding: 1px 5px;
   background: var(--bg-elev); border-radius: 3px;
   flex-shrink: 0;
 }

 .empty {
   color: var(--dim); text-align: center; padding: 40px 16px;
   font-size: 12px; line-height: 1.6;
 }
 .empty .hint { margin-top: 10px; font-size: 11px; color: var(--dim); opacity: .7; }

 .section-header .add-btn {
   width: 18px; height: 18px; border-radius: 4px; border: 1px solid var(--line);
   background: transparent; color: var(--dim); cursor: pointer; padding: 0;
   line-height: 1; font-size: 13px; font-weight: 400;
   display: inline-flex; align-items: center; justify-content: center;
 }
 .section-header .add-btn:hover { background: var(--bg-elev); color: var(--accent); border-color: var(--accent); }

 /* New-POU modal */
 #modal-bg {
   position: fixed; inset: 0; background: rgba(0,0,0,.55);
   display: none; align-items: center; justify-content: center; z-index: 100;
 }
 #modal-bg.show { display: flex; }
 #modal {
   background: var(--bg-elev); border: 1px solid var(--line);
   border-radius: 10px; padding: 16px; min-width: 240px;
 }
 #modal h3 {
   margin: 0 0 12px; color: var(--ink); font-size: 13px; font-weight: 500;
   text-transform: none; letter-spacing: 0;
 }
 #modal label {
   display: block; font-size: 10.5px; color: var(--dim);
   text-transform: uppercase; letter-spacing: .5px; margin: 8px 0 4px;
 }
 #modal input, #modal select {
   width: 100%; background: var(--bg); border: 1px solid var(--line);
   color: var(--ink); padding: 6px 8px; border-radius: 5px;
   font: 12px -apple-system, sans-serif;
 }
 #modal input:focus, #modal select:focus { outline: 0; border-color: var(--accent); }
 #modal .row { display: flex; gap: 8px; }
 #modal .row > * { flex: 1; }
 #modal .actions { display: flex; gap: 6px; margin-top: 14px; justify-content: flex-end; }
 #modal .actions button {
   background: var(--bg); border: 1px solid var(--line); color: var(--ink-2);
   padding: 5px 12px; border-radius: 5px; font-size: 12px; cursor: pointer;
 }
 #modal .actions button.primary {
   background: var(--accent); border-color: var(--accent); color: #1a1206; font-weight: 600;
 }
 #modal .actions button:hover { background: var(--bg-hover); }
 #modal .actions button.primary:hover { background: #ffae3e; }

 ::-webkit-scrollbar { width: 8px; }
 ::-webkit-scrollbar-track { background: transparent; }
 ::-webkit-scrollbar-thumb { background: var(--line); border-radius: 4px; }
 ::-webkit-scrollbar-thumb:hover { background: #353841; }

 /* TIA-Portal-style project tree */
 .tree { padding: 4px 6px 8px 6px; }
 .node {
   display: flex; align-items: center; gap: 6px;
   height: 23px; padding: 0 6px 0 2px; cursor: pointer; white-space: nowrap;
   border-radius: 4px;
 }
 .node:hover { background: var(--bg-hover); }
 .node .chev {
   width: 12px; flex-shrink: 0; color: var(--dim); font-size: 9px;
   display: inline-flex; align-items: center; justify-content: center;
   transition: transform .12s;
 }
 .node.collapsed .chev { transform: rotate(-90deg); }
 .node .chev.leaf { visibility: hidden; }
 .node .ico {
   width: 16px; height: 16px; flex-shrink: 0; color: var(--ink-2);
   display: inline-flex; align-items: center; justify-content: center;
 }
 .node .ico svg { width: 15px; height: 15px; display: block; }
 .node .ico.ico--ok     { color: var(--ok); }
 .node .ico.ico--accent { color: var(--accent); }
 .node .ico.ico--blue   { color: #6ab0ff; }
 .node .label { color: var(--ink-2); flex: 1; overflow: hidden; text-overflow: ellipsis; font-size: 12.5px; }
 .node.group > .label, .node.root > .label, .node.device > .label { color: var(--ink); }
 .node.root > .label, .node.device > .label { font-weight: 600; }
 .node.action > .label { color: var(--dim); }
 .node.action:hover > .label { color: var(--accent); }
 .node .count2 { color: var(--dim); font-size: 11px; margin-left: 4px; }
 .node.pou.selected, .node.selected { background: var(--bg-selected); }
 .node.pou.selected .label, .node.selected .label { color: var(--accent); }
 /* nested children → indentation + TIA vertical guide line */
 .children { margin-left: 13px; padding-left: 8px; border-left: 1px solid var(--guide); }
 .children.collapsed { display: none; }
 .add-btn2 {
   width: 17px; height: 17px; border-radius: 4px; border: 1px solid var(--line);
   background: transparent; color: var(--dim); cursor: pointer; padding: 0; line-height: 1;
   font-size: 13px; display: inline-flex; align-items: center; justify-content: center; margin-left: 4px;
 }
 .add-btn2:hover { background: var(--bg-elev); color: var(--accent); border-color: var(--accent); }
</style></head>
<body>
<div id="header">
  <div class="ptitle">Project tree</div>
</div>
<div id="tabrow">
  <div class="dtab active">Devices</div>
  <div class="treebtns">
    <button class="treebtn" id="btn-newpou" title="Add new block">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"><path d="M2 4.5a1 1 0 011-1h3.2l1.3 1.6H13a1 1 0 011 1V12a1 1 0 01-1 1H3a1 1 0 01-1-1z"/><path d="M8 7v3M6.5 8.5h3" stroke-linecap="round"/></svg>
    </button>
    <button class="treebtn" id="btn-collapse-all" title="Collapse all">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M4 6l4 4 4-4"/></svg>
    </button>
    <button class="treebtn" id="btn-expand-all" title="Expand all">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M4 10l4-4 4 4"/></svg>
    </button>
  </div>
</div>
<div id="content">
  <div class="empty">
    Open a project<br>or describe one in the PLC Agent chat.
    <div class="hint">File → Open · or “create a 3-floor elevator”</div>
  </div>
</div>

<div id="modal-bg" onclick="closeModalIfBg(event)">
  <div id="modal">
    <h3>New POU</h3>
    <label>Name</label>
    <input id="m-name" placeholder="MyProgram" autocomplete="off">
    <div class="row">
      <div>
        <label>Type</label>
        <select id="m-type">
          <option value="program">Program</option>
          <option value="functionBlock">Function Block</option>
          <option value="function">Function</option>
        </select>
      </div>
      <div>
        <label>Language</label>
        <select id="m-lang">
          <option value="ST">ST — Structured Text</option>
          <option value="LD">LD — Ladder Diagram</option>
          <option value="FBD">FBD — Function Block</option>
          <option value="SFC">SFC — Sequential</option>
          <option value="IL">IL — Instruction List</option>
        </select>
      </div>
    </div>
    <div class="actions">
      <button onclick="closeModal()">Cancel</button>
      <button class="primary" onclick="submitNewPou()">Create</button>
    </div>
  </div>
</div>

<script>
const content = document.getElementById('content');
let selectedPou = null;

function postToHost(msg) {
  try { window.bridge.postMessage(JSON.stringify(msg)); } catch (e) {}
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

const ICONS = {
  plc: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.8" y="2.5" width="12.4" height="11" rx="1"/><path d="M5 2.5v11" /><path d="M2 6h3M2 10h3" stroke-linecap="round"/><circle cx="9.6" cy="6" r=".7" fill="currentColor" stroke="none"/><circle cx="11.6" cy="6" r=".7" fill="currentColor" stroke="none"/></svg>',
  device: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="4" y="4" width="8" height="8" rx="1"/><path d="M6 1.6v2M10 1.6v2M6 12.4v2M10 12.4v2M1.6 6h2M1.6 10h2M12.4 6h2M12.4 10h2"/></svg>',
  diag: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M1 8h3l2-5 3 10 2-5h4"/></svg>',
  blocks: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2.3" y="2.5" width="7.5" height="6" rx="1"/><rect x="6.2" y="7.5" width="7.5" height="6" rx="1"/></svg>',
  tags: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"><path d="M2 3.5h5.5L14 8l-6.5 4.5H2z"/><circle cx="4.6" cy="8" r="1"/></svg>',
  datatypes: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2.5" y="3" width="11" height="10" rx="1"/><path d="M2.5 6.5h11M6.3 6.5v6.5"/></svg>',
  watch: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M1.5 8S4 3.7 8 3.7 14.5 8 14.5 8 12 12.3 8 12.3 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/></svg>',
  trace: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 2v12h12"/><path d="M3.5 11l3-3 2.5 1.6 3.7-5.1"/></svg>',
  comms: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="4" cy="4.2" r="1.7"/><circle cx="12" cy="6" r="1.7"/><circle cx="6.6" cy="12.4" r="1.7"/><path d="M5.4 4.9l5 1M5.1 5.7l1 5M11 7.5l-3.6 3.7"/></svg>',
  web: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c2.6 2.4 2.6 9.6 0 12M8 2c-2.6 2.4-2.6 9.6 0 12"/></svg>',
  info: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="8" cy="8" r="6"/><path d="M8 7.3v4" stroke-linecap="round"/><circle cx="8" cy="4.9" r=".7" fill="currentColor" stroke="none"/></svg>',
  alarm: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"><path d="M4 10.5V7a4 4 0 018 0v3.5l1.3 1.5H2.7z"/><path d="M6.4 13a1.6 1.6 0 003.2 0"/></svg>',
  resource: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2.5" y="3" width="11" height="4" rx="1"/><rect x="2.5" y="9" width="11" height="4" rx="1"/><circle cx="5" cy="5" r=".6" fill="currentColor" stroke="none"/><circle cx="5" cy="11" r=".6" fill="currentColor" stroke="none"/></svg>',
  project: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2" y="3.5" width="12" height="9.5" rx="1.2"/><path d="M2 6h12M5.5 3.5V6"/></svg>',
  folder: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"><path d="M2 4.5a1 1 0 011-1h3.2l1.3 1.6H13a1 1 0 011 1V12a1 1 0 01-1 1H3a1 1 0 01-1-1z"/></svg>',
  add: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><path d="M8 5v6M5 8h6"/></svg>',
  devnet: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="8" cy="3.5" r="1.6"/><circle cx="3.5" cy="12.5" r="1.6"/><circle cx="12.5" cy="12.5" r="1.6"/><path d="M8 5.1v3M8 8.1l-3.6 3M8 8.1l3.6 3"/></svg>',
  showtags: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M2 4h12M2 8h12M2 12h8"/></svg>',
  module: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="3" y="2.5" width="4" height="11" rx="1"/><rect x="9" y="2.5" width="4" height="11" rx="1"/></svg>',
  doc: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"><path d="M4 2.5h5L12 5.5V13a.5.5 0 01-.5.5h-7A.5.5 0 014 13z"/><path d="M9 2.5V6h3M6 9h4M6 11h4"/></svg>',
  main: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2.5" y="3" width="11" height="10" rx="1.2"/><path d="M5.5 6.5l2 2-2 2M9 10.5h2.5"/></svg>',
};

// A non-expandable section row (no children).
function secLeaf(icon, label, accent, count) {
  const ac = accent ? ' ico--' + accent : '';
  const c = (count || count === 0) && count !== '' ? `<span class="count2">${count}</span>` : '';
  return `<div class="node"><span class="chev leaf"></span>` +
         `<span class="ico${ac}">${ICONS[icon] || ''}</span>` +
         `<span class="label">${esc(label)}</span>${c}</div>`;
}
// An expandable group header (its children follow as the next .children div).
function groupHead(icon, label, accent, count, addBtn, cls) {
  const ac = accent ? ' ico--' + accent : '';
  const c = (count || count === 0) && count !== '' ? `<span class="count2">${count}</span>` : '';
  const add = addBtn ? `<button class="add-btn2" title="New POU" onclick="event.stopPropagation();openNewPouModal()">+</button>` : '';
  return `<div class="node group ${cls || ''}" data-toggle="1"><span class="chev">&#9662;</span>` +
         `<span class="ico${ac}">${ICONS[icon] || ''}</span>` +
         `<span class="label">${esc(label)}</span>${c}${add}</div>`;
}

// A dim "Add new …" / action row.
function addLeaf(label, action) {
  const a = action ? ` data-action="${action}"` : '';
  return `<div class="node action"${a}><span class="chev leaf"></span>` +
         `<span class="ico ico--accent">${ICONS.add}</span>` +
         `<span class="label">${esc(label)}</span></div>`;
}

function render(state) {
  if (!state) {
    content.innerHTML = '<div class="empty">Open a project<br>or describe one in the PLC Agent chat.<div class="hint">File → Open · or “create a 3-floor elevator”</div></div>';
    return;
  }

  const pous = state.pous || [];
  const resources = state.resources || [];
  const vbp = state._vars_by_pou || {};
  let tagCount = 0;
  for (const k in vbp) tagCount += (vbp[k] || []).length;
  const dev = (resources[0] || 'PLC_1').split('.')[0] + ' [Soft PLC]';

  let html = '<div class="tree">';

  // Project root.
  html += groupHead('project', state.project || 'Unnamed', 'accent', '', false, 'root');
  html += '<div class="children">';

  // Project-level items.
  html += addLeaf('Add new device');
  html += secLeaf('devnet', 'Devices & networks', 'blue');

  // Device node — everything nests beneath it (TIA "PLC_1 [CPU …]").
  html += groupHead('plc', dev, 'accent', '', false, 'device');
  html += '<div class="children">';

  html += secLeaf('device', 'Device configuration');
  html += secLeaf('diag', 'Online & diagnostics', 'ok');
  html += secLeaf('folder', 'Software units');

  // Program blocks — holds the project's POUs.
  html += groupHead('blocks', 'Program blocks', 'accent', pous.length, true);
  html += '<div class="children">';
  html += addLeaf('Add new block', 'new-pou');
  for (const pou of pous) {
    const isSel = pou.name === selectedPou;
    const typeLabel = pou.type === 'functionBlock' ? 'FB'
                   : pou.type === 'function' ? 'FN' : 'PRG';
    html += `<div class="node pou ${isSel ? 'selected' : ''}" data-pou="${esc(pou.name)}">
               <span class="chev leaf"></span>
               <span class="lang-badge ${esc(pou.lang || 'ST')}">${esc(pou.lang || 'ST')}</span>
               <span class="label">${esc(pou.name)}</span>
               <span class="pou-type">${typeLabel}</span>
             </div>`;
  }
  html += '</div>';

  html += secLeaf('folder', 'Technology objects');
  html += secLeaf('folder', 'External source files');

  // PLC tags — Show all / Add new / Default tag table.
  html += groupHead('tags', 'PLC tags', null, tagCount || '');
  html += '<div class="children">';
  html += `<div class="node"><span class="chev leaf"></span><span class="ico">${ICONS.showtags}</span><span class="label">Show all tags</span></div>`;
  html += addLeaf('Add new tag table');
  html += `<div class="node"><span class="chev leaf"></span><span class="ico">${ICONS.tags}</span><span class="label">Default tag table</span><span class="count2">[${tagCount}]</span></div>`;
  html += '</div>';

  html += secLeaf('datatypes', 'PLC data types');
  html += secLeaf('watch', 'Watch and force tables');
  html += secLeaf('folder', 'Online backups');
  html += secLeaf('trace', 'Traces');
  html += secLeaf('comms', 'OPC UA communication', 'blue');
  html += secLeaf('web', 'Web applications', 'blue');
  html += secLeaf('folder', 'Device proxy data');
  html += secLeaf('info', 'Program info');
  html += secLeaf('alarm', 'PLC supervisions & alarms', 'accent');
  html += secLeaf('doc', 'PLC alarm text lists');
  html += secLeaf('module', 'Local modules');

  if (resources.length) {
    html += groupHead('resource', 'Resources', null, resources.length);
    html += '<div class="children">';
    for (const r of resources) {
      html += `<div class="node"><span class="chev leaf"></span><span class="ico">${ICONS.resource}</span><span class="label">${esc(r)}</span></div>`;
    }
    html += '</div>';
  }

  html += '</div>'; // device children
  html += '</div>'; // project children
  html += '</div>'; // .tree

  // Variables of the selected POU.
  const vars = selectedPou ? (vbp[selectedPou] || []) : [];
  if (selectedPou) {
    html += '<div class="section">';
    html += `<div class="section-header"><span>${esc(selectedPou)} · variables</span><span class="count">${vars.length}</span></div>`;
    if (vars.length) {
      for (const v of vars) {
        html += `<div class="var" title="${esc(v.scope)} ${esc(v.type)}"><span class="scope-dot ${esc(v.scope)}"></span><span class="name">${esc(v.name)}</span><span class="type">${esc(v.type)}</span></div>`;
      }
    } else {
      html += `<div class="empty" style="padding:14px;font-size:11px;">no variables declared</div>`;
    }
    html += '</div>';
  }

  content.innerHTML = html;

  // Open a POU on click.
  content.querySelectorAll('.node.pou[data-pou]').forEach(el => {
    el.addEventListener('click', () => {
      selectedPou = el.dataset.pou;
      postToHost({type: 'open_pou', name: selectedPou});
      render(state);
    });
  });
  // "Add new block" → new-POU modal.
  content.querySelectorAll('.node.action[data-action="new-pou"]').forEach(el => {
    el.addEventListener('click', e => { e.stopPropagation(); openNewPouModal(); });
  });
  // Expand / collapse toggles.
  content.querySelectorAll('.node[data-toggle]').forEach(el => {
    el.addEventListener('click', () => {
      const kids = el.nextElementSibling;
      el.classList.toggle('collapsed');
      if (kids && kids.classList.contains('children')) kids.classList.toggle('collapsed');
    });
  });
}

window.render = render;

function openNewPouModal() {
  document.getElementById('modal-bg').classList.add('show');
  document.getElementById('m-name').value = '';
  setTimeout(() => document.getElementById('m-name').focus(), 30);
}
function closeModal() {
  document.getElementById('modal-bg').classList.remove('show');
}
function closeModalIfBg(ev) {
  if (ev.target.id === 'modal-bg') closeModal();
}
function submitNewPou() {
  const name = document.getElementById('m-name').value.trim();
  const pouType = document.getElementById('m-type').value;
  const lang = document.getElementById('m-lang').value;
  if (!name) { document.getElementById('m-name').focus(); return; }
  postToHost({type: 'create_pou', name, pou_type: pouType, body_language: lang});
  closeModal();
}
window.openNewPouModal = openNewPouModal;
window.closeModal = closeModal;
window.closeModalIfBg = closeModalIfBg;
window.submitNewPou = submitNewPou;

// Enter in name field = submit, Esc anywhere = cancel
document.addEventListener('keydown', (e) => {
  const modalShown = document.getElementById('modal-bg').classList.contains('show');
  if (!modalShown) return;
  if (e.key === 'Enter') { e.preventDefault(); submitNewPou(); }
  if (e.key === 'Escape') { e.preventDefault(); closeModal(); }
});

// Project-tree toolbar (TIA-style): collapse/expand all, add new block.
function setAllCollapsed(collapsed) {
  content.querySelectorAll('.node[data-toggle]').forEach(el => {
    const kids = el.nextElementSibling;
    el.classList.toggle('collapsed', collapsed);
    if (kids && kids.classList.contains('children'))
      kids.classList.toggle('collapsed', collapsed);
  });
}
document.getElementById('btn-collapse-all').addEventListener('click', () => setAllCollapsed(true));
document.getElementById('btn-expand-all').addEventListener('click', () => setAllCollapsed(false));
document.getElementById('btn-newpou').addEventListener('click', openNewPouModal);
</script>
</body></html>
"""


class SidebarPanel(wx.Panel):
    def __init__(self, parent, project_controller_getter, open_pou_callback,
                 create_pou_callback=None):
        super().__init__(parent)
        self._get_ctr = project_controller_getter
        self._open_pou = open_pou_callback
        self._create_pou = create_pou_callback
        self._webview_ready = False
        self._last_state_json = None  # avoid pointless RunScript calls

        self.SetBackgroundColour(wx.Colour(246, 247, 249))

        self.webview = wx.html2.WebView.New(self)
        self.webview.EnableContextMenu(False)
        self.webview.AddScriptMessageHandler("bridge")
        self.webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, self._on_loaded)
        self.webview.Bind(wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, self._on_js_msg)
        self.webview.SetPage(SIDEBAR_HTML, "")

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.webview, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._refresh, self._timer)
        self._timer.Start(2000)

    def _on_loaded(self, _e):
        self._webview_ready = True
        self._refresh()

    def _on_js_msg(self, event):
        try:
            msg = json.loads(event.GetString())
        except Exception:
            return
        if msg.get("type") == "open_pou":
            name = msg.get("name")
            if name and self._open_pou:
                try:
                    self._open_pou(name)
                except Exception as exc:
                    print(f"[sidebar] open_pou({name!r}) failed: {exc}", file=sys.stderr)
        elif msg.get("type") == "create_pou":
            if self._create_pou:
                try:
                    self._create_pou(
                        msg.get("name", "").strip(),
                        msg.get("pou_type", "program"),
                        msg.get("body_language", "ST"),
                    )
                    self._refresh()
                except Exception as exc:
                    print(f"[sidebar] create_pou failed: {exc}", file=sys.stderr)

    def force_refresh(self):
        self._refresh()

    def _refresh(self, _e=None):
        try:
            state = self._gather_state()
        except Exception as exc:
            state = None
            print(f"[sidebar] gather_state failed: {exc}", file=sys.stderr)
        if not self._webview_ready:
            return
        payload = json.dumps(state)
        if payload == self._last_state_json:
            return
        self._last_state_json = payload
        # JS try/catch guards the WKWebView race where LOADED fires before the
        # page script defines render() — avoids a "Can't find variable" dialog.
        self.webview.RunScript("try{render(" + payload + ")}catch(e){}")

    def _gather_state(self):
        ctr = self._get_ctr()
        if ctr is None:
            return None
        state = {"project": None, "pous": [], "variables": [], "resources": []}

        try:
            state["project"] = ctr.GetProjectName() or "(unnamed)"
        except Exception:
            state["project"] = "(unnamed)"

        # POUs
        try:
            for name in ctr.GetProjectPouNames():
                pou_type = "program"
                lang = "ST"
                try:
                    pou_type = ctr.GetPouType(name) or "program"
                except Exception:
                    pass
                try:
                    lang = ctr.GetPouBodyType(name) or "ST"
                except Exception:
                    pass
                state["pous"].append({
                    "name": name,
                    "type": pou_type,
                    "lang": lang,
                })
        except Exception:
            pass

        # Variables for first POU (placeholder until we wire click→selection back)
        # JS keeps selectedPou state on its side; on refresh JS won't re-send
        # it, so we read variables for all POUs and let JS filter.
        # Simpler: include vars for ALL POUs keyed by name.
        all_vars = {}
        try:
            project = ctr.GetProject() if hasattr(ctr, "GetProject") else getattr(ctr, "Project", None)
            if project is not None:
                for name in ctr.GetProjectPouNames():
                    pou = project.getpou(name)
                    if pou is None:
                        continue
                    vars_list = []
                    try:
                        iface_blocks = pou.getinterface()
                        if iface_blocks is not None:
                            for block in iface_blocks.iter():
                                # block tag is like inputVars/outputVars/localVars/inOutVars/externalVars
                                tag = (getattr(block, "tag", "") or "").split("}")[-1]
                                scope_map = {
                                    "inputVars":    "input",
                                    "outputVars":   "output",
                                    "localVars":    "local",
                                    "inOutVars":    "inout",
                                    "externalVars": "external",
                                }
                                scope = scope_map.get(tag)
                                if scope is None:
                                    continue
                                # iterate <variable name="..." > <type><BOOL/></type></variable>
                                for v_el in block.iter():
                                    vtag = (getattr(v_el, "tag", "") or "").split("}")[-1]
                                    if vtag != "variable":
                                        continue
                                    vname = v_el.get("name") or ""
                                    vtype = "?"
                                    # type child has one of BOOL/INT/REAL/... as its first child
                                    type_el = v_el.find("{*}type") if hasattr(v_el, "find") else None
                                    if type_el is not None and len(type_el):
                                        first = type_el[0]
                                        tname = (getattr(first, "tag", "") or "").split("}")[-1]
                                        if tname == "derived":
                                            vtype = first.get("name") or "derived"
                                        else:
                                            vtype = tname or "?"
                                    vars_list.append({
                                        "name": vname,
                                        "scope": scope,
                                        "type": vtype,
                                    })
                    except Exception:
                        pass
                    all_vars[name] = vars_list
        except Exception:
            pass
        state["_vars_by_pou"] = all_vars
        # For now also flatten the first POU's vars into top-level (JS
        # currently shows state.variables — keep that for back-compat).
        if state["pous"]:
            state["variables"] = all_vars.get(state["pous"][0]["name"], [])

        # Resources (simple)
        try:
            project = ctr.GetProject() if hasattr(ctr, "GetProject") else getattr(ctr, "Project", None)
            if project is not None:
                for cfg in project.getconfigurations() or []:
                    cfg_name = cfg.getname()
                    for res in cfg.getresource() or []:
                        state["resources"].append(f"{cfg_name}.{res.getname()}")
        except Exception:
            pass

        return state
