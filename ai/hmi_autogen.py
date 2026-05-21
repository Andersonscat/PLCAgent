"""hmi_autogen — deterministic HMI generation from the running PLC's
variable table. Triggered automatically by chat_panel after start_simulation
so the engineer always sees a visual interface, never an empty pane.

Two strategies:

1. Elevator detector — if variables look like an elevator (any of Call_N /
   Request_N / Req_N / Btn_N pattern present + a position variable + at
   least one motor variable), build an elevator-shaped SVG sized by the
   detected number of floors.

2. Generic fallback — render each variable as a card with its live value,
   plus force/release buttons for BOOLs and a numeric input + force for
   INT/REAL. Always works for any project.

Both return (html: str, watch_vars: list[str], caption: str).
"""

import re


# ---------------------------------------------------------------------------
# Detection & dispatch
# ---------------------------------------------------------------------------


_FLOOR_PREFIX_RE = re.compile(r"^(call|request|req|btn|floor|button)[_\-]?(\d+)$", re.I)
_AT_FLOOR_RE = re.compile(r"^atfloor[_\-]?(\d+)$|^floor[_\-]?(\d+)[_\-]?(at|sensor)$", re.I)
_POSITION_NAMES = {"carposition", "position", "currentfloor", "carpos", "elevator_pos"}
_TARGET_NAMES = {"targetfloor", "target", "targetpos", "destination"}
_MOTOR_UP_NAMES = {"motorup", "motor_up", "up", "moveup", "goingup"}
_MOTOR_DOWN_NAMES = {"motordown", "motor_down", "down", "movedown", "goingdown"}
_DOOR_OPEN_NAMES = {"dooropen", "door_open", "door", "opendoor", "doorsopen"}


def auto_generate(idx_map):
    """idx_map: {full_iec_path: (idx, type_string), ...}

    Returns (html, watch_vars, caption). Always succeeds — falls back to
    generic dashboard if no pattern matches.
    """
    # Build (short_name, full_path, type) tuples.
    vars_info = []
    for full_path, (_idx, typ) in idx_map.items():
        short = full_path.split(".")[-1]
        vars_info.append((short, full_path, typ))

    elevator = _try_build_elevator(vars_info)
    if elevator is not None:
        return elevator

    return _build_generic_dashboard(vars_info)


# ---------------------------------------------------------------------------
# Elevator builder
# ---------------------------------------------------------------------------


def _try_build_elevator(vars_info):
    short_to_full = {v[0]: v[1] for v in vars_info}
    short_lower = {v[0].lower(): v[0] for v in vars_info}

    # Find call/request buttons by suffix number.
    call_floors = {}   # floor_number -> short_name
    for short, _full, _typ in vars_info:
        m = _FLOOR_PREFIX_RE.match(short)
        if m:
            n = int(m.group(2))
            call_floors[n] = short
    if not call_floors:
        return None

    # Find core elevator components.
    position = _find_first(vars_info, _POSITION_NAMES)
    motor_up = _find_first(vars_info, _MOTOR_UP_NAMES)
    motor_down = _find_first(vars_info, _MOTOR_DOWN_NAMES)
    if position is None or motor_up is None or motor_down is None:
        return None

    door_open = _find_first(vars_info, _DOOR_OPEN_NAMES)
    target = _find_first(vars_info, _TARGET_NAMES)

    # AtFloor sensors (if present)
    at_floor = {}
    for short, _full, _typ in vars_info:
        m = _AT_FLOOR_RE.match(short)
        if m:
            n = int(next(g for g in m.groups() if g and g.isdigit()))
            at_floor[n] = short

    n_floors = max(call_floors.keys())
    if n_floors < 2:
        return None

    floors = sorted(call_floors.keys())

    watch_vars = list(call_floors.values()) + [position]
    if motor_up: watch_vars.append(motor_up)
    if motor_down: watch_vars.append(motor_down)
    if door_open: watch_vars.append(door_open)
    if target: watch_vars.append(target)
    watch_vars.extend(at_floor.values())

    html = _render_elevator_html(
        n_floors=n_floors,
        floors=floors,
        call_var={n: call_floors[n] for n in floors},
        at_var={n: at_floor.get(n) for n in floors},
        position_var=position,
        motor_up_var=motor_up,
        motor_down_var=motor_down,
        door_var=door_open,
        target_var=target,
    )
    return (html, watch_vars, f"Elevator HMI ({n_floors} floors)")


