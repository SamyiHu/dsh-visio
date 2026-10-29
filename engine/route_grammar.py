"""Relationship-driven connector layout, following Visio's glue model.

Nodes are shapes, edges are connectors (their `Connect` rows).  Every node exposes
**connection points** the way Visio defines them:

  * `Section N="Connection"` rows - `X`, `Y` in shape-local inches, `DirX`/`DirY`
    the outward normal (`0,0` meaning "free", which is pointed away from the centre);
  * otherwise the four edge midpoints a plain 2-D shape gets by default
    (left, bottom, right, top), normals pointing outwards.

Rules enforced (violations are reported, never drawn silently):

  R1  a connector leaves a point along its normal and enters along the opposite
  R2  one connection point carries at most one connector            (`anchor-shared`)
  R3  every segment is horizontal or vertical                       (`not-orthogonal`)
  R4  a connector never crosses an unrelated shape                  (`crosses-shape`)
  R5  a decision's branches spread over different points            (`branch-ports`)
"""

EPS = 1e-6
STUB = 0.22          # short straight run off the port, the way Visio leaves a shape


# --------------------------------------------------------------------------- points
def _outward(box, x, y):
    dx = x - (box["x"] + box["w"] / 2.0)
    dy = y - (box["y"] + box["h"] / 2.0)
    if abs(dx / (box["w"] / 2.0 or 1)) >= abs(dy / (box["h"] / 2.0 or 1)):
        return (1.0, 0.0) if dx >= 0 else (-1.0, 0.0)
    return (0.0, 1.0) if dy >= 0 else (0.0, -1.0)


def anchors(node):
    """[(x, y, nx, ny, key)] in page inches, normals pointing outwards."""
    box = node["bbox"]
    rows = node.get("conn") or []
    if rows:
        out = []
        for i, (x, y, dx, dy) in enumerate(rows):
            px, py = box["x"] + x, box["y"] + y
            if dx == 0 and dy == 0:
                dx, dy = _outward(box, px, py)
            out.append((px, py, dx, dy, "c%d" % i))
        return out
    cx, cy = box["x"] + box["w"] / 2.0, box["y"] + box["h"] / 2.0
    return [
        (box["x"], cy, -1.0, 0.0, "L"),
        (box["x"] + box["w"], cy, 1.0, 0.0, "R"),
        (cx, box["y"], 0.0, -1.0, "B"),
        (cx, box["y"] + box["h"], 0.0, 1.0, "T"),
    ]


def _dir_to(A, B):
    acx, acy = A["x"] + A["w"] / 2.0, A["y"] + A["h"] / 2.0
    bcx, bcy = B["x"] + B["w"] / 2.0, B["y"] + B["h"] / 2.0
    dx, dy = bcx - acx, bcy - acy
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    return dx / L, dy / L


OPP = {"L": "R", "R": "L", "T": "B", "B": "T"}


def _ideal(node, other):
    dx, dy = _dir_to(node["bbox"], other["bbox"])
    best, best_score = None, -9e9
    for pt in anchors(node):
        score = pt[2] * dx + pt[3] * dy
        if score > best_score:
            best, best_score = pt, score
    return best, best_score


def assign(nodes, edges):
    """One distinct point per connector end.

    Pass 1 - every end takes the side that faces its partner (the natural trunk).
    Pass 2 - ends that lost a contested side move to the best free one; a branch of a
    node that already has an entry prefers the side opposite that entry, so a
    decision's reject path leaves on the far side instead of doubling back.
    """
    want = {}
    groups = {}
    for e in edges:
        for end, node, other in (("a", e["a"], e["b"]), ("b", e["b"], e["a"])):
            pt, score = _ideal(nodes[node], nodes[other])
            want[(e["id"], end)] = (node, pt, score)
            groups.setdefault(node, []).append((e["id"], end, pt, score))

    choice, lost = {}, []
    for node, items in groups.items():
        seen = {}
        for eid, end, pt, score in sorted(items, key=lambda it: -it[3]):
            if pt[4] not in seen:
                seen[pt[4]] = (eid, end)
                choice[(eid, end)] = pt
            else:
                lost.append((eid, end, node, pt))
    # ends that could not have their ideal side
    out_deg = {}
    for e in edges:
        out_deg[e["a"]] = out_deg.get(e["a"], 0) + 1
    for eid, end, node, pt in sorted(lost, key=lambda it: -out_deg.get(it[2], 0)):
        taken = {v[4] for (n, v) in choice.items() if n[0] == node} if False else                 {pt2[4] for (e2, d2), pt2 in choice.items() if want.get((e2, d2), (None,))[0] == node}
        entry = None
        for (e2, d2), pt2 in choice.items():
            if d2 == "b" and want.get((e2, d2), (None,))[0] == node:
                entry = pt2[4]
                break
        order = []
        if end == "a" and entry:
            order.append(OPP.get(entry))
        order += [k for k in ("R", "B", "L", "T")]
        for key in order:
            if key and key not in taken:
                choice[(eid, end)] = next(x for x in anchors(nodes[node]) if x[4] == key)
                break
        else:
            choice[(eid, end)] = pt
    return choice


# --------------------------------------------------------------------------- routing
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


