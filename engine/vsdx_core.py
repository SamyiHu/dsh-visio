"""vsdx_core - dependency-free reader / editor / preview renderer for Visio .vsdx.

Only the Python standard library is used. A .vsdx is an OPC (zip) package; this module
keeps every part in memory, edits only the parts it needs to, and writes a new package.
"""
from __future__ import annotations

import copy
import os
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET

try:
    import kinds
except ImportError:  # pragma: no cover
    kinds = None
from datetime import datetime, timezone

NS_V = "http://schemas.microsoft.com/office/visio/2012/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PR = "http://schemas.openxmlformats.org/package/2006/relationships"

ET.register_namespace("", NS_V)
ET.register_namespace("r", NS_R)
ET.register_namespace("pr", NS_PR)

V = "{%s}" % NS_V
R = "{%s}" % NS_R


def _v(tag: str) -> str:
    return V + tag


def _cell(el, name: str):
    for c in el.findall(_v("Cell")):
        if c.get("N") == name:
            return c
    return None


def _cellv(el, name: str, default=None):
    c = _cell(el, name)
    return c.get("V") if c is not None else default


def _f(el, name: str, default: float = 0.0) -> float:
    v = _cellv(el, name)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _shape_text(el) -> str:
    t = el.find(_v("Text"))
    if t is None:
        return ""
    return "".join(t.itertext()).strip()


def _set_shape_text(el, text: str, runs: int = 0):
    """Replace the text; with `runs` > 0 keep per-line <cp IX> colour runs."""
    t = el.find(_v("Text"))
    if t is None:
        t = ET.SubElement(el, _v("Text"))
    for child in list(t):
        t.remove(child)
    t.text = None
    if runs <= 0:
        t.text = text
        return
    parts = text.split("\n")
    for i, line in enumerate(parts):
        cp = ET.SubElement(t, _v("cp"))
        cp.set("IX", str(min(i, runs - 1)))
        cp.tail = ("\n" if i else "") + line


def _rgb(value, default=None):
    if not value:
        return default
    m = re.match(r"^#([0-9A-Fa-f]{6})$", value.strip())
    if m:
        return "#" + m.group(1).upper()
    return default


class VsdxError(Exception):
    pass


