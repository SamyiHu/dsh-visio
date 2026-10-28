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
from vsdx_core import Vsdx, _v  # noqa: E402


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
