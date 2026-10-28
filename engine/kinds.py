# -*- coding: utf-8 -*-
"""Shape kinds written as real Visio geometry rows.

Every closed kind uses the Rel* row types, whose coordinates are fractions of
Width/Height - so a shape keeps its silhouette when the panel resizes it.
"""

# name -> (list of (row type, x, y), closed)
KINDS = {
    "rect": [("RelMoveTo", 0, 0), ("RelLineTo", 1, 0), ("RelLineTo", 1, 1),
             ("RelLineTo", 0, 1), ("RelLineTo", 0, 0)],
    "roundrect": [("RelMoveTo", 0, 0), ("RelLineTo", 1, 0), ("RelLineTo", 1, 1),
                  ("RelLineTo", 0, 1), ("RelLineTo", 0, 0)],
    "terminator": [("RelMoveTo", 0, 0), ("RelLineTo", 1, 0), ("RelLineTo", 1, 1),
                   ("RelLineTo", 0, 1), ("RelLineTo", 0, 0)],
    "diamond": [("RelMoveTo", 0.5, 0), ("RelLineTo", 1, 0.5), ("RelLineTo", 0.5, 1),
                ("RelLineTo", 0, 0.5), ("RelLineTo", 0.5, 0)],
    "triangle": [("RelMoveTo", 0.5, 0), ("RelLineTo", 1, 1), ("RelLineTo", 0, 1),
                 ("RelLineTo", 0.5, 0)],
    "parallelogram": [("RelMoveTo", 0.2, 0), ("RelLineTo", 1, 0), ("RelLineTo", 0.8, 1),
                      ("RelLineTo", 0, 1), ("RelLineTo", 0.2, 0)],
    "trapezoid": [("RelMoveTo", 0.2, 0), ("RelLineTo", 0.8, 0), ("RelLineTo", 1, 1),
                  ("RelLineTo", 0, 1), ("RelLineTo", 0.2, 0)],
    "hexagon": [("RelMoveTo", 0.25, 0), ("RelLineTo", 0.75, 0), ("RelLineTo", 1, 0.5),
                ("RelLineTo", 0.75, 1), ("RelLineTo", 0.25, 1), ("RelLineTo", 0, 0.5),
                ("RelLineTo", 0.25, 0)],
    "chevron": [("RelMoveTo", 0, 0), ("RelLineTo", 0.8, 0), ("RelLineTo", 1, 0.5),
                ("RelLineTo", 0.8, 1), ("RelLineTo", 0, 1), ("RelLineTo", 0.2, 0.5),
                ("RelLineTo", 0, 0)],
    "arrow_right": [("RelMoveTo", 0, 0.25), ("RelLineTo", 0.6, 0.25), ("RelLineTo", 0.6, 0),
                    ("RelLineTo", 1, 0.5), ("RelLineTo", 0.6, 1), ("RelLineTo", 0.6, 0.75),
                    ("RelLineTo", 0, 0.75), ("RelLineTo", 0, 0.25)],
    "arrow_left": [("RelMoveTo", 1, 0.25), ("RelLineTo", 0.4, 0.25), ("RelLineTo", 0.4, 0),
                   ("RelLineTo", 0, 0.5), ("RelLineTo", 0.4, 1), ("RelLineTo", 0.4, 0.75),
                   ("RelLineTo", 1, 0.75), ("RelLineTo", 1, 0.25)],
    "arrow_up": [("RelMoveTo", 0.25, 1), ("RelLineTo", 0.25, 0.4), ("RelLineTo", 0, 0.4),
                 ("RelLineTo", 0.5, 0), ("RelLineTo", 1, 0.4), ("RelLineTo", 0.75, 0.4),
                 ("RelLineTo", 0.75, 1), ("RelLineTo", 0.25, 1)],
    "arrow_down": [("RelMoveTo", 0.25, 0), ("RelLineTo", 0.25, 0.6), ("RelLineTo", 0, 0.6),
                   ("RelLineTo", 0.5, 1), ("RelLineTo", 1, 0.6), ("RelLineTo", 0.75, 0.6),
                   ("RelLineTo", 0.75, 0), ("RelLineTo", 0.25, 0)],
    "ellipse": [("Ellipse", 0, 0, 0, 0)],
    "text": [],
    "line": [("RelMoveTo", 0, 1), ("RelLineTo", 1, 0)],
}

# rounding is expressed as a fraction of the short side
ROUNDING = {"roundrect": 0.12, "terminator": 0.32}


def rows_for(kind: str, w: float, h: float):
    """Return (row type, {cell: value}) pairs in shape-local inches."""
    spec = KINDS.get(kind) or KINDS["rect"]
    rows = []
    for item in spec:
        if item[0] == "Ellipse":
            rows.append(("Ellipse", {"X": w / 2.0, "Y": h / 2.0, "A": h / 2.0,
                                     "B": w / 2.0, "C": h / 2.0, "D": w / 2.0}))
            continue
        kind_row, x, y = item
        rows.append((kind_row, {"X": x, "Y": y}))
    return rows