class Vsdx:
    """Open, inspect, edit and render a .vsdx file."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        if not os.path.exists(self.path):
            raise VsdxError("file not found: %s" % self.path)
        with zipfile.ZipFile(self.path, "r") as z:
            self.parts = {i.filename: z.read(i.filename) for i in z.infolist()}
            self.order = [i.filename for i in z.infolist()]
        self._dirty = set()
        self._pages = None
        self._serial = 0
        self._smap = None
        self._xmlcache = {}

    # ---------------------------------------------------------------- package
    def _xml(self, part: str):
        cached = self._xmlcache.get(part)
        if cached is not None:
            return cached
        data = self.parts.get(part)
        if data is None:
            raise VsdxError("missing part: %s" % part)
        root = ET.fromstring(data)
        self._xmlcache[part] = root
        return root

    def _rels(self, part: str):
        base = os.path.dirname(part)
        rels_part = "%s/_rels/%s.rels" % (base, os.path.basename(part))
        if rels_part not in self.parts:
            return {}
        root = self._xml(rels_part)
        out = {}
        for rel in root:
            out[rel.get("Id")] = rel.get("Target")
        return out

    # ------------------------------------------------------------------ pages
    @property
    def pages(self):
        if self._pages is not None:
            return self._pages
        root = self._xml("visio/pages/pages.xml")
        rels = self._rels("visio/pages/pages.xml")
        pages = []
        for p in root.findall(_v("Page")):
            rel = p.find(_v("Rel"))
            target = rels.get(rel.get("{%s}id" % NS_R)) if rel is not None else None
            part = "visio/pages/" + os.path.basename(target) if target else None
            sheet = p.find(_v("PageSheet"))
            w = _f(sheet, "PageWidth", 8.5) if sheet is not None else 8.5
            h = _f(sheet, "PageHeight", 11.0) if sheet is not None else 11.0
            w = _to_inches(w, _u(sheet, "PageWidth"))
            h = _to_inches(h, _u(sheet, "PageHeight"))
            pages.append({
                "index": len(pages) + 1,
                "id": p.get("ID"),
                "name": p.get("NameU") or p.get("Name") or ("Page-%d" % (len(pages) + 1)),
                "part": part,
                "width": w,
                "height": h,
            })
        self._pages = pages
        return pages

    def page_part(self, page: int = 1) -> str:
        pages = self.pages
        if page < 1 or page > len(pages):
            raise VsdxError("page %d out of range (1..%d)" % (page, len(pages)))
        part = pages[page - 1]["part"]
        if part not in self.parts:
            raise VsdxError("page part not found: %s" % part)
        return part

    # ----------------------------------------------------------------- masters
    def masters(self):
        if "visio/masters/masters.xml" not in self.parts:
            return {}
        root = self._xml("visio/masters/masters.xml")
        rels = self._rels("visio/masters/masters.xml")
        out = {}
        for m in root.findall(_v("Master")):
            rel = m.find(_v("Rel"))
            target = rels.get(rel.get("{%s}id" % NS_R)) if rel is not None else None
            out[m.get("ID")] = {
                "id": m.get("ID"),
                "name": m.get("NameU") or m.get("Name") or "",
                "part": ("visio/masters/" + os.path.basename(target)) if target else None,
            }
        return out

    def _master_size(self, part: str):
        cache = getattr(self, "_msize", None)
        if cache is None:
            cache = self._msize = {}
        if part in cache:
            return cache[part]
        try:
            root = self._xml(part)
        except VsdxError:
            cache[part] = (0.0, 0.0, 0.0, 0.0)
            return cache[part]
        sh = root.find(_v("Shapes"))
        sh = sh.find(_v("Shape")) if sh is not None else None
        if sh is None:
            cache[part] = (0.0, 0.0, 0.0, 0.0)
            return cache[part]
        w = _f(sh, "Width", 0.0)
        h = _f(sh, "Height", 0.0)
        cache[part] = (w, h, _f(sh, "LocPinX", w / 2), _f(sh, "LocPinY", h / 2))
        return cache[part]

    # ------------------------------------------------------------------ shapes
    def _iter_shapes(self, shapes_el, parent_id=None, depth=0):
        if shapes_el is None:
            return
        for sh in shapes_el.findall(_v("Shape")):
            yield sh, parent_id, depth
            sub = sh.find(_v("Shapes"))
            if sub is not None:
                yield from self._iter_shapes(sub, sh.get("ID"), depth + 1)

    def _connects(self, part: str):
        root = self._xml(part)
        out = {}
        conns = root.find(_v("Connects"))
        if conns is None:
            return out
        for c in conns.findall(_v("Connect")):
            out.setdefault(c.get("FromSheet"), []).append({
                "to": c.get("ToSheet"),
                "cell": c.get("FromCell"),
            })
        return out

    def shapes(self, page: int = 1):
        part = self.page_part(page)
        root = self._xml(part)
        connects = self._connects(part)
        masters = self.masters()
        out = []
        for sh, parent, depth in self._iter_shapes(root.find(_v("Shapes"))):
            master = masters.get(sh.get("Master"), {})
            w = _f(sh, "Width", 0.0)
            h = _f(sh, "Height", 0.0)
            locx = _f(sh, "LocPinX", w / 2)
            locy = _f(sh, "LocPinY", h / 2)
            pinx = _f(sh, "PinX", 0.0)
            piny = _f(sh, "PinY", 0.0)
            if (w == 0.0 or h == 0.0) and master.get("part"):
                mw, mh, mlx, mly = self._master_size(master["part"])
                w = w or mw
                h = h or mh
                locx = locx or mlx
                locy = locy or mly
            geom = sh.find(_v("Section"))
            kinds = []
            for sec in sh.findall(_v("Section")):
                if sec.get("N") == "Geometry":
                    for row in sec.findall(_v("Row")):
                        kinds.append(row.get("T") or "")
            props = {}
            for sec in sh.findall(_v("Section")):
                if sec.get("N") == "Property":
                    for row in sec.findall(_v("Row")):
                        nm = row.get("N") or ""
                        val = _cellv(row, "Value", "")
                        props[nm.replace("Prop.", "")] = val
            is_connector = any(_cell(sh, c) is not None for c in ("BeginX", "EndX"))
            out.append({
                "id": sh.get("ID"),
                "name": sh.get("NameU") or sh.get("Name") or "",
                "type": sh.get("Type") or "Shape",
                "parent": parent,
                "depth": depth,
                "master": master.get("name", ""),
                "text": _shape_text(sh),
                "bbox": {
                    "x": round(pinx - locx, 4),
                    "y": round(piny - locy, 4),
                    "w": round(w, 4),
                    "h": round(h, 4),
                },
                "geometry": [k for k in kinds if k],
                "connector": is_connector,
                "connects": connects.get(sh.get("ID"), []),
                "props": props,
            })
        return out

    def _shape_info(self, sh, parent, depth):
        cells, formulas, units = {}, {}, {}
        for c in sh.findall(_v("Cell")):
            cells[c.get("N")] = c.get("V")
            if c.get("U"):
                units[c.get("N")] = c.get("U")
            if c.get("F") is not None:
                formulas[c.get("N")] = c.get("F")
        sections = {}
        for sec in sh.findall(_v("Section")):
            name = sec.get("N")
            rows = []
            for row in sec.findall(_v("Row")):
                rows.append({
                    "row": row.get("T") or row.get("N") or row.get("IX"),
                    "cells": {c.get("N"): c.get("V") for c in row.findall(_v("Cell"))},
                })
            sections.setdefault(name, []).append({"ix": sec.get("IX"), "cells": {
                c.get("N"): c.get("V") for c in sec.findall(_v("Cell"))}, "rows": rows})
        return {
            "id": sh.get("ID"),
            "name": sh.get("NameU") or sh.get("Name") or "",
            "type": sh.get("Type") or "Shape",
            "master": sh.get("Master"),
            "parent": parent,
            "depth": depth,
            "text": _shape_text(sh),
            "cells": cells,
            "units": units,
            "formulas": formulas,
            "styles": {
                "LineStyle": sh.get("LineStyle"),
                "FillStyle": sh.get("FillStyle"),
                "TextStyle": sh.get("TextStyle"),
            },
            "sections": sections,
        }

    def _shape_map(self, page: int = 1):
        """Every shape of one page, parsed once (rendering calls this per shape)."""
        cached = getattr(self, "_smap", None)
        if cached is not None and cached[0] == page and cached[1] == self._serial:
            return cached[2]
        part = self.page_part(page)
        root = self._xml(part)
        mapping = {}
        for sh, parent, depth in self._iter_shapes(root.find(_v("Shapes"))):
            mapping[sh.get("ID")] = self._shape_info(sh, parent, depth)
        self._smap = (page, self._serial, mapping)
        return mapping

    def shape(self, shape_id, page: int = 1):
        info = self._shape_map(page).get(str(shape_id))
        if info is None:
            raise VsdxError("shape %s not found on page %d" % (shape_id, page))
        return info

    # ------------------------------------------------------------------- edits
    def _page_root(self, page: int):
        part = self.page_part(page)
        return part, self._xml(part)

    def _write_page(self, part: str, root):
        self.parts[part] = _tostring(root)
        self._xmlcache[part] = root
        self._dirty.add(part)

    def set_text(self, shape_id, text: str, page: int = 1):
        part, root = self._page_root(page)
        for sh, _p, _d in self._iter_shapes(root.find(_v("Shapes"))):
            if sh.get("ID") == str(shape_id):
                run_count = 0
                for sec in sh.findall(_v("Section")):
                    if sec.get("N") == "Character":
                        run_count = len(sec.findall(_v("Row")))
                _set_shape_text(sh, text, run_count)
                self._write_page(part, root)
                return True
        raise VsdxError("shape %s not found on page %d" % (shape_id, page))

    def set_cell(self, shape_id, cell: str, value, page: int = 1):
        return self.set_cells(shape_id, {cell: value}, page)

    def set_cells(self, shape_id, cells, page: int = 1):
        """Set several ShapeSheet cells in one parse/write cycle.

        A cell that had a formula loses it: the new literal value must win both in
        Visio's recalculation and in this renderer.
        """
        part, root = self._page_root(page)
        for sh, _p, _d in self._iter_shapes(root.find(_v("Shapes"))):
            if sh.get("ID") == str(shape_id):
                for name, value in cells.items():
                    c = _cell(sh, name)
                    if c is None:
                        c = ET.SubElement(sh, _v("Cell"))
                        c.set("N", name)
                    c.set("V", str(value))
                    c.attrib.pop("F", None)
                self._write_page(part, root)
                return True
        raise VsdxError("shape %s not found on page %d" % (shape_id, page))

    def move_shape(self, shape_id, x=None, y=None, w=None, h=None, page: int = 1):
        """Move / resize by bounding box (inches, origin bottom-left)."""
        det = self.shape(shape_id, page)
        cells = det["cells"]
        meta = next((sh for sh in self.shapes(page) if sh["id"] == str(shape_id)), None)
        if meta and meta.get("connector"):
            # A 1-D shape has no meaningful Width/Height: translating it rewrites the
            # endpoints instead, which is what Visio does when you drag a connector.
            bbox = meta["bbox"]
            dx = (float(x) - bbox["x"]) if x is not None else 0.0
            dy = (float(y) - bbox["y"]) if y is not None else 0.0
            try:
                begin_x = float(cells["BeginX"]) + dx
                begin_y = float(cells["BeginY"]) + dy
                end_x = float(cells["EndX"]) + dx
                end_y = float(cells["EndY"]) + dy
            except (KeyError, TypeError, ValueError):
                raise VsdxError("connector %s has no endpoints" % shape_id)
            return self.set_cells(shape_id, {
                "BeginX": round(begin_x, 6), "BeginY": round(begin_y, 6),
                "EndX": round(end_x, 6), "EndY": round(end_y, 6),
                "PinX": round((begin_x + end_x) / 2.0, 6),
                "PinY": round((begin_y + end_y) / 2.0, 6),
            }, page)
        try:
            cur_w = float(cells.get("Width") or 0.0)
            cur_h = float(cells.get("Height") or 0.0)
            cur_x = float(cells.get("PinX") or 0.0) - float(cells.get("LocPinX") or cur_w / 2.0)
            cur_y = float(cells.get("PinY") or 0.0) - float(cells.get("LocPinY") or cur_h / 2.0)
        except (TypeError, ValueError):
            raise VsdxError("shape %s has no numeric geometry" % shape_id)
        nw = float(w) if w is not None else cur_w
        nh = float(h) if h is not None else cur_h
        nx = float(x) if x is not None else cur_x
        ny = float(y) if y is not None else cur_y
        if nw <= 0 or nh <= 0:
            raise VsdxError("width and height must be positive")
        update = {
            "Width": round(nw, 6),
            "Height": round(nh, 6),
            "LocPinX": round(nw / 2.0, 6),
            "LocPinY": round(nh / 2.0, 6),
            "PinX": round(nx + nw / 2.0, 6),
            "PinY": round(ny + nh / 2.0, 6),
        }
        return self.set_cells(shape_id, update, page)

    def set_prop(self, shape_id, name: str, value, page: int = 1):
        part, root = self._page_root(page)
        for sh, _p, _d in self._iter_shapes(root.find(_v("Shapes"))):
            if sh.get("ID") == str(shape_id):
                sec = None
                for s in sh.findall(_v("Section")):
                    if s.get("N") == "Property":
                        sec = s
                        break
                if sec is None:
                    sec = ET.SubElement(sh, _v("Section"))
                    sec.set("N", "Property")
                row = None
                for r in sec.findall(_v("Row")):
                    if r.get("N") == name or r.get("N") == "Prop." + name:
                        row = r
                        break
                if row is None:
                    row = ET.SubElement(sec, _v("Row"))
                    row.set("N", "Prop." + name if not name.startswith("Prop.") else name)
                c = _cell(row, "Value")
                if c is None:
                    c = ET.SubElement(row, _v("Cell"))
                    c.set("N", "Value")
                c.set("V", str(value))
                self._write_page(part, root)
                return True
        raise VsdxError("shape %s not found on page %d" % (shape_id, page))

    def _new_id(self, root) -> str:
        top = 0
        for sh, _p, _d in self._iter_shapes(root.find(_v("Shapes"))):
            try:
                top = max(top, int(sh.get("ID")))
            except (TypeError, ValueError):
                pass
        return str(top + 1)

    def add_shape(self, page: int = 1, x: float = 1.0, y: float = 1.0,
                  w: float = 1.5, h: float = 0.75, text: str = "",
                  kind: str = "rect", fill: str = None, line: str = None):
        part, root = self._page_root(page)
        shapes_el = root.find(_v("Shapes"))
        if shapes_el is None:
            shapes_el = ET.SubElement(root, _v("Shapes"))
        sid = self._new_id(root)
        sh = ET.SubElement(shapes_el, _v("Shape"))
        sh.set("ID", sid)
        sh.set("NameU", "Sheet.%s" % sid)
        sh.set("Type", "Shape")
        sh.set("LineStyle", "0")
        sh.set("FillStyle", "0")
        sh.set("TextStyle", "0")
        cells = {
            "PinX": x + w / 2.0,
            "PinY": y + h / 2.0,
            "Width": w,
            "Height": h,
            "LocPinX": w / 2.0,
            "LocPinY": h / 2.0,
            "Angle": 0,
            "FlipX": 0,
            "FlipY": 0,
            "LineWeight": 0.01041666666666667,
            "LineColor": line or "#404040",
            "FillForegnd": fill or "#FFFFFF",
            "FillBkgnd": fill or "#FFFFFF",
            "FillPattern": 0 if kind == "text" else 1,
            "LinePattern": 0 if kind == "text" else 1,
            "Rounding": 0,
            "ShdwPattern": 0,
        }
        for k, v in cells.items():
            c = ET.SubElement(sh, _v("Cell"))
            c.set("N", k)
            c.set("V", str(v))
        if kind == "text":
            sec = None
            rows = []
        else:
            rows = kinds.rows_for(kind, w, h) if kinds else [
                ("RelMoveTo", {"X": 0, "Y": 0}), ("RelLineTo", {"X": 1, "Y": 0}),
                ("RelLineTo", {"X": 1, "Y": 1}), ("RelLineTo", {"X": 0, "Y": 1}),
                ("RelLineTo", {"X": 0, "Y": 0}),
            ]
            sec = ET.SubElement(sh, _v("Section"))
            sec.set("N", "Geometry")
            sec.set("IX", "0")
            if kinds and kind in kinds.ROUNDING:
                for c in sh.findall(_v("Cell")):
                    if c.get("N") == "Rounding":
                        c.set("V", str(min(w, h) * kinds.ROUNDING[kind]))
        for i, (t, cs) in enumerate(rows, start=1):
            if sec is None:
                break
            row = ET.SubElement(sec, _v("Row"))
            row.set("T", t)
            row.set("IX", str(i))
            for k, v in cs.items():
                c = ET.SubElement(row, _v("Cell"))
                c.set("N", k)
                c.set("V", str(v))
        if text:
            _set_shape_text(sh, text)
        self._write_page(part, root)
        return sid

    def add_master_shape(self, master_id, page: int = 1, x: float = None, y: float = None,
                         w: float = 1.5, h: float = 0.75, text: str = "", rows=None):
        """Place an instance of a master (stencil shape); geometry comes from the master."""
        part, root = self._page_root(page)
        shapes_el = root.find(_v("Shapes"))
        if shapes_el is None:
            shapes_el = ET.SubElement(root, _v("Shapes"))
        sid = self._new_id(root)
        if x is None:
            x = 1.0
        if y is None:
            y = 1.0
        sh = ET.SubElement(shapes_el, _v("Shape"))
        sh.set("ID", sid)
        sh.set("NameU", "Sheet.%s" % sid)
        sh.set("Type", "Shape")
        sh.set("Master", str(master_id))
        cells = {
            "PinX": x + w / 2.0, "PinY": y + h / 2.0,
            "Width": w, "Height": h,
            "LocPinX": w / 2.0, "LocPinY": h / 2.0,
            "Angle": 0, "FlipX": 0, "FlipY": 0,
        }
        for k, v in cells.items():
            c = ET.SubElement(sh, _v("Cell"))
            c.set("N", k)
            c.set("V", str(v))
        if rows:
            sec = ET.SubElement(sh, _v("Section"))
            sec.set("N", "Geometry")
            sec.set("IX", "0")
            for i, (kind_row, pts) in enumerate(rows, start=1):
                row = ET.SubElement(sec, _v("Row"))
                row.set("T", kind_row)
                row.set("IX", str(i))
                for axis, value in pts:
                    c = ET.SubElement(row, _v("Cell"))
                    c.set("N", axis)
                    c.set("V", str(value))
        if text:
            _set_shape_text(sh, text)
        self._write_page(part, root)
        return sid

    def connect(self, from_id, to_id, page: int = 1, label: str = ""):
        """Add a straight dynamic connector between two shapes."""
        part, root = self._page_root(page)
        page_shapes = {s["id"]: s for s in self.shapes(page)}
        a = page_shapes.get(str(from_id))
        b = page_shapes.get(str(to_id))
        if not a or not b:
            raise VsdxError("connect: shape ids %s -> %s not found" % (from_id, to_id))

        def center(s):
            bb = s["bbox"]
            return bb["x"] + bb["w"] / 2.0, bb["y"] + bb["h"] / 2.0

        def edge(s, tx, ty):
            """Point where the segment centre(s)->(tx,ty) leaves the shape box."""
            bb = s["bbox"]
            cx, cy = center(s)
            dx, dy = tx - cx, ty - cy
            if dx == 0 and dy == 0:
                return cx, cy
            hw, hh = bb["w"] / 2.0 or 0.01, bb["h"] / 2.0 or 0.01
            tx_ = hw / abs(dx) if dx else float("inf")
            ty_ = hh / abs(dy) if dy else float("inf")
            t = min(tx_, ty_)
            return cx + dx * t, cy + dy * t

        acx, acy = center(a)
        bcx, bcy = center(b)
        ax, ay = edge(a, bcx, bcy)
        bx, by = edge(b, acx, acy)
        shapes_el = root.find(_v("Shapes"))
        sid = self._new_id(root)
        sh = ET.SubElement(shapes_el, _v("Shape"))
        sh.set("ID", sid)
        sh.set("NameU", "Dynamic connector.%s" % sid)
        sh.set("Type", "Shape")
        sh.set("LineStyle", "0")
        sh.set("FillStyle", "0")
        sh.set("TextStyle", "0")
        d = {
            "PinX": round((ax + bx) / 2.0, 6),
            "PinY": round((ay + by) / 2.0, 6),
            "Width": round(abs(bx - ax), 6) or 0.01,
            "Height": round(abs(by - ay), 6),
            "LocPinX": round(abs(bx - ax) / 2.0, 6),
            "LocPinY": round(abs(by - ay) / 2.0, 6),
            "BeginX": ax, "BeginY": ay, "EndX": bx, "EndY": by,
            "LineWeight": 0.01041666666666667,
            "LineColor": "#404040",
            "EndArrow": 4,
            "BeginArrow": 0,
        }
        for k, v in d.items():
            c = ET.SubElement(sh, _v("Cell"))
            c.set("N", k)
            c.set("V", str(v))
        if label:
            _set_shape_text(sh, label)
        conns = root.find(_v("Connects"))
        if conns is None:
            conns = ET.SubElement(root, _v("Connects"))
        for from_cell, to_shape in (("BeginX", a["id"]), ("EndX", b["id"])):
            c = ET.SubElement(conns, _v("Connect"))
            c.set("FromSheet", sid)
            c.set("FromCell", from_cell)
            c.set("ToSheet", to_shape)
            c.set("ToCell", "PinX")
        self._write_page(part, root)
        return sid

    def delete_shape(self, shape_id, page: int = 1):
        """Delete a shape and every connector that dangles off it.

        Visio keeps a connector alive when one of its endpoints disappears; here the
        connector is removed with the shape so the drawing never shows orphan lines.
        """
        part, root = self._page_root(page)
        target = str(shape_id)
        present = set()
        for container in root.iter(_v("Shapes")):
            for sh in container.findall(_v("Shape")):
                present.add(sh.get("ID"))
        if target not in present:
            raise VsdxError("shape %s not found on page %d" % (shape_id, page))
        doomed = {target}
        conns = root.find(_v("Connects"))
        if conns is not None:
            grew = True
            while grew:
                grew = False
                for c in conns.findall(_v("Connect")):
                    sheet = c.get("FromSheet")
                    if c.get("ToSheet") in doomed and sheet and sheet not in doomed:
                        doomed.add(sheet)
                        grew = True
            for c in list(conns.findall(_v("Connect"))):
                if c.get("FromSheet") in doomed or c.get("ToSheet") in doomed:
                    conns.remove(c)
        for container in root.iter(_v("Shapes")):
            for sh in list(container.findall(_v("Shape"))):
                if sh.get("ID") in doomed:
                    container.remove(sh)
        self._write_page(part, root)
        return True

    def text_segments(self, shape_id, page: int = 1):
        """Rich-text runs of a shape: [{'text','color','pt','bold'}] with Character styles applied."""
        part = self.page_part(page)
        root = self._xml(part)
        target = str(shape_id)
        node = None
        for sh, _p, _d in self._iter_shapes(root.find(_v("Shapes"))):
            if sh.get("ID") == target:
                node = sh
                break
        if node is None:
            return []
        text_el = node.find(_v("Text"))
        if text_el is None:
            return []
        styles = {}
        for sec in node.findall(_v("Section")):
            if sec.get("N") == "Character":
                for row in sec.findall(_v("Row")):
                    ix = row.get("IX") or "0"
                    styles[ix] = {c.get("N"): c.get("V") for c in row.findall(_v("Cell"))}
        theme = self.theme().get("colors", {})
        variants = self.theme_variants()
        accent = (variants[0].get("varColor1") if variants else None) or theme.get("accent1")

        def parse_pt(v):
            try:
                f = float(v)
                return f * 72.0 if f < 2 else f
            except (TypeError, ValueError):
                return None

        out = []

        def emit(txt, ix):
            if not txt:
                return
            st = styles.get(ix, {})
            color = st.get("Color")
            if color and str(color).lower() == "themed":
                color = theme.get("dk1")
            if not st.get("Size"):
                st = dict(styles.get("0", {}), **st)
            seg = {
                "text": txt,
                "color": (str(color).upper() if color and str(color).startswith("#") else None),
                "pt": parse_pt(st.get("Size")),
                "bold": str(st.get("Style") or "") == "1",
            }
            out.append(seg)

        def walk(el, ix):
            if el.text:
                emit(el.text, ix)
            for child in el:
                cur = ix
                if child.tag == _v("cp"):
                    cur = child.get("IX") or "0"
                else:
                    walk(child, ix)
                if child.tail:
                    emit(child.tail, cur)

        walk(text_el, "0")
        return out

    # ------------------------------------------------------------- theme/palette
    def theme(self):
        """Colours and fonts of visio/theme/theme1.xml (DrawingML colour scheme)."""
        cached = getattr(self, "_theme", None)
        if cached is not None:
            return cached
        colors, fonts = {}, {}
        try:
            root = self._xml("visio/theme/theme1.xml")
            a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
            scheme = root.find(".//%sclrScheme" % a)
            if scheme is not None:
                for slot in scheme:
                    name = slot.tag.split("}")[-1]
                    clr = list(slot)[0] if len(slot) else None
                    if clr is None:
                        continue
                    val = clr.get("val") or clr.get("lastClr")
                    if val:
                        colors[name] = "#" + val.upper()
            fs_ = root.find(".//%sfontScheme" % a)
            if fs_ is not None:
                for kind in ("majorFont", "minorFont"):
                    node = fs_.find("%s%s" % (a, kind))
                    if node is None:
                        continue
                    latin = node.find("%slatin" % a)
                    if latin is not None and latin.get("typeface"):
                        fonts[kind] = latin.get("typeface")
        except (VsdxError, ET.ParseError):
            pass
        self._theme = {"colors": colors, "fonts": fonts}
        return self._theme

    def palette(self):
        """Document colour palette (visio/document.xml <Colors>)."""
        cached = getattr(self, "_palette", None)
        if cached is not None:
            return cached
        pal = {}
        try:
            root = self._xml("visio/document.xml")
            colors = root.find(_v("Colors"))
            if colors is not None:
                for e in colors.findall(_v("ColorEntry")):
                    ix, rgb = e.get("IX"), e.get("RGB")
                    if ix and rgb:
                        pal[str(ix)] = rgb.upper()
        except (VsdxError, ET.ParseError):
            pass
        self._palette = pal
        return pal

    def resolve_color(self, value):
        """'#RRGGBB' | palette index | 'Themed' -> '#RRGGBB' or None."""
        if value is None:
            return None
        v = str(value).strip()
        if v.startswith("#") and len(v) == 7:
            return v.upper()
        if v.isdigit():
            return self.palette().get(v)
        if v.lower() == "themed":
            return None
        return None

    def _master_cells(self, master_part):
        cache = getattr(self, "_mcells", None)
        if cache is None:
            cache = self._mcells = {}
        if master_part in cache:
            return cache[master_part]
        cells = {}
        try:
            root = self._xml(master_part)
            shapes = root.find(_v("Shapes"))
            sh = shapes.find(_v("Shape")) if shapes is not None else None
            if sh is not None:
                for c in sh.findall(_v("Cell")):
                    cells[c.get("N")] = c.get("V")
        except (VsdxError, ET.ParseError):
            pass
        cache[master_part] = cells
        return cells

    def _master_layers(self, master_part, sheets):
        """Master shape cells (with formulas) followed by the master's own style sheets."""
        cache = getattr(self, "_mlayers", None)
        if cache is None:
            cache = self._mlayers = {}
        if master_part in cache:
            return cache[master_part]
        layers = []
        try:
            root = self._xml(master_part)
            shapes = root.find(_v("Shapes"))
            sh = shapes.find(_v("Shape")) if shapes is not None else None
            if sh is not None:
                cells = {}
                for c in sh.findall(_v("Cell")):
                    cells[c.get("N")] = (c.get("V"), c.get("F"))
                layers.append(cells)
                for key in ("LineStyle", "FillStyle", "TextStyle"):
                    sid = str(sh.get(key) or "")
                    if sid and sid in sheets:
                        layers.append(sheets[sid])
        except (VsdxError, ET.ParseError):
            pass
        cache[master_part] = layers
        return layers

    def shape_cells_with_inheritance(self, shape_id, page: int = 1):
        """Local cells over master cells."""
        det = self.shape(shape_id, page)
        cells = dict(det["cells"])
        mid = det.get("master")
        parts = self.masters()
        if mid and mid in parts and parts[mid].get("part"):
            for k, v in self._master_cells(parts[mid]["part"]).items():
                cells.setdefault(k, v)
        return cells

    def stylesheets(self):
        """document.xml <StyleSheets>: id -> {cell: (value, formula)}."""
        cached = getattr(self, "_stylesheets", None)
        if cached is not None:
            return cached
        sheets = {}
        try:
            root = self._xml("visio/document.xml")
            node = root.find(_v("StyleSheets"))
            if node is not None:
                for sheet in node.findall(_v("StyleSheet")):
                    cells = {}
                    for c in sheet.findall(_v("Cell")):
                        cells[c.get("N")] = (c.get("V"), c.get("F"))
                    sheets[str(sheet.get("ID"))] = cells
        except (VsdxError, ET.ParseError):
            pass
        self._stylesheets = sheets
        return sheets

    def theme_variants(self):
        """vt:variationClrSchemeLst -> list of {'varColor1': '#RRGGBB', ...}."""
        cached = getattr(self, "_variants", None)
        if cached is not None:
            return cached
        out = []
        try:
            root = self._xml("visio/theme/theme1.xml")
            vt = "{http://schemas.microsoft.com/office/visio/2012/theme}"
            lst = root.find(".//%svariationClrSchemeLst" % vt)
            if lst is not None:
                for scheme in lst.findall(vt + "variationClrScheme"):
                    d = {}
                    for ch in scheme:
                        name = ch.tag.split("}")[-1]
                        clr = list(ch)[0] if len(ch) else None
                        val = clr.get("val") if clr is not None else None
                        if val:
                            d[name] = "#" + val.upper()
                    out.append(d)
        except (VsdxError, ET.ParseError):
            pass
        self._variants = out
        return out

    _STALE_PRONE = ("LineColor", "FillForegnd", "FillForeground", "FillBkgnd", "LinePattern", "FillPattern")

    def style(self, shape_id, page: int = 1):
        """Resolved fill / line / text colours, weight and arrows.

        Resolution order per cell: shape (unless its formula is Inh) -> style sheet
        (LineStyle / FillStyle / TextStyle) -> master -> theme.  Themed values use the
        theme's first variation colour scheme, the way Visio's default theme paints.
        """
        try:
            det = self.shape(shape_id, page)
        except VsdxError:
            return {}
        sheets = self.stylesheets()
        layers = [{k: (v, det.get("formulas", {}).get(k)) for k, v in det["cells"].items()}]
        style_ids = []
        for key in ("LineStyle", "FillStyle", "TextStyle"):
            sid = str((det.get("styles") or {}).get(key) or "")
            if sid and sid not in style_ids:
                style_ids.append(sid)
        for sid in style_ids:
            if sid in sheets:
                layers.append(sheets[sid])
        mid = det.get("master")
        mparts = self.masters()
        if mid and mid in mparts and mparts[mid].get("part"):
            layers.extend(self._master_layers(mparts[mid]["part"], sheets))
        style_cells = set()
        for layer in layers[1:]:
            style_cells.update(layer.keys())
        # "No Style" sheet is the last resort, never before the master
        if "0" in sheets:
            layers.append(sheets["0"])

        def raw(name):
            """Cell value with Visio semantics: THEMEVAL / Themed -> theme, Inh -> next layer."""
            for layer in layers:
                if name not in layer:
                    continue
                val, formula = layer[name]
                if val is None or val == "":
                    continue
                fl = (formula or "").strip().lower()
                if str(val).strip().lower() == "themed" or "themeval" in fl:
                    return ("__themed__", name)
                if fl == "inh" and name in style_cells and name in Vsdx._STALE_PRONE:
                    continue          # a style sheet owns this cell, the cached colour is stale
                return val
            return None

        theme = self.theme().get("colors", {})
        variants = self.theme_variants()
        v0 = variants[0] if variants else {}
        accent = v0.get("varColor1") or theme.get("accent1")

        def shade(hex_color, factor):
            if not hex_color:
                return None
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            return "#%02X%02X%02X" % (int(r * factor), int(g * factor), int(b * factor))

        def themed(name):
            if name in ("FillForegnd", "FillForeground", "FillBkgnd", "FillColor"):
                return accent
            if name == "LineColor":
                return shade(accent, 0.76)      # Visio paints lines a shade darker than the fill
            if name in ("TextColor", "Color"):
                return theme.get("dk1") or "#000000"
            return None

        def color(name):
            val = raw(name)
            if val is None or val == "":
                return None
            if isinstance(val, tuple):
                return themed(val[1])
            txt = str(val).strip()
            if txt.lower() == "themed":
                return themed(name)
            if txt.startswith("#") and len(txt) == 7:
                return txt.upper()
            if txt.isdigit():
                return self.palette().get(txt)
            return None

        def scalar(name, default=None):
            v = raw(name)
            return default if v is None or isinstance(v, tuple) else v

        pattern = str(scalar("FillPattern", "1"))
        fill = color("FillForegnd") or color("FillForeground")
        if fill is None and pattern not in ("0", "1"):
            fill = color("FillBkgnd")
        if pattern == "0":
            fill = None
        line = color("LineColor") or shade(accent, 0.76) or theme.get("dk1")
        if str(scalar("LinePattern", "1")) == "0":
            line = None

        text_color, font_pt = None, None
        units = det.get("units") or {}

        def in_points(name, value):
            """Visio writes points with U="PT"; internal inches have no unit."""
            return value if str(units.get(name) or "").upper() == "PT" else value * 72.0

        for sec in det["sections"].get("Character", []):
            for row in sec["rows"]:
                tc = row["cells"].get("Color")
                if tc and text_color is None:
                    text_color = themed("Color") if str(tc).lower() == "themed" else _rgb(str(tc), None)
                if row["cells"].get("Size") and font_pt is None:
                    try:
                        v = float(row["cells"]["Size"])
                        font_pt = v if str(units.get("Size") or "").upper() == "PT" else v * 72.0
                    except ValueError:
                        pass
        if font_pt is None and raw("Char.Size"):
            try:
                v = float(raw("Char.Size"))
                font_pt = v if str(units.get("Char.Size") or "").upper() == "PT" else v * 72.0
            except (TypeError, ValueError):
                pass

        weight = None
        try:
            if scalar("LineWeight") is not None:
                weight = float(scalar("LineWeight"))
                if str(units.get("LineWeight") or "").upper() == "PT":
                    weight = weight / 72.0
        except (TypeError, ValueError):
            weight = None

        return {
            "fill": fill,
            "line": line,
            "text": text_color,
            "font_pt": font_pt,
            "weight_in": weight,
            "pattern": str(scalar("LinePattern", "1")),
            "end_arrow": str(scalar("EndArrow", "0")),
            "theme": theme,
            "variants": v0,
        }

    def _master_outline(self, master_id):
        """Outline of a master's first shape, as 0..1 fractions of its own box."""
        try:
            meta = self.masters().get(str(master_id))
            if not meta or not meta.get("part"):
                return None
            root = self._xml(meta["part"])
        except VsdxError:
            return None
        shapes = root.find(_v("Shapes"))
        sh = shapes.find(_v("Shape")) if shapes is not None else None
        if sh is None:
            return None
        mw = _f(sh, "Width", 0.0)
        mh = _f(sh, "Height", 0.0)
        if not mw or not mh:
            return None
        sec = None
        for candidate in sh.findall(_v("Section")):
            if candidate.get("N") == "Geometry":
                sec = candidate
                break
        if sec is None:
            return None
        pts = []
        for row in sec.findall(_v("Row")):
            kind = row.get("T") or ""
            if not (kind.endswith("MoveTo") or kind.endswith("LineTo")):
                return None
            x = _f(row, "X", 0.0)
            y = _f(row, "Y", 0.0)
            if not kind.startswith("Rel"):
                x, y = x / mw, y / mh
            pts.append((x, y))
        return (pts, mw, mh) if len(pts) >= 4 else None

    def geometry_paths(self, shape_id, page: int = 1):
        """Real outline of a shape in page coordinates (inches, y up).

        Honours the Rel* row types (coordinates in 0..1 of Width/Height), the
        PinPoint/LocPin offset and FlipX/FlipY, so previews match what Visio
        draws instead of a bounding box. Returns subpaths:
        {"pts": [(x, y), ...], "closed": bool, "no_fill": bool, "no_line": bool}
        or {"ellipse": (cx, cy, rx, ry), ...} for Ellipse rows.
        """
        try:
            sh = self.shape(shape_id, page)
        except VsdxError:
            return []
        cells = sh["cells"]

        def num(name, default=0.0):
            v = cells.get(name)
            try:
                return float(v) if v not in (None, "") else default
            except (TypeError, ValueError):
                return default

        w, h = num("Width"), num("Height")
        ox = num("PinX") - num("LocPinX")
        oy = num("PinY") - num("LocPinY")
        fx = str(cells.get("FlipX") or "0") not in ("0", "")
        fy = str(cells.get("FlipY") or "0") not in ("0", "")

        def to_page(x, y):
            if fx:
                x = w - x
            if fy:
                y = h - y
            return (ox + x, oy + y)

        paths = []
        for sec in sh["sections"].get("Geometry") or []:
            sec_cells = sec.get("cells") or {}
            if str(sec_cells.get("NoShow") or "0") not in ("0", ""):
                continue
            no_fill = str(sec_cells.get("NoFill") or "0") not in ("0", "")
            no_line = str(sec_cells.get("NoLine") or "0") not in ("0", "")
            cur = None
            for row in sec["rows"]:
                kind = str(row.get("row") or "")
                rc = row["cells"]

                def val(name, default=0.0):
                    v = rc.get(name)
                    try:
                        return float(v) if v not in (None, "") else default
                    except (TypeError, ValueError):
                        return default

                rel = kind.startswith("Rel")
                base = kind[3:] if rel else kind
                if base in ("MoveTo", "LineTo", "PolylineTo", "ArcTo", "NURBSTo", "SplineKnot"):
                    x, y = val("X"), val("Y")
                    if rel:
                        x, y = x * w, y * h
                    pt = to_page(x, y)
                    if base == "MoveTo" or cur is None:
                        cur = [pt]
                        paths.append({"pts": cur, "closed": False, "no_fill": no_fill, "no_line": no_line})
                    else:
                        cur.append(pt)
                elif base == "Ellipse":
                    cx, cy, rx, ry = val("X"), val("Y"), val("A"), val("B")
                    if rel:
                        cx, cy, rx, ry = cx * w, cy * h, rx * w, ry * h
                    px, py = to_page(cx, cy)
                    paths.append({"ellipse": (px, py, abs(rx), abs(ry)), "closed": True,
                                  "no_fill": no_fill, "no_line": no_line})
                    cur = None
        for p in paths:
            pts = p.get("pts")
            if pts and len(pts) > 2:
                (x0, y0), (x1, y1) = pts[0], pts[-1]
                p["closed"] = abs(x0 - x1) < 1e-6 and abs(y0 - y1) < 1e-6
        spread = {(round(pt[0], 3), round(pt[1], 3)) for p in paths for pt in p.get("pts") or []}
        master_id = sh.get("master") or cells.get("Master")
        need_master = len(spread) < 3
        if master_id and not need_master:
            _found = self._master_outline(master_id)
            if _found and len(spread) < len(_found[0]):
                need_master = True
        if need_master and master_id:
            # The generator can leave a broken local Geometry (X rows only).  A
            # master instance still has a usable outline in its master part.
            found = self._master_outline(master_id)
            if found:
                outline, mw, mh = found
                iw = w or mw
                ih = h or mh
                return [{
                    "pts": [(ox + fx * iw, oy + fy * ih) for fx, fy in outline],
                    "closed": True,
                    "no_fill": False,
                    "no_line": False,
                }]
        return paths

    def geometry_points(self, shape_id, page: int = 1):
        """Absolute polyline of a shape's first Geometry section (inches, y up)."""
        try:
            sh = self.shape(shape_id, page)
        except VsdxError:
            return []
        cells = sh["cells"]
        try:
            ox = float(cells["PinX"]) - float(cells.get("LocPinX") or 0.0)
            oy = float(cells["PinY"]) - float(cells.get("LocPinY") or 0.0)
        except (KeyError, ValueError):
            return []
        secs = sh["sections"].get("Geometry") or []
        if not secs:
            return []
        rows = secs[0]["rows"]
        pts = []
        if rows and str(rows[0].get("row") or "").lower().find("moveto") < 0:
            pts.append((ox, oy))          # connectors start at the origin when no MoveTo row is written
        for row in rows:
            c = row["cells"]
            xv, yv = c.get("X"), c.get("Y")
            if xv is None and yv is None:
                continue
            try:
                px = float(xv) if xv is not None else (pts[-1][0] - ox if pts else 0.0)
                py = float(yv) if yv is not None else (pts[-1][1] - oy if pts else 0.0)
            except ValueError:
                continue
            pts.append((ox + px, oy + py))
        return pts

    def label_point(self, shape_id, page: int = 1):
        try:
            sh = self.shape(shape_id, page)
        except VsdxError:
            return None
        cells = sh["cells"]
        secs = sh["sections"].get("Control") or []
        if not secs or not secs[0]["rows"]:
            return None
        row = secs[0]["rows"][0]["cells"]
        try:
            ox = float(cells["PinX"]) - float(cells.get("LocPinX") or 0.0)
            oy = float(cells["PinY"]) - float(cells.get("LocPinY") or 0.0)
            return (ox + float(row["X"]), oy + float(row["Y"]))
        except (KeyError, ValueError):
            return None

    # ------------------------------------------------------------------ render
    def view_box(self, page: int = 1) -> dict:
        """Page rect plus every drawable shape, so nothing spills out of frame.

        Drawings generated by scripts often run past the page edge (a 17in flow on
        an 11.7in page). Visio keeps the whole drawing visible and marks the page
        area; clipping to the page makes those drawings look squeezed.
        """
        meta = self.pages[page - 1]
        page_w, page_h = meta["width"], meta["height"]
        xs, ys = [0.0], [0.0]
        xe, ye = [page_w], [page_h]
        for s in self.shapes(page):
            # Connectors can stretch far outside the page (they span their endpoints),
            # so letting them into the view box shrinks the whole drawing.
            if s.get("type") == "Guide" or s.get("depth") != 0 or s.get("connector"):
                continue
            bb = s["bbox"]
            if bb["w"] <= 0 or bb["h"] <= 0:
                continue
            xs.append(bb["x"])
            xe.append(bb["x"] + bb["w"])
            ys.append(page_h - bb["y"] - bb["h"])
            ye.append(page_h - bb["y"])
        pad = 0.25
        vx = min(xs) - pad
        vy = min(ys) - pad
        return {
            "x": round(vx, 4),
            "y": round(vy, 4),
            "w": round(max(xe) + pad - vx, 4),
            "h": round(max(ye) + pad - vy, 4),
            "page": {"w": page_w, "h": page_h},
        }

    def text_runs(self, shape_id, page: int = 1):
        """Per-line text with the colour of its first character run.

        Shape text is stored as one string plus <cp IX="n"/> run markers; each run
        points at a Character row that carries its own colour (Visio draws those
        colour changes, a single-colour <text> does not).
        """
        try:
            sh = self.shape(shape_id, page)
        except VsdxError:
            return None
        part, root = self._page_root(page)
        el = None
        for candidate, _part, _depth in self._iter_shapes(root.find(_v("Shapes"))):
            if candidate.get("ID") == str(shape_id):
                el = candidate
                break
        if el is None:
            return None
        text_el = el.find(_v("Text"))
        if text_el is None:
            return None
        chars = []          # (char, run index)
        index = 0
        if text_el.text:
            for ch in text_el.text:
                chars.append((ch, index))
        for child in text_el:
            if child.tag == _v("cp"):
                try:
                    index = int(child.get("IX") or 0)
                except ValueError:
                    index = 0
            if child.tail:
                for ch in child.tail:
                    chars.append((ch, index))
        if not chars:
            return None
        colors = {}
        for sec in sh["sections"].get("Character") or []:
            for row in sec.get("rows") or []:
                cells = row["cells"]
                color = cells.get("Color")
                if color:
                    colors[str(row.get("row"))] = color
        out = []
        for line in "".join(ch for ch, _ in chars).split("\n"):
            out.append(line)
        # walk again to attach the run index of each line's first character
        lines = []
        current = []
        current_index = None
        for ch, idx in chars:
            if ch == "\n":
                lines.append((current_index, "".join(current)))
                current = []
                current_index = None
                continue
            if current_index is None:
                current_index = idx
            current.append(ch)
        lines.append((current_index, "".join(current)))
        return [(txt, colors.get(str(ix))) for ix, txt in lines]

    def to_svg(self, page: int = 1, show_ids: bool = False, interactive: bool = False,
               background: bool = True) -> str:
        meta = self.pages[page - 1]
        W, H = meta["width"], meta["height"]
        shapes = self.shapes(page)
        view = self.view_box(page)
        out = []
        out.append(
            '<svg xmlns="http://www.w3.org/2000/svg" width="%0.0f" height="%0.0f" '
            'overflow="visible" viewBox="%0.4f %0.4f %0.4f %0.4f" '
            'font-family="Segoe UI, Arial, sans-serif">'
            % (view["w"] * 96, view["h"] * 96, view["x"], view["y"], view["w"], view["h"])
        )
        if background:
            out.append('<rect x="%0.4f" y="%0.4f" width="%0.4f" height="%0.4f" fill="#F4F5F7"/>'
                       % (view["x"], view["y"], view["w"], view["h"]))
            out.append('<rect x="0" y="0" width="%0.3f" height="%0.3f" fill="#FFFFFF" '
                       'stroke="#C9CDD4" stroke-width="0.01"/>' % (W, H))
        else:
            # Transparent sheet: the panel paints the grid behind it, so the page
            # is only an outline.  vector-effect keeps the hairlines crisp at any zoom.
            out.append('<rect x="0" y="0" width="%0.3f" height="%0.3f" fill="none" '
                       'stroke="#9AA3AF" stroke-width="0.012" stroke-dasharray="0.08 0.06" '
                       'vector-effect="non-scaling-stroke"/>' % (W, H))
        # Arrow head marker; one per connector colour (kept small and simple).
        arrow_colors = set()
        for _s in shapes:
            if _s["connector"]:
                _c = self.style(_s["id"], page).get("line") or "#404040"
                if str(self.style(_s["id"], page).get("end_arrow") or "0") != "0":
                    arrow_colors.add(_c)
        if arrow_colors:
            out.append("<defs>")
            for _c in sorted(arrow_colors):
                out.append('<marker id="dshv-arrow-%s" viewBox="0 0 10 10" refX="9" refY="5" '
                           'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
                           '<path d="M 0 0 L 10 5 L 0 10 z" fill="%s"/></marker>' % (_c.lstrip("#"), _c))
            out.append("</defs>")
        open_group = (lambda sid: '<g data-shape-id="%s">' % _esc(sid)) if interactive else (lambda sid: "<g>")
        for s in shapes:
            if s["connector"] or s["depth"] != 0 or s.get("type") == "Guide":
                continue
            bb = s["bbox"]
            if bb["w"] <= 0 or bb["h"] <= 0:
                continue
            x = bb["x"]
            y = H - bb["y"] - bb["h"]
            st = self.style(s["id"], page)
            cells = self.shape(s["id"], page)["cells"]
            fill = st.get("fill") or "#FFFFFF"
            stroke = st.get("line") or "#404040"
            text_color = st.get("text") or "#1A1A1A"
            weight = st.get("weight_in") or 0.0104
            try:
                fill_op = 1.0 - float(cells.get("FillForegndTrans") or 0.0)
            except (TypeError, ValueError):
                fill_op = 1.0
            fill_op = max(0.0, min(1.0, fill_op))
            pattern = str(st.get("pattern") or "1")
            paths = self.geometry_paths(s["id"], page)
            out.append(open_group(s["id"]))
            if paths and pattern == "0":
                out.append('<rect x="%0.3f" y="%0.3f" width="%0.3f" height="%0.3f" fill="transparent" stroke="none"/>'
                           % (x, y, bb["w"], bb["h"]))
            if not paths:
                # Text-only shape: no box of its own, but keep a click target.
                out.append('<rect x="%0.3f" y="%0.3f" width="%0.3f" height="%0.3f" fill="transparent" stroke="none"/>'
                           % (x, y, bb["w"], bb["h"]))
            for p in paths:
                fill_attr = "none" if (p["no_fill"] or pattern == "0") else fill
                if p["no_line"] or weight <= 0:
                    stroke_attr = ' stroke="none"'
                else:
                    stroke_attr = ' stroke="%s" stroke-width="%0.4f"' % (stroke, weight)
                if "ellipse" in p:
                    cx0, cy0, rx, ry = p["ellipse"]
                    out.append('<ellipse cx="%0.4f" cy="%0.4f" rx="%0.4f" ry="%0.4f" fill="%s"%s/>'
                               % (cx0, H - cy0, rx, ry, fill_attr, stroke_attr))
                else:
                    pts = p["pts"]
                    d = "M %0.4f %0.4f" % (pts[0][0], H - pts[0][1])
                    for px, py in pts[1:]:
                        d += " L %0.4f %0.4f" % (px, H - py)
                    if p.get("closed"):
                        d += " Z"
                    opacity_attr = '' if fill_op >= 1.0 else ' fill-opacity="%0.2f"' % fill_op
                    out.append('<path d="%s" fill="%s"%s%s stroke-linejoin="round"/>'
                               % (d, fill_attr, opacity_attr, stroke_attr))
                    # Thin geometry (lines, connectors, arrows) is hard to hit: add an
                    # invisible 12px stroke that keeps its width at any zoom.
                    thin = (not p.get("closed")) or bb["w"] < 0.35 or bb["h"] < 0.35
                    if thin:
                        out.append('<path d="%s" fill="none" stroke="transparent" stroke-width="12" '
                                   'vector-effect="non-scaling-stroke" pointer-events="stroke"/>' % d)
            if s["text"]:
                raw_lines = s["text"].split("\n")[:8]
                cells = self.shape(s["id"], page)["cells"]
                try:
                    tw = float(cells.get("TxtWidth") or 0) or bb["w"]
                except (TypeError, ValueError):
                    tw = bb["w"]
                font_pt = st.get("font_pt")
                fs = (font_pt / 72.0) if font_pt else max(0.06, min(0.22, bb["h"] / (len(raw_lines) + 1.6)))
                em = max(_text_em(ln) for ln in raw_lines) or 1.0
                if fs * em > tw:                      # shrink so the line fits its text box
                    fs = tw / em
                # Soft-wrap to the text box, the way Visio does.  Without this a long
                # caption runs straight out of its shape (and pushes lines off-centre).
                lines = []
                budget = max(1.0, (tw * 0.94) / fs)
                for raw in raw_lines:
                    if _text_em(raw) <= budget or not raw:
                        lines.append(raw)
                        continue
                    chunk = ""
                    for ch in raw:
                        if _text_em(chunk + ch) > budget and chunk:
                            lines.append(chunk)
                            chunk = ch
                        else:
                            chunk += ch
                    if chunk:
                        lines.append(chunk)
                lines = lines[:10]
                if len(lines) != len(raw_lines):
                    fs = min(fs, max(0.05, (bb["h"] * 0.86) / (len(lines) * 1.35)))
                # Text anchor: master instances inherit TxtPin* in master units,
                # which lands outside a resized instance -> centre on the box.
                is_master = bool(s.get("master") or cells.get("Master"))
                try:
                    if is_master or cells.get("TxtPinX") is None:
                        tx = bb["x"] + bb["w"] / 2.0
                    else:
                        tx = float(cells["TxtPinX"]) + float(cells.get("PinX") or 0) - float(cells.get("LocPinX") or 0)
                    if is_master or cells.get("TxtPinY") is None:
                        ty = bb["y"] + bb["h"] / 2.0
                    else:
                        ty = float(cells["TxtPinY"]) + float(cells.get("PinY") or 0) - float(cells.get("LocPinY") or 0)
                except (KeyError, TypeError, ValueError):
                    tx, ty = bb["x"] + bb["w"] / 2, bb["y"] + bb["h"] / 2
                try:
                    bkgnd = int(float(cells.get("TextBkgnd") or 0))
                except (TypeError, ValueError):
                    bkgnd = 0
                if bkgnd != 0:
                    _bg = st.get("text_bkgnd") or "#FFFFFF"
                    _bh = len(lines) * fs * 1.35 + fs * 0.4
                    out.append('<rect x="%0.4f" y="%0.4f" width="%0.4f" height="%0.4f" fill="%s"/>'
                               % (tx - tw / 2.0, H - ty - _bh / 2.0, tw, _bh, _bg))
                runs = self.text_runs(s["id"], page) or []
                for i, ln in enumerate(lines):
                    fill = text_color
                    for run_text, run_color in runs:
                        if run_text.strip() and run_text.strip() == ln.strip() and run_color:
                            fill = run_color
                            break
                    out.append('<text x="%0.4f" y="%0.4f" font-size="%0.4f" fill="%s" text-anchor="middle" dominant-baseline="middle">%s</text>'
                               % (tx, H - ty + (i - (len(lines) - 1) / 2.0) * fs * 1.35, fs, fill, _esc(ln[:120])))
            if show_ids:
                out.append('<text x="%0.3f" y="%0.3f" font-size="0.09" fill="#C0392B" text-anchor="start">#%s</text>'
                           % (x, y - 0.03, s["id"]))
            out.append("</g>")
        _shape_out = out
        out = []
        for s in shapes:
            if not s["connector"]:
                continue
            det = self.shape(s["id"], page)
            c = det["cells"]
            try:
                x1, y1 = float(c["BeginX"]), float(c["BeginY"])
                x2, y2 = float(c["EndX"]), float(c["EndY"])
            except (KeyError, TypeError, ValueError):
                continue
            cst = self.style(s["id"], page)
            line_color = cst.get("line") or "#404040"
            # A connector's own weight is often a hairline (0.0002in), which is
            # sub-pixel on screen; keep it visible but thin.
            raw_width = cst.get("weight_in") or 0.0
            # Keep the stored weight.  Vision treats a hairline as 1 screen pixel, so
            # do the same instead of pretending the file says 0.75pt.
            width_attr = ('stroke-width="1" vector-effect="non-scaling-stroke"'
                          if raw_width < 0.007 else 'stroke-width="%0.4f"' % raw_width)
            end_on = str(cst.get("end_arrow") or "0") != "0"
            begin_on = str(cst.get("begin_arrow") or "0") != "0"
            marker = 'url(#dshv-arrow-%s)' % line_color.lstrip("#") if end_on else "none"
            marker_start = 'url(#dshv-arrow-%s)' % line_color.lstrip("#") if begin_on else "none"
            out.append(open_group(s["id"]))
            pts_ = self.geometry_points(s["id"], page)
            if len(pts_) >= 2:
                d = "M %0.4f %0.4f" % (pts_[0][0], H - pts_[0][1])
                for px, py in pts_[1:]:
                    d += " L %0.4f %0.4f" % (px, H - py)
                out.append('<path d="%s" fill="none" stroke="%s" %s marker-start="%s" '
                       'marker-end="%s" stroke-linejoin="round"/>'
                       % (d, line_color, width_attr, marker_start, marker))
            else:
                d = "M %0.4f %0.4f L %0.4f %0.4f" % (x1, H - y1, x2, H - y2)
                out.append('<path d="%s" fill="none" stroke="%s" %s marker-end="%s"/>'
                           % (d, line_color, width_attr, marker))
            # fat, invisible target so a 0.01in line can be clicked
            out.append('<path d="%s" fill="none" stroke="transparent" stroke-width="12" '
                       'vector-effect="non-scaling-stroke" pointer-events="stroke"/>' % d)
            if s["text"]:
                mx, my = (x1 + x2) / 2.0, H - (y1 + y2) / 2.0
                label = [ln for ln in s["text"].split("\n") if ln.strip()][:4]
                for i, ln in enumerate(label):
                    out.append('<text x="%0.3f" y="%0.3f" font-size="0.08" fill="#1A1A1A" text-anchor="middle">%s</text>'
                               % (mx, my + (i - (len(label) - 1) / 2.0) * 0.105, _esc(ln[:60])))
            out.append("</g>")
        out.append("</svg>")
        _k = 0
        while _k < len(_shape_out) and not _shape_out[_k].startswith('<g'):
            _k += 1
        _close = [c for c in out if c.strip() == '</svg>']
        _conn = [c for c in out if c.strip() != '</svg>']
        out = _shape_out[:_k] + _conn + _shape_out[_k:] + _close
        return "\n".join(out)

    def save_svg(self, out_path: str, page: int = 1, show_ids: bool = False) -> str:
        svg = self.to_svg(page, show_ids)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        return out_path

    # -------------------------------------------------------------------- save
    def _prune_backups(self, keep: int = 20):
        """Keep only the newest `keep` .bak-<stamp> files beside this document."""
        try:
            folder = os.path.dirname(self.path)
            base = os.path.basename(self.path) + ".bak-"
            names = sorted((n for n in os.listdir(folder) if n.startswith(base)), reverse=True)
            for name in names[max(1, int(keep)):]:
                os.remove(os.path.join(folder, name))
        except OSError:
            pass

    LENGTH_UNITS = ("MM", "CM", "M", "PT", "IN", "FT")

    def normalize_units(self):
        """Rewrite mixed-unit cells into Visio internal units (inches, no U).

        Generators often write inch values while labelling them U="MM"/U="PT",
        or write a line weight in points. Visio honours U, so the drawing then
        opens with a tiny page, invisible text or 70x too thick lines. Here the
        values are converted into inches and the misleading U attribute is
        dropped, so Visio and the preview agree.
        """
        changed = 0
        page_cells = ("PageWidth", "PageHeight", "PageScale", "DrawingScale",
                      "LineToNodeX", "LineToNodeY", "LineToLineX", "LineToLineY",
                      "PageLeftMargin", "PageRightMargin", "PageTopMargin", "PageBottomMargin")
        pages_part = "visio/pages/pages.xml"
        root = self._xml(pages_part)
        for cell in root.iter(_v("Cell")):
            unit = str(cell.get("U") or "").upper()
            if not unit or cell.get("N") not in page_cells:
                continue
            try:
                float(cell.get("V"))
            except (TypeError, ValueError):
                continue
            # The values are already inches; the U label is what misleads Visio.
            cell.attrib.pop("U", None)
            changed += 1
        self.parts[pages_part] = _tostring(root)
        self._dirty.add(pages_part)
        self._pages = None

        for part in [n for n in self.order if n.startswith("visio/pages/page") and n.endswith(".xml")]:
            root = self._xml(part)
            touched = 0
            for cell in root.iter(_v("Cell")):
                unit = str(cell.get("U") or "").upper()
                if not unit:
                    continue
                name = cell.get("N")
                try:
                    v = float(cell.get("V"))
                except (TypeError, ValueError):
                    continue
                if name == "LineWeight":
                    # weights are written in points; Visio stores inches
                    cell.set("V", _fmt(v / 72.0 if unit == "PT" else _to_inches(v, unit)))
                elif unit in self.LENGTH_UNITS:
                    # everything else is already inches (only the label is wrong)
                    pass
                else:
                    continue
                cell.attrib.pop("U", None)
                touched += 1
            if touched:
                self.parts[part] = _tostring(root)
                self._xmlcache[part] = root
                self._dirty.add(part)
                changed += touched
        self._serial += 1
        self._smap = None
        return {"cells": changed}

    def save(self, out_path: str = None, backup: bool = True, keep_backups: int = 20) -> str:
        out_path = os.path.abspath(out_path or self.path)
        if backup and out_path == self.path:
            now = datetime.now(timezone.utc)
            stamp = now.strftime("%Y%m%d-%H%M%S") + "-%03d" % (now.microsecond // 1000)
            shutil.copy2(self.path, "%s.bak-%s" % (self.path, stamp))
            self._prune_backups(keep_backups)
        tmp = out_path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for name in self.order:
                z.writestr(name, self.parts[name])
            for name, data in self.parts.items():
                if name not in self.order:
                    z.writestr(name, data)
        os.replace(tmp, out_path)
        self._serial += 1
        self._smap = None
        return out_path

    # ------------------------------------------------------------------ reports
    def info(self):
        return {
            "path": self.path,
            "pages": [{"index": p["index"], "name": p["name"], "width_in": p["width"], "height_in": p["height"]} for p in self.pages],
            "masters": list(self.masters().values()),
            "parts": len(self.parts),
        }

    def text_dump(self) -> str:
        lines = ["# %s" % os.path.basename(self.path)]
        for p in self.pages:
            lines.append("\n## %s (page %d, %.2f x %.2f in)" % (p["name"], p["index"], p["width"], p["height"]))
            for s in self.shapes(p["index"]):
                if s["depth"] > 0:
                    continue
                t = s["text"].replace("\n", " / ")
                bb = s["bbox"]
                lines.append("- #%s %s%s [%s] %.2f,%.2f %.2fx%.2f%s" % (
                    s["id"],
                    ("<%s> " % s["master"]) if s["master"] else "",
                    ("(%s) " % s["type"]) if s["type"] != "Shape" else "",
                    t,
                    bb["x"], bb["y"], bb["w"], bb["h"],
                    " -> %s" % ",".join(c["to"] for c in s["connects"]) if s["connects"] else "",
                ))
        return "\n".join(lines)


def _u(el, name):
    """Unit attribute of a named cell (None when the cell has no U)."""
    if el is None:
        return None
    for c in el.findall(_v("Cell")):
        if c.get("N") == name:
            return c.get("U")
    return None


def _to_inches(value, unit):
    u = str(unit or "").upper()
    if u in ("MM", "MILLIMETERS"):
        return value / 25.4
    if u in ("CM",):
        return value / 2.54
    if u in ("M",):
        return value / 0.0254
    if u in ("PT",):
        return value / 72.0
    return value


def _fmt(v) -> str:
    s = ("%.10f" % float(v)).rstrip("0").rstrip(".")
    return s or "0"


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _text_em(text: str) -> float:
    """Rough advance width of a line, in em (CJK = 1em, Latin ~0.55em)."""
    total = 0.0
    for ch in text:
        code = ord(ch)
        if code >= 0x2E80 or 0xFF00 <= code <= 0xFF60:
            total += 1.0
        elif ch == " ":
            total += 0.28
        else:
            total += 0.55
    return total or 1.0


def _tostring(root) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + ET.tostring(root, encoding="utf-8")
