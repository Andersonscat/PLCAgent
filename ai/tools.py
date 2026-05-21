"""Agent tools — thin wrappers over ProjectController / PLCControler.

Each tool returns a JSON-serializable result. Errors are returned as
{"error": "..."} rather than raised, so the agent loop can show the
model what went wrong and let it retry.
"""

import traceback


# Tool schemas in Anthropic tool-use format. Kept in this module so the
# implementations and schemas live side-by-side.
TOOL_SCHEMAS = [
    {
        "name": "list_pous",
        "description": (
            "List all Program Organization Units (POUs) in the currently "
            "open project. Returns a list of {name, type, body_language} "
            "where type is program/function/functionBlock and body_language "
            "is ST/LD/FBD/SFC/IL."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_pou_text",
        "description": (
            "Get the body text of a POU. Only valid when the POU's body "
            "language is ST (Structured Text). For graphical POUs (LD/FBD/SFC) "
            "use get_pou_xml instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pou_name": {"type": "string", "description": "POU name as returned by list_pous"},
            },
            "required": ["pou_name"],
        },
    },
    {
        "name": "set_pou_text",
        "description": (
            "Replace the body text of a Structured Text POU. IMPORTANT: "
            "the text must contain ONLY executable statements — NO "
            "VAR_INPUT/VAR_OUTPUT/VAR blocks. Declarations live in the POU "
            "interface and are added separately via add_pou_variable. "
            "If you include VAR blocks here, Beremiz will report 'No variable "
            "defined' because it parses the interface from XML, not from body text. "
            "Example correct body: 'Motor := (Start OR Motor) AND NOT Stop;'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pou_name": {"type": "string"},
                "text": {"type": "string", "description": "Executable ST statements only — no VAR blocks"},
            },
            "required": ["pou_name", "text"],
        },
    },
    {
        "name": "add_pou_variable",
        "description": (
            "Add a variable to a POU's interface. scope is one of input/"
            "output/inout/local/external. var_type is an IEC 61131-3 type "
            "(BOOL, INT, DINT, REAL, TIME, STRING, etc., or a user-defined "
            "function block name like TON)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pou_name": {"type": "string"},
                "scope": {"type": "string", "enum": ["input", "output", "inout", "local", "external"]},
                "name": {"type": "string"},
                "var_type": {"type": "string"},
                "initial_value": {"type": "string", "description": "Optional initial value as ST literal (e.g. '0', 'TRUE', 'T#5s')"},
            },
            "required": ["pou_name", "scope", "name", "var_type"],
        },
    },
    {
        "name": "list_pou_variables",
        "description": "List declared variables (interface) of a POU.",
        "input_schema": {
            "type": "object",
            "properties": {"pou_name": {"type": "string"}},
            "required": ["pou_name"],
        },
    },
    {
        "name": "create_pou",
        "description": (
            "Create a new POU. pou_type is one of program/function/functionBlock. "
            "body_language is one of ST/LD/FBD/SFC/IL — prefer ST."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pou_name": {"type": "string"},
                "pou_type": {"type": "string", "enum": ["program", "function", "functionBlock"]},
                "body_language": {"type": "string", "enum": ["ST", "LD", "FBD", "SFC", "IL"]},
            },
            "required": ["pou_name", "pou_type", "body_language"],
        },
    },
    {
        "name": "delete_pou",
        "description": (
            "Delete a POU from the project. Use when a default empty POU "
            "(e.g. 'program0' created by File→New) is breaking compilation, "
            "or when refactoring."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"pou_name": {"type": "string"}},
            "required": ["pou_name"],
        },
    },
    {
        "name": "save_project",
        "description": "Persist buffered changes to the PLCopen XML file on disk.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "compile_project",
        "description": (
            "Build the project: ST/LD → IEC → C → native via MatIEC + platform builder. "
            "Returns success flag and any compiler diagnostics. Blocking — may take a few seconds."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "start_simulation",
        "description": (
            "Build, transfer, and start the compiled program inside the local OpenPLC simulation runtime. "
            "After success, variables become observable in the Debugger panel and can be forced via force_variable. "
            "Blocking — may take 5-10 seconds."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "stop_simulation",
        "description": "Stop the running simulation and disconnect from runtime.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_debug_variables",
        "description": (
            "List all IEC variables currently observable in the running simulation. "
            "Returns full IECPath (e.g. 'Config0.Res0.instance0.Start') and type. "
            "Call this after start_simulation to learn the exact paths needed for force_variable."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "force_variable",
        "description": (
            "Force a variable to a fixed value in the running simulation. Used to drive inputs "
            "(e.g. simulate a Start button press) or override outputs for testing. "
            "iec_path is the full path from list_debug_variables. value is a string the runtime parses "
            "by type: 'TRUE'/'FALSE' for BOOL, '42' for INT/DINT, '3.14' for REAL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iec_path": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["iec_path", "value"],
        },
    },
    {
        "name": "release_variable",
        "description": "Release a previously forced variable so it returns to PLC-controlled value.",
        "input_schema": {
            "type": "object",
            "properties": {"iec_path": {"type": "string"}},
            "required": ["iec_path"],
        },
    },
    {
        "name": "set_hmi",
        "description": (
            "Register an HTML+SVG+JS page as the live HMI for the running PLC. "
            "The page is served at http://127.0.0.1:8765/ and shown in the IDE's "
            "HMI View tab. Use this AFTER start_simulation succeeds, so the "
            "PLC's variables are known. The page can: GET /state (returns JSON "
            "{variables:{name:{value,type}}} with the watched vars) every "
            "100ms, POST /force?path=NAME&value=VALUE to drive an input, POST "
            "/release?path=NAME to release a force. Pass the variable names "
            "your HTML will reference in watch_vars — bridge subscribes them. "
            "Names match the suffix of the PLC's IECPath (case-insensitive)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "html": {
                    "type": "string",
                    "description": "Complete HTML document. Use SVG for the machine drawing. JS polls /state and POSTs /force.",
                },
                "watch_vars": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "PLC variable names the HMI reads/writes (e.g. ['Call_1','MotorUp','CurrentFloor']).",
                },
                "caption": {
                    "type": "string",
                    "description": "Tab caption, e.g. 'Elevator HMI' or 'Conveyor View'. Optional.",
                },
            },
            "required": ["html", "watch_vars"],
        },
    },
    {
        "name": "add_ladder_rung",
        "description": (
            "Append a Ladder Diagram (LD) rung to an LD POU. Supports series "
            "AND parallel branches (seal-in logic, OR-conditions). The POU "
            "must have body_language='LD' (set via create_pou). All "
            "referenced variables must exist via add_pou_variable. Layout "
            "(x/y, wiring, waypoints) is computed automatically.\n\n"
            "Rung structure: leftRail → [series_before] → [branches in parallel] "
            "→ [series_after] → coil → rightRail. Use branches=[[A],[B]] for "
            "classic seal-in: contact A OR contact B. For simple series, leave "
            "branches empty and use either `contacts` (legacy) or `series_before`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pou_name": {"type": "string"},
                "contacts": {
                    "type": "array",
                    "description": "Legacy: series chain (equivalent to series_before). Empty = unconditional coil.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "var": {"type": "string"},
                            "negated": {"type": "boolean", "description": "true for normally-closed (--/--)"},
                        },
                        "required": ["var"],
                    },
                },
                "series_before": {
                    "type": "array",
                    "description": "Contacts in series BEFORE the parallel branches.",
                    "items": {
                        "type": "object",
                        "properties": {"var": {"type": "string"}, "negated": {"type": "boolean"}},
                        "required": ["var"],
                    },
                },
                "branches": {
                    "type": "array",
                    "description": (
                        "Parallel branches (OR'd together). Each branch is a list "
                        "of contacts in series at its own row. For seal-in: "
                        "branches=[[{var:'Start'}], [{var:'Motor'}]] gives "
                        "(Start OR Motor). Empty branch [] = a wire (always TRUE)."
                    ),
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"var": {"type": "string"}, "negated": {"type": "boolean"}},
                            "required": ["var"],
                        },
                    },
                },
                "series_after": {
                    "type": "array",
                    "description": "Contacts in series AFTER the parallel branches.",
                    "items": {
                        "type": "object",
                        "properties": {"var": {"type": "string"}, "negated": {"type": "boolean"}},
                        "required": ["var"],
                    },
                },
                "coil_var": {"type": "string", "description": "Variable assigned by the coil"},
                "coil_negated": {"type": "boolean", "description": "true for negated coil (--(/)--)"},
            },
            "required": ["pou_name", "coil_var"],
        },
    },
    {
        "name": "add_ladder_move_rung",
        "description": (
            "Append a Ladder Diagram (LD) rung containing a MOVE function block "
            "— the LD/FBD equivalent of TIA Portal's MOVE box. The rung is:\n"
            "  leftRail → [enable contact] → MOVE.EN ; MOVE.ENO → rightRail\n"
            "  source (inVariable) → MOVE.IN ; MOVE.OUT → destination (outVariable)\n"
            "When the enable contact is energized, MOVE copies `source` into "
            "`destination` each scan (dst := src). The POU must have "
            "body_language='LD'. All referenced variables must already exist via "
            "add_pou_variable (source/destination must be the same data type). "
            "Layout, wiring and EN/ENO power flow are computed automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pou_name": {"type": "string"},
                "source": {"type": "string", "description": "Variable whose value is read (wired to MOVE IN)."},
                "destination": {"type": "string", "description": "Variable that receives the value (wired from MOVE OUT)."},
                "enable_var": {
                    "type": "string",
                    "description": (
                        "Optional BOOL contact gating the MOVE (wired to EN). "
                        "Omit for an unconditional copy executed every scan."
                    ),
                },
            },
            "required": ["pou_name", "source", "destination"],
        },
    },
]


