"""sim_bridge — tiny HTTP server that exposes the running PLC's variable
values to a browser-based animation (loaded into our HMI WebView pane).

Design:
- One background thread runs Python's stdlib HTTPServer on 127.0.0.1:8765.
- A VariableSubscriber consumer is registered with the running
  ProjectController for each watched IEC variable. It just caches the
  latest value as data arrives from the PLC debug thread.
- Routes:
    GET /                      → elevator.html
    GET /state                 → JSON of latest cached values + meta
    POST /force?path=…&value=… → forces a variable (drives PLC inputs)
- Independent of Beremiz's SVG HMI / twisted stack. Pure stdlib + a couple
  of weak Beremiz API calls.
"""

import json
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765


class VariableSubscriber:
    """Consumer object accepted by ProjectController.SubscribeDebugIECVariable.

    Beremiz's debug dispatcher calls NewValues on us each time the debug
    thread polls a new sample from the PLC binary. With buffer_list=False
    the signature is NewValues(latest_tick, latest_value); with True it's
    NewValues(ticks_list, values_list). We cache the latest value either way.
    """

    def __init__(self, ctr, iec_path):
        self.ctr = ctr
        self.iec_path = iec_path
        self.value = None
        self.data_type = None
        self.last_update_tick = None
        self.call_count = 0
        self.last_raw = None

    def SetDataType(self, data_type):
        self.data_type = data_type

    def NewValues(self, ticks, values):
        # Beremiz dispatches each sample as either:
        #   buffer_list=False → values is a single (value, forced_flag) tuple
        #   buffer_list=True  → values is a list of such tuples
        # We unpack the actual value out of element [0]; element [1] is whether
        # the variable is currently being force-overridden.
        self.call_count += 1
        if isinstance(values, list):
            if not values:
                return
            sample = values[-1]
            self.last_update_tick = ticks[-1] if isinstance(ticks, list) else ticks
        else:
            sample = values
            self.last_update_tick = ticks
        if isinstance(sample, tuple) and len(sample) >= 1:
            self.value = sample[0]
        else:
            self.value = sample

    # Kept for compatibility — __tick__ subscriptions would call this.
    def NewDataAvailable(self, ticks=None):
        pass


class Bridge:
    """Holds subscribers + the HTTP server. One per running simulation."""

    def __init__(self, ctr, variables, page_html):
        """
        variables: list of (iec_path, friendly_name)
            iec_path is the full path PLC uses, e.g. 'Config0.Res0.instance0.CarPosition'
            friendly_name is what the JS sees, e.g. 'car_position'
        page_html: HTML/SVG/JS string served at GET /
        """
        self.ctr = ctr
        self.subs = {}
        self.friendly_to_path = {}
        idx_map = getattr(ctr, "_IECPathToIdx", {}) or {}
        for iec_path, friendly in variables:
            sub = VariableSubscriber(ctr, iec_path)
            ctr.SubscribeDebugIECVariable(iec_path, sub, buffer_list=False)
            # Beremiz only auto-sets data_type via the DebugViewer wrapper.
            # We call SetDataType ourselves so the JSON state has type info.
            if iec_path in idx_map:
                sub.SetDataType(idx_map[iec_path][1])
            self.subs[iec_path] = sub
            self.friendly_to_path[friendly] = iec_path
        self.page_html = page_html
        self._server = None
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        bridge = self
        handler = _make_handler(bridge)
        self._server = ThreadingHTTPServer((BRIDGE_HOST, BRIDGE_PORT), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="plc-cursor-sim-bridge"
        )
        self._thread.start()

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
        for iec_path, sub in self.subs.items():
            try:
                self.ctr.UnsubscribeDebugIECVariable(iec_path, sub)
            except Exception:
                pass
        self.subs.clear()

    def state(self):
        out = {"ts": time.time(), "variables": {}}
        for friendly, iec_path in self.friendly_to_path.items():
            sub = self.subs.get(iec_path)
            out["variables"][friendly] = {
                "value": sub.value if sub else None,
                "type": sub.data_type if sub else None,
                "calls": sub.call_count if sub else 0,
                "last_raw": sub.last_raw if sub else None,
            }
        return out

    def force(self, friendly_or_path, value_str):
        iec_path = self.friendly_to_path.get(friendly_or_path, friendly_or_path)
        if iec_path not in self.subs:
            return {"error": f"not subscribed: {iec_path}"}
        idx_map = getattr(self.ctr, "_IECPathToIdx", {})
        if iec_path not in idx_map:
            return {"error": f"unknown iec_path: {iec_path}"}
        iec_type = idx_map[iec_path][1]
        fvalue = _coerce(value_str, iec_type)
        self.ctr.ForceDebugIECVariable(iec_path, fvalue)
        return {"ok": True, "iec_path": iec_path, "value": fvalue}

    def release(self, friendly_or_path):
        iec_path = self.friendly_to_path.get(friendly_or_path, friendly_or_path)
        try:
            self.ctr.ReleaseDebugIECVariable(iec_path)
            return {"ok": True}
        except Exception as exc:
            return {"error": str(exc)}


def _coerce(s, iec_type):
    t = (iec_type or "").upper()
    if t == "BOOL":
        return str(s).strip().lower() in ("true", "1", "t", "yes", "on")
    if t in ("REAL", "LREAL"):
        return float(s)
    if t.endswith("INT") or t in ("BYTE", "WORD", "DWORD", "LWORD"):
        return int(float(s))
    return s


def _make_handler(bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs):
            pass  # silence stdout spam

        def _json(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                # Serve whatever HTML this bridge was constructed with.
                # (Earlier we hot-reloaded the bundled elevator.html from
                # disk for dev convenience, but that clobbered any custom
                # page registered via the agent's set_hmi tool.)
                body = bridge.page_html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/state":
                return self._json(200, bridge.state())
            self._json(404, {"error": "not found", "path": parsed.path})

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if parsed.path == "/force":
                path = (qs.get("path") or [None])[0]
                value = (qs.get("value") or [None])[0]
                if not path or value is None:
                    return self._json(400, {"error": "missing path or value"})
                return self._json(200, bridge.force(path, value))
            if parsed.path == "/release":
                path = (qs.get("path") or [None])[0]
                if not path:
                    return self._json(400, {"error": "missing path"})
                return self._json(200, bridge.release(path))
            self._json(404, {"error": "not found", "path": parsed.path})

    return Handler


def load_elevator_page():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "elevator.html"), "r", encoding="utf-8") as f:
        return f.read()
