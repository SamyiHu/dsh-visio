#!/usr/bin/env python
"""visio_bridge - one JSON request on stdin, one JSON response on stdout.

The Host plugin spawns this file as a short-lived process for each operation:

    python visio_bridge.py  < request.json > response.json

Request:  {"action": "open" | ..., ...}
Response: {"ok": true, "state": {...}} or {"ok": false, "error": "..."}

Every mutating action saves the .vsdx in place (with a bounded .bak history) and
returns the refreshed state, so the browser panel can redraw the preview from a
single round trip.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vsdx_core import Vsdx, VsdxError  # noqa: E402
import blank_doc  # noqa: E402

try:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# One source of truth: the plugin version in package.json.  The bridge used to
# report a hard-coded 1.0.0 forever, so the engine string in /config and /ping
# disagreed with the build shown in the panel footer.
try:
    import json as _json
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "package.json"), "r", encoding="utf-8") as _fh:
        ENGINE_VERSION = _json.load(_fh)["version"]
except Exception:
    ENGINE_VERSION = "0.0.0"
MAX_BACKUPS = 20
DRAWING_EXT = (".vsdx", ".vsdm")
BAD_NAME = re.compile(r'[\\/:*?"<>|\r\n\t]')
CELL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,63}$")


class BadRequest(Exception):
    pass


def text(value, field: str, limit: int = 4000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise BadRequest("%s must be a string" % field)
    if len(value) > limit:
        raise BadRequest("%s is too long (max %d characters)" % (field, limit))
    return value


def number(value, field: str):
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise BadRequest("%s must be a number" % field)
    if out != out or abs(out) > 1e6:
        raise BadRequest("%s is out of range" % field)
    return out


def drawing_path(value, must_exist: bool = True) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BadRequest("path is required")
    path = os.path.abspath(value.strip())
    if not path.lower().endswith(DRAWING_EXT):
        raise BadRequest("path must end with .vsdx or .vsdm")
    if must_exist:
        if not os.path.isfile(path):
            raise BadRequest("file not found: %s" % path)
    return path


def page_of(value, pages) -> int:
    try:
        page = int(value or 1)
    except (TypeError, ValueError):
        page = 1
    return max(1, min(page, len(pages)))


def props_of(detail) -> dict:
    out = {}
    for section in detail.get("sections", {}).get("Property", []):
        for row in section.get("rows", []):
            name = str(row.get("row") or "")
            if name.startswith("Prop."):
                name = name[5:]
            if name:
                out[name] = row.get("cells", {}).get("Value", "")
    return out


def detail_of(doc, shape_id, page: int):
    sid = str(shape_id)
    det = doc.shape(sid, page)
    try:
        style = doc.style(sid, page)
    except Exception:
        style = {}
    return {
        "id": sid,
        "type": det.get("type") or "Shape",
        "master": det.get("master") or "",
        "text": det.get("text") or "",
        "parent": det.get("parent"),
        "cells": det.get("cells") or {},
        "props": props_of(det),
        "style": {
            "fill": style.get("fill"),
            "line": style.get("line"),
            "text": style.get("text"),
            "font_pt": style.get("font_pt"),
            "weight": style.get("weight_in"),
            "end_arrow": style.get("end_arrow"),
        },
        "sections": sorted({str(k) for k in (det.get("sections") or {}).keys()}),
    }


_DOC_CACHE = {}
_CACHE_LIMIT = 8


def load_doc(path: str):
    """Parse once per (path, mtime, size); the daemon keeps it warm between calls."""
    key = os.path.abspath(path)
    try:
        stat = os.stat(key)
    except OSError:
        raise BadRequest("file not found: %s" % path)
    hit = _DOC_CACHE.pop(key, None)
    if hit and hit[0] == stat.st_mtime_ns and hit[1] == stat.st_size:
        _DOC_CACHE[key] = hit
        return hit[2]
    doc = Vsdx(key)
    _DOC_CACHE[key] = [stat.st_mtime_ns, stat.st_size, doc]
    while len(_DOC_CACHE) > _CACHE_LIMIT:
        _DOC_CACHE.pop(next(iter(_DOC_CACHE)), None)
    return doc


def forget_doc(path: str) -> None:
    _DOC_CACHE.pop(os.path.abspath(path), None)


def build_state(path: str, page=1, selected=None, notice: str = "", saved: bool = False) -> dict:
    doc = load_doc(path)
    pages = doc.pages
    page = page_of(page, pages)
    shapes = doc.shapes(page)
    detail = None
    if selected is not None and str(selected) != "":
        sid = str(selected)
        if any(s["id"] == sid for s in shapes):
            detail = detail_of(doc, sid, page)
    meta = pages[page - 1]
    return {
        "ok": True,
        "path": doc.path,
        "name": os.path.basename(doc.path),
        "folder": os.path.dirname(doc.path),
        "page": page,
        "pageCount": len(pages),
        "pageName": meta["name"],
        "pageSize": {"w": meta["width"], "h": meta["height"]},
        "pages": [{"index": p["index"], "name": p["name"], "width": p["width"], "height": p["height"]} for p in pages],
        "masters": list(doc.masters().values()),
        "shapes": shapes,
        "detail": detail,
        "svg": doc.to_svg(page, interactive=True, background=False),
        "saved": bool(saved),
        "notice": notice,
        "mtime": os.path.getmtime(doc.path),
        "engine": ENGINE_VERSION,
        **_history_state(doc.path),
    }


_UNDO = {}
_REDO = {}
HISTORY_LIMIT = 25


def _stack(store, path):
    return store.setdefault(os.path.abspath(path), [])


def snapshot(path: str) -> None:
    """Remember the bytes on disk before a mutation, for undo."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return
    stack = _stack(_UNDO, path)
    stack.append(data)
    while len(stack) > HISTORY_LIMIT:
        stack.pop(0)
    _REDO.pop(os.path.abspath(path), None)


def _restore(path: str, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)
    forget_doc(path)


def _history_state(path: str) -> dict:
    key = os.path.abspath(path)
    return {"canUndo": len(_UNDO.get(key) or []), "canRedo": len(_REDO.get(key) or [])}


def action_undo(req):
    path = drawing_path(req.get("path"))
    key = os.path.abspath(path)
    stack = _UNDO.get(key) or []
    if not stack:
        raise BadRequest("没有可撤销的操作")
    with open(key, "rb") as fh:
        current = fh.read()
    _stack(_REDO, key).append(current)
    _restore(key, stack.pop())
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    return build_state(path, page, notice="已撤销")


def action_redo(req):
    path = drawing_path(req.get("path"))
    key = os.path.abspath(path)
    stack = _REDO.get(key) or []
    if not stack:
        raise BadRequest("没有可重做的操作")
    with open(key, "rb") as fh:
        current = fh.read()
    _stack(_UNDO, key).append(current)
    _restore(key, stack.pop())
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    return build_state(path, page, notice="已重做")


def save_doc(doc, backup: bool) -> None:
    snapshot(doc.path)
    doc.save(backup=backup, keep_backups=MAX_BACKUPS)
    try:
        stat = os.stat(doc.path)
        _DOC_CACHE[os.path.abspath(doc.path)] = [stat.st_mtime_ns, stat.st_size, doc]
    except OSError:
        forget_doc(doc.path)


def action_ping(_req):
    return {"ok": True, "engine": ENGINE_VERSION, "python": sys.version.split()[0]}


def action_list(req):
    folder = req.get("dir")
    if not isinstance(folder, str) or not folder.strip():
        raise BadRequest("dir is required")
    folder = os.path.abspath(folder.strip())
    if not os.path.isdir(folder):
        raise BadRequest("folder not found: %s" % folder)
    entries = []
    try:
        names = os.listdir(folder)
    except OSError as exc:
        raise BadRequest("cannot read folder: %s" % exc)
    for name in names:
        if name.startswith("~$") or not name.lower().endswith(DRAWING_EXT):
            continue
        full = os.path.join(folder, name)
        try:
            info = os.stat(full)
        except OSError:
            continue
        if not os.path.isfile(full):
            continue
        entries.append({"name": name, "path": full, "size": info.st_size, "mtime": int(info.st_mtime)})
    entries.sort(key=lambda item: -item["mtime"])
    return {"ok": True, "dir": folder, "files": entries}