def _coerce_value(value_str, iec_type):
    """Parse a string into the right Python type for ForceDebugIECVariable."""
    t = iec_type.upper()
    if t == "BOOL":
        s = value_str.strip().lower()
        if s in ("true", "1", "t", "yes", "on"):
            return True
        if s in ("false", "0", "f", "no", "off"):
            return False
        raise ValueError(f"BOOL expects TRUE/FALSE, got '{value_str}'")
    if t in ("SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT", "BYTE", "WORD", "DWORD", "LWORD"):
        return int(value_str, 0)
    if t in ("REAL", "LREAL"):
        return float(value_str)
    if t == "STRING":
        return str(value_str)
    # Time/date/duration etc — pass through as string, runtime will parse.
    return value_str


def _pou_tagname(pou_name, pou_type=None):
    """Build the tagname format PLCControler expects: 'P::Name' / 'F::Name' / 'FB::Name'."""
    prefix_map = {"program": "P", "function": "F", "functionBlock": "FB"}
    if pou_type:
        return f"{prefix_map[pou_type]}::{pou_name}"
    # Default to program if unspecified — caller should pass type when known.
    return f"P::{pou_name}"


class Tools:
    """Bound to a ProjectController instance (one per open project)."""

    def __init__(self, project_controller, logger=None, on_hmi_request=None):
        self.ctr = project_controller
        self.log = logger or (lambda msg: None)
        # Strong refs to keep listener callables alive for the duration of forcing.
        # Beremiz uses a WeakKeyDictionary internally — without our own ref the
        # subscription would be GC'd immediately after force_variable returns.
        self._forced_listeners = {}
        # Callback that wires the agent's HMI request into the chat panel /
        # HMI WebView. Signature: (html: str, matched_vars: list[(iec_path,
        # friendly)], caption: str) → None.
        self._on_hmi_request = on_hmi_request

    def dispatch(self, name, arguments):
        """Route a tool call by name. Returns a JSON-serializable result dict."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"unknown tool: {name}"}
        try:
            return handler(**arguments)
        except Exception as exc:
            self.log(f"[tool {name} failed] {exc}\n{traceback.format_exc()}")
            return {"error": str(exc)}

    # ---- individual tools -----------------------------------------------

    def _plc(self):
        """PLCControler accessor — raises if no project is open."""
        plc = getattr(self.ctr, "PLCControler", None) or self.ctr
        return plc

    def _tool_list_pous(self):
        plc = self._plc()
        pou_names = plc.GetProjectPouNames()
        result = []
        for name in pou_names:
            pou = plc.GetPou(name) if hasattr(plc, "GetPou") else None
            pou_type = pou.getpouType() if pou else "program"
            body_lang = "ST"
            try:
                body_lang = plc.GetPouBodyType(name)
            except Exception:
                pass
            result.append({"name": name, "type": pou_type, "body_language": body_lang})
        return {"pous": result}

    def _tool_get_pou_text(self, pou_name):
        plc = self._plc()
        tagname = _pou_tagname(pou_name)
        text = plc.GetEditedElementText(tagname)
        return {"pou_name": pou_name, "text": text or ""}

    def _tool_set_pou_text(self, pou_name, text):
        plc = self._plc()
        tagname = _pou_tagname(pou_name)
        plc.SetEditedElementText(tagname, text)
        if hasattr(plc, "BufferProject"):
            plc.BufferProject()
        return {"ok": True, "pou_name": pou_name, "bytes": len(text)}

    def _tool_add_pou_variable(self, pou_name, scope, name, var_type, initial_value=""):
        plc = self._plc()
        project = plc.GetProject() if hasattr(plc, "GetProject") else getattr(plc, "Project", None)
        if project is None:
            return {"error": "no project open"}
        pou = project.getpou(pou_name)
        if pou is None:
            return {"error": f"POU '{pou_name}' not found"}

        var_class_map = {
            "input": "inputVars",
            "output": "outputVars",
            "inout": "inOutVars",
            "local": "localVars",
            "external": "externalVars",
        }
        var_class = var_class_map[scope]
        var_type_obj = plc.GetVarTypeObject(var_type)
        pou.addpouVar(var_type_obj, name, var_class=var_class, initval=initial_value or "")
        if hasattr(plc, "BufferProject"):
            plc.BufferProject()
        return {"ok": True, "pou_name": pou_name, "scope": scope, "name": name, "type": var_type}

    def _tool_list_pou_variables(self, pou_name):
        plc = self._plc()
        names = plc.GetProjectPouVariableNames(pou_name)
        return {"variables": list(names)}

    def _tool_create_pou(self, pou_name, pou_type, body_language):
        plc = self._plc()
        plc.ProjectAddPou(pou_name, pou_type, body_language)
        return {"ok": True, "pou_name": pou_name}

    def _tool_delete_pou(self, pou_name):
        plc = self._plc()
        plc.ProjectRemovePou(pou_name)
        return {"ok": True, "pou_name": pou_name}

    def _tool_save_project(self):
        if hasattr(self.ctr, "SaveProject"):
            self.ctr.SaveProject()
            return {"ok": True}
        return {"error": "ProjectController has no SaveProject method"}

    # ---- simulation control --------------------------------------------

    def _tool_start_simulation(self):
        if not hasattr(self.ctr, "_Run"):
            return {"error": "ProjectController has no _Run method"}
        original_logger = self.ctr.logger
        captured = _CapturingLogger(original_logger)
        self.ctr.logger = captured
        try:
            success = self.ctr._Run()
        except Exception as exc:
            self.ctr.logger = original_logger
            return {"ok": False, "error": str(exc), "log": captured.text()}
        self.ctr.logger = original_logger
        return {"ok": bool(success), "log": captured.text()}

    def _tool_stop_simulation(self):
        if not hasattr(self.ctr, "_Stop"):
            return {"error": "ProjectController has no _Stop method"}
        try:
            self.ctr._Stop()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def _tool_list_debug_variables(self):
        idx_map = getattr(self.ctr, "_IECPathToIdx", None)
        if not idx_map:
            return {"error": "no debug variables (sim not running or build incomplete)"}
        return {
            "variables": [
                {"iec_path": path, "type": typ}
                for path, (_idx, typ) in idx_map.items()
            ]
        }

    def _tool_force_variable(self, iec_path, value):
        # Subscribe-then-force pattern. ForceDebugIECVariable is a no-op
        # for paths that aren't in IECdebug_datas, so we register a dummy
        # listener first to ensure the entry exists.
        if not hasattr(self.ctr, "SubscribeDebugIECVariable"):
            return {"error": "ProjectController has no debug subscription API"}
        idx_map = getattr(self.ctr, "_IECPathToIdx", {})
        if iec_path not in idx_map:
            return {
                "error": f"unknown iec_path '{iec_path}'; call list_debug_variables to see valid paths"
            }
        iec_type = idx_map[iec_path][1]
        try:
            fvalue = _coerce_value(value, iec_type)
        except ValueError as exc:
            return {"error": f"cannot coerce '{value}' to {iec_type}: {exc}"}

        # Keep a strong ref to listener so the WeakKeyDictionary doesn't drop it.
        listener = self._forced_listeners.setdefault(iec_path, lambda *a, **kw: None)
        self.ctr.SubscribeDebugIECVariable(iec_path, listener, buffer_list=False)
        self.ctr.ForceDebugIECVariable(iec_path, fvalue)
        return {"ok": True, "iec_path": iec_path, "value": value, "coerced": str(fvalue), "type": iec_type}

    def _tool_set_hmi(self, html, watch_vars, caption="HMI View"):
        if self._on_hmi_request is None:
            return {"error": "no HMI handler registered (chat panel not connected)"}
        idx_map = getattr(self.ctr, "_IECPathToIdx", {}) or {}
        # Build {lowercased_suffix → full_iec_path} for fuzzy matching.
        lowered = {p.split(".")[-1].lower(): p for p in idx_map.keys()}
        matched, unmatched = [], []
        for friendly in watch_vars:
            key = friendly.split(".")[-1].lower()
            path = lowered.get(key)
            if path is None:
                unmatched.append(friendly)
            else:
                matched.append((path, friendly))
        try:
            self._on_hmi_request(html, matched, caption)
        except Exception as exc:
            return {"error": f"HMI handler raised: {exc}"}
        return {
            "ok": True,
            "watched": len(matched),
            "unmatched": unmatched,
            "url": "http://127.0.0.1:8765/",
        }

    def _tool_release_variable(self, iec_path):
        if not hasattr(self.ctr, "ReleaseDebugIECVariable"):
            return {"error": "ProjectController has no debug release API"}
        self.ctr.ReleaseDebugIECVariable(iec_path)
        return {"ok": True, "iec_path": iec_path}

    def _tool_add_ladder_rung(self, pou_name,
                              contacts=None, series_before=None, branches=None,
                              series_after=None,
                              coil_var=None, coil_negated=False):
        from plcopen.plcopen import PLCOpenParser
        from collections import namedtuple
        Pt = namedtuple("Pt", ["x", "y"])

        def P(x, y):
            return Pt(x, y)

        # ---- normalize args (legacy `contacts` → series_before) -------
        if contacts is not None and series_before is None and not branches:
            series_before = contacts
        series_before = list(series_before or [])
        series_after = list(series_after or [])
        branches = [list(b) for b in (branches or [])]
        if not coil_var:
            return {"error": "coil_var required"}

        # ---- locate POU + LD body --------------------------------------
        plc = self._plc()
        project = plc.GetProject() if hasattr(plc, "GetProject") else getattr(plc, "Project", None)
        if project is None:
            return {"error": "no project open"}
        pou = project.getpou(pou_name)
        if pou is None:
            return {"error": f"POU '{pou_name}' not found"}

        try:
            body_type = plc.GetPouBodyType(pou_name)
        except Exception:
            body_type = None
        if body_type and body_type != "LD":
            return {"error": f"POU '{pou_name}' body language is '{body_type}', not 'LD'"}

        body = pou.getbody()
        if isinstance(body, list):
            body = body[0] if body else None
        if body is None:
            return {"error": "POU has no body"}
        ld = body.getcontent()

        # ---- next localId + rung count for vertical placement ---------
        existing = ld.getcontent() or []
        max_id = 0
        rung_count = 0
        max_bottom = 0
        for inst in existing:
            try:
                if inst.getlocalId() > max_id:
                    max_id = inst.getlocalId()
            except Exception:
                pass
            try:
                bottom = inst.gety() + inst.getheight()
                if bottom > max_bottom:
                    max_bottom = bottom
            except Exception:
                pass
            if type(inst).__name__ == "leftPowerRail":
                rung_count += 1
        next_id = [max_id + 1]   # mutable counter for nested helpers

        def nid():
            v = next_id[0]; next_id[0] += 1
            return v

        # ---- layout constants -----------------------------------------
        CONTACT_W, CONTACT_H = 30, 20
        RAIL_W = 3
        H_GAP = 50            # horizontal gap between elements
        BRANCH_DY = 40        # vertical gap between parallel branches
        RUNG_GAP = 28         # vertical gap before next rung
        NETWORK_HEADER = 30   # room above each rung for the "Network N" header
        TOP_MARGIN = 30
        LEFT_X = 30
        center_y_rel = CONTACT_H // 2

        # Number of parallel branches (0 = no parallel section, plain series).
        nb = len(branches)
        rung_height = CONTACT_H if nb == 0 else CONTACT_H + (nb - 1) * BRANCH_DY
        # Place this rung below the actual bottom of all existing content (so
        # tall seal-in/branch rungs don't overlap the next), leaving room above
        # for the network header.
        if max_bottom:
            rung_y_top = max_bottom + RUNG_GAP + NETWORK_HEADER
        else:
            rung_y_top = TOP_MARGIN + NETWORK_HEADER

        # Y of the MAIN (top) row — where series_before / series_after / coil sit.
        main_y_top = rung_y_top
        main_y_center = main_y_top + center_y_rel

        # ---- horizontal layout: x positions for everything ------------
        cur_x = LEFT_X + RAIL_W + 40
        sb_xs = []
        for _ in series_before:
            sb_xs.append(cur_x)
            cur_x += CONTACT_W + H_GAP
        split_x = cur_x                                 # x where parallel split happens

        # Each branch's contact x positions
        branch_xs = []
        max_branch_w = 0
        for branch in branches:
            xs = []
            bx = split_x
            for _ in branch:
                xs.append(bx)
                bx += CONTACT_W + H_GAP
            branch_xs.append(xs)
            branch_w = bx - split_x
            if branch_w > max_branch_w:
                max_branch_w = branch_w
        # If no branches, "merge_x" == split_x; nothing crossed.
        merge_x = split_x + max_branch_w if nb else split_x

        sa_xs = []
        cur_x = merge_x
        for _ in series_after:
            sa_xs.append(cur_x)
            cur_x += CONTACT_W + H_GAP
        coil_x = cur_x
        right_rail_x = coil_x + CONTACT_W + 40

        # Branch row Y centers (top branch is on main row)
        branch_y_centers = []
        for i in range(nb):
            branch_y_centers.append(main_y_center + i * BRANCH_DY)

        # ---- builders --------------------------------------------------
        def make_contact(spec, x, y_top):
            c = PLCOpenParser.CreateElement("contact", "ldObjects")
            c.setlocalId(nid())
            c.setvariable(spec["var"])
            c.setnegated(bool(spec.get("negated", False)))
            c.setheight(CONTACT_H); c.setwidth(CONTACT_W)
            c.setx(x); c.sety(y_top)
            c.addconnectionPointIn()
            c.connectionPointIn.setrelPositionXY(0, center_y_rel)
            c.addconnectionPointOut()
            c.connectionPointOut.setrelPositionXY(CONTACT_W, center_y_rel)
            return c

        def wire(in_conn, src_id, points):
            in_conn.addconnection()
            in_conn.setconnectionId(0, src_id)
            in_conn.setconnectionPoints(0, points)

        # ---- left rail ------------------------------------------------
        left_rail = PLCOpenParser.CreateElement("leftPowerRail", "ldObjects")
        left_rail.setlocalId(nid())
        # rail spans full rung height
        left_rail.setheight(rung_height); left_rail.setwidth(RAIL_W)
        left_rail.setx(LEFT_X); left_rail.sety(main_y_top)
        # If we have a series_before, single outlet on main row.
        # If no series_before but branches exist, one outlet per branch.
        # If neither (no contacts AT ALL → unconditional coil), single outlet on main row.
        if series_before or not branches:
            outlet_ys_rel = [center_y_rel]
        else:
            outlet_ys_rel = [(by - main_y_top) for by in branch_y_centers]
        for rel_y in outlet_ys_rel:
            conn = PLCOpenParser.CreateElement("connectionPointOut", "leftPowerRail")
            left_rail.appendconnectionPointOut(conn)
            conn.setrelPositionXY(RAIL_W, rel_y)
        ld.appendcontent(left_rail)
        left_rail_id = left_rail.getlocalId()
        left_outlet_x = LEFT_X + RAIL_W

        # ---- series_before on main row --------------------------------
        prev_id = left_rail_id
        prev_out_x = left_outlet_x
        prev_out_y = main_y_center
        for i, spec in enumerate(series_before):
            cx = sb_xs[i]
            c = make_contact(spec, cx, main_y_top)
            wire(c.connectionPointIn, prev_id,
                 [P(cx, main_y_center), P(prev_out_x, prev_out_y)])
            ld.appendcontent(c)
            prev_id = c.getlocalId()
            prev_out_x = cx + CONTACT_W
            prev_out_y = main_y_center

        # After series_before, the "current source" feeds the parallel split.
        split_src_id, split_src_x, split_src_y = prev_id, prev_out_x, prev_out_y

        # ---- branches in parallel -------------------------------------
        branch_end_info = []  # list of (last_id, last_out_x, last_out_y) per branch
        for bi, branch in enumerate(branches):
            by = branch_y_centers[bi]
            # First contact in this branch (or empty → bare wire)
            if not branch:
                # Empty branch = a wire short-circuit. We represent it as a
                # virtual segment connecting split → merge at this branch's y.
                branch_end_info.append((split_src_id, split_src_x, split_src_y))
                continue
            # Source for first contact's input: if series_before existed, source
            # is the same single point (split_src). If not, source is this branch's
            # own outlet on the left rail.
            if series_before:
                src_id = split_src_id
                src_x, src_y = split_src_x, split_src_y
            else:
                src_id = left_rail_id
                src_x, src_y = left_outlet_x, by

            for j, spec in enumerate(branch):
                cx = branch_xs[bi][j]
                c = make_contact(spec, cx, by - center_y_rel)
                # Input connection: route from (src_x, src_y) → (cx, by)
                # Use intermediate point at our x for clean vertical-then-horizontal
                if src_y == by:
                    pts = [P(cx, by), P(src_x, src_y)]
                else:
                    pts = [P(cx, by), P(src_x, by), P(src_x, src_y)]
                wire(c.connectionPointIn, src_id, pts)
                ld.appendcontent(c)
                src_id = c.getlocalId()
                src_x = cx + CONTACT_W
                src_y = by
            branch_end_info.append((src_id, src_x, src_y))

        # ---- merge node (virtual) — collected by series_after's first
        # input or directly by the coil's input ----------------------
        # If we have branches, we need a node that "OR"s all branch outputs.
        # In PLCopen LD this is just a connection-with-multiple-inputs on the
        # next element. So the next element (first of series_after or the coil)
        # gets one connectionPointIn with MULTIPLE <connection> children.

        def make_multi_inputs(conn, sources):
            """sources: list of (src_id, src_out_x, src_out_y, our_x, our_y) tuples.
            Each becomes one <connection> child of `conn`."""
            for i, (src_id, src_x, src_y, our_x, our_y) in enumerate(sources):
                conn.addconnection()
                conn.setconnectionId(i, src_id)
                if src_y == our_y:
                    pts = [P(our_x, our_y), P(src_x, src_y)]
                else:
                    pts = [P(our_x, our_y), P(our_x, src_y), P(src_x, src_y)]
                conn.setconnectionPoints(i, pts)

        # After branches (or after series_before if no branches), what's the
        # "current source" feeding the rest of the row?
        if branches:
            # Sources to merge → list of (src_id, src_x, src_y)
            merge_sources = list(branch_end_info)
            # The first element after merge (could be series_after[0] or coil)
            # consumes these as multi-input. We'll handle it specially below.
            post_merge_source = None  # signal multi-input
        else:
            merge_sources = None
            post_merge_source = (prev_id, prev_out_x, prev_out_y)

        # ---- series_after on main row ---------------------------------
        first_after_seen = False
        for i, spec in enumerate(series_after):
            cx = sa_xs[i]
            c = make_contact(spec, cx, main_y_top)
            if not first_after_seen and merge_sources is not None:
                # This first contact merges all branches.
                first_after_seen = True
                src_list = [(sid, sx, sy, cx, main_y_center) for sid, sx, sy in merge_sources]
                make_multi_inputs(c.connectionPointIn, src_list)
            else:
                src_id, src_x, src_y = post_merge_source
                wire(c.connectionPointIn, src_id,
                     [P(cx, main_y_center), P(src_x, src_y)])
            ld.appendcontent(c)
            post_merge_source = (c.getlocalId(), cx + CONTACT_W, main_y_center)

        # ---- coil -----------------------------------------------------
        coil = PLCOpenParser.CreateElement("coil", "ldObjects")
        coil.setlocalId(nid())
        coil.setvariable(coil_var)
        coil.setnegated(bool(coil_negated))
        coil.setheight(CONTACT_H); coil.setwidth(CONTACT_W)
        coil.setx(coil_x); coil.sety(main_y_top)
        coil.addconnectionPointIn()
        coil.connectionPointIn.setrelPositionXY(0, center_y_rel)
        if not first_after_seen and merge_sources is not None:
            # Branches feed directly into coil (no series_after).
            src_list = [(sid, sx, sy, coil_x, main_y_center) for sid, sx, sy in merge_sources]
            make_multi_inputs(coil.connectionPointIn, src_list)
        else:
            src_id, src_x, src_y = post_merge_source
            wire(coil.connectionPointIn, src_id,
                 [P(coil_x, main_y_center), P(src_x, src_y)])
        coil.addconnectionPointOut()
        coil.connectionPointOut.setrelPositionXY(CONTACT_W, center_y_rel)
        ld.appendcontent(coil)

        # ---- right rail -----------------------------------------------
        right_rail = PLCOpenParser.CreateElement("rightPowerRail", "ldObjects")
        right_rail.setlocalId(nid())
        right_rail.setheight(rung_height); right_rail.setwidth(RAIL_W)
        right_rail.setx(right_rail_x); right_rail.sety(main_y_top)
        rconn = PLCOpenParser.CreateElement("connectionPointIn", "rightPowerRail")
        right_rail.appendconnectionPointIn(rconn)
        rconn.setrelPositionXY(0, center_y_rel)
        rconn.addconnection()
        rconn.setconnectionId(0, coil.getlocalId())
        rconn.setconnectionPoints(0, [P(right_rail_x, main_y_center),
                                      P(coil_x + CONTACT_W, main_y_center)])
        ld.appendcontent(right_rail)

        if hasattr(plc, "BufferProject"):
            plc.BufferProject()

        return {
            "ok": True,
            "pou_name": pou_name,
            "rung_index": rung_count,
            "series_before": len(series_before),
            "branches": len(branches),
            "branch_widths": [len(b) for b in branches],
            "series_after": len(series_after),
            "coil": coil_var,
        }

    def _tool_add_ladder_move_rung(self, pou_name, source, destination, enable_var=None):
        """Append an LD rung with a MOVE block: dst := src, gated by enable_var.

        Mirrors TIA Portal's MOVE box. Power flow runs along the EN/ENO row
        (left rail → optional enable contact → EN; ENO → right rail); the data
        row carries source (inVariable) → IN and OUT → destination (outVariable).
        """
        from plcopen.plcopen import PLCOpenParser
        from collections import namedtuple
        Pt = namedtuple("Pt", ["x", "y"])

        def P(x, y):
            return Pt(x, y)

        if not source or not destination:
            return {"error": "source and destination required"}

        # ---- locate POU + LD body (same as _tool_add_ladder_rung) ------
        plc = self._plc()
        project = plc.GetProject() if hasattr(plc, "GetProject") else getattr(plc, "Project", None)
        if project is None:
            return {"error": "no project open"}
        pou = project.getpou(pou_name)
        if pou is None:
            return {"error": f"POU '{pou_name}' not found"}
        try:
            body_type = plc.GetPouBodyType(pou_name)
        except Exception:
            body_type = None
        if body_type and body_type != "LD":
            return {"error": f"POU '{pou_name}' body language is '{body_type}', not 'LD'"}
        body = pou.getbody()
        if isinstance(body, list):
            body = body[0] if body else None
        if body is None:
            return {"error": "POU has no body"}
        ld = body.getcontent()

        # ---- next localId + rung count for vertical placement ----------
        existing = ld.getcontent() or []
        max_id = 0
        rung_count = 0
        max_bottom = 0
        for inst in existing:
            try:
                if inst.getlocalId() > max_id:
                    max_id = inst.getlocalId()
            except Exception:
                pass
            try:
                bottom = inst.gety() + inst.getheight()
                if bottom > max_bottom:
                    max_bottom = bottom
            except Exception:
                pass
            if type(inst).__name__ == "leftPowerRail":
                rung_count += 1
        next_id = [max_id + 1]

        def nid():
            v = next_id[0]; next_id[0] += 1
            return v

        # ---- layout ----------------------------------------------------
        TOP_MARGIN = 30
        RUNG_GAP = 28
        NETWORK_HEADER = 30      # room above each rung for the "Network N" header
        LEFT_X = 30
        RAIL_W = 3
        CONTACT_W, CONTACT_H = 30, 20
        BLOCK_W, BLOCK_H = 90, 100

        if max_bottom:
            block_y_top = max_bottom + RUNG_GAP + NETWORK_HEADER
        else:
            block_y_top = TOP_MARGIN + NETWORK_HEADER
        en_y = block_y_top + 40          # power-flow row (EN / ENO)
        in_y = block_y_top + 80          # data row (IN / OUT)
        rung_height = BLOCK_H

        contact_x = LEFT_X + RAIL_W + 60
        contact_y_top = en_y - CONTACT_H // 2
        block_x = contact_x + CONTACT_W + 80
        block_out_x = block_x + BLOCK_W

        invar_w, invar_h = 160, 40
        invar_x = LEFT_X + RAIL_W + 30
        invar_y_top = in_y - invar_h // 2
        invar_out_x = invar_x + invar_w

        outvar_w, outvar_h = 90, 40
        outvar_x = block_out_x + 60
        outvar_y_top = in_y - outvar_h // 2
        right_rail_x = outvar_x + outvar_w + 60

        def wire(in_conn, src_id, points, formal=None):
            in_conn.addconnection()
            in_conn.setconnectionId(0, src_id)
            in_conn.setconnectionPoints(0, points)
            if formal is not None:
                in_conn.setconnectionParameter(0, formal)

        # ---- left rail (single outlet on the EN row) -------------------
        left_rail = PLCOpenParser.CreateElement("leftPowerRail", "ldObjects")
        left_rail.setlocalId(nid())
        left_rail.setheight(rung_height); left_rail.setwidth(RAIL_W)
        left_rail.setx(LEFT_X); left_rail.sety(block_y_top)
        conn = PLCOpenParser.CreateElement("connectionPointOut", "leftPowerRail")
        left_rail.appendconnectionPointOut(conn)
        conn.setrelPositionXY(RAIL_W, en_y - block_y_top)
        ld.appendcontent(left_rail)
        left_rail_id = left_rail.getlocalId()
        left_outlet_x = LEFT_X + RAIL_W

        # ---- optional enable contact feeding EN ------------------------
        en_src_id, en_src_x = left_rail_id, left_outlet_x
        if enable_var:
            c = PLCOpenParser.CreateElement("contact", "ldObjects")
            c.setlocalId(nid())
            c.setvariable(enable_var)
            c.setnegated(False)
            c.setheight(CONTACT_H); c.setwidth(CONTACT_W)
            c.setx(contact_x); c.sety(contact_y_top)
            c.addconnectionPointIn()
            c.connectionPointIn.setrelPositionXY(0, CONTACT_H // 2)
            wire(c.connectionPointIn, left_rail_id,
                 [P(contact_x, en_y), P(left_outlet_x, en_y)])
            c.addconnectionPointOut()
            c.connectionPointOut.setrelPositionXY(CONTACT_W, CONTACT_H // 2)
            ld.appendcontent(c)
            en_src_id, en_src_x = c.getlocalId(), contact_x + CONTACT_W

        # ---- source inVariable feeding IN ------------------------------
        invar = PLCOpenParser.CreateElement("inVariable", "fbdObjects")
        invar.setlocalId(nid())
        invar.setexpression(source)
        invar.setheight(invar_h); invar.setwidth(invar_w)
        invar.setx(invar_x); invar.sety(invar_y_top)
        invar.addconnectionPointOut()
        invar.connectionPointOut.setrelPositionXY(invar_w, invar_h // 2)
        ld.appendcontent(invar)
        invar_id = invar.getlocalId()

        # ---- MOVE block (EN, IN → ENO, OUT) ----------------------------
        block = PLCOpenParser.CreateElement("block", "fbdObjects")
        block.setlocalId(nid())
        block.settypeName("MOVE")
        block.setheight(BLOCK_H); block.setwidth(BLOCK_W)
        block.setx(block_x); block.sety(block_y_top)

        en_var = PLCOpenParser.CreateElement("variable", "inputVariables")
        block.inputVariables.appendvariable(en_var)
        en_var.setformalParameter("EN")
        en_var.connectionPointIn.setrelPositionXY(0, 40)
        wire(en_var.connectionPointIn, en_src_id,
             [P(block_x, en_y), P(en_src_x, en_y)])

        in_var = PLCOpenParser.CreateElement("variable", "inputVariables")
        block.inputVariables.appendvariable(in_var)
        in_var.setformalParameter("IN")
        in_var.connectionPointIn.setrelPositionXY(0, 80)
        wire(in_var.connectionPointIn, invar_id,
             [P(block_x, in_y), P(invar_out_x, in_y)])

        eno_var = PLCOpenParser.CreateElement("variable", "outputVariables")
        block.outputVariables.appendvariable(eno_var)
        eno_var.setformalParameter("ENO")
        eno_var.addconnectionPointOut()
        eno_var.connectionPointOut.setrelPositionXY(BLOCK_W, 40)

        out_var = PLCOpenParser.CreateElement("variable", "outputVariables")
        block.outputVariables.appendvariable(out_var)
        out_var.setformalParameter("OUT")
        out_var.addconnectionPointOut()
        out_var.connectionPointOut.setrelPositionXY(BLOCK_W, 80)

        ld.appendcontent(block)
        block_id = block.getlocalId()

        # ---- destination outVariable (from MOVE OUT) -------------------
        outvar = PLCOpenParser.CreateElement("outVariable", "fbdObjects")
        outvar.setlocalId(nid())
        outvar.setexpression(destination)
        outvar.setheight(outvar_h); outvar.setwidth(outvar_w)
        outvar.setx(outvar_x); outvar.sety(outvar_y_top)
        outvar.addconnectionPointIn()
        outvar.connectionPointIn.setrelPositionXY(0, outvar_h // 2)
        wire(outvar.connectionPointIn, block_id,
             [P(outvar_x, in_y), P(block_out_x, in_y)], formal="OUT")
        ld.appendcontent(outvar)

        # ---- right rail (from MOVE ENO) --------------------------------
        right_rail = PLCOpenParser.CreateElement("rightPowerRail", "ldObjects")
        right_rail.setlocalId(nid())
        right_rail.setheight(rung_height); right_rail.setwidth(RAIL_W)
        right_rail.setx(right_rail_x); right_rail.sety(block_y_top)
        rconn = PLCOpenParser.CreateElement("connectionPointIn", "rightPowerRail")
        right_rail.appendconnectionPointIn(rconn)
        rconn.setrelPositionXY(0, en_y - block_y_top)
        rconn.addconnection()
        rconn.setconnectionId(0, block_id)
        rconn.setconnectionPoints(0, [P(right_rail_x, en_y), P(block_out_x, en_y)])
        rconn.setconnectionParameter(0, "ENO")
        ld.appendcontent(right_rail)

        if hasattr(plc, "BufferProject"):
            plc.BufferProject()

        return {
            "ok": True,
            "pou_name": pou_name,
            "rung_index": rung_count,
            "block": "MOVE",
            "enable": enable_var,
            "source": source,
            "destination": destination,
        }

    def _tool_compile_project(self):
        if not hasattr(self.ctr, "_Build"):
            return {"error": "ProjectController has no _Build method"}

        original_logger = self.ctr.logger
        captured = _CapturingLogger(original_logger)
        self.ctr.logger = captured
        try:
            result = self.ctr._Build()
        except Exception as exc:
            self.ctr.logger = original_logger
            return {"ok": False, "error": str(exc), "log": captured.text()}
        self.ctr.logger = original_logger

        return {
            "ok": bool(result),
            "build_result": result,
            "log": captured.text(),
            "errors": captured.errors,
            "warnings": captured.warnings,
        }


class _CapturingLogger:
    """Tee wrapper around LogPseudoFile. Forwards every write to the real
    logger (so the user sees output live in the bottom pane) and also
    accumulates it so the compile tool can hand the text to the agent."""

    LOG_LIMIT = 16000  # truncate to keep agent context bounded

    def __init__(self, real):
        self._real = real
        self._buf = []
        self.errors = []
        self.warnings = []

    def _record(self, s, bucket=None):
        self._buf.append(s)
        if bucket is not None:
            bucket.append(s.rstrip("\n"))

    def write(self, s, style=None):
        self._record(s)
        return self._real.write(s, style)

    def write_warning(self, s):
        self._record(s, self.warnings)
        return self._real.write_warning(s)

    def write_error(self, s):
        self._record(s, self.errors)
        return self._real.write_error(s)

    def text(self):
        full = "".join(self._buf)
        if len(full) > self.LOG_LIMIT:
            return full[: self.LOG_LIMIT // 2] + "\n...[truncated]...\n" + full[-self.LOG_LIMIT // 2 :]
        return full

    def __getattr__(self, name):
        # Forward any other LogPseudoFile method (flush, isatty, etc.) to the real logger.
        return getattr(self._real, name)
