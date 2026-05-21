"""ld_parse — turn a PLCOpen LD body into a list of *network* segments with
geometry, for the segmented HTML LD editor.

We don't reconstruct the logical series/parallel model; we parse the actual
geometry (element positions + connection waypoints) so the SVG renderer can
redraw the exact ladder. A network = one left power rail + the elements in its
vertical band (matches how add_ladder_rung lays rungs out top-to-bottom).

`parse_ld_networks(ld_root)` takes the PLCOpen `<LD>` element (etree-like; the
PLCOpen parser objects support .iter()/.tag/.get()/.find()/.text). Returns:

  [ { "index": int, "title": str, "comment": str,
      "x0","y0","w","h": ints (band bbox, element-local origin = (x0,y0)),
      "elements": [ {kind,id,x,y,w,h,var,negated,btype,ports,wires} ] } ]

Coordinates in each element/wire are **network-local** (origin subtracted).
"""


def _local(el, tag):
    """Strip namespace and compare."""
    return (getattr(el, "tag", "") or "").split("}")[-1] == tag


def _kind(el):
    t = (getattr(el, "tag", "") or "").split("}")[-1]
    return {
        "leftPowerRail": "leftrail",
        "rightPowerRail": "rightrail",
        "contact": "contact",
        "coil": "coil",
        "block": "block",
        "inVariable": "invar",
        "outVariable": "outvar",
    }.get(t)


def _pos(el):
    p = el.find("{*}position") if hasattr(el, "find") else None
    if p is None:
        return 0, 0
    try:
        return int(float(p.get("x") or 0)), int(float(p.get("y") or 0))
    except Exception:
        return 0, 0


def _int(el, attr, default=0):
    try:
        return int(float(el.get(attr) or default))
    except Exception:
        return default


def _text(el, tag):
    c = el.find("{*}" + tag) if hasattr(el, "find") else None
    return (c.text or "").strip() if c is not None and c.text else ""


def _input_wires(el):
    """All input connection polylines (absolute coords) for an element."""
    wires = []
    for cpi in (el.iter("{*}connectionPointIn") if hasattr(el, "iter") else []):
        for conn in cpi:
            if not _local(conn, "connection"):
                continue
            pts = []
            for pp in conn:
                if _local(pp, "position"):
                    try:
                        pts.append((int(float(pp.get("x"))), int(float(pp.get("y")))))
                    except Exception:
                        pass
            if pts:
                wires.append(pts)
    return wires


def _block_ports(el):
    ports = []
    for grp, direction in (("inputVariables", "in"), ("outputVariables", "out")):
        container = el.find("{*}" + grp) if hasattr(el, "find") else None
        if container is None:
            continue
        for v in container:
            if not _local(v, "variable"):
                continue
            name = v.get("formalParameter") or ""
            cp = v.find("{*}connectionPointIn") or v.find("{*}connectionPointOut")
            rx = ry = 0
            if cp is not None:
                rp = cp.find("{*}relPosition")
                if rp is not None:
                    rx, ry = _int(rp, "x"), _int(rp, "y")
            ports.append({"name": name, "rx": rx, "ry": ry, "dir": direction})
    return ports


def _element(el):
    kind = _kind(el)
    if kind is None:
        return None
    x, y = _pos(el)
    e = {
        "kind": kind, "id": _int(el, "localId"),
        "x": x, "y": y, "w": _int(el, "width"), "h": _int(el, "height"),
        "var": None, "negated": el.get("negated") == "true",
        "btype": None, "ports": [], "wires": _input_wires(el),
    }
    if kind in ("contact", "coil"):
        e["var"] = _text(el, "variable")
    elif kind in ("invar", "outvar"):
        e["var"] = _text(el, "expression")
    elif kind == "block":
        e["btype"] = el.get("typeName") or "BLOCK"
        e["ports"] = _block_ports(el)
    return e


def parse_ld_networks(ld_root):
    insts = []
    try:
        for el in ld_root:           # direct children = instances
            e = _element(el)
            if e is not None:
                insts.append(e)
    except Exception:
        return []
    if not insts:
        return []

    # Network bands: each left rail starts a network; band spans to the next
    # left rail's y (sorted top→bottom).
    rails = sorted([e for e in insts if e["kind"] == "leftrail"], key=lambda e: e["y"])
    if not rails:
        return []
    bounds = []
    for i, r in enumerate(rails):
        top = r["y"]
        bot = rails[i + 1]["y"] if i + 1 < len(rails) else 10 ** 9
        bounds.append((top, bot))

    networks = []
    for ni, (top, bot) in enumerate(bounds):
        elems = [e for e in insts if top <= e["y"] < bot]
        if not elems:
            continue
        x0 = min(e["x"] for e in elems)
        y0 = min(e["y"] for e in elems)
        maxx = max(e["x"] + e["w"] for e in elems)
        maxy = max(e["y"] + e["h"] for e in elems)
        # localize coordinates
        local = []
        for e in elems:
            le = dict(e)
            le["x"] = e["x"] - x0
            le["y"] = e["y"] - y0
            le["wires"] = [[(px - x0, py - y0) for (px, py) in w] for w in e["wires"]]
            local.append(le)
        networks.append({
            "index": ni, "title": "", "comment": "",
            "x0": x0, "y0": y0, "w": maxx - x0, "h": maxy - y0,
            "elements": local,
        })
    return networks
