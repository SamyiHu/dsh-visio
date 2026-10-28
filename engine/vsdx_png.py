"""vsdx_png - optional Pillow-based PNG preview for .vsdx pages.

Pillow is the only third-party dependency of this skill and only this module uses it;
everything else runs on the standard library.
"""
from __future__ import annotations

import os

from vsdx_core import Vsdx, VsdxError

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    """Character wrap for CJK, word wrap for ASCII runs."""
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        tokens, buf = [], ""
        for ch in para:
            if ch.isascii() and not ch.isspace():
                buf += ch
            else:
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(ch)
        if buf:
            tokens.append(buf)
        cur = ""
        for tok in tokens:
            trial = cur + tok
            if draw.textlength(trial, font=font) <= max_w or not cur:
                cur = trial
            else:
                if tok.isspace():
                    lines.append(cur)
                    cur = ""
                else:
                    lines.append(cur.rstrip())
                    cur = tok.lstrip() if tok.isspace() else tok
        lines.append(cur)
    return lines


def render_png(path: str, page: int = 1, out_path: str = None, dpi: int = 96,
               scale: float = 2.0, show_ids: bool = False, grid: bool = False) -> str:
    from PIL import Image, ImageDraw

    doc = Vsdx(path)
    meta = doc.pages[page - 1]
    W = int(meta["width"] * dpi * scale)
    H = int(meta["height"] * dpi * scale)
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    if grid:
        step = 0.25 * dpi * scale
        major = 4 * step
        x = 0.0
        while x < W:
            shade = (226, 230, 236) if abs((x / major) - round(x / major)) < 0.02 else (241, 243, 246)
            draw.line([(x, 0), (x, H)], fill=shade)
            x += step
        y = 0.0
        while y < H:
            shade = (226, 230, 236) if abs((y / major) - round(y / major)) < 0.02 else (241, 243, 246)
            draw.line([(0, y), (W, y)], fill=shade)
            y += step
    k = dpi * scale  # pixels per inch

    def px(x, y):
        return (x * k, (meta["height"] - y) * k)

    shapes = doc.shapes(page)
    for s in shapes:
        if s["connector"] or s["depth"] != 0:
            continue
        bb = s["bbox"]
        if bb["w"] <= 0 or bb["h"] <= 0:
            continue
        x0, y0 = px(bb["x"], bb["y"] + bb["h"])
        x1, y1 = px(bb["x"] + bb["w"], bb["y"])
        st = doc.style(s["id"], page)
        fill = st.get("fill") or "#FFFFFF"
        stroke = st.get("line") or "#404040"
        text_color = st.get("text") or (st.get("theme") or {}).get("dk1") or "#1A1A1A"
        fontsize = st.get("font_pt")
        if not fontsize:
            nlines = max(1, s["text"].count("\n") + 1) if s["text"] else 1
            fontsize = max(0.06, min(0.25, bb["h"] / (nlines + 1.6))) * 72.0
        line_w = max(1, int(round((st.get("weight_in") or 0.0104) * k)))
        master = (s.get("master") or "").lower()
        has_geometry = bool(s["geometry"])
        if not has_geometry:
            # Text-only shape: no box of its own (matches the SVG renderer).
            pass
        elif any("Ellipse" in g for g in s["geometry"]):
            draw.ellipse([x0, y0, x1, y1], fill=fill, outline=stroke, width=line_w)
        elif "decision" in master:
            pts = [((x0 + x1) // 2, y0), (x1, (y0 + y1) // 2), ((x0 + x1) // 2, y1), (x0, (y0 + y1) // 2)]
            draw.polygon(pts, fill=fill, outline=stroke)
            draw.line(pts + [pts[0]], fill=stroke, width=line_w)
        elif "process" in master:
            draw.rounded_rectangle([x0, y0, x1, y1], radius=max(4, (x1 - x0) // 12), fill=fill, outline=stroke, width=line_w)
        else:
            draw.rectangle([x0, y0, x1, y1], fill=fill, outline=stroke, width=line_w)
        if s["text"]:
            segs = []
            try:
                segs = doc.text_segments(s["id"], page)
            except Exception:
                segs = []
            if not segs:
                segs = [{"text": s["text"], "color": None, "pt": fontsize, "bold": False}]
            maxw = max(10, (x1 - x0) - int(6 * scale))
            boxh = (y1 - y0) - int(4 * scale)
            lines = [[]]
            for seg in segs:
                parts = seg["text"].split("\n")
                for i, part in enumerate(parts):
                    if i:
                        lines.append([])
                    if part:
                        lines[-1].append({"text": part, "color": seg["color"], "pt": seg["pt"], "bold": seg["bold"]})
            def seg_font(pt):
                fs_ = int(round((pt or fontsize or 10) / 72.0 * k))
                return _font(max(int(6 * scale), fs_))
            def line_width(line, factor=1.0):
                w = 0
                for sg in line:
                    w += draw.textlength(sg["text"], font=seg_font((sg["pt"] or 10) * factor))
                return w
            widest = max([line_width(l) for l in lines if l] or [0])
            factor = 1.0
            if widest > maxw:
                factor = maxw / widest
            heights = []
            for line in lines:
                pt = max([(sg["pt"] or fontsize or 10) * factor for sg in line] or [10])
                heights.append(int(round(pt / 72.0 * k * 1.25)))
            total = sum(heights)
            ty = (y0 + y1) // 2 - total // 2
            for line, lh in zip(lines, heights):
                if not line:
                    ty += lh
                    continue
                wsum = line_width(line, factor)
                tx = (x0 + x1) // 2 - wsum / 2
                for sg in line:
                    f = seg_font((sg["pt"] or fontsize or 10) * factor)
                    col = sg["color"] or text_color
                    draw.text((tx, ty), sg["text"], font=f, fill=col)
                    tx += draw.textlength(sg["text"], font=f)
                ty += lh
        if show_ids:
            f = _font(max(9, int(8 * scale)))
            draw.text((x0 + 2, y0 - int(10 * scale)), "#%s" % s["id"], font=f, fill="#C0392B")

    for s in shapes:
        if not s["connector"]:
            continue
        det = doc.shape(s["id"], page)
        c = det["cells"]
        try:
            bx, by = float(c["BeginX"]), float(c["BeginY"])
            ex, ey = float(c["EndX"]), float(c["EndY"])
        except (KeyError, TypeError, ValueError):
            continue
        st = doc.style(s["id"], page)
        pts = doc.geometry_points(s["id"], page)
        if len(pts) >= 2:
            poly = [px(px_, py_) for px_, py_ in pts]
        else:
            poly = [px(bx, by), px(ex, ey)]
        line_color = st.get("line") or "#404040"
        conn_w = max(1, int(round((st.get("weight_in") or 0.0104) * k)))
        draw.line(poly, fill=line_color, width=conn_w, joint="curve")
        # arrow head at the end of the connector
        if len(poly) >= 2 and str(st.get("end_arrow") or "0") not in ("0", "None"):
            import math
            (ax_, ay_), (bx_, by_) = poly[-2], poly[-1]
            ang = math.atan2(by_ - ay_, bx_ - ax_)
            alen = max(6 * scale, int(round(conn_w * 5)))
            pts_arrow = [
                (bx_, by_),
                (bx_ - alen * math.cos(ang - 0.32), by_ - alen * math.sin(ang - 0.32)),
                (bx_ - alen * math.cos(ang + 0.32), by_ - alen * math.sin(ang + 0.32)),
            ]
            draw.polygon(pts_arrow, fill=line_color)
        label = s["text"]
        if label:
            f = _font(max(int(7 * scale), int(8 * scale)))
            lines = label.split("\n")
            widths = [draw.textlength(l, font=f) for l in lines]
            bw = max(widths) + int(6 * scale)
            bh = int(len(lines) * 10 * scale)
            lp = doc.label_point(s["id"], page)
            if lp:
                mx, my = px(lp[0], lp[1])
            else:
                mx = sum(p[0] for p in poly) // len(poly)
                my = sum(p[1] for p in poly) // len(poly)
            draw.rectangle([mx - bw / 2, my - bh / 2, mx + bw / 2, my + bh / 2], fill="white")
            for i, l in enumerate(lines):
                draw.text((mx - widths[i] / 2, my - bh / 2 + i * int(10 * scale)), l, font=f, fill=st.get("text") or "#1A1A1A")

    out_path = out_path or (os.path.splitext(path)[0] + ".png")
    img.save(out_path)
    return out_path