def _crosses(path, boxes, skip):
    for i in range(len(path) - 1):
        (x1, y1), (x2, y2) = path[i], path[i + 1]
        for sid, b in boxes.items():
            if sid in skip:
                continue
            if _seg_hits(x1, y1, x2, y2, b):
                return True
    return False


def _clean(path):
    out = [path[0]]
    for pt in path[1:]:
        if abs(pt[0] - out[-1][0]) > 1e-6 or abs(pt[1] - out[-1][1]) > 1e-6:
            out.append(pt)
    return out


def _join(a, n1, b, n2, shift=0.0):
    """Orthogonal path between two stub ends, honouring exit and entry axes."""
    ax, ay = a
    bx, by = b
    h1 = abs(n1[0]) >= abs(n1[1])
    h2 = abs(n2[0]) >= abs(n2[1])
    if h1 and h2:
        mid = (ax + bx) / 2.0 + shift
        return [(ax, ay), (mid, ay), (mid, by), (bx, by)]
    if not h1 and not h2:
        mid = (ay + by) / 2.0 + shift
        return [(ax, ay), (ax, mid), (bx, mid), (bx, by)]
    if h1:
        return [(ax, ay), (bx, ay), (bx, by)]
    return [(ax, ay), (ax, by), (bx, by)]


def route(nodes, edges, choice):
    boxes = {nid: nodes[nid]["bbox"] for nid in nodes}
    routes, bad = {}, []
    for e in edges:
        pa, pb = choice[(e["id"], "a")], choice[(e["id"], "b")]
        p1, n1 = (pa[0], pa[1]), (pa[2], pa[3])
        p2, n2 = (pb[0], pb[1]), (pb[2], pb[3])
        skip = {e["a"], e["b"]}
        best, blocked = None, True
        for stub in (STUB, STUB * 2, STUB * 3, STUB * 5):
            a = (p1[0] + n1[0] * stub, p1[1] + n1[1] * stub)
            b = (p2[0] + n2[0] * stub, p2[1] + n2[1] * stub)
            for shift in (0.0, 0.3, -0.3, 0.6, -0.6, 1.0, -1.0):
                path = _clean([p1, a] + _join(a, n1, b, n2, shift)[1:-1] + [b, p2])
                if not _crosses(path, boxes, skip):
                    best, blocked = path, False
                    break
                if best is None:
                    best = path
            if not blocked:
                break
        if best is None:
            best = _clean([p1, p2])
        if blocked:
            bad.append({"connector": e["id"], "code": "route-blocked",
                        "message": "找不到不穿框的走线"})
        routes[e["id"]] = best
    return routes, bad


# --------------------------------------------------------------------------- grammar
def check(nodes, edges, choice, routes):
    issues = []
    boxes = {k: nodes[k]["bbox"] for k in nodes}
    used = {}
    for e in edges:
        for end in ("a", "b"):
            pt = choice[(e["id"], end)]
            key = (e[end], pt[4])
            if key in used:
                issues.append({"connector": e["id"], "code": "anchor-shared",
                               "message": "形状 #%s 的连接点 %s 被 #%s 和 #%s 共用"
                                          % (e[end], pt[4], used[key], e["id"])})
            used[key] = e["id"]
        path = routes.get(e["id"]) or []
        for i in range(len(path) - 1):
            (x1, y1), (x2, y2) = path[i], path[i + 1]
            if abs(x1 - x2) > 1e-4 and abs(y1 - y2) > 1e-4:
                issues.append({"connector": e["id"], "code": "not-orthogonal",
                               "message": "线段不是水平/垂直"})
        if len(path) > 1 and _crosses(path, boxes, {e["a"], e["b"]}):
            issues.append({"connector": e["id"], "code": "crosses-shape",
                           "message": "连线穿过无关形状"})
        for pt, seg, node, sign in (
                (choice[(e["id"], "a")], (path[0], path[1]) if len(path) > 1 else None, e["a"], 1),
                (choice[(e["id"], "b")], (path[-2], path[-1]) if len(path) > 1 else None, e["b"], -1)):
            if not seg or (pt[2] == 0 and pt[3] == 0):
                continue
            vx, vy = seg[1][0] - seg[0][0], seg[1][1] - seg[0][1]
            if (vx * pt[2] + vy * pt[3]) * sign <= 0:
                issues.append({"connector": e["id"], "code": "dir-mismatch",
                               "message": "形状 #%s 连接点 %s 处的线没有沿法线引出/进入" % (node, pt[4])})
    outs = {}
    for e in edges:
        outs.setdefault(e["a"], []).append(e["id"])
    for node, ids in outs.items():
        if len(ids) >= 2:
            keys = {choice[(i, "a")][4] for i in ids}
            if len(keys) < len(ids):
                issues.append({"connector": None, "code": "branch-ports",
                               "message": "形状 #%s 有 %d 条出线，只用到 %d 个连接点"
                                          % (node, len(ids), len(keys))})
    return issues


def layout(nodes, edges):
    if not nodes or not edges:
        return {}, [], {}
    choice = assign(nodes, edges)
    routes, bad = route(nodes, edges, choice)
    return routes, check(nodes, edges, choice, routes) + bad, choice