def action_create(req):
    folder = text(req.get("dir"), "dir", 1000).strip()
    if not folder:
        raise BadRequest("dir is required")
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise BadRequest("folder not found: %s" % folder)
    name = text(req.get("name"), "name", 120).strip()
    if not name:
        raise BadRequest("name is required")
    if BAD_NAME.search(name):
        raise BadRequest('name cannot contain \\ / : * ? " < > |')
    if not name.lower().endswith(DRAWING_EXT):
        name += ".vsdx"
    path = os.path.join(folder, name)
    if os.path.exists(path) and req.get("overwrite") is not True:
        raise BadRequest("file already exists: %s" % path)
    width = number(req.get("width") or 11.0, "width")
    height = number(req.get("height") or 8.5, "height")
    blank_doc.create(path, width=width, height=height, page_name=text(req.get("pageName"), "pageName", 60) or "Page-1",
                     title=text(req.get("title"), "title", 200))
    title = text(req.get("title"), "title", 200).strip()
    if title:
        doc = load_doc(path)
        doc.add_shape(page=1, x=0.5, y=height - 1.15, w=max(1.0, width - 1.0), h=0.75,
                      text=title, kind="text")
        doc.save(backup=False)
    return build_state(path, 1, None, notice="已创建 %s" % os.path.basename(path), saved=True)


def action_open(req):
    path = drawing_path(req.get("path"))
    return build_state(path, req.get("page"), req.get("selected"), saved=False)


def action_stat(req):
    path = drawing_path(req.get("path"))
    info = os.stat(path)
    return {"ok": True, "path": path, "mtime": info.st_mtime, "size": info.st_size}


def action_text(req):
    path = drawing_path(req.get("path"))
    return {"ok": True, "text": load_doc(path).text_dump()}


