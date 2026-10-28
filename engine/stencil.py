# -*- coding: utf-8 -*-
"""Import masters from a Visio stencil (.vssx / .vstx) into a drawing."""

import copy
import os
import zipfile
import xml.etree.ElementTree as ET

NS = "{http://schemas.microsoft.com/office/visio/2012/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MASTER_TYPE = "http://schemas.microsoft.com/visio/2010/relationships/master"


class StencilError(Exception):
    pass


def _read(zf, name):
    try:
        return zf.read(name)
    except KeyError:
        raise StencilError("stencil is missing %s" % name)


MASTERS_NS = "http://schemas.microsoft.com/office/visio/2012/main"
CONTENT_TYPES = "[Content_Types].xml"


def _ensure_masters_part(doc):
    """Create visio/masters/* and the links to it when the drawing has none."""
    if "visio/masters/masters.xml" in doc.parts:
        return
    doc.parts["visio/masters/masters.xml"] = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Masters xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xml:space="preserve"/>'
    ).encode("utf-8")
    doc.parts["visio/masters/_rels/masters.xml.rels"] = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    ).encode("utf-8")

    rels_name = "visio/_rels/document.xml.rels"
    rels_root = ET.fromstring(doc.parts[rels_name])
    used = {rel.get("Id") for rel in rels_root.findall(PKG_REL + "Relationship")}
    n = 1
    while ("rId%d" % n) in used:
        n += 1
    rel = ET.SubElement(rels_root, PKG_REL + "Relationship")
    rel.set("Id", "rId%d" % n)
    rel.set("Type", "http://schemas.microsoft.com/visio/2010/relationships/masters")
    rel.set("Target", "masters/masters.xml")
    doc.parts[rels_name] = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)


def _override_content_type(doc, part_name, content_type):
    try:
        root = ET.fromstring(doc.parts[CONTENT_TYPES])
    except KeyError:
        return
    wanted = "/" + part_name
    for el in root.findall(
            "{http://schemas.openxmlformats.org/package/2006/content-types}Override"):
        if el.get("PartName", "").lower() == wanted.lower():
            return
    el = ET.SubElement(
        root,
        "{http://schemas.openxmlformats.org/package/2006/content-types}Override")
    el.set("PartName", wanted)
    el.set("ContentType", content_type)
    doc.parts[CONTENT_TYPES] = ET.tostring(root, encoding="utf-8", xml_declaration=True)


def list_masters(path):
    if not os.path.isfile(path):
        raise StencilError("stencil not found: %s" % path)
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(_read(zf, "visio/masters/masters.xml"))
        out = []
        for el in root.findall(NS + "Master"):
            out.append({"id": el.get("ID"), "name": el.get("NameU") or el.get("Name") or "Master"})
        return out


def _master_rel_id(master_el):
    rel = master_el.find(NS + "Rel")
    return rel.get(REL_NS + "id") if rel is not None else None


def _parse_rels(data):
    out = {}
    if not data:
        return out
    root = ET.fromstring(data)
    for rel in root.findall(PKG_REL + "Relationship"):
        out[rel.get("Id")] = rel.get("Target")
    return out


