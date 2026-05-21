"""Claude agent — tool-use loop bound to a project's Tools instance.

Single-turn API: caller hands us a user message + a list of prior turns;
we run the tool loop until Claude returns a final assistant text, then
return the updated message list. The chat panel keeps the conversation
state and renders streamed updates via the on_event callback.
"""

import json
import os
import sys
import threading

try:
    from anthropic import Anthropic
except ImportError:  # SDK not installed yet
    Anthropic = None


def _log(msg):
    """Mirror agent activity to stderr so it lands in the IDE log file.
    Used for headless diagnosis — user can grep the log after running."""
    print(f"[agent] {msg}", file=sys.stderr, flush=True)


SYSTEM_PROMPT = """You are an embedded coding agent inside OpenPLC Editor, helping a control engineer write and debug PLC programs.

You can read and edit POUs (Program Organization Units), declare their interface variables, create/delete POUs, save the project, and compile it. The project follows IEC 61131-3 — POU types are program/function/functionBlock, body languages are ST/LD/FBD/SFC/IL. Prefer Structured Text (ST) — it's textual, you can edit it directly. For graphical languages your edits go through the XML model, which is harder; ask the user to convert to ST first if needed.

CRITICAL — POU structure in PLCopen XML:
- Variables live in the POU's INTERFACE (separate XML section). Declare them with add_pou_variable (one per variable), specifying scope: input/output/inout/local/external.
- The BODY for ST POUs (set_pou_text) contains ONLY executable statements. Do NOT include VAR_INPUT / VAR_OUTPUT / VAR / END_VAR blocks in body text — Beremiz parses interface from XML, not from body text. Putting VAR blocks in the body causes 'No variable defined' compile errors even when the text looks correct.
- Correct order for an ST program: create_pou(body_language='ST') → add_pou_variable (× N for each var) → set_pou_text (body only) → save_project → compile_project.

Ladder Diagram (LD) — when to use:
- Many US controls engineers prefer LD over ST for discrete logic (start/stop, interlocks, motor control). Offer LD when the user says "ladder", "rung", "contact/coil", or asks for visual logic.
- Create an LD POU via create_pou(body_language='LD'). Declare variables the same way (add_pou_variable).
- Append rungs with add_ladder_rung — supports both series and parallel branches:
  * Pure series: pass `series_before=[{var:A}, {var:B}]`, leave `branches` empty. Produces `--[A]--[B]--(coil)--`.
  * Seal-in (latch): `branches=[[{var:Start}], [{var:Motor}]]` + `series_after=[{var:Stop,negated:True}]` + `coil_var:Motor`. Produces `--[Start || Motor]--[/Stop]--(Motor)--`. This is THE canonical PLC pattern — start latches motor, stop drops it.
  * Multiple parallel conditions: branches=[[A], [B], [C]] gives A OR B OR C.
  * Negated contact: {var:X, negated:true}.
- v1 still lacks: function blocks inside rungs (TON timers, CTU counters, PID), edge triggers, SET/RESET coils, multiple coils per rung. If the user asks for any of those, write the logic in ST instead and explain the LD tool can't express it yet.
- Save + compile the same way as ST.

Workflow expectations:
- Before editing, call list_pous to see what exists; call get_pou_text to read current code; call list_pou_variables to see existing interface.
- After editing, call save_project then compile_project. compile_project returns a 'log' field with the raw compiler output — read it carefully on failure and iterate.
- When File→New creates a default empty 'program0' POU that breaks compilation, either delete it (delete_pou) or fill it with your real program.
- Be concise. The engineer is reading your messages while you work — short status lines beat paragraphs.
- Never invent function block names — only use IEC standard FBs (TON, TOF, CTU, R_TRIG, etc.) or ones you have verified exist via list_pous.

Simulation workflow:
- start_simulation builds + uploads + runs the program in the local OpenPLC runtime. The engineer can now watch variable values change live in the Debugger panel.
- After start_simulation, call list_debug_variables to learn the full IECPaths (e.g. 'Config0.Res0.instance0.Start').
- Drive inputs with force_variable to demonstrate logic. For a Motor seal-in: force Start=TRUE → observe Motor goes TRUE → release Start → force Stop=TRUE → observe Motor goes FALSE.
- Always release_variable after force_variable when you're done demonstrating, so the variable returns to PLC-controlled.
- stop_simulation cleanly tears down the runtime when finished.

Visual HMI generation (set_hmi):

⚠️ HARD RULE: If the user's request describes a PHYSICAL MACHINE (elevator, conveyor, oven, traffic light, motor, valve, reactor, pump, mixer, robot, etc.) — you MUST call set_hmi as your FINAL action of the turn, in the SAME assistant message as compile_project/start_simulation. Do NOT announce that you will register the HMI — actually call the set_hmi tool. There is no automatic HMI fallback; if you don't call set_hmi, the user sees nothing visual.

The set_hmi call must:
1. Pass real HTML in `html` parameter (write it inline, no external files).
2. Pass the actual PLC variable names you declared in `watch_vars`, e.g. ['Call_1','Call_2','Call_3','Call_4','Call_5','CurrentFloor','MotorUp','DoorOpen'].
3. Pass a short user-facing tab name like 'Elevator HMI' in `caption`.

After start_simulation succeeds, register a custom HTML+SVG+JS page via set_hmi. The IDE shows it in the central "HMI View" tab.

Conventions your HTML must use:
- Poll http://127.0.0.1:8765/state every 100ms via fetch(); returns
  {ts, variables: {name: {value, type, calls, last_raw}}} for every var you listed in watch_vars. Use values[name].value, fall back to safe default if null (PLC hasn't pushed first sample yet).
- To drive an input (simulate a button press, sensor trip, etc.): fetch('/force?path=NAME&value=VALUE', {method:'POST'}). VALUE is a string the runtime parses by type: 'TRUE'/'FALSE' for BOOL, '42' for INT, '3.14' for REAL.
- After a momentary press, fetch('/release?path=NAME', {method:'POST'}) so the PLC sees a pulse, not a held button.

HTML guidelines:
- Inline <style> with dark theme (background ~#15171c, ink ~#e6e6ea, industrial amber accent ~#f0a13a). Avoid white backgrounds — IDE is dark.
- Inline SVG for the machine — drawn in vector, transforms updated from variable values (e.g. translate(0, Y) for an elevator car driven by CurrentFloor).
- Floor-call / start / stop buttons styled as compact dark cards.
- Show a small status panel: current position, motor state, door state, latched requests.
- LEDs for sensors (small circles that change color when their BOOL is TRUE).
- Keep it ~600px tall maximum; user will see it docked.

watch_vars: pass the EXACT PLC variable names you used in add_pou_variable. The bridge matches by suffix, case-insensitive. For example if you declared Call_1, MotorUp, CurrentFloor in program0, pass ['Call_1','MotorUp','CurrentFloor'].

Caption: short human-readable tab name e.g. 'Elevator HMI', 'Conveyor View', 'Reactor SCADA'.

Workflow: write PLC → start_simulation → set_hmi → optional force_variable / chat-driven demo.

You are NOT a chatbot. You write PLC code that compiles and runs."""