def _find_first(vars_info, name_set):
    for short, _full, _typ in vars_info:
        if short.lower() in name_set:
            return short
    return None


def _render_elevator_html(n_floors, floors, call_var, at_var,
                         position_var, motor_up_var, motor_down_var,
                         door_var, target_var):
    SHAFT_TOP = 40
    SHAFT_BOTTOM = 580
    RAIL_LEFT = 50
    RAIL_RIGHT = 210
    floor_height = (SHAFT_BOTTOM - SHAFT_TOP) // n_floors
    # Floor y centers (top → high floor, bottom → floor 1)
    floor_centers = {}
    for i, fnum in enumerate(sorted(floors)):
        # fnum=1 → bottom, fnum=n → top
        floor_centers[fnum] = SHAFT_BOTTOM - (fnum - 0.5) * floor_height
    svg_height = SHAFT_BOTTOM + 40

    # SVG elements
    rails_svg = (
        f'<rect x="{RAIL_LEFT}" y="{SHAFT_TOP}" '
        f'width="{RAIL_RIGHT-RAIL_LEFT}" height="{SHAFT_BOTTOM-SHAFT_TOP}" '
        f'fill="#0a0a0e" stroke="#3a3a44" stroke-width="2"/>'
    )
    # Floor dividers + labels + LEDs
    floor_lines = []
    floor_labels = []
    led_svg = []
    for fnum in sorted(floors):
        y = SHAFT_BOTTOM - (fnum - 1) * floor_height  # divider y
        if fnum > 1:
            floor_lines.append(
                f'<line x1="{RAIL_LEFT}" y1="{y}" x2="{RAIL_RIGHT}" y2="{y}" '
                f'stroke="#3a3a44" stroke-width="1"/>'
            )
        cy = floor_centers[fnum]
        floor_labels.append(
            f'<text x="{RAIL_LEFT-6}" y="{cy+4}" font-size="11" fill="#7a7a82" '
            f'text-anchor="end">F{fnum}</text>'
        )
        led_svg.append(
            f'<circle id="led-f{fnum}" cx="{RAIL_RIGHT+14}" cy="{cy}" '
            f'r="5" fill="#3a3a44"/>'
        )

    # Buttons HTML
    btn_html = []
    for fnum in sorted(floors, reverse=True):
        label = f"Floor {fnum}" + (" — Lobby" if fnum == 1 else "")
        btn_html.append(
            f'<button data-var="{call_var[fnum]}">{label}</button>'
        )

    # JS configs
    js_config = {
        "position": position_var,
        "motor_up": motor_up_var,
        "motor_down": motor_down_var,
        "door": door_var,
        "target": target_var,
        "n_floors": n_floors,
        "floor_centers": {str(k): v for k, v in floor_centers.items()},
        "at_floor": {str(k): v for k, v in at_var.items() if v},
        "calls": {str(k): v for k, v in call_var.items()},
        "rail_left": RAIL_LEFT,
        "rail_right": RAIL_RIGHT,
    }
    import json
    config_json = json.dumps(js_config)

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
 :root {{ --bg:#15171c; --line:#3a3a44; --ink:#d6d6d6; --dim:#7a7a82;
          --accent:#f0a13a; --on:#67d97a; --off:#3a3a44; --car:#6ab0ff; }}
 * {{ box-sizing: border-box; }}
 html,body {{ margin:0; padding:0; height:100%; background:var(--bg);
             color:var(--ink); font:13px -apple-system,Helvetica,sans-serif; }}
 .wrap {{ display:flex; height:100%; padding:14px; gap:14px; }}
 .shaft {{ flex:0 0 auto; }}
 .panel {{ flex:1; background:#1e1e22; border:1px solid var(--line);
           border-radius:8px; padding:14px; display:flex; flex-direction:column; gap:10px; }}
 h3 {{ margin:0; font-size:11px; color:var(--dim); text-transform:uppercase; letter-spacing:.5px; }}
 .btns {{ display:flex; flex-direction:column; gap:6px; }}
 .btns button {{ background:#1a1c20; color:var(--ink); border:1px solid var(--line);
                 border-radius:5px; padding:10px 12px; font-size:13px; cursor:pointer;
                 text-align:left; transition:all .12s; }}
 .btns button:hover {{ background:#26262d; }}
 .btns button.lit {{ background:#3a2a14; border-color:#a06d28; color:#e0bd6c; }}
 .status {{ font:12px ui-monospace,monospace; color:var(--dim);
            background:#101015; border:1px solid var(--line); border-radius:5px;
            padding:8px 11px; line-height:1.6; }}
 .status b {{ color:var(--ink); font-weight:500; }}
 .leds {{ display:flex; flex-direction:column; gap:6px; font-size:11.5px; color:var(--dim); }}
 .leds .row {{ display:flex; align-items:center; gap:8px; }}
 .leds .led {{ width:8px; height:8px; border-radius:50%; background:var(--off); transition:background .15s; }}
 .leds .led.on {{ background:var(--on); box-shadow:0 0 6px var(--on); }}
 .footer {{ font-size:10.5px; color:var(--dim); opacity:.6; margin-top:auto; }}
 .debug {{ font:11px ui-monospace,monospace; color:#8a8a92; background:#101015;
           border:1px solid var(--line); border-radius:5px; padding:6px 9px; min-height:18px; }}
</style></head>
<body>
<div class="wrap">

<svg class="shaft" width="240" height="{svg_height}" viewBox="0 0 240 {svg_height}"
  {rails_svg}
  {''.join(floor_lines)}
  {''.join(floor_labels)}
  {''.join(led_svg)}
  <g id="car" transform="translate(130, {SHAFT_BOTTOM - floor_height/2})">
    <rect x="-55" y="-{floor_height//2 - 5}" width="110" height="{floor_height - 10}"
          fill="#101015"/>
    <rect id="door-left"  x="-55" y="-{floor_height//2 - 5}"
          width="55" height="{floor_height - 10}" fill="#2d6ca8" stroke="#1a4570"/>
    <rect id="door-right" x="0" y="-{floor_height//2 - 5}"
          width="55" height="{floor_height - 10}" fill="#2d6ca8" stroke="#1a4570"/>
    <rect x="-60" y="-{floor_height//2}" width="120" height="{floor_height}"
          fill="none" stroke="#6ab0ff" stroke-width="2.5" rx="3"/>
  </g>
</svg>

<div class="panel">
  <h3>Floor calls</h3>
  <div class="btns" id="btns">{''.join(btn_html)}</div>

  <h3>Status</h3>
  <div class="status" id="status">Connecting…</div>

  <h3>Live signals</h3>
  <div class="leds">
    <div class="row"><div id="sig-up" class="led"></div>MotorUp ({motor_up_var})</div>
    <div class="row"><div id="sig-dn" class="led"></div>MotorDown ({motor_down_var})</div>
    {'<div class="row"><div id="sig-door" class="led"></div>Door ('+(door_var or '')+')</div>' if door_var else ''}
  </div>

  <div class="footer">PLC-driven HMI · 10 Hz · {n_floors} floors · auto-generated from variables</div>
  <div class="debug" id="dbg">(click a floor to call the car)</div>
</div>
</div>

<script>
const CONF = {config_json};
const API = location.origin;
const $ = id => document.getElementById(id);
const car = $('car');
const doorL = $('door-left');
const doorR = $('door-right');

function val(vars, name, fallback) {{
  const v = vars[name];
  return (v && v.value !== null && v.value !== undefined) ? v.value : fallback;
}}

function carY(pos) {{
  pos = Math.max(1, Math.min(CONF.n_floors, Number(pos) || 1));
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  const a = CONF.floor_centers[lo], b = CONF.floor_centers[hi];
  return a + (b - a) * (pos - lo);
}}

async function poll() {{
  try {{
    const r = await fetch(API + '/state', {{cache: 'no-store'}});
    const j = await r.json();
    render(j.variables || {{}});
  }} catch (e) {{
    $('status').innerHTML = '<b style="color:#ff7878">disconnected</b>';
  }}
}}

function render(vars) {{
  const pos = Number(val(vars, CONF.position, 1));
  const mup = !!val(vars, CONF.motor_up, false);
  const mdn = !!val(vars, CONF.motor_down, false);
  const dor = CONF.door ? !!val(vars, CONF.door, false) : false;

  car.setAttribute('transform', `translate(130, ${{carY(pos).toFixed(1)}})`);
  const slide = dor ? 50 : 0;
  doorL.setAttribute('x', -55 - slide);
  doorR.setAttribute('x', 0 + slide);

  for (const [fn, name] of Object.entries(CONF.at_floor)) {{
    const led = $('led-f' + fn);
    if (led) led.setAttribute('fill', val(vars, name, false) ? '#67d97a' : '#3a3a44');
  }}

  $('sig-up').classList.toggle('on', mup);
  $('sig-dn').classList.toggle('on', mdn);
  if (CONF.door) $('sig-door').classList.toggle('on', dor);

  // Button "lit" state if its request is currently TRUE
  document.querySelectorAll('#btns button').forEach(b => {{
    const lit = !!val(vars, b.dataset.var, false);
    b.classList.toggle('lit', lit);
  }});

  // Status text
  let curFloor = '—';
  for (const [fn, n] of Object.entries(CONF.at_floor)) {{
    if (val(vars, n, false)) {{ curFloor = fn; break; }}
  }}
  let calls = [];
  for (const [fn, n] of Object.entries(CONF.calls)) {{
    if (val(vars, n, false)) calls.push('F' + fn);
  }}
  const tgt = CONF.target ? val(vars, CONF.target, 0) : null;
  $('status').innerHTML =
    'Position: <b>' + pos.toFixed(2) + '</b> · At floor: <b>' + curFloor + '</b><br>' +
    'Motor: <b>' + (mup ? 'UP' : mdn ? 'DOWN' : 'idle') + '</b>' +
    (CONF.door ? ' · Door: <b>' + (dor ? 'OPEN' : 'closed') + '</b>' : '') +
    (tgt ? '<br>Target: <b>F' + tgt + '</b>' : '') +
    '<br>Calls: ' + (calls.length ? calls.join(', ') : '<span style="color:#7a7a82">none</span>');
}}

document.querySelectorAll('#btns button').forEach(b => {{
  b.addEventListener('click', async () => {{
    const v = b.dataset.var;
    const ts = new Date().toLocaleTimeString().split(' ')[0];
    try {{
      const r = await fetch(API + '/force?path=' + v + '&value=TRUE', {{method:'POST'}});
      const j = await r.json();
      $('dbg').innerHTML = j.ok
        ? '<span style="color:#67d97a">[' + ts + '] force ' + v + ' → ok</span>'
        : '<span style="color:#ff7878">[' + ts + '] ' + JSON.stringify(j) + '</span>';
    }} catch (e) {{
      $('dbg').innerHTML = '<span style="color:#ff7878">[' + ts + '] fetch failed</span>';
    }}
    setTimeout(() => fetch(API + '/release?path=' + v, {{method:'POST'}}), 250);
  }});
}});

setInterval(poll, 100);
poll();
</script>
</body></html>
"""


# ---------------------------------------------------------------------------
# Generic dashboard builder (fallback)
# ---------------------------------------------------------------------------


def _build_generic_dashboard(vars_info):
    if not vars_info:
        return (
            "<html><body style='background:#15171c;color:#7a7a82;font-family:sans-serif;"
            "display:flex;align-items:center;justify-content:center;height:100vh;text-align:center'>"
            "<div>No debug variables registered yet.<br>"
            "<small style='opacity:.7'>Compile and start a project that declares some.</small></div>"
            "</body></html>",
            [],
            "HMI View",
        )

    watch = [v[0] for v in vars_info]
    rows_html = []
    for short, _full, typ in vars_info:
        type_class = "bool" if typ == "BOOL" else "num"
        rows_html.append(
            f'<div class="row {type_class}" data-var="{short}" data-type="{typ}">'
            f'  <span class="name">{short}</span>'
            f'  <span class="type">{typ}</span>'
            f'  <span class="value" id="v-{short}">…</span>'
            f'  <span class="actions"></span>'
            f'</div>'
        )

    import json
    return (f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
 html,body {{ margin:0; padding:0; background:#15171c; color:#e6e6ea;
              font:13px -apple-system,Helvetica,sans-serif; height:100%; }}
 .header {{ padding:12px 16px; border-bottom:1px solid #2a2c33; }}
 .header h2 {{ margin:0; font-size:14px; font-weight:500; }}
 .header p {{ margin:3px 0 0; color:#7a7a82; font-size:11.5px; }}
 .table {{ padding:8px 0; height:calc(100vh - 56px); overflow-y:auto; }}
 .row {{ display:grid; grid-template-columns: 1fr 60px 100px auto;
         align-items:center; gap:10px; padding:7px 16px;
         border-bottom:1px solid #1f2127; font:12px ui-monospace,monospace; }}
 .row:hover {{ background:#1a1c20; }}
 .name {{ color:#e6e6ea; }}
 .type {{ color:#7a7a82; font-size:10.5px; padding:1px 6px; background:#1a1c20;
          border-radius:3px; text-align:center; }}
 .value {{ color:#f0a13a; font-weight:500; }}
 .actions {{ display:flex; gap:4px; justify-content:flex-end; }}
 .actions button {{ background:#1a1c20; border:1px solid #2a2c33; color:#b5b8bf;
                    font-size:10.5px; padding:3px 8px; border-radius:3px; cursor:pointer; }}
 .actions button:hover {{ background:#252830; color:#fff; }}
 .actions input {{ background:#101015; border:1px solid #2a2c33; color:#e6e6ea;
                   font:11px ui-monospace,monospace; padding:2px 5px; border-radius:3px;
                   width:60px; }}
 ::-webkit-scrollbar {{ width:8px; }}
 ::-webkit-scrollbar-thumb {{ background:#2a2c33; border-radius:4px; }}
</style></head>
<body>
<div class="header">
  <h2>Variable Dashboard</h2>
  <p>Auto-generated · {len(vars_info)} variables · polling at 10 Hz</p>
</div>
<div class="table">{''.join(rows_html)}</div>

<script>
const API = location.origin;
const VARS = {json.dumps(watch)};

document.querySelectorAll('.row').forEach(row => {{
  const name = row.dataset.var;
  const type = row.dataset.type;
  const actions = row.querySelector('.actions');
  if (type === 'BOOL') {{
    actions.innerHTML =
      `<button data-act="t">TRUE</button>` +
      `<button data-act="f">FALSE</button>` +
      `<button data-act="r">Release</button>`;
    actions.querySelectorAll('button').forEach(b => {{
      b.addEventListener('click', async () => {{
        const a = b.dataset.act;
        if (a === 'r') {{
          await fetch(API + '/release?path=' + name, {{method:'POST'}});
        }} else {{
          await fetch(API + '/force?path=' + name + '&value=' + (a==='t'?'TRUE':'FALSE'),
                      {{method:'POST'}});
        }}
      }});
    }});
  }} else {{
    const inp = document.createElement('input');
    inp.placeholder = '0';
    const btn = document.createElement('button');
    btn.textContent = 'Force';
    const rel = document.createElement('button');
    rel.textContent = 'Release';
    actions.appendChild(inp); actions.appendChild(btn); actions.appendChild(rel);
    btn.addEventListener('click', async () => {{
      await fetch(API + '/force?path=' + name + '&value=' + encodeURIComponent(inp.value),
                  {{method:'POST'}});
    }});
    rel.addEventListener('click', async () => {{
      await fetch(API + '/release?path=' + name, {{method:'POST'}});
    }});
  }}
}});

async function poll() {{
  try {{
    const r = await fetch(API + '/state');
    const j = await r.json();
    for (const [name, info] of Object.entries(j.variables || {{}})) {{
      const el = document.getElementById('v-' + name);
      if (!el) continue;
      const v = info.value;
      if (v === null || v === undefined) el.textContent = '—';
      else if (typeof v === 'boolean') el.textContent = v ? 'TRUE' : 'FALSE';
      else if (typeof v === 'number') el.textContent = (v % 1 === 0) ? v : v.toFixed(3);
      else el.textContent = String(v);
    }}
  }} catch (e) {{}}
}}
setInterval(poll, 100);
poll();
</script>
</body></html>
""", watch, "Variable Dashboard")
