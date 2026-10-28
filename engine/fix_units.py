#!/usr/bin/env python
"""Standalone unit repair for .vsdx files.

Generators often write inch values into Visio cells while labelling them
U="MM" or U="PT". Visio honours the label, so such a drawing opens with a
0.65 x 0.46 inch page, 0.16 pt text and 54 pt lines - everything collapses
into a pile of overlapping blocks. The preview built into this plugin reads
the same cells, so it used to disagree with Visio.

This script rewrites every labelled cell into Visio internal units (inches)
and drops the misleading U attribute, in place, with a .bak-<stamp> backup.

    python engine/fix_units.py "D:\\drawings\\flow.vsdx" [more.vsdx ...]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vsdx_core import Vsdx, VsdxError  # noqa: E402


def main(argv) -> int:
    if not argv:
        print(__doc__.strip())
        return 2
    failed = 0
    for path in argv:
        if not path.lower().endswith(".vsdx"):
            print("skip (not .vsdx): %s" % path)
            failed += 1
            continue
        try:
            doc = Vsdx(path)
            before = (doc.pages[0]["width"], doc.pages[0]["height"]) if doc.pages else (0, 0)
            report = doc.normalize_units()
            doc.save()
            after = (doc.pages[0]["width"], doc.pages[0]["height"]) if doc.pages else (0, 0)
            print("%s: %d cells, page %.2f x %.2f -> %.2f x %.2f in"
                  % (os.path.basename(path), report["cells"], before[0], before[1], after[0], after[1]))
        except VsdxError as exc:
            print("%s: %s" % (os.path.basename(path), exc))
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
