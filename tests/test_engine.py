#!/usr/bin/env python
"""End-to-end tests for the DSH Visio engine and JSON bridge.

Run from the plugin folder:

    python tests/test_engine.py

The tests write into tests/_out (created and removed by the suite) because the
DSH workspace sandbox only allows writes below the workspace root.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import time
import unittest
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "engine")
OUT = os.path.join(HERE, "_out")
sys.path.insert(0, ENGINE)

import blank_doc  # noqa: E402
import visio_bridge  # noqa: E402
from vsdx_core import Vsdx, VsdxError, _v  # noqa: E402


def run_bridge(payload: dict):
    """Drive main() in-process: the Host speaks the same stdin/stdout JSON contract.

    A child process cannot be spawned under the DSH file sandbox (Windows denies the
    pipe), so the test redirects the process streams instead of piping.
    """
    saved_in, saved_out = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps(payload, ensure_ascii=False))
    sys.stdout = io.StringIO()
    try:
        code = visio_bridge.main()
        body = sys.stdout.getvalue().strip()
    finally:
        sys.stdin, sys.stdout = saved_in, saved_out
    assert body, "bridge produced no output"
    result = json.loads(body)
    assert result.get("ok") is (code == 0), "exit code disagrees with ok flag: %r" % result
    return result


class EngineTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(OUT, ignore_errors=True)
        os.makedirs(OUT, exist_ok=True)
        self.path = os.path.join(OUT, "drawing.vsdx")

    def test_create_and_roundtrip(self):
        blank_doc.create(self.path, width=11, height=8.5, page_name="Page-1", title="Demo")
        doc = Vsdx(self.path)
        info = doc.info()
        self.assertEqual(len(info["pages"]), 1)
        self.assertAlmostEqual(info["pages"][0]["width_in"], 11.0)
        self.assertEqual(doc.shapes(1), [])

    def test_edit_cycle(self):
        blank_doc.create(self.path)
        doc = Vsdx(self.path)
        a = doc.add_shape(1, 1.0, 5.0, 2.0, 1.0, "Start", "rect", "#EAF2FF", "#2F6FBF")
        b = doc.add_shape(1, 5.0, 5.0, 2.0, 1.0, "Next", "ellipse")
        label = doc.add_shape(1, 1.0, 6.6, 4.0, 0.7, "Title", "text")
        link = doc.connect(a, b, 1, label="go")
        doc.set_text(b, "Step 2")
        doc.move_shape(b, x=5.5, y=4.25, w=2.4, h=1.1)
        doc.set_cells(a, {"FillForegnd": "#FFE7C2", "LineColor": "#AA5500"})
        doc.set_prop(a, "Owner", "Example Owner")
        doc.save(backup=False)

        fresh = Vsdx(self.path)
        shapes = {s["id"]: s for s in fresh.shapes(1)}
        self.assertEqual(set(shapes), {a, b, label, link})
        self.assertTrue(shapes[link]["connector"])
        self.assertEqual(shapes[b]["text"], "Step 2")
        self.assertAlmostEqual(shapes[b]["bbox"]["x"], 5.5)
        self.assertAlmostEqual(shapes[b]["bbox"]["w"], 2.4)
        self.assertEqual(fresh.style(a, 1)["fill"], "#FFE7C2")
        self.assertEqual(fresh.style(a, 1)["line"], "#AA5500")
        detail = fresh.shape(a, 1)
        candidates = [row for row in detail["sections"].get("Property", [])]
        self.assertTrue(candidates)
        self.assertIn("Owner", fresh.text_dump() + json.dumps(detail))

        svg = fresh.to_svg(1, interactive=True)
        for sid in shapes:
            self.assertIn('data-shape-id="%s"' % sid, svg)
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.rstrip().endswith("</svg>"))

    def test_set_cells_drops_formula(self):
        blank_doc.create(self.path)
        doc = Vsdx(self.path)
        sid = doc.add_shape(1, 1, 1, 1, 1, "x")
        part, root = doc._page_root(1)
        for sh, _p, _d in doc._iter_shapes(root.find(_v("Shapes"))):
            if sh.get("ID") == sid:
                for cell in sh.findall(_v("Cell")):
                    if cell.get("N") == "FillForegnd":
                        cell.set("F", 'THEMEVAL("FillColor")')
        doc._write_page(part, root)
        doc.set_cells(sid, {"FillForegnd": "#123456"})
        doc.save(backup=False)
        with zipfile.ZipFile(self.path) as z:
            xml = z.read("visio/pages/page1.xml").decode("utf-8")
        self.assertIn('V="#123456"', xml)
        self.assertNotIn('F="THEMEVAL(', xml)

    def test_backup_and_prune(self):
        blank_doc.create(self.path)
        doc = Vsdx(self.path)
        sid = doc.add_shape(1, 1, 1, 2, 1, "x")
        doc.save(backup=False)
        for i in range(4):
            doc = Vsdx(self.path)
            doc.set_text(sid, "t%d" % i)
            doc.save(keep_backups=2)
            time.sleep(0.02)
        backups = [n for n in os.listdir(OUT) if n.startswith("drawing.vsdx.bak-")]
        self.assertEqual(len(backups), 2)
        self.assertEqual(Vsdx(self.path).shape(sid, 1)["text"], "t3")

    def test_xml_integrity_of_new_document(self):
        blank_doc.create(self.path, 8.2677, 11.6929, page_name="A4")
        with zipfile.ZipFile(self.path) as z:
            self.assertIn("[Content_Types].xml", z.namelist())
            for name in z.namelist():
                ET.fromstring(z.read(name))

    def test_delete_removes_connectors(self):
        blank_doc.create(self.path)
        doc = Vsdx(self.path)
        a = doc.add_shape(1, 1, 1, 1, 1, "a")
        b = doc.add_shape(1, 4, 1, 1, 1, "b")
        link = doc.connect(a, b, 1)
        doc.delete_shape(b, 1)
        doc.save(backup=False)
        ids = {s["id"] for s in Vsdx(self.path).shapes(1)}
        self.assertIn(a, ids)
        self.assertNotIn(b, ids)
        self.assertNotIn(link, ids)

    def test_page_bounds_and_validation(self):
        with self.assertRaises(Exception):
            blank_doc.create(self.path, 0, 8)

    def test_validate_flags_zero_size_and_unbound(self):
        path = os.path.join(OUT, "audit.vsdx")
        blank_doc.create(path, 11, 8.5, "P1", "Audit")
        doc = Vsdx(path)
        a = doc.add_shape(page=1, x=1, y=5, w=2, h=1, text="A")
        b = doc.add_shape(page=1, x=5, y=5, w=2, h=1, text="B")
        doc.connect(a, b, label="go", page=1)
        doc.set_cells(a, {"Width": 0}, page=1)          # collapse one shape
        doc.save()
        report = run_bridge({"action": "validate", "path": path})
        codes = {item["code"] for item in report["issues"]}
        self.assertIn("zero-size", codes)
        self.assertEqual(report["counts"]["error"], 1)
        self.assertEqual(report["connectors"], 1)
        labels = [i for i in report["issues"] if i["code"] == "connector-label"]
        self.assertTrue(labels and "go" in labels[0]["message"])

    def test_text_runs_use_character_colours(self):
        path = os.path.join(OUT, "runs.vsdx")
        blank_doc.create(path, 11, 8.5, "P1", "Runs")
        doc = Vsdx(path)
        sid = doc.add_shape(page=1, x=1, y=5, w=2, h=1, text="one\ntwo")
        doc.save()
        runs = Vsdx(path).text_runs(sid, 1)
        self.assertEqual([r[0] for r in runs], ["one", "two"])
        self.assertIsNone(runs[1][1])                   # no Character override -> None

    def test_stencil_info_and_sheet(self):
        import make_vssx
        st = os.path.join(OUT, "shapes.vssx")
        make_vssx.build(st)
        info = run_bridge({"action": "stencil_info", "file": st})
        names = [m["name"] for m in info["masters"]]
        self.assertEqual(names, ["Rectangle", "Diamond", "Arrow Right"])
        self.assertTrue(all(m["width"] and m["height"] for m in info["masters"]))
        sheet = run_bridge({"action": "stencil_sheet", "file": st})
        self.assertTrue(os.path.getsize(sheet["out"]) > 2000)

    def test_snapshot_matches_page(self):
        path = os.path.join(OUT, "shot.vsdx")
        blank_doc.create(path, 11, 8.5, "P1", "")
        doc = Vsdx(path)
        doc.add_shape(page=1, x=1, y=5, w=2, h=1, text="Hello")
        doc.save()
        out = os.path.join(OUT, "shots")
        snap = run_bridge({"action": "snapshot", "path": path, "out": out, "dpi": 96})
        self.assertEqual(len(snap["files"]), 1)
        from PIL import Image
        with Image.open(snap["files"][0]) as img:
            self.assertGreater(img.size[0], 900)
            self.assertGreater(img.size[1], 700)


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shutil.rmtree(OUT, ignore_errors=True)
        os.makedirs(OUT, exist_ok=True)
        cls.path = os.path.join(OUT, "bridge.vsdx")

    def test_full_flow(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        ping = run_bridge({"action": "ping"})
        self.assertTrue(ping["ok"])

        created = run_bridge({
            "action": "create", "dir": OUT, "name": "bridge", "width": 11, "height": 8.5,
            "title": "Bridge demo",
        })
        self.assertTrue(created["ok"], created)
        self.assertEqual(created["path"], self.path)
        self.assertEqual(created["page"], 1)
        self.assertTrue(created["svg"].count("data-shape-id") >= 1)

        added = run_bridge({
            "action": "add_shape", "path": self.path, "x": 1, "y": 5, "w": 2, "h": 1,
            "text": "Hello", "kind": "rect", "fill": "#EAF2FF",
        })
        self.assertTrue(added["ok"], added)
        first = added["detail"]["id"]
        self.assertEqual(added["notice"], "已添加形状 #%s" % first)

        second = run_bridge({
            "action": "add_shape", "path": self.path, "x": 5, "y": 5, "w": 2, "h": 1,
            "text": "World", "kind": "ellipse",
        })["detail"]["id"]

        linked = run_bridge({"action": "connect", "path": self.path, "from": first, "to": second})
        self.assertTrue(linked["ok"])

        updated = run_bridge({"action": "set_text", "path": self.path, "shape_id": second, "text": "Line 1\nLine 2"})
        self.assertTrue(updated["ok"])
        self.assertIn("Line 2", updated["detail"]["text"])

        cells = run_bridge({
            "action": "set_cells", "path": self.path, "shape_id": first,
            "cells": {"FillForegnd": "#FFE7C2", "LineWeight": 0.02},
        })
        self.assertEqual(cells["detail"]["style"]["fill"], "#FFE7C2")

        moved = run_bridge({"action": "move", "path": self.path, "shape_id": first, "x": 2.5, "w": 3})
        self.assertAlmostEqual(float(moved["detail"]["cells"]["PinX"]) - 1.5, 2.5, places=3)

        prop = run_bridge({"action": "set_prop", "path": self.path, "shape_id": first, "name": "Tag", "value": "A1"})
        self.assertEqual(prop["detail"]["props"]["Tag"], "A1")

        listed = run_bridge({"action": "list", "dir": OUT})
        self.assertTrue(any(item["name"] == "bridge.vsdx" for item in listed["files"]))

        stat = run_bridge({"action": "stat", "path": self.path})
        self.assertTrue(stat["ok"])
        self.assertGreater(stat["mtime"], 0)

        exported = run_bridge({"action": "export", "path": self.path, "format": "svg"})
        self.assertTrue(os.path.isfile(exported["out"]))

        text = run_bridge({"action": "text", "path": self.path})
        self.assertIn("Bridge demo", text["text"])
        self.assertIn("Line 1 / Line 2", text["text"])

        detail = run_bridge({"action": "get_shape", "path": self.path, "shape_id": first})
        self.assertEqual(detail["detail"]["id"], first)
        self.assertEqual(detail["detail"]["props"].get("Tag"), "A1")

        removed = run_bridge({"action": "delete", "path": self.path, "shape_id": second})
        self.assertTrue(removed["ok"])
        self.assertNotIn(second, [s["id"] for s in removed["shapes"]])

    def test_errors(self):
        self.assertFalse(run_bridge({"action": "nope"})["ok"])
        self.assertFalse(run_bridge({"action": "open"})["ok"])
        self.assertFalse(run_bridge({"action": "open", "path": os.path.join(OUT, "missing.vsdx")})["ok"])
        self.assertFalse(run_bridge({"action": "open", "path": os.path.join(ENGINE, "vsdx_core.py")})["ok"])
        created = run_bridge({"action": "create", "dir": OUT, "name": "../../escape"})
        self.assertFalse(created["ok"])
        first = run_bridge({"action": "create", "dir": OUT, "name": "collision"})
        self.assertTrue(first["ok"], first)
        again = run_bridge({"action": "create", "dir": OUT, "name": "collision"})
        self.assertFalse(again["ok"], "creating an existing file must fail without overwrite")
        allowed = run_bridge({"action": "create", "dir": OUT, "name": "collision", "overwrite": True})
        self.assertTrue(allowed["ok"], allowed)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(OUT, ignore_errors=True)
        os.makedirs(OUT, exist_ok=True)

    def _new(self, name):
        path = os.path.join(OUT, name)
        blank_doc.create(path, width=11, height=8.5, page_name="Page-1", title="t")
        return Vsdx(path)

    def test_rel_geometry_is_real_outline(self):
        doc = self._new("geo.vsdx")
        sid = doc.add_shape(1, 2.0, 3.0, 1.5, 0.75, text="box", kind="rect")
        paths = doc.geometry_paths(sid, 1)
        self.assertEqual(len(paths), 1)
        pts = paths[0]["pts"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.assertAlmostEqual(min(xs), 2.0, places=3)
        self.assertAlmostEqual(max(xs), 3.5, places=3)
        self.assertAlmostEqual(min(ys), 3.0, places=3)
        self.assertAlmostEqual(max(ys), 3.75, places=3)

    def test_normalize_units_rewrites_point_weights(self):
        doc = self._new("norm.vsdx")
        sid = doc.add_shape(1, 1.0, 1.0, 2.0, 1.0, text="n", kind="rect")
        part = doc.page_part(1)
        root = doc._xml(part)
        for sh, _p, _d in doc._iter_shapes(root.find(_v("Shapes"))):
            if sh.get("ID") == str(sid):
                for c in sh.findall(_v("Cell")):
                    if c.get("N") == "LineWeight":
                        c.set("V", "0.75")
                        c.set("U", "PT")
        doc._write_page(part, root)
        report = doc.normalize_units()
        self.assertGreater(report["cells"], 0)
        root = doc._xml(part)
        weights = [c for c in root.iter(_v("Cell")) if c.get("N") == "LineWeight"]
        self.assertTrue(weights)
        self.assertTrue(all(c.get("U") is None for c in weights))
        self.assertAlmostEqual(float(weights[0].get("V")), 0.75 / 72.0, places=6)


# --------------------------------------------------- connector editing regressions
TOL = 1e-4


def _saved_page(path, page=1):
    """The page part exactly as it sits inside the saved package."""
    part = Vsdx(path).page_part(page)
    with zipfile.ZipFile(path) as z:
        return ET.fromstring(z.read(part))


def _saved_shape(root, shape_id):
    for sh in root.iter(_v("Shape")):
        if sh.get("ID") == str(shape_id):
            return sh
    raise AssertionError("shape %s missing from the saved page" % shape_id)


def _saved_cells(root, shape_id):
    return {c.get("N"): c.get("V") for c in _saved_shape(root, shape_id).findall(_v("Cell"))}


def _saved_point(root, shape_id, x_name, y_name):
    cells = _saved_cells(root, shape_id)
    return (float(cells[x_name]), float(cells[y_name]))


def _connect_rows(root, from_sheet=None, from_cell=None):
    """Page-level <Connects> rows, the way Visio stores glue."""
    conns = root.find(_v("Connects"))
    if conns is None:
        return []
    rows = []
    for c in conns.findall(_v("Connect")):
        if from_sheet is not None and c.get("FromSheet") != str(from_sheet):
            continue
        if from_cell is not None and c.get("FromCell") != from_cell:
            continue
        rows.append({
            "FromSheet": c.get("FromSheet"), "FromCell": c.get("FromCell"),
            "ToSheet": c.get("ToSheet"), "ToCell": c.get("ToCell"),
        })
    return rows


def _add_connection_point(doc, shape_id, x, y, page=1):
    """Give a shape an explicit Section N="Connection" row (X/Y are shape-local)."""
    part, root = doc._page_root(page)
    for sh, _p, _d in doc._iter_shapes(root.find(_v("Shapes"))):
        if sh.get("ID") != str(shape_id):
            continue
        sec = ET.SubElement(sh, _v("Section"))
        sec.set("N", "Connection")
        sec.set("IX", "0")
        row = ET.SubElement(sec, _v("Row"))
        row.set("IX", "0")
        for name, value in (("X", x), ("Y", y), ("DirX", 0), ("DirY", 0)):
            cell = ET.SubElement(row, _v("Cell"))
            cell.set("N", name)
            cell.set("V", str(value))
        break
    else:
        raise AssertionError("shape %s not found" % shape_id)
    doc._write_page(part, root)


def _axis_aligned(points):
    return all(abs(a[0] - b[0]) <= TOL or abs(a[1] - b[1]) <= TOL
               for a, b in zip(points, points[1:]))


def _pts(points):
    return [(round(float(x), 4), round(float(y), 4)) for x, y in points]


def _has_point(points, pt):
    return any(abs(p[0] - pt[0]) <= TOL and abs(p[1] - pt[1]) <= TOL for p in points)


def _runs(points):
    return list(zip(points, points[1:]))


def _moved_runs(points, before, delta, axis):
    """Runs of the dragged line that now sit exactly delta away along their normal.

    axis="y" is a horizontal run slid vertically; axis="x" is a vertical run slid
    sideways.  The run must still be parallel to the original one and both of its
    end points must be the originals translated by delta.
    """
    out = []
    for a, b in _runs(points):
        if axis == "y":
            if (abs(a[1] - b[1]) <= TOL                    # still horizontal
                    and abs(a[1] - (before[0][1] + delta)) <= TOL
                    and abs(b[1] - (before[1][1] + delta)) <= TOL
                    and abs(a[0] - before[0][0]) <= TOL
                    and abs(b[0] - before[1][0]) <= TOL):
                out.append((a, b))
        else:
            if (abs(a[0] - b[0]) <= TOL                    # still vertical
                    and abs(a[0] - (before[0][0] + delta)) <= TOL
                    and abs(b[0] - (before[1][0] + delta)) <= TOL
                    and abs(a[1] - before[0][1]) <= TOL
                    and abs(b[1] - before[1][1]) <= TOL):
                out.append((a, b))
    return out


class ConnectorEditTests(unittest.TestCase):
    """Engine-side regressions for connector editing, checked against the saved file.

    Every case edits a throw-away copy under tests/_out, saves it, and reads the
    package back: asserting on the in-memory object would let a silent no-op pass,
    and what matters is what Visio finds in the file.  Coordinates come back
    rounded to 6 decimals by set_route, so comparisons use a 1e-4 tolerance.
    """

    def setUp(self):
        shutil.rmtree(OUT, ignore_errors=True)
        os.makedirs(OUT, exist_ok=True)

    # ---------------------------------------------------------- builders
    def _new(self, name):
        path = os.path.join(OUT, name)
        blank_doc.create(path, 11, 8.5, "Page-1", "t")
        return path

    def _two_boxes(self, path, by=5.0):
        """Two 2x1 boxes plus the connector that joins them."""
        doc = Vsdx(path)
        a = doc.add_shape(1, 1.0, 5.0, 2.0, 1.0, "A", "rect")
        b = doc.add_shape(1, 5.0, by, 2.0, 1.0, "B", "rect")
        link = doc.connect(a, b, 1, label="go")
        doc.save(backup=False)
        return a, b, link

    def _box(self, path, x, y, w=1.5, h=1.0):
        doc = Vsdx(path)
        sid = doc.add_shape(1, x, y, w, h, "C", "rect")
        doc.save(backup=False)
        return sid

    def _ports(self, path, shape_id):
        bbox = next(s for s in Vsdx(path).shapes(1) if s["id"] == str(shape_id))["bbox"]
        return [(bbox["x"], bbox["y"] + bbox["h"] / 2.0),
                (bbox["x"] + bbox["w"], bbox["y"] + bbox["h"] / 2.0),
                (bbox["x"] + bbox["w"] / 2.0, bbox["y"]),
                (bbox["x"] + bbox["w"] / 2.0, bbox["y"] + bbox["h"])]

    def _route(self, path, link, points):
        doc = Vsdx(path)
        doc.set_route(link, points, page=1)
        doc.save(backup=False)

    # ------------------------------------------------------- reglue / glue
    def test_reglue_end_snaps_to_nearest_edge_midpoint(self):
        path = self._new("reglue-end.vsdx")
        a, b, link = self._two_boxes(path)
        c = self._box(path, 8.0, 3.0)
        root = _saved_page(path)
        begin = _saved_point(root, link, "BeginX", "BeginY")
        old_end = _saved_point(root, link, "EndX", "EndY")
        self.assertEqual(_pts([begin])[0], (3.0, 5.5))
        self.assertEqual(_pts([old_end])[0], (5.0, 5.5))

        doc = Vsdx(path)
        doc.reglue(link, "end", c, x=8.6, y=4.2, page=1)
        doc.save(backup=False)

        root = _saved_page(path)
        end = _saved_point(root, link, "EndX", "EndY")
        ports = self._ports(path, c)
        self.assertTrue(_has_point(ports, end),
                        "EndX/EndY %r is not one of the target's edge midpoints %r"
                        % (_pts([end])[0], _pts(ports)))
        # (8.6, 4.2) is nearest the top midpoint of the box at (8, 3, 1.5, 1)
        self.assertEqual(_pts([end])[0], (8.75, 4.0))
        self.assertNotEqual(_pts([end])[0], _pts([old_end])[0])
        self.assertEqual(_pts([_saved_point(root, link, "BeginX", "BeginY")])[0], _pts([begin])[0],
                         "re-gluing the end moved the start")
        # exactly one glue row for this end, pointing at the new target
        rows = _connect_rows(root, link, "EndX")
        self.assertEqual(len(rows), 1, "expected one Connects row for EndX, got %r" % (rows,))
        self.assertEqual(rows[0]["ToSheet"], str(c))
        self.assertEqual(rows[0]["ToCell"], "PinX")
        self.assertEqual([r["ToSheet"] for r in _connect_rows(root, link, "BeginX")], [str(a)])

    def test_reglue_uses_connection_rows_when_present(self):
        path = self._new("reglue-port.vsdx")
        a, b, link = self._two_boxes(path)
        c = self._box(path, 8.0, 3.0, w=2.0, h=1.0)
        doc = Vsdx(path)
        _add_connection_point(doc, c, 0.25, 0.25)      # absolute (8.25, 3.25)
        doc.save(backup=False)

        doc = Vsdx(path)
        rows = doc.shape(c, 1)["sections"]["Connection"][0]["rows"]
        self.assertTrue(rows, "the injected Connection section did not parse")

        doc.reglue(link, "end", c, x=8.9, y=4.4, page=1)
        doc.save(backup=False)
        end = _saved_point(_saved_page(path), link, "EndX", "EndY")
        self.assertEqual(_pts([end])[0], (8.25, 3.25),
                         "a declared Connection point must beat the default edge midpoints")
        for px, py in self._ports(path, c):            # (8,3.5) (10,3.5) (9,3) (9,4)
            self.assertNotEqual(_pts([end])[0], _pts([(px, py)])[0])

    def test_reglue_start_is_symmetric(self):
        path = self._new("reglue-start.vsdx")
        a, b, link = self._two_boxes(path)
        c = self._box(path, 8.0, 3.0)
        doc = Vsdx(path)
        doc.reglue(link, "start", c, x=8.2, y=3.1, page=1)
        doc.save(backup=False)

        root = _saved_page(path)
        begin = _saved_point(root, link, "BeginX", "BeginY")
        self.assertEqual(_pts([begin])[0], (8.0, 3.5), "start end did not snap to the nearest port")
        rows = _connect_rows(root, link, "BeginX")
        self.assertEqual(len(rows), 1, "expected one Connects row for BeginX, got %r" % (rows,))
        self.assertEqual(rows[0]["ToSheet"], str(c))
        self.assertEqual(rows[0]["ToCell"], "PinX")
        # the far end still belongs to B and never moved
        self.assertEqual(_pts([_saved_point(root, link, "EndX", "EndY")])[0], (5.0, 5.5))
        self.assertEqual([r["ToSheet"] for r in _connect_rows(root, link, "EndX")], [str(b)])

        # re-gluing the same end replaces the row instead of appending a second one
        doc = Vsdx(path)
        doc.reglue(link, "start", a, x=1.0, y=5.0, page=1)
        doc.save(backup=False)
        root = _saved_page(path)
        rows = _connect_rows(root, link, "BeginX")
        self.assertEqual(len(rows), 1, "re-gluing appended a duplicate Connects row: %r" % (rows,))
        self.assertEqual(rows[0]["ToSheet"], str(a))
        self.assertEqual(_pts([_saved_point(root, link, "BeginX", "BeginY")])[0], (1.0, 5.5))

    def test_reglue_moves_the_drawn_polyline_end_too(self):
        """A hand-drawn route must follow the endpoint, or the picture desyncs."""
        path = self._new("reglue-route.vsdx")
        a, b, link = self._two_boxes(path)
        c = self._box(path, 8.0, 3.0)
        route = [(3.0, 5.5), (4.0, 5.5), (4.0, 3.5), (5.0, 3.5)]
        self._route(path, link, route)

        doc = Vsdx(path)
        self.assertEqual(_pts(doc.drawn_points(link, 1)), _pts(route))

        doc.reglue(link, "end", c, x=8.0, y=3.6, page=1)
        doc.save(backup=False)

        doc = Vsdx(path)
        geometry = _pts(doc.geometry_points(link, 1))
        drawn = _pts(doc.drawn_points(link, 1))
        port = (8.0, 3.5)                              # left midpoint of C
        self.assertEqual(geometry[0], _pts([route[0]])[0],
                         "reglue moved the wrong end of the polyline")
        self.assertEqual(geometry[-1], port,
                         "the stored polyline still ends at %r, the new port is %r"
                         % (geometry[-1], port))
        self.assertEqual(drawn[0], _pts([route[0]])[0])
        self.assertEqual(drawn[-1], port, "drawn_points still shows the old end: %r" % (drawn,))
        root = _saved_page(path)
        self.assertEqual(_pts([_saved_point(root, link, "BeginX", "BeginY")])[0], _pts([route[0]])[0])
        self.assertEqual(_pts([_saved_point(root, link, "EndX", "EndY")])[0], port)

        # the start handle gets the same treatment
        doc = Vsdx(path)
        doc.reglue(link, "start", a, x=2.0, y=6.0, page=1)   # top midpoint of A
        doc.save(backup=False)
        doc = Vsdx(path)
        geometry = _pts(doc.geometry_points(link, 1))
        self.assertEqual(geometry[0], (2.0, 6.0),
                         "the start handle did not move the polyline: %r" % (geometry,))
        self.assertEqual(geometry[-1], port, "re-gluing the start disturbed the other end")
        root = _saved_page(path)
        self.assertEqual(_pts([_saved_point(root, link, "BeginX", "BeginY")])[0], (2.0, 6.0))

    # --------------------------------------------------- move_segment drags
    def test_move_segment_keeps_endpoints_and_stays_axis_aligned(self):
        path = self._new("segment.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)
        route = [(3.0, 5.5), (4.0, 5.5), (4.0, 3.5), (5.5, 3.5), (5.5, 4.5), (6.5, 4.5)]
        self._route(path, link, route)

        doc = Vsdx(path)
        before = _pts(doc.drawn_points(link, 1))
        self.assertEqual(before, _pts(route), "set_route did not survive the round trip")

        delta = 0.4
        doc.move_segment(link, 2, delta, page=1)       # horizontal run (4,3.5)->(5.5,3.5)
        doc.save(backup=False)

        doc = Vsdx(path)
        after = _pts(doc.drawn_points(link, 1))
        expected = [(3.0, 5.5), (4.0, 5.5), (4.0, 3.9), (5.5, 3.9), (5.5, 4.5), (6.5, 4.5)]
        self.assertEqual(after, expected, "only the dragged run may move, and only by delta")
        self.assertEqual(after[0], before[0], "the start point moved: %r -> %r" % (before[0], after[0]))
        self.assertEqual(after[-1], before[-1], "the end point moved: %r -> %r" % (before[-1], after[-1]))
        self.assertTrue(_axis_aligned(after), "the polyline is no longer axis aligned: %r" % (after,))
        # the dragged run itself is the only run translated by delta
        moved = _moved_runs(after, (before[2], before[3]), delta, "y")
        self.assertEqual(len(moved), 1, "the dragged run did not move by delta: %r" % (after,))
        self.assertEqual(_pts([moved[0][0], moved[0][1]]), [(4.0, 3.9), (5.5, 3.9)])
        root = _saved_page(path)
        self.assertEqual(_pts([_saved_point(root, link, "BeginX", "BeginY")])[0], before[0])
        self.assertEqual(_pts([_saved_point(root, link, "EndX", "EndY")])[0], before[-1])

    def test_move_segment_of_a_vertical_run_moves_sideways(self):
        path = self._new("segment-vertical.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)
        route = [(3.0, 5.5), (4.0, 5.5), (4.0, 3.5), (5.0, 3.5)]
        self._route(path, link, route)

        doc = Vsdx(path)
        before = _pts(doc.drawn_points(link, 1))
        doc.move_segment(link, 1, 0.4, page=1)         # vertical run (4,5.5)->(4,3.5)
        doc.save(backup=False)

        after = _pts(Vsdx(path).drawn_points(link, 1))
        expected = [(3.0, 5.5), (4.4, 5.5), (4.4, 3.5), (5.0, 3.5)]
        self.assertEqual(after, expected, "a vertical run must slide sideways by delta")
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[-1], before[-1])
        self.assertTrue(_axis_aligned(after), "not axis aligned: %r" % (after,))
        moved = _moved_runs(after, (before[1], before[2]), 0.4, "x")
        self.assertEqual(len(moved), 1, "the dragged run did not move by delta: %r" % (after,))

    def test_move_segment_splits_a_straight_line_without_moving_ends(self):
        path = self._new("segment-straight.vsdx")
        a, b, link = self._two_boxes(path)             # side by side -> straight connector
        doc = Vsdx(path)
        before = _pts(doc.drawn_points(link, 1))
        self.assertEqual(before, [(3.0, 5.5), (5.0, 5.5)],
                         "expected a straight two-point connector, got %r" % (before,))

        delta = 0.5
        doc.move_segment(link, 0, delta, page=1)       # first drag splits it into a jog
        doc.save(backup=False)

        after = _pts(Vsdx(path).drawn_points(link, 1))
        self.assertGreaterEqual(len(after), 4,
                                "a straight line must gain a jog, got %r" % (after,))
        self.assertEqual(after[0], before[0], "the start point moved: %r -> %r" % (before[0], after[0]))
        self.assertEqual(after[-1], before[-1], "the end point moved: %r -> %r" % (before[-1], after[-1]))
        self.assertTrue(_axis_aligned(after), "the jog is not axis aligned: %r" % (after,))
        # one horizontal run sits delta above the old line, inside the old span
        moved = [r for r in _runs(after)
                 if abs(r[0][1] - r[1][1]) <= TOL
                 and abs(r[0][1] - (before[0][1] + delta)) <= TOL]
        self.assertEqual(len(moved), 1, "no run was translated by %.2f: %r" % (delta, after))
        self.assertGreaterEqual(min(moved[0][0][0], moved[0][1][0]), before[0][0] - TOL)
        self.assertLessEqual(max(moved[0][0][0], moved[0][1][0]), before[1][0] + TOL)
        # and two stubs keep the line attached to both original ends
        self.assertEqual(len([r for r in _runs(after) if abs(r[0][0] - r[1][0]) <= TOL]), 2,
                         "the jog should have exactly two vertical stubs: %r" % (after,))
        root = _saved_page(path)
        self.assertEqual(_pts([_saved_point(root, link, "BeginX", "BeginY")])[0], before[0])
        self.assertEqual(_pts([_saved_point(root, link, "EndX", "EndY")])[0], before[-1])

    def test_move_segment_near_the_end_inserts_a_corner(self):
        path = self._new("segment-tail.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)
        route = [(3.0, 5.5), (4.0, 5.5), (4.0, 3.5), (5.0, 3.5)]
        self._route(path, link, route)

        doc = Vsdx(path)
        before = _pts(doc.drawn_points(link, 1))
        doc.move_segment(link, 2, 0.4, page=1)         # last run, touches the end point
        doc.save(backup=False)

        after = _pts(Vsdx(path).drawn_points(link, 1))
        self.assertEqual(after[0], before[0], "the start point moved: %r -> %r" % (before[0], after[0]))
        self.assertEqual(after[-1], before[-1], "the end point moved: %r -> %r" % (before[-1], after[-1]))
        self.assertTrue(_axis_aligned(after), "not axis aligned: %r" % (after,))
        # the tail run now sits delta above where it was, joined by a stub
        moved = _moved_runs(after, (before[2], before[3]), 0.4, "y")
        self.assertEqual(len(moved), 1,
                         "the dragged tail run did not move: %r" % (after,))
        self.assertGreaterEqual(len(after), len(before),
                                "dragging the tail must add a corner, not drop one")

    # ------------------------------------------------------------ simplify
    def test_simplify_keeps_only_real_corners(self):
        simplify = Vsdx._simplify
        # collinear middle points on both legs disappear, the corner stays
        self.assertEqual(simplify([(0, 0), (0.5, 0), (1, 0), (1, 0.5), (1, 1)]),
                         [(0, 0), (1, 0), (1, 1)])
        # a fully collinear run collapses to its two endpoints
        self.assertEqual(simplify([(0, 0), (1, 0), (2, 0)]), [(0, 0), (2, 0)])
        # duplicate points are dropped before the corner test
        self.assertEqual(simplify([(0, 0), (0, 0), (1, 0), (1, 0), (1, 1)]),
                         [(0, 0), (1, 0), (1, 1)])
        # mixed: redundant points plus duplicates around two real corners
        self.assertEqual(simplify([(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (2, 2), (3, 2)]),
                         [(0, 0), (2, 0), (2, 2), (3, 2)])
        # a two-point run is returned untouched, whatever its direction
        self.assertEqual(simplify([(0, 0), (3, 4)]), [(0, 0), (3, 4)])
        self.assertEqual(simplify([(0, 0), (1, 1)]), [(0, 0), (1, 1)])

    def test_simplify_collapses_a_router_micro_step(self):
        """A 0.017in step is invisible in the file but reads as a kink on screen."""
        simplify = Vsdx._simplify
        raw = [(4.95, 5.05), (5.899, 5.05), (5.899, 6.173), (7.083, 6.173),
               (7.083, 3.947), (7.1, 3.947), (7.1, 3.25)]
        out = simplify(raw)
        self.assertEqual(len(out), 5, "the micro step survived: %r" % (out,))
        self.assertEqual(out[0], raw[0], "the start point moved")
        self.assertEqual(out[-1], raw[-1], "the end point moved")
        # the two runs that carried the step are now one straight vertical run
        self.assertAlmostEqual(out[3][0], out[4][0], places=6,
                               msg="the vertical run still has a step: %r" % (out,))
        self.assertEqual(out[3][0], 7.1, "the step did not snap to the glued end")
        self.assertTrue(_axis_aligned(out), "not axis aligned: %r" % (out,))
        # a step that a person could have drawn on purpose is kept
        real = [(0, 0), (1, 0), (1, 0.05), (2, 0.05), (2, 0.2)]
        self.assertEqual(len(simplify(real)), len(real),
                         "a 0.05in corner was swallowed: %r" % (simplify(real),))

    # ------------------------------------------------ degenerate connectors
    def test_set_route_rejects_a_zero_length_connector(self):
        """A zero-length line renders as a bare arrow head floating in mid-air."""
        path = self._new("zero.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)
        doc = Vsdx(path)
        with self.assertRaises(VsdxError):
            doc.set_route(link, [(2.0, 4.0), (2.0, 4.0)], page=1)

    def test_degenerate_connector_is_marked_not_drawn_as_an_arrow(self):
        """Both ends on the same spot: no line, a marker instead, and still clickable."""
        path = self._new("degenerate.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)
        doc = Vsdx(path)
        part, root = doc._page_root(1)
        # A single-point Geometry is what the panel actually wrote into demo.vsdx:
        # both Begin and End landed on the same spot, so drawn_points() is one point.
        for sh, _p, _d in doc._iter_shapes(root.find(_v("Shapes"))):
            if sh.get("ID") != str(link):
                continue
            for name in ("BeginX", "BeginY", "EndX", "EndY"):
                for cell in sh.findall(_v("Cell")):
                    if cell.get("N") == name:
                        cell.set("V", "4.0")
            for sec in list(sh.findall(_v("Section"))):
                if sec.get("N") != "Geometry":
                    continue
                sh.remove(sec)
            # Two rows on the same spot: this is exactly what demo.vsdx ended up with
            # (Begin == End == (7.1, 5.5)), and drawn_points() collapses it to one point.
            sec = ET.SubElement(sh, _v("Section"))
            sec.set("N", "Geometry")
            sec.set("IX", "0")
            for ix, kind in ((0, "MoveTo"), (1, "LineTo")):
                row = ET.SubElement(sec, _v("Row"))
                row.set("T", kind)
                row.set("IX", str(ix))
                for nm, val in (("X", 1.0), ("Y", 1.0)):
                    cell = ET.SubElement(row, _v("Cell"))
                    cell.set("N", nm)
                    cell.set("V", str(val))
        doc._write_page(part, root)
        doc.save(backup=False)

        svg = Vsdx(path).to_svg(1, interactive=True, background=False)
        self.assertNotIn('marker-end="url(#dshv-arrow', svg,
                         "a zero-length connector still draws an arrow head")
        self.assertIn("stroke-dasharray=\"3 2\"", svg,
                      "the broken connector is not marked for the user")
        self.assertIn('pointer-events="stroke"', svg,
                      "the broken connector lost its click target")

    def test_reglue_never_leaves_the_line_crossing_a_shape(self):
        """Dragging one end across the page must not park the line on a box.

        A hand-drawn route wins over the router, so an end drag that puts a
        segment through an unrelated shape would keep that crossing forever.
        """
        path = self._new("reglue-cross.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)
        blocker = self._box(path, 3.5, 4.2, 1.5, 1.0)      # sits between a and b
        doc = Vsdx(path)
        # give it a hand-drawn route that runs straight through the blocker
        doc.set_route(link, [(3.0, 5.5), (6.0, 5.5)], page=1)
        doc.save(backup=False)

        doc = Vsdx(path)
        doc.reglue(link, "end", a, page=1)
        doc.save(backup=False)

        doc = Vsdx(path)
        pts = _pts(doc.drawn_points(link, 1))
        boxes = {s["id"]: s["bbox"] for s in doc.shapes(1) if not s["connector"]}
        glued = {str(c["to"]) for c in next(s for s in doc.shapes(1) if s["id"] == link)["connects"]}
        for sid, box in boxes.items():
            if sid in glued:
                continue
            for i in range(len(pts) - 1):
                self.assertFalse(
                    Vsdx._seg_hits_box(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], box),
                    "connector %s still cuts through shape %s: %r" % (link, sid, pts))
        self.assertTrue(_axis_aligned(pts), "re-route is not orthogonal: %r" % (pts,))

    # ------------------------------------------------------------- 1-D lines
    def test_add_line_stores_a_1d_line_not_a_box(self):
        """A line has two ends; it is not a rectangle with a diagonal inside."""
        path = self._new("line.vsdx")
        doc = Vsdx(path)
        doc.add_shape(1, 1.0, 5.0, 2.0, 1.0, "A", "rect")
        lid = doc.add_line(1, 1.0, 3.0, 4.0, 3.0)
        doc.save(backup=False)

        doc = Vsdx(path)
        meta = next(s for s in doc.shapes(1) if s["id"] == str(lid))
        self.assertTrue(meta.get("line"), "the line is not flagged as a line")
        self.assertFalse(meta["connector"], "a plain line must not become a connector")
        self.assertEqual(_pts(meta["points"]), [(1.0, 3.0), (4.0, 3.0)])
        # a zero-height box used to be skipped by the renderer entirely
        svg = doc.to_svg(1, interactive=True, background=False)
        self.assertIn('stroke-linecap="round"', svg, "a horizontal line was not drawn")
        self.assertIn('x1="1.0000"', svg)

    def test_set_line_moves_one_end(self):
        path = self._new("line2.vsdx")
        doc = Vsdx(path)
        lid = doc.add_line(1, 1.0, 3.0, 4.0, 3.0)
        doc.save(backup=False)
        doc = Vsdx(path)
        doc.set_line(lid, 1.0, 2.0, 4.0, 3.0)
        doc.save(backup=False)
        cells = Vsdx(path).shape(lid, 1)["cells"]
        self.assertAlmostEqual(float(cells["BeginY"]), 2.0, places=6)
        self.assertAlmostEqual(float(cells["EndY"]), 3.0, places=6)
        self.assertAlmostEqual(float(cells["Height"]), 1.0, places=6)

    def test_connect_honours_explicit_ports(self):
        """The dot the user dragged from must be the dot the line is glued to."""
        path = self._new("ports.vsdx")
        doc = Vsdx(path)
        a = doc.add_shape(1, 1.0, 5.0, 2.0, 1.0, "A", "rect")
        b = doc.add_shape(1, 5.0, 5.0, 2.0, 1.0, "B", "rect")
        cid = doc.connect(a, b, 1, from_port=(3.0, 5.05), to_port=(5.0, 5.05))
        doc.save(backup=False)
        cells = Vsdx(path).shape(cid, 1)["cells"]
        self.assertAlmostEqual(float(cells["BeginX"]), 3.0, places=6)
        self.assertAlmostEqual(float(cells["BeginY"]), 5.05, places=6)
        self.assertAlmostEqual(float(cells["EndX"]), 5.0, places=6)
        self.assertAlmostEqual(float(cells["EndY"]), 5.05, places=6)

    def test_router_keeps_a_glued_port(self):
        """Re-routing must not move an end to another side of the box."""
        path = self._new("pinned.vsdx")
        doc = Vsdx(path)
        a = doc.add_shape(1, 1.0, 5.0, 2.0, 1.0, "A", "rect")
        b = doc.add_shape(1, 5.0, 2.0, 2.0, 1.0, "B", "rect")
        cid = doc.connect(a, b, 1, from_port=(2.0, 5.0), to_port=(5.0, 2.5))
        doc.save(backup=False)

        doc = Vsdx(path)
        routes, _issues = doc.page_routes(1)
        start = routes[str(cid)][0]
        self.assertAlmostEqual(start[0], 2.0, places=3,
                               msg="the router moved the glued end away: %r" % (start,))
        self.assertAlmostEqual(start[1], 5.0, places=3,
                               msg="the router moved the glued end away: %r" % (start,))

    def test_svg_draws_the_same_polyline_the_panel_shows(self):
        """Rendering must use drawn_points(), not the raw Geometry rows."""
        path = self._new("render-parity.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)
        raw = [(3.0, 5.5), (4.0, 5.5), (4.0, 3.5), (5.5, 3.5), (5.5, 4.5)]
        self._route(path, link, raw)
        doc = Vsdx(path)
        svg = doc.to_svg(1, interactive=True, background=False)
        drawn = doc.drawn_points(link, 1)
        first = "M %0.4f %0.4f" % (drawn[0][0], 8.5 - drawn[0][1])
        self.assertIn(first, svg, "the svg does not start where drawn_points does")

    # --------------------------------------------------------- drawn_points
    def test_drawn_points_prefers_manual_geometry_then_simplifies_auto_route(self):
        path = self._new("drawn.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)     # offset boxes -> Z shaped auto route
        manual = [(3.0, 5.5), (4.0, 5.5), (4.0, 3.5), (5.5, 3.5), (5.5, 4.5)]
        self._route(path, link, manual)

        doc = Vsdx(path)
        auto_raw, _issues = doc.page_routes(1)
        self.assertEqual(_pts(doc.drawn_points(link, 1)), _pts(manual),
                         "hand-drawn geometry must win over the automatic route")
        self.assertNotEqual(_pts(doc.drawn_points(link, 1)),
                            _pts(Vsdx._simplify(auto_raw[link])))
        self.assertEqual(len(doc.geometry_points(link, 1)), len(manual),
                         "the manual Geometry section lost rows")

        doc.clear_route(link, page=1)
        doc.save(backup=False)
        doc = Vsdx(path)
        self.assertEqual(doc.geometry_points(link, 1), [], "clear_route left Geometry behind")
        auto_raw, _issues = doc.page_routes(1)
        simplified = _pts(Vsdx._simplify(auto_raw[link]))
        self.assertEqual(_pts(doc.drawn_points(link, 1)), simplified,
                         "an automatic route must come back simplified")
        self.assertGreater(len(auto_raw[link]), len(simplified),
                           "the router's collinear stub points should be simplified away")

    def test_drawn_points_accepts_a_two_point_manual_route(self):
        """A two-point Geometry section is still hand-drawn, not 'no geometry'."""
        path = self._new("drawn-two.vsdx")
        a, b, link = self._two_boxes(path, by=3.5)     # auto route is a Z, manual is straight
        manual = [(3.0, 5.5), (4.5, 5.5)]
        self._route(path, link, manual)

        doc = Vsdx(path)
        auto_raw, _issues = doc.page_routes(1)
        self.assertGreater(len(Vsdx._simplify(auto_raw[link])), 2,
                           "the automatic route should have corners for this case")
        self.assertEqual(_pts(doc.geometry_points(link, 1)), _pts(manual))
        self.assertEqual(_pts(doc.drawn_points(link, 1)), _pts(manual),
                         "a two-point manual route was ignored in favour of the auto route")


if __name__ == "__main__":
    unittest.main(verbosity=2)