def import_master(doc, stencil_path, master_id):
    """Copy one master from the stencil into `doc`; returns the new master id."""
    with zipfile.ZipFile(stencil_path) as zf:
        src_root = ET.fromstring(_read(zf, "visio/masters/masters.xml"))
        src_rel_data = None
        try:
            src_rel_data = zf.read("visio/masters/_rels/masters.xml.rels")
        except KeyError:
            pass
        src_rels = _parse_rels(src_rel_data)

        master_el = None
        for el in src_root.findall(NS + "Master"):
            if str(el.get("ID")) == str(master_id):
                master_el = el
                break
        if master_el is None:
            raise StencilError("master %s not found in stencil" % master_id)
        rel_id = _master_rel_id(master_el)
        target = src_rels.get(rel_id) if rel_id else None
        if not target:
            raise StencilError("master %s has no drawable part" % master_id)
        part_name = "visio/masters/" + os.path.basename(target)
        payload = _read(zf, part_name)

    _ensure_masters_part(doc)
    _override_content_type(doc, "visio/masters/masters.xml", "application/vnd.ms-visio.masters+xml")
    dst_root = ET.fromstring(doc.parts["visio/masters/masters.xml"])
    existing = [int(el.get("ID")) for el in dst_root.findall(NS + "Master")]
    new_id = str(max(existing + [0]) + 1)

    index = 1
    while ("visio/masters/master%d.xml" % index) in doc.parts:
        index += 1
    dst_part = "visio/masters/master%d.xml" % index
    doc.parts[dst_part] = payload
    _override_content_type(doc, dst_part, "application/vnd.ms-visio.master+xml")

    rels_name = "visio/masters/_rels/masters.xml.rels"
    rels_root = ET.fromstring(doc.parts[rels_name])
    used = {rel.get("Id") for rel in rels_root.findall(PKG_REL + "Relationship")}
    n = 1
    while ("rId%d" % n) in used:
        n += 1
    new_rid = "rId%d" % n
    rel = ET.SubElement(rels_root, PKG_REL + "Relationship")
    rel.set("Id", new_rid)
    rel.set("Type", MASTER_TYPE)
    rel.set("Target", os.path.basename(dst_part))
    doc.parts[rels_name] = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)

    clone = copy.deepcopy(master_el)
    clone.set("ID", new_id)
    for attr in ("UniqueID", "BaseID"):
        clone.attrib.pop(attr, None)
    old_rel = clone.find(NS + "Rel")
    if old_rel is None:
        old_rel = ET.SubElement(clone, NS + "Rel")
    old_rel.set(REL_NS + "id", new_rid)
    dst_root.append(clone)
    doc.parts["visio/masters/masters.xml"] = ET.tostring(dst_root, encoding="utf-8", xml_declaration=True)

    doc._xmlcache.pop("visio/masters/masters.xml", None)
    doc._smap = None
    return new_id


def master_size(doc, master_id):
    meta = doc.masters().get(str(master_id))
    if not meta:
        return 1.5, 0.75
    root = doc._xml(meta["part"])
    shapes_el = root.find(NS + "Shapes")
    sh = shapes_el.find(NS + "Shape") if shapes_el is not None else None
    if sh is not None:
        found = {}
        for cell in sh.findall(NS + "Cell"):
            if cell.get("N") in ("Width", "Height"):
                try:
                    found[cell.get("N")] = float(cell.get("V"))
                except (TypeError, ValueError):
                    pass
        if found.get("Width") and found.get("Height"):
            return found["Width"], found["Height"]
    sheet = root.find(NS + "PageSheet")
    w = h = None
    if sheet is not None:
        for cell in sheet.findall(NS + "Cell"):
            if cell.get("N") == "PageWidth":
                w = cell.get("V")
            elif cell.get("N") == "PageHeight":
                h = cell.get("V")
    try:
        return float(w), float(h)
    except (TypeError, ValueError):
        return 1.5, 0.75


def _master_rows(doc, master_id):
    """Bake the master outline into 0..1 rows so the instance is self-contained."""
    meta = doc.masters().get(str(master_id))
    if not meta or not meta.get("part"):
        return None
    root = doc._xml(meta["part"])
    shapes_el = root.find(NS + "Shapes")
    sh = shapes_el.find(NS + "Shape") if shapes_el is not None else None
    if sh is None:
        return None
    mw = mh = None
    for cell in sh.findall(NS + "Cell"):
        if cell.get("N") == "Width":
            mw = float(cell.get("V"))
        elif cell.get("N") == "Height":
            mh = float(cell.get("V"))
    if not mw or not mh:
        return None
    rows = []
    for sec in sh.findall(NS + "Section"):
        if sec.get("N") != "Geometry":
            continue
        for row in sec.findall(NS + "Row"):
            kind = row.get("T") or ""
            if kind not in ("MoveTo", "LineTo", "RelMoveTo", "RelLineTo"):
                return None
            pts = {}
            for cell in row.findall(NS + "Cell"):
                if cell.get("N") in ("X", "Y"):
                    pts[cell.get("N")] = float(cell.get("V") or 0)
            if kind.startswith("Rel"):
                fx, fy = pts.get("X", 0), pts.get("Y", 0)
            else:
                fx, fy = pts.get("X", 0) / mw, pts.get("Y", 0) / mh
            rows.append(("RelMoveTo" if kind.endswith("MoveTo") else "RelLineTo",
                         [("X", round(fx, 6)), ("Y", round(fy, 6))]))
    return rows or None