def action_get_shape(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    if not sid:
        raise BadRequest("shape_id is required")
    return {"ok": True, "detail": detail_of(doc, sid, page)}


def action_set_text(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    value = text(req.get("text"), "text", 4000)
    doc.set_text(sid, value, page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="文本已保存", saved=True)


def action_set_cells(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    cells = req.get("cells")
    if not isinstance(cells, dict) or not cells:
        raise BadRequest("cells must be a non-empty object")
    clean = {}
    for name, value in cells.items():
        if not isinstance(name, str) or not CELL_NAME.match(name):
            raise BadRequest("invalid cell name: %s" % name)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise BadRequest("cell %s must be a string or number" % name)
        clean[name] = value
    doc.set_cells(sid, clean, page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="已更新 %d 个单元格" % len(clean), saved=True)


def action_stencil_list(req):
    import stencil
    file = text(req.get("file"), "file", 1000).strip()
    if not os.path.isabs(file):
        file = os.path.abspath(file)
    return {"ok": True, "file": file, "masters": stencil.list_masters(file)}


def action_stencil_add(req):
    import stencil
    path = drawing_path(req.get("path"))
    file = text(req.get("file") or req.get("stencil"), "file", 1000).strip()
    if not file:
        raise BadRequest("stencil file is required (pass stencil=<path to .vssx>)")
    master = text(req.get("master"), "master", 40).strip()
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    masters = stencil.list_masters(file)
    if str(master).isdigit():
        target = str(master)
    else:
        wanted = str(master).strip().lower()
        found = next((m for m in masters if str(m["name"]).strip().lower() == wanted), None)             or next((m for m in masters if wanted and wanted in str(m["name"]).lower()), None)
        if found is None:
            raise BadRequest("master %r not found; available: %s"
                             % (master, ", ".join(m["name"] for m in masters)))
        target = found["id"]
    new_id = stencil.import_master(doc, file, target)
    sid = stencil.add_instance(doc, new_id, page=page,
                               x=req.get("x"), y=req.get("y"),
                               w=req.get("w"), h=req.get("h"),
                               text=req.get("text") or "")
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="已插入模具形状", saved=True)


def action_shape_kinds(req):
    import kinds
    return {"ok": True, "kinds": sorted(kinds.KINDS.keys())}


def action_svg(req):
    """Just the page SVG - used to reconcile after an optimistic drag."""
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    return {"ok": True, "svg": doc.to_svg(page, interactive=True),
            "mtime": os.path.getmtime(path), **_history_state(path)}


def action_move(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    kwargs = {}
    for key in ("x", "y", "w", "h", "angle"):
        if req.get(key) is not None:
            kwargs[key] = number(req.get(key), key)
    if not kwargs:
        raise BadRequest("nothing to change; pass x, y, w and/or h")
    doc.move_shape(sid, page=page, **kwargs)
    save_doc(doc, req.get("backup", True))
    if req.get("light"):
        # The panel already moved the shape on screen; skip the full page render.
        return {"ok": True, "saved": True, "notice": "位置已保存",
                "mtime": os.path.getmtime(path), "shape_id": sid,
                **_history_state(path)}
    return build_state(path, page, sid, notice="位置/大小已保存", saved=True)


def action_set_prop(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    name = text(req.get("name"), "name", 120).strip()
    if not name:
        raise BadRequest("name is required")
    value = text(req.get("value"), "value", 2000)
    doc.set_prop(sid, name, value, page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="形状数据已保存", saved=True)


def _point(req, key):
    """Read an [x, y] pair from the request, or None when it is absent."""
    raw = req.get(key)
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise BadRequest("%s must be [x, y]" % key)
    return [number(raw[0], key), number(raw[1], key)]


def action_add_line(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    start = _point(req, "start") or [number(req.get("x1", 2.0), "x1"),
                                     number(req.get("y1", 3.0), "y1")]
    end = _point(req, "end") or [number(req.get("x2", 4.0), "x2"),
                                 number(req.get("y2", 3.0), "y2")]
    sid = doc.add_line(page=page, x1=start[0], y1=start[1], x2=end[0], y2=end[1],
                       arrow=bool(req.get("arrow")),
                       color=text(req.get("line"), "line", 20) or "#404040")
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="已添加直线 #%s" % sid, saved=True)


def action_set_line(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    start = _point(req, "start")
    end = _point(req, "end")
    if not start or not end:
        raise BadRequest("start and end are required")
    doc.set_line(sid, start[0], start[1], end[0], end[1], page=page)
    save_doc(doc, req.get("backup", True))
    if req.get("light"):
        return {"ok": True, "saved": True, "notice": "直线已更新",
                "mtime": os.path.getmtime(path), "shape_id": sid,
                **_history_state(path)}
    return build_state(path, page, sid, notice="直线已更新", saved=True)


# ------------------------------------------------------------- agent guide
GUIDE = {
  'open': {'meaning': 'Read a drawing: pages, page size, shapes (id/text/bbox), text outline.',
           'usage': 'path (required)', 'limits': 'Read-only. Coordinates are inches, origin bottom-left.',
           'checks': 'Always open first to learn existing shape ids before editing.'},
  'get_shape': {'meaning': 'Every ShapeSheet cell of one shape.', 'usage': 'path, shape_id',
                'limits': 'Cell values are raw strings.', 'checks': 'Use before changing a cell.'},
  'add_shape': {'meaning': 'Add a shape from a built-in kind, a shape-library name, or freeform vertices.',
                'usage': 'path, x, y, w, h, text, kind, fill, line; optional geometry, font_color, font_size, bold, line_pattern, line_width, angle',
                'limits': 'Use kind from kinds/shape_list. geometry = [[x,y],...] in 0..1 fractions (or [(row,x,y),...]); it OVERRIDES kind and is the ESCAPE HATCH for any silhouette (arrow heads, gates). Text supports \n for a two-line label: first line bold, second smaller. Colors are #RRGGBB. Keep shapes inside the page.',
                'example': '{"action":"add_shape","path":P,"x":1,"y":2,"w":2,"h":0.8,"kind":"step","text":"MCU 库制作\n库制作人"}',
                'checks': 'After adding, run audit_full to detect overlap / out-of-page / text overflow.'},
  'shape_list': {'meaning': 'List cached shapes: built-in defaults (read-only) + user library.',
                 'usage': 'no parameters', 'limits': 'Built-in default library cannot be overwritten; same-name user shapes override it.',
                 'checks': 'Call before add_shape when you want a consistent visual style.'},
  'shape_save': {'meaning': 'Cache a shape the model just composed, after verifying it renders.',
                 'usage': 'name, shape (kind or geometry + style)',
                 'limits': 'A shape that does not render is REJECTED and not cached. Written to ~/.dsh/visio-shapes.json (or DSH_VISIO_SHAPES). User library persists across upgrades.',
                 'example': '{"action":"shape_save","name":"my_gate","shape":{"geometry":[[0.5,0],[1,0.5],[0.5,1],[0,0.5],[0.5,0]],"fill":"#C55A1F","font_color":"#FFFFFF"}}',
                 'checks': 'Render once to confirm, then reuse via add_shape(kind=name).'},
  'move_endpoint': {'meaning': 'Move one connector end to an exact point, keeping the route orthogonal.',
                   'usage': 'path, shape_id, end=start|end, x, y',
                   'limits': 'Drops the glue of that end; the neighbouring run slides with it, the rest of the polyline stays put.',
                   'checks': 'Use after open(); audit_full flags an end that lands inside a shape.'},
  'set_end_direction': {'meaning': 'Make a glued connector end leave its shape from a chosen side.',
                        'usage': 'path, shape_id, end=start|end, direction=top|bottom|left|right',
                        'limits': 'The end must already be glued to a shape; the hand-drawn route is dropped so the router re-lays it from that side.',
                        'checks': 'Pair it with set_cell LinePattern (1 solid, 2 dashed) for rework/return lines.'},
  'add_anchor': {'meaning': 'Invisible 0.02in anchor just outside one side of a shape.',
                 'usage': 'path, shape_id, side=top|bottom|left|right, gap (default 0.02)',
                 'limits': 'The anchor is a text-kind shape, so it paints nothing; connect to it instead of to the shape.',
                 'checks': 'Use it when an arrow must stop on the border instead of heading for the shape centre.'},
  'swimlane': {'meaning': 'Wrap an existing row of shapes in a lane band with a header.',
               'usage': 'path, nodes=[shape ids], title, owner; optional fill, line, pad_x, pad_bottom, head',
               'limits': 'The band is sized from the node bounding box (never shorter than its nodes) and pushed behind them.',
               'checks': 'Create the nodes first, then the lane; audit_full confirms nothing overlaps the header.'},
  'connect_styled': {'meaning': 'One action for a styled orthogonal link: explicit points + line colour + dashed pattern.',
                     'usage': 'path, from, to, points [[x,y],...], line_color, line_pattern (2=dashed), line_width, label; optional from_port/to_port, orthogonal (default true), within [x,y,w,h], label_pos auto|above|below|left|right|[x,y], allow_off_midpoint + user_approved (user consent required)',
                     'limits': 'points must be axis-aligned waypoints in sheet inches; first/last should meet the two shapes.',
                     'checks': 'Use distinct colours: navy for normal flow, red dashed for rework, green for cross-lane delivery.'},
  'connect': {'meaning': 'Add a glued connector between two shapes.',
              'usage': 'path, from, to, label; optional from_port/to_port [x,y]',
              'limits': 'from and to must be existing shape ids; cannot connect a shape to itself. The router re-routes around unrelated shapes; a hand-drawn route that crosses a shape is discarded.',
              'checks': 'Run audit_full / validate after connecting.'},
  'set_route': {'meaning': 'Replace a connector polyline with explicit points.',
                'usage': 'path, shape_id, points [[x,y],...]',
                'limits': 'First and last points must differ (degenerate routes are rejected). Runs should be axis-aligned (H/V).',
                'checks': 'Prefer the automatic router; use this only for a deliberate orthogonal detour.'},
  'move': {'meaning': 'Move / resize / rotate a shape by bbox.',
           'usage': 'path, shape_id, x, y, w, h, angle (degrees, CCW)',
           'limits': 'w and h must be > 0. Connectors move their endpoints instead of resizing.',
           'checks': 'audit_full after placing to catch overlaps.'},
  'align': {'meaning': 'Snap shapes to each other (edges, centres, connection points) - the same assist the UI uses.',
            'usage': 'path, shape_ids [..], mode = edges|centres|ports',
            'limits': 'Only moves shapes, never connectors. Alignment tolerance 0.35in.',
            'checks': 'Run after a batch of add_shape to make the drawing tidy.'},
  'audit_full': {'meaning': 'Full quality audit: validate + overlap + out-of-page + text overflow + connector crossing.',
                 'usage': 'path', 'limits': 'Read-only.',
                 'checks': 'Run this before declaring a drawing finished; fix every error.'},
  'snapshot': {'meaning': 'Render pages to PNG for the human/model to review.',
               'usage': 'path, review=true (adds a structured report), dpi, out, all',
               'limits': 'The tool result is TEXT: a PNG path plus a report, NOT an inline image (DSH tool output schema is text-only). The model reads the report; the user views the PNG in the panel.',
               'checks': 'Use review=true as the CHECK STAGE of every drawing task.'},
  'validate': {'meaning': 'Relationship audit: empty links, dangling ids, drifting endpoints, zero-size shapes.',
               'usage': 'path', 'limits': 'Does NOT check overlap / out-of-page; use audit_full for that.',
               'checks': 'Basic subset of audit_full.'},
  'kinds': {'meaning': 'List the 16 built-in shape kinds.', 'usage': 'no parameters',
            'limits': 'For richer styles use shape_list; for arbitrary silhouettes use geometry.',
            'checks': ''},
  'capabilities': {'meaning': 'Full machine-readable tool contract (this guide).',
                   'usage': 'no parameters', 'limits': 'Use it at the start of a drawing task.',
                   'checks': ''},
  'move_label': {'meaning': 'Move a connector label without moving the line.',
                 'usage': 'path, shape_id, dx, dy (inches)',
                 'limits': 'dy is positive UP (drawing coordinates, not screen pixels).',
                 'checks': 'snapshot to confirm the label sits where intended.'},
}

GUIDE_ORDER = ['open', 'get_shape', 'add_shape', 'shape_list', 'shape_save', 'connect',
               'set_route', 'connect_styled', 'move', 'align', 'audit_full', 'snapshot', 'validate',
               'kinds', 'capabilities', 'move_label']

def action_guide(req):
    one = text(req.get('which'), 'which', 40) if req.get('which') else None
    if one:
        if one not in GUIDE:
            raise BadRequest('no guide for action %s' % one)
        return {'ok': True, 'action': one, **GUIDE[one]}
    return {'ok': True, 'order': GUIDE_ORDER, 'guide': GUIDE,
            'workflow': ['1 open/capabilities', '2 shape_list + kinds',
                         '3 add_shape (prefer library names; geometry is the escape hatch)',
                         '4 connect + align', '5 audit_full, fix errors',
                         '6 snapshot(review=true) and read the report',
                         '7 shape_save for shapes worth reusing'],
            'hard_rules': [
              'Coordinates: inches, origin bottom-left.',
              'Prefer add_shape(kind=library name) over freeform geometry.',
              'geometry is the escape hatch when 16 kinds + library are not enough; it is harder to maintain/align.',
              'Every drawing task must end with audit_full + snapshot(review=true).',
              'User shape library lives outside the repo and survives upgrades; built-in library is read-only.',
            ]}

# ------------------------------------------------------------- shape library
BUILTIN_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shape_library.json')

def user_lib_path():
    override = os.environ.get('DSH_VISIO_SHAPES')
    if override:
        return override
    return os.path.join(os.path.expanduser('~'), '.dsh', 'visio-shapes.json')

def load_library():
    """Built-in defaults (read-only) merged with the user's cached shapes."""
    out = {}
    try:
        with open(BUILTIN_LIB, 'r', encoding='utf-8') as fh:
            out.update(json.load(fh).get('shapes') or {})
    except Exception:
        pass
    try:
        with open(user_lib_path(), 'r', encoding='utf-8') as fh:
            out.update(json.load(fh).get('shapes') or {})
    except Exception:
        pass
    return out

def action_shape_list(_req):
    lib = load_library()
    return {'ok': True, 'count': len(lib), 'builtin': BUILTIN_LIB, 'user': user_lib_path(),
            'shapes': [{'name': k, 'builtin': k in (json.load(open(BUILTIN_LIB, encoding='utf-8')).get('shapes') or {})
                        if os.path.exists(BUILTIN_LIB) else False, 'label': (v or {}).get('label', '')}
                       for k, v in sorted(lib.items())]}

def action_shape_save(req):
    """Cache a shape the model just composed, after verifying it renders."""
    name = text(req.get('name'), 'name', 60).strip()
    if not name:
        raise BadRequest('name is required')
    spec = req.get('shape') or {}
    if not isinstance(spec, dict) or not (spec.get('geometry') or spec.get('kind')):
        raise BadRequest('shape must contain geometry or kind')
    # verify: write a scratch drawing, render it, count paths
    import tempfile
    import blank_doc
    from vsdx_core import Vsdx
    tmp = os.path.join(tempfile.gettempdir(), 'dsh-visio-shape-check.vsdx')
    blank_doc.create(tmp, 4, 3, 'check', 't')
    d = Vsdx(tmp)
    d.add_shape(1, 0.5, 0.5, 2, 1, str(spec.get('text') or ''),
                spec.get('kind', 'rect'), spec.get('fill'), spec.get('line'),
                geometry=spec.get('geometry'), font_color=spec.get('font_color'),
                font_size=spec.get('font_size'), bold=spec.get('bold'))
    d.save(backup=False)
    svg = Vsdx(tmp).to_svg(1, interactive=False, background=False)
    if svg.count('<path') < 1:
        raise BadRequest('shape did not render - refusing to cache it')
    path = user_lib_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {'shapes': {}}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception:
        pass
    data.setdefault('shapes', {})[name] = spec
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return {'ok': True, 'name': name, 'path': path, 'rendered': True}

def action_add_shape(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    import kinds
    kind = text(req.get("kind"), "kind", 60) or "rect"
    lib = load_library()
    preset = lib.get(kind) or {}
    if kind not in kinds.KINDS and not preset:
        raise BadRequest("unknown kind %s; known: %s, or names from shape_list" % (kind, ", ".join(sorted(kinds.KINDS))))
    eff_kind = kind if kind in kinds.KINDS else preset.get("kind", "rect")
    sid = doc.add_shape(
        page=page,
        x=number(req.get("x", 1.0), "x"),
        y=number(req.get("y", 1.0), "y"),
        w=number(req.get("w", 1.6), "w"),
        h=number(req.get("h", 0.8), "h"),
        text=text(req.get("text"), "text", 4000) or str(preset.get("text") or ""),
        kind=eff_kind,
        fill=text(req.get("fill"), "fill", 20) or preset.get("fill"),
        line=text(req.get("line"), "line", 20) or preset.get("line"),
        geometry=req.get("geometry") or preset.get("geometry"),
        font_color=text(req.get("font_color"), "font_color", 20) or preset.get("font_color"),
        font_size=req.get("font_size") or preset.get("font_size"),
        bold=req.get("bold") if req.get("bold") is not None else preset.get("bold"),
        line_pattern=req.get("line_pattern"),
        line_width=req.get("line_width"),
        angle=req.get("angle"),
        text_bg=req.get("text_bg"),
    )
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="已添加形状 #%s" % sid, saved=True)


def action_connect(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    src = text(req.get("from"), "from", 40)
    dst = text(req.get("to"), "to", 40)
    if not src or not dst:
        raise BadRequest("from and to are required")
    if src == dst:
        raise BadRequest("cannot connect a shape to itself")
    sid = doc.connect(src, dst, page, label=text(req.get("label"), "label", 500),
                      from_port=_point(req, "from_port"), to_port=_point(req, "to_port"),
                      line_width=req.get("line_width"), line_color=req.get("line_color"),
                      line_pattern=req.get("line_pattern"))
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="已连接 #%s → #%s" % (src, dst), saved=True)


def action_delete(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    doc.delete_shape(sid, page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, None, notice="已删除形状 #%s" % sid, saved=True)


def action_normalize(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    report = doc.normalize_units()
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, None,
                       notice="已修复 %d 个单元格的单位标注" % report["cells"], saved=True)


def action_export(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    fmt = (text(req.get("format"), "format", 10) or "svg").lower()
    out = text(req.get("out"), "out", 1000).strip()
    if fmt == "svg":
        out = out or os.path.splitext(path)[0] + ".svg"
        doc.save_svg(out, page, show_ids=bool(req.get("show_ids")))
    elif fmt == "png":
        # Render the same SVG the panel shows: the older vsdx_png routine drew a
        # bounding box for custom Geometry, so freeform silhouettes (decision
        # gates, arrow heads, composed shapes) exported as plain rectangles.
        import svg_raster
        out = out or os.path.splitext(path)[0] + ".png"
        svg = doc.to_svg(page, interactive=False, background=True)
        svg_raster.rasterize(svg, scale=float(req.get("dpi") or 110)).save(out)
    else:
        raise BadRequest("format must be svg or png")
    return {"ok": True, "out": out}



def action_validate(req):
    """Relationship audit: connectors, empty links, zero-size shapes, dangling ids."""
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    shapes = doc.shapes(page)
    by_id = {s["id"]: s for s in shapes}
    issues = []

    def add(level, code, sid, message, hint=None):
        item = {"level": level, "code": code, "shape": sid, "message": message}
        if hint:
            item["hint"] = hint
        issues.append(item)

    seen = set()
    for s in shapes:
        sid = s["id"]
        if sid in seen:
            add("error", "duplicate-id", sid, "形状 ID 重复")
        seen.add(sid)
        b = s["bbox"]
        if not s["connector"] and s["type"] != "Guide" and (b["w"] <= 0 or b["h"] <= 0):
            add("error", "zero-size", sid, "形状宽或高为 0，Visio 里也看不到", "用 move 重新设置宽高")
        if s["connector"]:
            cells = doc.shape(sid, page)["cells"]
            missing = [k for k in ("BeginX", "BeginY", "EndX", "EndY") if cells.get(k) in (None, "")]
            if missing:
                add("error", "connector-no-endpoints", sid, "连接线缺少端点坐标：%s" % ", ".join(missing))
                continue
            conns = s.get("connects") or []
            if not conns:
                add("warn", "connector-unbound", sid, "空关系：连接线没有 Connect 记录，只是画在两点之间，移动形状时不会跟随",
                     "用 connect 动作把两端绑到形状上")
            for c in conns:
                if c["to"] not in by_id:
                    add("error", "connect-dangling", sid, "Connect 指向不存在的形状 #%s" % c["to"])
            try:
                x1, y1 = float(cells["BeginX"]), float(cells["BeginY"])
                x2, y2 = float(cells["EndX"]), float(cells["EndY"])
            except (TypeError, ValueError):
                continue
            # A connector that runs through an unrelated shape looks broken to a reader
            # even though every Connect row is present - report it.
            ends = {str(c['to']) for c in conns}
            route = [(x1, y1), (x2, y2)]
            if abs(x2 - x1) > 0.02 and abs(y2 - y1) > 0.02:
                if abs(x2 - x1) >= abs(y2 - y1):
                    mx_ = (x1 + x2) / 2.0
                    route = [(x1, y1), (mx_, y1), (mx_, y2), (x2, y2)]
                else:
                    my_ = (y1 + y2) / 2.0
                    route = [(x1, y1), (x1, my_), (x2, my_), (x2, y2)]
            for i in range(len(route) - 1):
                ax, ay = route[i]
                bx, by = route[i + 1]
                for o in shapes:
                    if o['connector'] or o['type'] == 'Guide' or o['id'] in ends:
                        continue
                    # A lane band is a backdrop, not an obstacle: it legitimately
                    # contains every connector that runs along its row.
                    ob = o['bbox']
                    if (not (o.get('text') or '').strip()
                            and ob['w'] * ob['h'] > 4 * max((abs(x2 - x1) + 0.1) * (abs(y2 - y1) + 0.1), 0.01)):
                        continue
                        continue
                    if _segment_hits_box(ax, ay, bx, by, o['bbox'], 0.02):
                        label_ = (o.get('text') or '').split('|')[0][:12] or '无文字'
                        add('warn', 'connector-crosses-shape', sid,
                            '连接线穿过形状 #%s（%s）' % (o['id'], label_),
                            '调整形状位置或缩短连线')
                        break
            _pts = doc.geometry_points(sid, page)
            if len(_pts) >= 2:
                (_lx, _ly), (_ex, _ey) = _pts[-2], _pts[-1]
                _leg = ((_ex - _lx) ** 2 + (_ey - _ly) ** 2) ** 0.5
                if _leg < 0.12:
                    add('warn', 'arrow-degenerate', sid,
                        '箭头前的最后一段只有 %.2f in，虚线的空隙会把箭头吞掉' % _leg,
                        '把最后一段延长到 0.15in 以上')
            for _o in shapes:
                if _o['connector'] or _o['type'] == 'Guide' or _o['id'] in ends:
                    continue
                _b = _o['bbox']
                if not (_o.get('text') or '').strip() and _b['w'] > 5 and _b['h'] > 1:
                    continue      # lane backdrop, not a shape the end can land inside
                if (len(_pts) > 2 and
                        min(x2 - _b['x'], _b['x'] + _b['w'] - x2, y2 - _b['y'], _b['y'] + _b['h'] - y2) > 0.06):
                    add('warn', 'endpoint-inside-shape', sid,
                        '手绘走线的终点落在形状 #%s 内部 %.2f in' % (_o['id'], min(x2 - _b['x'], _b['x'] + _b['w'] - x2, y2 - _b['y'], _b['y'] + _b['h'] - y2)),
                        '贴到边框外 0.02in 再落点，或用 from_port/to_port 钉在端口上')
                    break
            # A connector should meet a shape on a side MIDPOINT, not on an arbitrary
            # point along an edge: Visio glues to connection points and a mid-edge
            # landing reads as a mistake.  Only checked when the end actually sits
            # on some shape's border.
            for _lab, (_px, _py) in (("起点", (x1, y1)), ("终点", (x2, y2))):
                for _o in shapes:
                    if _o["connector"] or _o["type"] == "Guide":
                        continue
                    _b = _o["bbox"]
                    _tol = 0.05
                    _near_v = abs(_px - _b["x"]) < _tol or abs(_px - (_b["x"] + _b["w"])) < _tol
                    _near_h = abs(_py - _b["y"]) < _tol or abs(_py - (_b["y"] + _b["h"])) < _tol
                    _in_x = _b["x"] - _tol <= _px <= _b["x"] + _b["w"] + _tol
                    _in_y = _b["y"] - _tol <= _py <= _b["y"] + _b["h"] + _tol
                    if not ((_in_x and _near_h) or (_in_y and _near_v)):
                        continue
                    _mids = [(_b["x"] + _b["w"] / 2.0, _b["y"]),
                             (_b["x"] + _b["w"] / 2.0, _b["y"] + _b["h"]),
                             (_b["x"], _b["y"] + _b["h"] / 2.0),
                             (_b["x"] + _b["w"], _b["y"] + _b["h"] / 2.0)]
                    _best = min(((_px - _mx) ** 2 + (_py - _my) ** 2) ** 0.5 for _mx, _my in _mids)
                    if _best > 0.08:
                        add("warn", "endpoint-off-midpoint", sid,
                            "%s贴在第 #%s 的边上，但离侧面中点 %.2f in" % (_lab, _o["id"], _best),
                            "连到左边/右边/上边/下边的中点，或用 from_port/to_port")
                    break

            for label, (px, py) in (("起点", (x1, y1)), ("终点", (x2, y2))):
                if not any(_point_in_box(px, py, o["bbox"], 0.12) for o in shapes if not o["connector"] and o["type"] != "Guide"):
                    add("warn", "connector-floating-%s" % ("start" if label == "起点" else "end"),
                        sid, "%s没有落在任何形状上" % label, "检查连接线端点坐标")
            if s.get("text"):
                add("info", "connector-label", sid, "线上文字：%s" % s["text"].replace("\n", " / "))
    counts = {"error": 0, "warn": 0, "info": 0}
    for item in issues:
        counts[item["level"]] += 1
    return {"ok": True, "path": path, "page": page, "counts": counts,
            "issues": issues, "shapes": len(shapes),
            "connectors": len([s for s in shapes if s["connector"]])}


def _segment_hits_box(x1, y1, x2, y2, box, pad=0.0, steps=24):
    """True when the segment passes through the box (sampled, good enough for a warning)."""
    bx1, by1 = box["x"] + pad, box["y"] + pad
    bx2, by2 = box["x"] + box["w"] - pad, box["y"] + box["h"] - pad
    if bx2 <= bx1 or by2 <= by1:
        return False
    for k in range(1, steps):
        t = k / float(steps)
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        if bx1 <= x <= bx2 and by1 <= y <= by2:
            return True
    return False


def _point_in_box(x, y, box, pad=0.0):
    return (box["x"] - pad) <= x <= (box["x"] + box["w"] + pad) and \
           (box["y"] - pad) <= y <= (box["y"] + box["h"] + pad)



def _sheet_png(masters, out_path, cols=4, tile=220):
    """Contact sheet: every master drawn in its own tile, labelled."""
    from PIL import Image, ImageDraw, ImageFont
    rows = max(1, (len(masters) + cols - 1) // cols)
    pad = 14
    W = cols * tile + pad * 2
    H = rows * (tile + 26) + pad * 2
    img = Image.new("RGB", (W, H), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 13)
    except OSError:
        font = ImageFont.load_default()
    for i, (name, w, h, pts) in enumerate(masters):
        cx = pad + (i % cols) * tile
        cy = pad + (i // cols) * (tile + 26)
        draw.rectangle([cx, cy, cx + tile - 8, cy + tile - 8], outline="#D0D5DD")
        if not pts:
            continue
        span_x = max(w, 0.001)
        span_y = max(h, 0.001)
        sc = min((tile - 40) / span_x, (tile - 40) / span_y)
        ox = cx + (tile - 8 - span_x * sc) / 2.0
        oy = cy + (tile - 8 - span_y * sc) / 2.0
        poly = [(ox + px * sc, oy + (h - py) * sc) for px, py in pts]
        draw.polygon(poly, fill="#EDF2FB", outline="#355694")
        draw.text((cx + 6, cy + tile - 2), name[:26], fill="#1A1A1A", font=font)
    img.save(out_path)
    return out_path


def action_stencil_info(req):
    import stencil
    file = text(req.get("file"), "file", 1000).strip()
    if not file:
        raise BadRequest("file is required (path to a .vssx/.vstx)")
    if not os.path.isabs(file):
        file = os.path.abspath(file)
    master = text(req.get("master"), "master", 60).strip() or None
    masters = stencil.master_detail(file, master)
    return {"ok": True, "file": file, "count": len(masters), "masters": masters}


def action_stencil_sheet(req):
    import stencil
    file = text(req.get("file"), "file", 1000).strip()
    if not os.path.isabs(file):
        file = os.path.abspath(file)
    out = text(req.get("out"), "out", 1000).strip()
    if not out:
        out = os.path.splitext(file)[0] + "-sheet.png"
    masters = stencil.master_detail(file)
    tiles = []
    for m in masters:
        try:
            w, h, pts = stencil.master_outline(file, m["id"])
        except Exception:            # a master without simple geometry still gets a tile
            w, h, pts = 1.0, 1.0, []
        tiles.append((m["name"], w or 1.0, h or 1.0, pts))
    _sheet_png(tiles, out)
    return {"ok": True, "file": file, "out": out, "masters": len(tiles)}


def action_snapshot(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    pages = list(range(1, len(doc.pages) + 1)) if req.get("all") else [page_of(req.get("page"), doc.pages)]
    out_dir = text(req.get("out"), "out", 1000).strip()
    if out_dir and not os.path.isabs(out_dir):
        out_dir = os.path.join(os.path.dirname(path), out_dir)
    if not out_dir:
        out_dir = os.path.join(os.path.dirname(path), "preview")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    import svg_raster
    files = []
    dpi = float(req.get("dpi") or 110)
    for number in pages:
        target = os.path.join(out_dir, "%s-p%d.png" % (stem, number))
        svg = doc.to_svg(number, interactive=False, background=False)
        svg_raster.rasterize(svg, scale=dpi).save(target)
        files.append(target)
    result = {'ok': True, 'path': path, 'pages': len(pages), 'files': files}
    if req.get('review'):
        audit = action_audit_full({'path': path, 'page': req.get('page')})
        result['report'] = {'counts': audit['counts'], 'issues': audit['issues'][:40]}
        result['note'] = 'TEXT-ONLY result: read the report; view the PNG in the Visio panel.'
    return result


def audit_geometry(doc, page, base_issues):
    """Extend validate() with the checks the UI panel offers: overlap, page
    bounds and rough text overflow.  Returns (issues, counts)."""
    shapes = [x for x in doc.shapes(page) if not x['connector'] and not x.get('line')]
    page_w = doc.pages[page - 1]['width']
    page_h = doc.pages[page - 1]['height']
    issues = list(base_issues)

    def add(level, code, sid, message):
        issues.append({'level': level, 'code': code, 'shape': sid, 'message': message})

    for a in shapes:
        b = a['bbox']
        if b['x'] < -0.001 or b['y'] < -0.001 or b['x'] + b['w'] > page_w + 0.001 or b['y'] + b['h'] > page_h + 0.001:
            add('error', 'out-of-page', a['id'], '形状超出页面范围')
        txt = (a.get('text') or '').strip()
        if txt and b['w'] > 0 and b['h'] > 0:
            # ~0.09in per Chinese glyph at 11pt; two lines need ~0.32in height
            longest = max(len(line) for line in txt.split('\n'))
            if longest * 0.095 > b['w'] * 1.15:
                add('warn', 'text-overflow', a['id'], '文字可能超出形状宽度')
            if len(txt.split('\n')) > max(2, int(b['h'] / 0.24)):
                add('warn', 'text-overflow-y', a['id'], '文字行数可能超出形状高度')
            try:
                _fs = float(doc.style(a['id'], page).get('font_pt') or 0)
            except (TypeError, ValueError):
                _fs = 0.0
            if _fs:
                _need = len(txt.split("\n")) * _fs / 72.0 * 1.32
                if _need > b['h'] * 0.96 + 1e-6:
                    add('warn', 'text-clipped-y', a['id'],
                        '文字需要 %.2f in 高，形状只有 %.2f in，会被压扁' % (_need, b['h']))
    for i, a in enumerate(shapes):
        for b2 in shapes[i + 1:]:
            # overlap check below (pure geometry)
            A, B = a['bbox'], b2['bbox']
            ox = min(A['x'] + A['w'], B['x'] + B['w']) - max(A['x'], B['x'])
            oy = min(A['y'] + A['h'], B['y'] + B['h']) - max(A['y'], B['y'])
            if ox > 0.05 and oy > 0.05:
                # A lane band legitimately contains its nodes - only flag when
                # the smaller box is not mostly inside the bigger one.
                small, big = sorted((A, B), key=lambda z: z['w'] * z['h'])
                if (ox * oy) / max(small['w'] * small['h'], 1e-6) > 0.85:
                    continue
                add('warn', 'overlap', a['id'], '形状 #%s 与 #%s 重叠 %.2f x %.2f in' % (a['id'], b2['id'], ox, oy))
    counts = {'error': 0, 'warn': 0, 'info': 0}
    for it in issues:
        counts[it.get('level', 'info')] = counts.get(it.get('level', 'info'), 0) + 1
    return issues, counts

def action_audit_full(req):
    base = action_validate(req)
    path = drawing_path(req.get('path'))
    doc = load_doc(path)
    page = page_of(req.get('page'), doc.pages)
    issues, counts = audit_geometry(doc, page, base.get('issues') or [])
    strict = req.get('strict') is True
    failed = strict and (counts.get('error', 0) + counts.get('warn', 0)) > 0
    error = ('strict audit failed: %d error / %d warning' % (counts.get('error', 0), counts.get('warn', 0))) if failed else None
    return {'ok': not failed, 'path': path, 'page': page, 'issues': issues, 'counts': counts,
            'strict': strict, 'error': error,
            'checks': ['validate', 'overlap', 'out-of-page', 'text-overflow', 'text-clipped-y',
                       'connector-crossing', 'arrow-degenerate', 'endpoint-inside-shape',
                       'endpoint-off-midpoint']}

def action_align(req):
    """Snap a list of shapes to a shared edge/centre - the UI's alignment assist.
    mode=edges aligns left edges, centres aligns centre lines, ports aligns the
    nearest connection points.  Only the x axis is shifted to keep rows intact."""
    path = drawing_path(req.get('path'))
    doc = load_doc(path)
    page = page_of(req.get('page'), doc.pages)
    ids = [str(x) for x in (req.get('shape_ids') or [])]
    mode = text(req.get('mode'), 'mode', 20) or 'edges'
    if len(ids) < 2:
        raise BadRequest('shape_ids needs at least 2 ids')
    by_id = {s['id']: s for s in doc.shapes(page)}
    missing = [x for x in ids if x not in by_id]
    if missing:
        raise BadRequest('unknown shape ids: %s' % ', '.join(missing))
    boxes = [by_id[x]['bbox'] for x in ids]
    target = (min(b['x'] for b in boxes) if mode == 'edges'
              else (sum(b['x'] + b['w'] / 2 for b in boxes) / len(boxes) if mode == 'centres'
                    else min(b['x'] for b in boxes)))
    moved = []
    for sid, b in zip(ids, boxes):
        want = target if mode == 'edges' else target - b['w'] / 2
        if abs(b['x'] - want) > 0.001:
            doc.move_shape(sid, x=want, y=b['y'], w=b['w'], h=b['h'], page=page)
            moved.append({'id': sid, 'from': round(b['x'], 4), 'to': round(want, 4)})
    save_doc(doc, req.get('backup', True))
    return {'ok': True, 'path': path, 'mode': mode, 'moved': moved,
            'note': 'This is the same edge/centre snapping the panel uses while dragging.'}

def action_capabilities(_req):
    return {"ok": True, "actions": sorted(ACTIONS.keys()),
            "kinds": list_kinds(), "notes": {
                "stencils": "stencil_info / stencil_sheet / stencil_add take a .vssx/.vstx path",
                "visual": "snapshot writes PNG files per page; export writes one SVG/PNG",
                "units": "inches, origin bottom-left",
            }}


def list_kinds():
    try:
        import kinds
        return sorted(kinds.KINDS.keys())
    except Exception:
        return []


def action_move_label(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    dx = number(req.get("dx") or 0, "dx")
    dy = number(req.get("dy") or 0, "dy")
    doc.move_label(sid, dx=dx, dy=dy, page=page)
    save_doc(doc, req.get("backup", True))
    if req.get("light"):
        return {"ok": True, "saved": True, "notice": "文字位置已保存",
                "mtime": os.path.getmtime(path), "shape_id": sid, **_history_state(path)}
    return build_state(path, page, sid, notice="文字位置已保存", saved=True)


def action_probe(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    direction = text(req.get("direction"), "direction", 10) or "right"
    result = doc.probe(sid, direction, page=page,
                       gap=number(req.get("gap") or 0.4, "gap"),
                       tol=number(req.get("tol") or 0.35, "tol"),
                       reach=number(req.get("reach") or 3.0, "reach"))
    result["path"] = path
    result["page"] = page
    return result


def action_duplicate(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    direction = text(req.get("direction"), "direction", 10) or "right"
    result = doc.duplicate(sid, direction=direction,
                           gap=number(req.get("gap") or 0.4, "gap"),
                           connect=req.get("connect", True) is not False,
                           page=page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, result["new_id"],
                       notice="已复制为 #%s" % result["new_id"], saved=True)


def action_bend(req):
    """Insert a bend point into a connector's polyline (manual routing)."""
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    x = number(req.get("x"), "x")
    y = number(req.get("y"), "y")
    doc.bend(sid, x, y, page=page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="已添加拐点", saved=True)


def _midpoint_policy(doc, page, shape_id, point, allow, approved, label):
    """Keep a hand-drawn connector end on a side MIDPOINT of its shape.

    Snaps within 0.15in.  A point that sits on the border but further away is
    refused, because a corner landing reads as a mistake.  The escape hatch is
    deliberately two keys: the model may only bypass after asking the user.
    """
    shape = next((s for s in doc.shapes(page) if s["id"] == str(shape_id)), None)
    if shape is None:
        return point
    b = shape["bbox"]
    if b["w"] < 0.1 or b["h"] < 0.1:      # anchor helpers are meant to be invisible
        return point
    mids = [(b["x"] + b["w"] / 2.0, b["y"]), (b["x"] + b["w"] / 2.0, b["y"] + b["h"]),
            (b["x"], b["y"] + b["h"] / 2.0), (b["x"] + b["w"], b["y"] + b["h"] / 2.0)]
    px, py = float(point[0]), float(point[1])
    best = min(mids, key=lambda m: (m[0] - px) ** 2 + (m[1] - py) ** 2)
    dist = ((best[0] - px) ** 2 + (best[1] - py) ** 2) ** 0.5
    if dist <= 0.15:
        return best
    tol = 0.05
    on_border = ((abs(px - b["x"]) < tol or abs(px - (b["x"] + b["w"])) < tol)
                 and b["y"] - tol <= py <= b["y"] + b["h"] + tol) or \
                ((abs(py - b["y"]) < tol or abs(py - (b["y"] + b["h"])) < tol)
                 and b["x"] - tol <= px <= b["x"] + b["w"] + tol)
    if not on_border:
        return point
    if allow and approved:
        return point
    if allow and not approved:
        raise BadRequest("绕过端点中点约束需要先征得用户同意：请在对话里说明理由并得到确认，"
                         "再同时传 user_approved=true")
    raise BadRequest("%s (%.2f, %.2f) 距 #%s 最近的侧面中点 %.2f in（上限 0.15in）；"
                     "请改到左/右/上/下边中点，或征得用户同意后传 allow_off_midpoint=true + user_approved=true"
                     % (label, px, py, shape_id, dist))


def action_connect_styled(req):
    """Create a styled connector whose polyline is EXACTLY the given points.

    `points` must include both glued endpoints (use open() to read the shape
    edges) and only axis-aligned waypoints.  No auto-routing is applied: what
    the model specifies is what is drawn, so a corridor never turns diagonal.
    """
    path = drawing_path(req.get('path'))
    doc = load_doc(path)
    page = page_of(req.get('page'), doc.pages)
    src, dst = text(req.get('from'), 'from', 40), text(req.get('to'), 'to', 40)
    if not src or not dst:
        raise BadRequest('from and to are required')
    pts = [tuple(p[:2]) for p in (req.get('points') or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    if req.get('orthogonal', True) is not False:
        for n, ((x1, y1), (x2, y2)) in enumerate(zip(pts, pts[1:]), start=1):
            if abs(x1 - x2) > 1e-3 and abs(y1 - y2) > 1e-3:
                raise BadRequest(
                    'points 第 %d 段是斜线 (%.2f,%.2f)->(%.2f,%.2f)；orthogonal 模式只允许横/竖，'
                    '需要斜线请显式传 orthogonal=false' % (n, x1, y1, x2, y2))
    within = req.get('within')
    if within:
        if not isinstance(within, (list, tuple)) or len(within) != 4:
            raise BadRequest('within 需要 [x, y, w, h]（英寸）')
        wx, wy, ww, wh = (float(v) for v in within)
        for n, (px, py) in enumerate(pts, start=1):
            if not (wx - 1e-6 <= px <= wx + ww + 1e-6 and wy - 1e-6 <= py <= wy + wh + 1e-6):
                raise BadRequest(
                    'points 第 %d 点 (%.2f,%.2f) 跑出 within 矩形 [%.2f,%.2f,%.2f,%.2f]；'
                    '先把走线收进泳道再画' % (n, px, py, wx, wy, ww, wh))
    if len(pts) < 2:
        raise BadRequest('points must include both endpoints and at least 2 points')
    _allow = req.get('allow_off_midpoint') is True
    _approved = req.get('user_approved') is True
    pts[0] = _midpoint_policy(doc, page, src, pts[0], _allow, _approved, '起点')
    pts[-1] = _midpoint_policy(doc, page, dst, pts[-1], _allow, _approved, '终点')
    _cross_allow = req.get('allow_cross_shapes') is True
    _xs = [p[0] for p in pts]
    _ys = [p[1] for p in pts]
    _route_area = max((max(_xs) - min(_xs)) * (max(_ys) - min(_ys)), 0.5)
    for _n, (_p1, _p2) in enumerate(zip(pts, pts[1:]), start=1):
        for _o in doc.shapes(page):
            if _o["connector"] or _o["id"] in (str(src), str(dst)):
                continue
            _ob = _o["bbox"]
            if not (_o.get("text") or "").strip() and _ob["w"] * _ob["h"] > 4 * _route_area:
                continue                      # lane backdrop, not an obstacle
            if _segment_hits_box(_p1[0], _p1[1], _p2[0], _p2[1], _ob, -0.01):
                if _cross_allow and _approved:
                    break
                if _cross_allow and not _approved:
                    raise BadRequest("允许穿图形走线需要先征得用户同意：请在对话里说明理由并得到确认，"
                                     "再同时传 user_approved=true")
                raise BadRequest("走线第 %d 段 (%.2f,%.2f)->(%.2f,%.2f) 穿过形状 #%s；"
                                 "请绕开，或征得用户同意后传 allow_cross_shapes=true + user_approved=true"
                                 % (_n, _p1[0], _p1[1], _p2[0], _p2[1], _o["id"]))

    cid = doc.connect(src, dst, page,
                      label=text(req.get('label'), 'label', 200),
                      line_width=req.get('line_width'),
                      line_color=req.get('line_color') or '#17365D',
                      line_pattern=req.get('line_pattern'),
                      from_port=_point(req, 'from_port'), to_port=_point(req, 'to_port'))
    doc.save(backup=False)
    d2 = load_doc(path)
    d2.set_route(cid, pts, page=page)
    placed = _place_label(d2, cid, page, req.get('label_pos'),
                           text(req.get('label'), 'label', 200), pts, list(d2.shapes(page)))
    if req.get('text_bg'):
        # White plate behind the connector label so it never merges with the line.
        d2.set_cells(cid, {'TextBkgnd': 1}, page=page)
    d2.save(backup=False)
    return {'ok': True, 'connector': cid, 'points': len(pts),
            'line_color': req.get('line_color') or '#17365D',
            'dashed': req.get('line_pattern') == 2, 'label_at': placed,
            'ends': {'from': [round(pts[0][0], 3), round(pts[0][1], 3)],
                     'to': [round(pts[-1][0], 3), round(pts[-1][1], 3)]}}
def _place_label(doc, cid, page, mode, label, pts, shapes):
    """Put a connector label where the caller asked, nudging it off other boxes."""
    if not label or mode in (None, '', 'auto'):
        return None
    try:
        cur = doc.label_point(cid, page)
    except Exception:
        cur = None
    if not cur:
        mid = pts[len(pts) // 2]
        cur = (mid[0], mid[1])
    span = max(zip(pts, pts[1:]), key=lambda seg: abs(seg[0][0] - seg[1][0]) + abs(seg[0][1] - seg[1][1]))
    (ax, ay), (bx, by) = span
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    if isinstance(mode, (list, tuple)) and len(mode) >= 2:
        target = (float(mode[0]), float(mode[1]))
        step = (0.0, 0.14)
    else:
        offset = {'above': (0, 0.17), 'below': (0, -0.17), 'left': (-0.17, 0), 'right': (0.17, 0)}
        if mode not in offset:
            raise BadRequest("label_pos must be auto/above/below/left/right or [x,y]")
        target = (mx + offset[mode][0], my + offset[mode][1])
        step = (offset[mode][0] * 0.8, offset[mode][1] * 0.8)
    w = max(0.5, 0.095 * len(label))
    h = 0.18

    def hits(tx, ty):
        for s in shapes:
            if s['connector']:
                continue
            b = s['bbox']
            if (tx - w / 2 < b['x'] + b['w'] and tx + w / 2 > b['x']
                    and ty - h / 2 < b['y'] + b['h'] and ty + h / 2 > b['y']):
                return True
        return False

    tx, ty = target
    for _ in range(3):
        if not hits(tx, ty):
            break
        tx += step[0]
        ty += step[1]
    doc.move_label(cid, dx=tx - cur[0], dy=ty - cur[1], page=page)
    return {'x': round(tx, 3), 'y': round(ty, 3)}


def action_add_anchor(req):
    """Invisible 0.02in anchor just outside one side of a shape.

    Hand-routed connectors glue to the anchor instead of to the shape, so the
    arrowhead stops on the border instead of heading for the shape centre.
    """
    path = drawing_path(req.get('path'))
    doc = load_doc(path)
    page = page_of(req.get('page'), doc.pages)
    sid = text(req.get('shape_id'), 'shape_id', 40)
    side = (text(req.get('side'), 'side', 10) or 'top').lower()
    if side not in ('top', 'bottom', 'left', 'right'):
        raise BadRequest('side must be top / bottom / left / right')
    gap = number(req.get('gap') if req.get('gap') is not None else 0.02, 'gap')
    box = None
    for s in doc.shapes(page):
        if s['id'] == sid:
            box = s['bbox']
            break
    if box is None:
        raise BadRequest('unknown shape id: %s' % sid)
    cx, cy = box['x'] + box['w'] / 2.0, box['y'] + box['h'] / 2.0
    point = {'top': (cx, box['y'] + box['h'] + gap),
             'bottom': (cx, box['y'] - gap),
             'left': (box['x'] - gap, cy),
             'right': (box['x'] + box['w'] + gap, cy)}[side]
    aid = doc.add_shape(page=page, x=point[0] - 0.01, y=point[1] - 0.01,
                        w=0.02, h=0.02, text='', kind='text')
    save_doc(doc, req.get('backup', True))
    return {'ok': True, 'anchor': aid, 'shape': sid, 'side': side,
            'x': point[0], 'y': point[1]}


def action_swimlane(req):
    """Wrap a row of existing shapes in a lane band with a header.

    The band is sized from the nodes (pad_x / pad_bottom / head), pushed behind
    them, and the title/owner text is placed on the header line - so a lane can
    never end up shorter than the nodes it holds.
    """
    path = drawing_path(req.get('path'))
    doc = load_doc(path)
    page = page_of(req.get('page'), doc.pages)
    ids = [str(x) for x in (req.get('nodes') or [])]
    if not ids:
        raise BadRequest('nodes needs at least one shape id')
    by_id = {s['id']: s for s in doc.shapes(page)}
    missing = [x for x in ids if x not in by_id]
    if missing:
        raise BadRequest('unknown shape ids: %s' % ', '.join(missing))
    boxes = [by_id[x]['bbox'] for x in ids]
    pad_x = number(req.get('pad_x') if req.get('pad_x') is not None else 0.45, 'pad_x')
    pad_b = number(req.get('pad_bottom') if req.get('pad_bottom') is not None else 0.30, 'pad_bottom')
    head = number(req.get('head') if req.get('head') is not None else 0.42, 'head')
    x0 = min(b['x'] for b in boxes) - pad_x
    x1 = max(b['x'] + b['w'] for b in boxes) + pad_x
    y0 = min(b['y'] for b in boxes) - pad_b
    y1 = max(b['y'] + b['h'] for b in boxes) + head
    lane = doc.add_shape(page=page, x=x0, y=y0, w=x1 - x0, h=y1 - y0, text='', kind='rect',
                         fill=text(req.get('fill'), 'fill', 20) or '#EDF2F9',
                         line=text(req.get('line'), 'line', 20) or '#D6DEE9')
    doc.send_to_back(lane, page)
    title = text(req.get('title'), 'title', 80)
    if title:
        doc.add_shape(page=page, x=x0 + 0.18, y=y1 - 0.30, w=max(1.2, 0.13 * len(title)), h=0.22,
                      text=title, kind='text', font_color='#1F3864',
                      font_size=number(req.get('title_size') or 11, 'title_size'), bold=True)
    owner = text(req.get('owner'), 'owner', 160)
    if owner:
        doc.add_shape(page=page, x=x0 + 0.18 + (max(1.2, 0.13 * len(title)) + 0.35 if title else 0.0),
                      y=y1 - 0.30, w=max(1.4, 0.075 * len(owner)), h=0.22, text=owner, kind='text',
                      font_color='#7F7F7F', font_size=8.5)
    save_doc(doc, req.get('backup', True))
    return {'ok': True, 'lane': lane, 'bounds': [round(x0, 3), round(y0, 3), round(x1 - x0, 3), round(y1 - y0, 3)],
            'nodes': ids, 'note': 'lane pushed behind the nodes; title sits on the header line'}


def action_set_route(req):
    """Replace the connector's polyline with an explicit list of points."""
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    raw = req.get("points") or []
    points = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            points.append((number(item[0], "x"), number(item[1], "y")))
        elif isinstance(item, dict):
            points.append((number(item.get("x"), "x"), number(item.get("y"), "y")))
    if len(points) < 2:
        raise BadRequest("points must contain at least two [x, y] pairs")
    doc.set_route(sid, points, page=page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="走线已更新", saved=True)


def action_clear_route(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    doc.clear_route(sid, page=page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="已恢复自动走线", saved=True)


def action_route_style(req):
    """One-click detour for a connector: up, down, left, right, or auto."""
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    style = text(req.get("style"), "style", 10) or "auto"
    doc.route_style(sid, style, page=page)
    save_doc(doc, req.get("backup", True))
    notice = "已恢复自动走线" if style == "auto" else "走线已改为%s" % style
    return build_state(path, page, sid, notice=notice, saved=True)


def action_move_segment(req):
    """Slide one segment of a connector (Visio-style segment drag)."""
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    index = int(number(req.get("index") or 0, "index"))
    delta = number(req.get("delta"), "delta")
    doc.move_segment(sid, index, delta, page=page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="走线已调整", saved=True)


def action_move_endpoint(req):
    """Move one connector end to an exact point (free drag, no glue hunt)."""
    path = drawing_path(req.get('path'))
    doc = load_doc(path)
    page = page_of(req.get('page'), doc.pages)
    sid = text(req.get('shape_id'), 'shape_id', 40)
    end = (text(req.get('end'), 'end', 10) or 'end').lower()
    if end in ('begin', 'from'):
        end = 'start'
    if end == 'to':
        end = 'end'
    if end not in ('start', 'end'):
        raise BadRequest("end must be start or end")
    x = number(req.get('x'), 'x')
    y = number(req.get('y'), 'y')
    doc.move_endpoint(sid, end, x, y, page)
    save_doc(doc, req.get('backup', True))
    return build_state(path, page, sid, notice="端点已移动", saved=True)


def action_set_end_direction(req):
    """Point one connector end at a chosen side of the shape it is glued to."""
    path = drawing_path(req.get('path'))
    doc = load_doc(path)
    page = page_of(req.get('page'), doc.pages)
    sid = text(req.get('shape_id'), 'shape_id', 40)
    end = (text(req.get('end'), 'end', 10) or 'end').lower()
    if end in ('begin', 'from'):
        end = 'start'
    if end == 'to':
        end = 'end'
    direction = (text(req.get('direction'), 'direction', 10) or 'top').lower()
    try:
        doc.set_end_direction(sid, end, direction, page)
    except VsdxError as error:
        raise BadRequest(str(error))
    save_doc(doc, req.get('backup', True))
    return build_state(path, page, sid, notice="端点方向已调整", saved=True)


def action_reglue(req):
    """Re-attach one end of a connector (drag an end handle onto another shape)."""
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    sid = text(req.get("shape_id"), "shape_id", 40)
    end = text(req.get("end"), "end", 10) or "end"
    to = text(req.get("to"), "to", 40)
    if not to:
        raise BadRequest("to is required")
    doc.reglue(sid, end, to, x=req.get("x"), y=req.get("y"), page=page)
    save_doc(doc, req.get("backup", True))
    return build_state(path, page, sid, notice="端点已重新连接", saved=True)


ACTIONS = {
    "ping": action_ping,
    "list": action_list,
    "create": action_create,
    "open": action_open,
    "render": action_open,
    "svg": action_svg,
    "undo": action_undo,
    "stencils": action_stencil_list,
    "stencil_add": action_stencil_add,
    "kinds": action_shape_kinds,
    "redo": action_redo,
    "stat": action_stat,
    "text": action_text,
    "get_shape": action_get_shape,
    "set_text": action_set_text,
    "set_cells": action_set_cells,
    "move": action_move,
    "set_prop": action_set_prop,
    "add_shape": action_add_shape,
    "shape_list": action_shape_list,
    "guide": action_guide,
    "align": action_align,
    "audit_full": action_audit_full,
    "shape_save": action_shape_save,
    "add_line": action_add_line,
    "set_line": action_set_line,
    "connect": action_connect,
    "connect_styled": action_connect_styled,
    "add_anchor": action_add_anchor,
    "swimlane": action_swimlane,
    "probe": action_probe,
    "bend": action_bend,
    "move_segment": action_move_segment,
    "reglue": action_reglue,
    "set_end_direction": action_set_end_direction,
    "move_endpoint": action_move_endpoint,
    "route_style": action_route_style,
    "set_route": action_set_route,
    "clear_route": action_clear_route,
    "duplicate": action_duplicate,
    "delete": action_delete,
    "normalize": action_normalize,
    "export": action_export,
    "move_label": action_move_label,
    "validate": action_validate,
    "stencil_info": action_stencil_info,
    "stencil_sheet": action_stencil_sheet,
    "snapshot": action_snapshot,
    "capabilities": action_capabilities,
}


def handle(request) -> dict:
    action = request.get("action")
    handler = ACTIONS.get(action)
    if handler is None:
        raise BadRequest("unknown action: %s" % action)
    return handler(request)


def serve() -> int:
    """Line-oriented daemon: one JSON request per line, one JSON reply per line."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise BadRequest("request must be a JSON object")
            result = handle(request)
        except (BadRequest, VsdxError) as exc:
            result = {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
                      "trace": traceback.format_exc(limit=6)}
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    if "--serve" in sys.argv[1:]:
        return serve()
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise BadRequest("empty request")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise BadRequest("request must be a JSON object")
        result = handle(request)
    except (BadRequest, VsdxError) as exc:
        result = {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - report, never crash the host
        result = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
                  "trace": traceback.format_exc(limit=6)}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
