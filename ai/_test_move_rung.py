"""Standalone validation for add_ladder_move_rung (and add_ladder_rung).

Builds the TIA-style two-network program headlessly and runs the IEC code
generator over it. If the generated LD XML is malformed, GenerateProgram
raises — so a clean run with sane output is the pass condition.

Run:  ../.venv/bin/python -m ai._test_move_rung   (from editor/)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EDITOR = os.path.dirname(HERE)
sys.path.insert(0, EDITOR)

# GraphicCommons builds wx brushes at import time, and the controls/graphics
# packages have an import-order cycle that only resolves once wx + controls
# are loaded first. Mirror the app's startup order headlessly.
import wx  # noqa: E402
_app = wx.App()
import controls  # noqa: E402,F401  (pre-cache to break the cycle)

from PLCControler import PLCControler  # noqa: E402
from ai.tools import Tools  # noqa: E402


def main():
    ctr = PLCControler()
    ctr.CreateNewProject({
        "projectName": "MoveTest", "productName": "test",
        "productVersion": "1", "companyName": "test",
    })

    tools = Tools(ctr, logger=lambda *a, **k: None)

    def call(tool, **kw):
        r = tools.dispatch(tool, kw)
        if isinstance(r, dict) and r.get("error"):
            print(f"  !! {tool} -> {r['error']}")
            sys.exit(1)
        print(f"  ok {tool}: {r}")
        return r

    print("create LD program POU 'Main'")
    call("create_pou", pou_name="Main", pou_type="program", body_language="LD")

    print("declare variables")
    for n in ("Start", "Stop", "Motor", "Send"):
        call("add_pou_variable", pou_name="Main", scope="local", name=n, var_type="BOOL")
    for n in ("Input", "Output"):
        call("add_pou_variable", pou_name="Main", scope="local", name=n, var_type="INT")

    print("Network 1: seal-in motor latch")
    call("add_ladder_rung", pou_name="Main",
         branches=[[{"var": "Start"}], [{"var": "Motor"}]],
         series_after=[{"var": "Stop", "negated": True}],
         coil_var="Motor")

    print("Network 2: MOVE Input -> Output gated by Send")
    call("add_ladder_move_rung", pou_name="Main",
         enable_var="Send", source="Input", destination="Output")

    print("generate IEC code (validates the XML)")
    errors, warnings = [], []
    from PLCGenerator import GenerateCurrentProgram
    chunks = GenerateCurrentProgram(ctr, ctr.GetProject(), errors, warnings)
    program = "".join(c[0] if isinstance(c, tuple) else c for c in chunks)
    if errors:
        print("  !! generation errors:", errors)
        sys.exit(1)
    print("  warnings:", warnings or "none")
    print("-" * 60)
    print(program)
    print("-" * 60)
    # Sanity assertions
    assert "MOVE" in program, "MOVE not in generated program"
    assert "Output" in program and "Input" in program
    assert "Motor" in program and "Start" in program
    print("PASS: MOVE block + seal-in generated and compiled to IEC text")


if __name__ == "__main__":
    main()