def add_instance(doc, master_id, page=1, x=None, y=None, w=None, h=None, text=""):
    mw, mh = master_size(doc, master_id)
    w = float(w) if w else mw
    h = float(h) if h else mh
    rows = _master_rows(doc, master_id)
    return doc.add_master_shape(str(master_id), page=page, x=x, y=y, w=w, h=h, text=text, rows=rows)


def _master_el(path, master_id):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(_read(zf, "visio/masters/masters.xml"))
        rels = _parse_rels(_read(zf, "visio/masters/_rels/masters.xml.rels"))
        for el in root.findall(NS + "Master"):
            if master_id not in (None, "", str(el.get("ID"))) and master_id not in (
                    el.get("NameU"), el.get("Name")):
                continue
            part = rels.get(_master_rel_id(el))
            if not part:
                continue
            body = ET.fromstring(_read(zf, "visio/masters/" + part))
            return el, body
    raise StencilError("master not found: %s" % master_id)


def master_detail(path, master_id=None):
    """Name, description, size and text of every master (or just one)."""
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(_read(zf, "visio/masters/masters.xml"))
        rels = _parse_rels(_read(zf, "visio/masters/_rels/masters.xml.rels"))
        out = []
        for el in root.findall(NS + "Master"):
            if master_id and master_id not in (str(el.get("ID")), el.get("NameU"), el.get("Name")):
                continue
            part = rels.get(_master_rel_id(el))
            body = ET.fromstring(_read(zf, "visio/masters/" + part)) if part else None
            w = h = None
            text = ""
            shapes = 0
            if body is not None:
                for sh in body.iter(NS + "Shape"):
                    shapes += 1
                    if not text:
                        t = sh.find(NS + "Text")
                        if t is not None and t.text:
                            text = t.text.strip()[:120]
                    for cell in sh.findall(NS + "Cell"):
                        if cell.get("N") == "Width" and w is None:
                            w = float(cell.get("V") or 0)
                        elif cell.get("N") == "Height" and h is None:
                            h = float(cell.get("V") or 0)
            out.append({
                "id": el.get("ID"),
                "name": el.get("NameU") or el.get("Name") or "Master",
                "prompt": el.get("Prompt") or el.get("Description") or "",
                "keywords": el.get("Keywords") or "",
                "icon": el.get("Icon") == "1",
                "shapes": shapes,
                "width": w,
                "height": h,
                "text": text,
            })
    return out


def master_outline(path, master_id):
    """Polygon points (inches, origin bottom-left) of a master's first shape."""
    el, body = _master_el(path, master_id)
    sh = body.find(NS + "Shapes/" + NS + "Shape") if body.find(NS + "Shapes") is not None else None
    if sh is None:
        raise StencilError("master has no shape: %s" % master_id)
    w = h = 0.0
    for cell in sh.findall(NS + "Cell"):
        if cell.get("N") == "Width":
            w = float(cell.get("V") or 0)
        elif cell.get("N") == "Height":
            h = float(cell.get("V") or 0)
    pts = []
    for sec in sh.findall(NS + "Section"):
        if sec.get("N") != "Geometry":
            continue
        for row in sec.findall(NS + "Row"):
            x = y = None
            for cell in row.findall(NS + "Cell"):
                if cell.get("N") == "X":
                    x = float(cell.get("V") or 0)
                elif cell.get("N") == "Y":
                    y = float(cell.get("V") or 0)
            if x is None or y is None:
                continue
            if (row.get("T") or "").startswith("Rel"):
                pts.append((x * w, y * h))
            else:
                pts.append((x, y))
    return w, h, pts
