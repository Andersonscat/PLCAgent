"""ladder_html — renders an animated SVG ladder-logic view as an HTML
fragment. Used by hmi_autogen as a "Ladder Logic" tab alongside the
process mimic, giving the HMI an unmistakable PLC look.

Each contact/coil is drawn with classic symbol shapes (`--| |--`,
`--|/|--`, `--( )--`, `--(/)--`); the renderer JS polls /state at 10 Hz
and colors elements green-on-energized.
"""

import json
import re


# ---------------------------------------------------------------------------
# Auto-synthesis: build a believable ladder from the project's variables.
# ---------------------------------------------------------------------------


_INPUT_HINTS = re.compile(r"^(call|btn|req|request|start|stop|emerg|pb|sensor|atfloor|door[a-z]*|enable|reset)", re.I)
_OUTPUT_HINTS = re.compile(r"^(motor|out|lamp|valve|run|coil|alarm|relay|fan|pump|drive)", re.I)


def synth_rungs(vars_info, max_rungs=10):
    """Return a list of rung dicts based on whatever variables exist.

    A rung = {branches: [[ContactSpec...]...], series_after: [...],
              coil: {var, negated}, label?: str}.
    """
    inputs = [v[0] for v in vars_info if v[2] == "BOOL" and _INPUT_HINTS.match(v[0])]
    outputs = [v[0] for v in vars_info if v[2] == "BOOL" and _OUTPUT_HINTS.match(v[0])]
    other_bools = [v[0] for v in vars_info if v[2] == "BOOL"
                   and v[0] not in inputs and v[0] not in outputs]

    # Fallback if heuristics found nothing — split all BOOLs in halves.
    if not inputs and not outputs:
        all_bool = [v[0] for v in vars_info if v[2] == "BOOL"]
        if not all_bool:
            return []
        mid = max(1, len(all_bool) // 2)
        inputs = all_bool[:mid]
        outputs = all_bool[mid:] or all_bool[:1]

    rungs = []

    # Group calls/requests as parallel input on the first rung (seal-in shape).
    calls = [v for v in inputs if re.match(r"^(call|req|request|btn)", v, re.I)]
    if outputs and len(calls) >= 2:
        primary_out = outputs[0]
        stop_var = next((v for v in inputs if re.match(r"^stop", v, re.I)), None)
        rungs.append({
            "label": f"{primary_out} dispatch — any call",
            "branches": [[{"var": c}] for c in calls[:5]],
            "series_after": ([{"var": stop_var, "negated": True}] if stop_var else []),
            "coil": {"var": primary_out},
        })

    # One rung per remaining output, with 2-3 input contacts in series.
    remaining_outputs = outputs[1:] if rungs else outputs
    for out in remaining_outputs[: max_rungs - len(rungs)]:
        picks = (inputs + other_bools)[:3]
        rungs.append({
            "label": f"{out} — interlock",
            "branches": [],
            "series_before": [{"var": v} for v in picks[:2]] if picks else [],
            "series_after": [{"var": picks[2]}] if len(picks) >= 3 else [],
            "coil": {"var": out},
        })

    # If still need filler, add a few "monitor" rungs (single contact → coil
    # with the same name, prefix with M_) — pure decoration but reads as a
    # complex live ladder.
    if len(rungs) < 4 and (inputs or other_bools):
        for src in (inputs + other_bools)[: 4 - len(rungs)]:
            rungs.append({
                "label": f"monitor {src}",
                "branches": [],
                "series_before": [{"var": src}],
                "series_after": [],
                "coil": {"var": src + "_status"},  # virtual — will read None, render gray
            })

    return rungs


# ---------------------------------------------------------------------------
# HTML/JS renderer
# ---------------------------------------------------------------------------


def render_ladder_html_fragment(rungs):
    """Return an HTML/JS fragment that renders the given rungs as an animated
    SVG ladder. Drop this into an existing HMI page; it expects window.fetch
    + /state to be available (same bridge as the rest of the HMI)."""
    if not rungs:
        return (
            "<div style='padding:40px;text-align:center;color:#6c6f78;font-size:12px'>"
            "No rungs to render — declare a few BOOL variables and reopen.</div>"
        )
    return f"""
<div id="ladder-wrap" style="padding:14px 14px 24px 14px;color:#d6d6d6;
     font:13px -apple-system,Helvetica,sans-serif;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
    <div style="font-size:11px;color:#6c6f78;text-transform:uppercase;letter-spacing:.6px;">
      Ladder Logic · {len(rungs)} rungs
    </div>
    <div id="ladder-tick" style="font:10.5px ui-monospace,monospace;color:#3a6f9c;">
      0 Hz
    </div>
  </div>
  <svg id="ladder-svg" width="100%" viewBox="0 0 720 {60 + len(rungs)*66}"
       xmlns="http://www.w3.org/2000/svg"
       style="background:#0a0a0e;border:1px solid #2a2c33;border-radius:6px;"></svg>
</div>
<script>
(function() {{
  const RUNGS = {json.dumps(rungs)};
  const svg = document.getElementById('ladder-svg');
  const tickEl = document.getElementById('ladder-tick');
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const LEFT_X = 30, RIGHT_X = 690;
  const RUNG_TOP = 30, RUNG_DY = 66;
  const CONTACT_W = 60, CONTACT_H = 22;
  const COIL_W = 40, COIL_H = 22;
  const BRANCH_DY = 28;

  const ON = '#67d97a', OFF = '#3a3a44', INK = '#d6d6d6', DIM = '#7a7a82';

  // Cache of variable name → current value (updated by poll loop)
  let live = {{}};

  function mkEl(name, attrs, children) {{
    const el = document.createElementNS(SVG_NS, name);
    for (const k in (attrs || {{}})) el.setAttribute(k, attrs[k]);
    for (const c of (children || [])) el.appendChild(c);
    return el;
  }}
  function mkText(x, y, str, attrs) {{
    const t = mkEl('text', Object.assign({{x:x, y:y, fill:'currentColor',
      'font-family':'ui-monospace,monospace', 'font-size':'10'}}, attrs || {{}}));
    t.textContent = str;
    return t;
  }}

  function isOn(varName) {{
    if (!varName) return false;
    const v = live[varName];
    if (v === undefined || v === null) return false;
    return !!v;
  }}

  // True if contact lets signal through (closed)
  function contactClosed(spec) {{
    const on = isOn(spec.var);
    return spec.negated ? !on : on;
  }}

  function drawContact(spec, x, y, energized) {{
    const g = mkEl('g', {{class:'contact'}});
    const color = energized && contactClosed(spec) ? ON : OFF;
    const cy = y + CONTACT_H/2;
    // wires to/from contact
    g.appendChild(mkEl('line', {{x1:x, y1:cy, x2:x+12, y2:cy,
      stroke: energized ? ON : OFF, 'stroke-width': 2}}));
    g.appendChild(mkEl('line', {{x1:x+CONTACT_W-12, y1:cy, x2:x+CONTACT_W, y2:cy,
      stroke: (energized && contactClosed(spec)) ? ON : OFF, 'stroke-width': 2}}));
    // contact symbol — two short vertical bars
    g.appendChild(mkEl('line', {{x1:x+14, y1:y, x2:x+14, y2:y+CONTACT_H,
      stroke: color, 'stroke-width': 2.5}}));
    g.appendChild(mkEl('line', {{x1:x+CONTACT_W-14, y1:y, x2:x+CONTACT_W-14, y2:y+CONTACT_H,
      stroke: color, 'stroke-width': 2.5}}));
    if (spec.negated) {{
      // diagonal slash to denote NC
      g.appendChild(mkEl('line', {{x1:x+12, y1:y+CONTACT_H-3, x2:x+CONTACT_W-12, y2:y+3,
        stroke: color, 'stroke-width': 1.5}}));
    }}
    // variable name above
    const lbl = mkText(x + CONTACT_W/2, y - 4, spec.var,
                       {{'text-anchor':'middle', fill: INK, 'font-size': '10'}});
    g.appendChild(lbl);
    return g;
  }}

  function drawCoil(spec, x, y, energized) {{
    const g = mkEl('g', {{class:'coil'}});
    const cy = y + COIL_H/2;
    const color = energized ? ON : OFF;
    // wire in
    g.appendChild(mkEl('line', {{x1:x, y1:cy, x2:x+8, y2:cy,
      stroke: energized ? ON : OFF, 'stroke-width': 2}}));
    // wire out to right rail
    g.appendChild(mkEl('line', {{x1:x+COIL_W-8, y1:cy, x2:x+COIL_W, y2:cy,
      stroke: energized ? ON : OFF, 'stroke-width': 2}}));
    // half-ellipses
    g.appendChild(mkEl('path', {{
      d: `M ${{x+8}} ${{y+2}} Q ${{x-4}} ${{cy}} ${{x+8}} ${{y+COIL_H-2}}`,
      stroke: color, 'stroke-width': 2.5, fill: 'none'
    }}));
    g.appendChild(mkEl('path', {{
      d: `M ${{x+COIL_W-8}} ${{y+2}} Q ${{x+COIL_W+4}} ${{cy}} ${{x+COIL_W-8}} ${{y+COIL_H-2}}`,
      stroke: color, 'stroke-width': 2.5, fill: 'none'
    }}));
    if (spec.negated) {{
      g.appendChild(mkEl('line', {{x1:x+8, y1:y+COIL_H-3, x2:x+COIL_W-8, y2:y+3,
        stroke: color, 'stroke-width': 1.5}}));
    }}
    g.appendChild(mkText(x+COIL_W/2, y-4, spec.var,
      {{'text-anchor':'middle', fill: INK, 'font-size': '10'}}));
    return g;
  }}

  function drawWire(x1, y1, x2, y2, energized) {{
    return mkEl('line', {{x1:x1, y1:y1, x2:x2, y2:y2,
      stroke: energized ? ON : OFF, 'stroke-width': 2}});
  }}

  function renderRung(rung, rIdx) {{
    const yTop = RUNG_TOP + rIdx * RUNG_DY;
    const yCenter = yTop + CONTACT_H/2;
    const branches = rung.branches || [];
    const sbefore = rung.series_before || [];
    const safter = rung.series_after || [];
    const coil = rung.coil;
    const g = mkEl('g', {{}});

    // rung label (small dim text)
    if (rung.label) {{
      g.appendChild(mkText(LEFT_X, yTop - 12, rung.label,
        {{fill: DIM, 'font-size': '9'}}));
    }}

    // Layout positions (mirror the same algorithm tools.add_ladder_rung uses)
    let cursor = LEFT_X + 16;
    const sbXs = [];
    for (let i = 0; i < sbefore.length; i++) {{
      sbXs.push(cursor);
      cursor += CONTACT_W + 14;
    }}
    const splitX = cursor;
    const branchXs = [];
    let maxBranchW = 0;
    for (const branch of branches) {{
      const xs = [];
      let bx = splitX;
      for (let i = 0; i < branch.length; i++) {{
        xs.push(bx);
        bx += CONTACT_W + 14;
      }}
      branchXs.push(xs);
      if (bx - splitX > maxBranchW) maxBranchW = bx - splitX;
    }}
    const mergeX = splitX + (branches.length ? maxBranchW : 0);
    const saXs = [];
    cursor = mergeX;
    for (let i = 0; i < safter.length; i++) {{
      saXs.push(cursor);
      cursor += CONTACT_W + 14;
    }}
    const coilX = Math.min(cursor, RIGHT_X - COIL_W - 16);

    // energization (simplified: rail is always live; we propagate left-to-right)
    const leftLive = true;

    // ---- series_before ----
    let upstream = leftLive;
    let prevX = LEFT_X;
    for (let i = 0; i < sbefore.length; i++) {{
      const x = sbXs[i];
      g.appendChild(drawContact(sbefore[i], x, yTop, upstream));
      // wire from previous endpoint to contact input
      g.appendChild(drawWire(prevX, yCenter, x, yCenter, upstream));
      upstream = upstream && contactClosed(sbefore[i]);
      prevX = x + CONTACT_W;
    }}
    // wire from last sbefore to split point
    if (prevX < splitX) g.appendChild(drawWire(prevX, yCenter, splitX, yCenter, upstream));

    // ---- branches ----
    let afterMergeLive = upstream;
    if (branches.length > 0) {{
      let anyBranchOn = false;
      // For each branch, simulate up to its end
      const branchEnds = [];
      for (let bi = 0; bi < branches.length; bi++) {{
        const by = yCenter + bi * BRANCH_DY;
        // If sbefore existed, branch input is upstream from split point; else it's left rail
        let branchUp = sbefore.length > 0 ? upstream : leftLive;
        let bPrev = sbefore.length > 0 ? splitX : LEFT_X;
        // vertical drop from split (or rail) down to this branch row
        if (bi === 0) {{
          // top branch is on main row already
        }} else {{
          g.appendChild(drawWire(splitX, yCenter, splitX, by, branchUp));
          bPrev = splitX;
        }}
        const branch = branches[bi];
        if (branch.length === 0) {{
          // bare wire: signal goes straight through
          g.appendChild(drawWire(bPrev, by, mergeX, by, branchUp));
          branchEnds.push({{x: mergeX, y: by, live: branchUp}});
          if (branchUp) anyBranchOn = true;
          continue;
        }}
        for (let ci = 0; ci < branch.length; ci++) {{
          const x = branchXs[bi][ci];
          g.appendChild(drawWire(bPrev, by, x, by, branchUp));
          g.appendChild(drawContact(branch[ci], x, by - CONTACT_H/2, branchUp));
          branchUp = branchUp && contactClosed(branch[ci]);
          bPrev = x + CONTACT_W;
        }}
        // wire from end of branch to merge point
        g.appendChild(drawWire(bPrev, by, mergeX, by, branchUp));
        // vertical wire from branch back up to merge node
        if (bi > 0) {{
          g.appendChild(drawWire(mergeX, by, mergeX, yCenter, branchUp));
        }}
        branchEnds.push({{x: mergeX, y: by, live: branchUp}});
        if (branchUp) anyBranchOn = true;
      }}
      afterMergeLive = anyBranchOn;
    }}

    // ---- series_after ----
    let prev = mergeX;
    let postLive = afterMergeLive;
    for (let i = 0; i < safter.length; i++) {{
      const x = saXs[i];
      g.appendChild(drawWire(prev, yCenter, x, yCenter, postLive));
      g.appendChild(drawContact(safter[i], x, yTop, postLive));
      postLive = postLive && contactClosed(safter[i]);
      prev = x + CONTACT_W;
    }}
    // wire to coil
    g.appendChild(drawWire(prev, yCenter, coilX, yCenter, postLive));
    // coil
    g.appendChild(drawCoil(coil, coilX, yTop, postLive));
    // wire from coil to right rail
    g.appendChild(drawWire(coilX + COIL_W, yCenter, RIGHT_X, yCenter, postLive));

    return g;
  }}

  function rebuild() {{
    // Clear and redraw everything (cheap enough for ~10 rungs at 10 Hz)
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    // Power rails
    const totalH = 20 + RUNGS.length * RUNG_DY;
    svg.appendChild(mkEl('line', {{x1: LEFT_X, y1: 14, x2: LEFT_X, y2: totalH+14,
      stroke: ON, 'stroke-width': 3}}));
    svg.appendChild(mkEl('line', {{x1: RIGHT_X, y1: 14, x2: RIGHT_X, y2: totalH+14,
      stroke: ON, 'stroke-width': 3}}));
    for (let i = 0; i < RUNGS.length; i++) {{
      svg.appendChild(renderRung(RUNGS[i], i));
    }}
  }}

  let frames = 0, lastSec = Date.now();
  async function poll() {{
    try {{
      const r = await fetch('/state', {{cache: 'no-store'}});
      const j = await r.json();
      live = {{}};
      for (const [n, info] of Object.entries(j.variables || {{}})) {{
        live[n] = info.value;
      }}
      rebuild();
      frames++;
      const now = Date.now();
      if (now - lastSec > 1000) {{
        tickEl.textContent = frames + ' Hz';
        frames = 0; lastSec = now;
      }}
    }} catch (e) {{}}
  }}
  setInterval(poll, 100);
  poll();
}})();
</script>
"""