class Agent:
    def __init__(self, tools, on_event=None, model="claude-opus-4-7", max_iterations=20):
        self.tools = tools
        self.on_event = on_event or (lambda kind, payload: None)
        self.model = model
        self.max_iterations = max_iterations
        self.messages = []
        self._client = None
        # Signal set by chat panel when user clicks Stop. Checked between
        # API turns and between tool dispatches. Currently in-flight API
        # calls or tool calls run to completion — we abort at next safe point.
        self._abort = threading.Event()

    def abort(self):
        self._abort.set()

    def _client_lazy(self):
        if self._client is None:
            if Anthropic is None:
                raise RuntimeError(
                    "anthropic SDK not installed. Run: pip install anthropic"
                )
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Export it before launching the editor."
                )
            self._client = Anthropic(api_key=api_key)
        return self._client

    def send(self, user_text):
        """Run one user→assistant round, possibly with many tool-use cycles.

        Emits events via on_event(kind, payload):
            ('assistant_text', str)  — text chunk from model
            ('tool_call', {name, input})
            ('tool_result', {name, output})
            ('error', str)
        """
        from ai.tools import TOOL_SCHEMAS

        self.messages.append({"role": "user", "content": user_text})
        self._abort.clear()   # fresh turn — clear any stale abort flag
        _log(f"USER → {user_text[:200]}")

        try:
            client = self._client_lazy()
        except RuntimeError as exc:
            self.on_event("error", str(exc))
            return

        for _ in range(self.max_iterations):
            if self._abort.is_set():
                self._repair_orphan_tool_uses()
                self.on_event("error", "stopped by user")
                return

            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_SCHEMAS,
                    messages=self.messages,
                )
            except Exception as exc:
                # API call rejected (often: orphan tool_use from a previous
                # broken turn). Repair the conversation and surface the error
                # so the next user message starts from a valid state.
                self._repair_orphan_tool_uses()
                self.on_event("error", f"API call failed: {exc}")
                return

            if self._abort.is_set():
                # Drop the response we just received — we're stopping. Don't
                # append it to history (might have unanswered tool_use).
                self.on_event("error", "stopped by user")
                return

            assistant_content = response.content
            self.messages.append({"role": "assistant", "content": assistant_content})

            tool_uses = [b for b in assistant_content if b.type == "tool_use"]
            for block in assistant_content:
                if block.type == "text" and block.text:
                    self.on_event("assistant_text", block.text)
                    _log(f"AI text: {block.text[:300]}")

            if response.stop_reason != "tool_use" or not tool_uses:
                return

            # Build tool_results, never letting a single bad serialization
            # break the loop — every tool_use MUST get a matching tool_result
            # block, otherwise Anthropic rejects the next request.
            tool_results = []
            for use in tool_uses:
                if self._abort.is_set():
                    # Abort mid-batch — synthesize cancellation results for
                    # the rest so history stays balanced for next time.
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": json.dumps({"error": "aborted by user"}),
                    })
                    continue
                _log(f"→ {use.name}({json.dumps(use.input, ensure_ascii=False)[:400]})")
                self.on_event("tool_call", {"name": use.name, "input": use.input})
                try:
                    output = self.tools.dispatch(use.name, use.input)
                except Exception as exc:
                    output = {"error": f"dispatch raised: {exc}"}
                try:
                    content = json.dumps(_safe_for_json(output))
                except Exception as exc:
                    content = json.dumps({"error": f"result serialization failed: {exc}"})
                _ok = isinstance(output, dict) and output.get("ok") in (True, None) and "error" not in output
                _log(f"  {'✓' if _ok else '✗'} {use.name} → {content[:400]}")
                self.on_event("tool_result", {"name": use.name, "output": output})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": use.id,
                    "content": content,
                })
            self.messages.append({"role": "user", "content": tool_results})

            if self._abort.is_set():
                self.on_event("error", "stopped by user")
                return

        self.on_event("error", f"agent exceeded {self.max_iterations} tool iterations")
        # After exhausting iterations the last assistant message may still
        # have unanswered tool_use — pair them so the next user turn is valid.
        self._repair_orphan_tool_uses()

    def _repair_orphan_tool_uses(self):
        """If the last assistant message in history contains tool_use blocks
        that have no matching tool_result in the following user message,
        synthesize placeholder tool_result blocks so the conversation is
        a valid Anthropic API input for the next request."""
        if not self.messages:
            return
        last = self.messages[-1]
        # The orphan can only be on the assistant side — a user message after
        # it would already have results.
        if last.get("role") != "assistant":
            return
        content = last.get("content", [])
        tool_use_ids = []
        for block in content:
            btype = getattr(block, "type", None) or (isinstance(block, dict) and block.get("type"))
            if btype == "tool_use":
                bid = getattr(block, "id", None) or (isinstance(block, dict) and block.get("id"))
                if bid:
                    tool_use_ids.append(bid)
        if not tool_use_ids:
            return
        synthetic = [{
            "type": "tool_result",
            "tool_use_id": tid,
            "content": json.dumps({"error": "aborted — conversation reset"}),
        } for tid in tool_use_ids]
        self.messages.append({"role": "user", "content": synthetic})


def _safe_for_json(obj):
    """Recursively coerce odd types (wx objects, sets, bytes) to JSON-safe ones."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_safe_for_json(v) for v in obj]
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return repr(obj)
    return repr(obj)
