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

ENGINE_VERSION = "1.0.0"
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
    file = text(req.get("file"), "file", 1000).strip()
    master = text(req.get("master"), "master", 40).strip()
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    new_id = stencil.import_master(doc, file, master)
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
    for key in ("x", "y", "w", "h"):
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


def action_add_shape(req):
    path = drawing_path(req.get("path"))
    doc = load_doc(path)
    page = page_of(req.get("page"), doc.pages)
    import kinds
    kind = text(req.get("kind"), "kind", 24) or "rect"
    if kind not in kinds.KINDS:
        raise BadRequest("unknown kind %s; known: %s" % (kind, ", ".join(sorted(kinds.KINDS))))
    sid = doc.add_shape(
        page=page,
        x=number(req.get("x", 1.0), "x"),
        y=number(req.get("y", 1.0), "y"),
        w=number(req.get("w", 1.6), "w"),
        h=number(req.get("h", 0.8), "h"),
        text=text(req.get("text"), "text", 4000),
        kind=kind,
        fill=text(req.get("fill"), "fill", 20) or None,
        line=text(req.get("line"), "line", 20) or None,
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
    sid = doc.connect(src, dst, page, label=text(req.get("label"), "label", 500))
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
        from vsdx_png import render_png
        out = out or os.path.splitext(path)[0] + ".png"
        render_png(path, page, out, show_ids=bool(req.get("show_ids")), grid=bool(req.get("grid")))
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


def _point_in_box(x, y, box, pad=0.0):
    return (box["x"] - pad) <= x <= (box["x"] + box["w"] + pad) and \
           (box["y"] - pad) <= y <= (box["y"] + box["h"] + pad)


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
    "connect": action_connect,
    "delete": action_delete,
    "normalize": action_normalize,
    "export": action_export,
    "validate": action_validate,
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
