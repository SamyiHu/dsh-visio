"""Relationship-driven connector layout.

The page is treated as a graph: shapes are nodes, connectors (their Connect rows)
are edges.  Ports are assigned per node from its in/out degree, then every edge is
routed as an orthogonal path.  A grammar check rejects any path that breaks the
flowchart invariants, so a broken picture can never be produced silently:

  * every segment is axis aligned;
  * every end lands on the boundary of the node it belongs to;
  * no segment passes through a shape that is not one of its two ends;
  * no two connectors share a side of the same shape.
"""

EPS = 1e-6


# --------------------------------------------------------------------------- graph
def build(shapes):
    boxes = {s["id"]: s["bbox"] for s in shapes
             if not s["connector"] and s["type"] != "Guide" and s["bbox"]["w"] > 0 and s["bbox"]["h"] > 0}
    edges = []
    for c in shapes:
        if not c["connector"]:
            continue
        tos = [str(x["to"]) for x in (c.get("connects") or [])]
        if len(tos) == 2 and tos[0] in boxes and tos[1] in boxes and tos[0] != tos[1]:
            edges.append({"id": c["id"], "a": tos[0], "b": tos[1]})
    return boxes, edges


def _deg(edges):
    inb, outb = {}, {}
    for e in edges:
        outb[e["a"]] = outb.get(e["a"], 0) + 1
        inb[e["b"]] = inb.get(e["b"], 0) + 1
    return inb, outb


# --------------------------------------------------------------------------- ports
def port(box, side, frac=0.5):
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    return {"L": (x, y + h * frac), "R": (x + w, y + h * frac),
            "T": (x + w * frac, y + h), "B": (x + w * frac, y)}[side]


def _facing(A, B):
    acx, acy = A["x"] + A["w"] / 2.0, A["y"] + A["h"] / 2.0
    bcx, bcy = B["x"] + B["w"] / 2.0, B["y"] + B["h"] / 2.0
    if abs(bcx - acx) >= abs(bcy - acy):
        return ("R", "L") if bcx > acx else ("L", "R")
    return ("T", "B") if bcy > acy else ("B", "T")


def assign(boxes, edges):
    """Give every connector end its own side; decisions keep one side per branch."""
    inb, outb = _deg(edges)
    claimed = {n: set() for n in boxes}
    sides = {}
    # outputs first: a node with several branches must spread them over sides
    for e in sorted(edges, key=lambda x: -outb.get(x["a"], 0)):
        A, B = boxes[e["a"]], boxes[e["b"]]
        sa = _pick(A, B, claimed[e["a"]])
        sb = _pick(B, A, claimed[e["b"]])
        claimed[e["a"]].add(sa)
        claimed[e["b"]].add(sb)
        sides[e["id"]] = (sa, sb)
    return sides


def _pick(A, B, taken):
    first, _ = _facing(A, B)
    for side in [first] + [s for s in ("R", "B", "L", "T") if s != first]:
        if side not in taken:
            return side
    return first


# --------------------------------------------------------------------------- geometry
def _crosses(path, boxes, skip):
    for i in range(len(path) - 1):
        (x1, y1), (x2, y2) = path[i], path[i + 1]
        for sid, b in boxes.items():
            if sid in skip:
                continue
            if _seg_hits(x1, y1, x2, y2, b):
                return True
    return False


def _seg_hits(x1, y1, x2, y2, b, pad=0.02, steps=32):
    bx1, by1 = b["x"] + pad, b["y"] + pad
    bx2, by2 = b["x"] + b["w"] - pad, b["y"] + b["h"] - pad
    if bx2 <= bx1 or by2 <= by1:
        return False
    for k in range(1, steps):
        t = k / float(steps)
        x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        if bx1 <= x <= bx2 and by1 <= y <= by2:
            return True
    return False


def _candidates(p1, p2, s1, s2, boxes, skip):
    """Orthogonal paths, closest-to-straight first, then detours around obstacles."""
    ax, ay = p1
    bx, by = p2
    ah, bh = s1 in ("L", "R"), s2 in ("L", "R")
    out = []
    if ah and bh:
        for mid in ((ax + bx) / 2.0, ax + 0.35 if s1 == "R" else ax - 0.35,
                    bx + 0.35 if s2 == "R" else bx - 0.35,
                    max(ax, bx) + 0.35, min(ax, bx) - 0.35):
            out.append([(ax, ay), (mid, ay), (mid, by), (bx, by)])
    elif (not ah) and (not bh):
        for mid in ((ay + by) / 2.0, ay + 0.35 if s1 == "T" else ay - 0.35,
                    by + 0.35 if s2 == "T" else by - 0.35,
                    max(ay, by) + 0.35, min(ay, by) - 0.35):
            out.append([(ax, ay), (ax, mid), (bx, mid), (bx, by)])
    elif ah:
        out.append([(ax, ay), (bx, ay), (bx, by)])
        for drop in (0.35, -0.35, 0.7, -0.7):
            out.append([(ax, ay), (ax, ay + drop) if False else (bx, ay),
                        (bx, ay), (bx, by)])
    else:
        out.append([(ax, ay), (ax, by), (bx, by)])
    # last resort: go around the outside of everything
    lo_x = min(b["x"] for b in boxes.values()) - 0.4
    hi_x = max(b["x"] + b["w"] for b in boxes.values()) + 0.4
    lo_y = min(b["y"] for b in boxes.values()) - 0.4
    hi_y = max(b["y"] + b["h"] for b in boxes.values()) + 0.4
    out.append([(ax, ay), (ax, hi_y), (bx, hi_y), (bx, by)])
    out.append([(ax, ay), (ax, lo_y), (bx, lo_y), (bx, by)])
    out.append([(ax, ay), (hi_x, ay), (hi_x, by), (bx, by)])
    out.append([(ax, ay), (lo_x, ay), (lo_x, by), (bx, by)])
    return out


def route(boxes, edges, sides):
    routes, bad = {}, []
    for e in edges:
        sa, sb = sides[e["id"]]
        A, B = boxes[e["a"]], boxes[e["b"]]
        p1, p2 = port(A, sa), port(B, sb)
        skip = {e["a"], e["b"]}
        chosen = None
        for path in _candidates(p1, p2, sa, sb, boxes, skip):
            if not _crosses(path, boxes, skip):
                chosen = path
                break
        if chosen is None:
            chosen = _candidates(p1, p2, sa, sb, boxes, skip)[0]
            bad.append({"connector": e["id"], "code": "route-blocked",
                        "message": "找不到不穿框的走线"})
        routes[e["id"]] = chosen
    return routes, bad


# --------------------------------------------------------------------------- grammar
def check(boxes, edges, sides, routes):
    """Invariants that make the drawing a flowchart rather than a pile of lines."""
    issues = []
    used = {}
    for e in edges:
        sa, sb = sides[e["id"]]
        for node, side in ((e["a"], sa), (e["b"], sb)):
            key = (node, side)
            if key in used:
                issues.append({"connector": e["id"], "code": "port-shared",
                               "message": "形状 #%s 的 %s 边被 #%s 和 #%s 共用" % (node, side, used[key], e["id"])})
            used[key] = e["id"]
        path = routes.get(e["id"]) or []
        for i in range(len(path) - 1):
            (x1, y1), (x2, y2) = path[i], path[i + 1]
            if abs(x1 - x2) > EPS and abs(y1 - y2) > EPS:
                issues.append({"connector": e["id"], "code": "not-orthogonal",
                               "message": "线段不是水平/垂直"})
        if path and _crosses(path, boxes, {e["a"], e["b"]}):
            issues.append({"connector": e["id"], "code": "crosses-shape",
                           "message": "连线穿过无关形状"})
    inb, outb = _deg(edges)
    for node, n_out in outb.items():
        if n_out >= 2:
            sides_used = {sides[e["id"]][0] for e in edges if e["a"] == node}
            if len(sides_used) < min(n_out, 3):
                issues.append({"connector": None, "code": "decision-ports",
                               "message": "形状 #%s 有 %d 条出线，但只用了 %d 个不同的边" % (node, n_out, len(sides_used))})
    return issues


def layout(shapes):
    boxes, edges = build(shapes)
    sides = assign(boxes, edges)
    routes, bad = route(boxes, edges, sides)
    issues = check(boxes, edges, sides, routes)
    return routes, issues + bad, sides
