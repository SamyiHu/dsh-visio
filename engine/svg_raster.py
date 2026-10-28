# -*- coding: utf-8 -*-
"""Rasterise the SVG our own renderer emits.

The panel shows `Vsdx.to_svg()`; if the PNG export used a second, independent
drawing routine the two would drift apart (different corners, no arrow heads,
different text metrics).  So the PNG path takes the very same SVG string and
paints it with Pillow.  Only the element subset we emit is supported.
"""
from __future__ import annotations

import math
import re

from PIL import Image, ImageDraw, ImageFont

TEXT_RE = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)" font-size="([\d.]+)" fill="([^"]+)"([^>]*)>([^<]*)</text>')
PATH_RE = re.compile(r'<path d="([^"]+)"([^/]*)/>')
RECT_RE = re.compile(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"([^/]*)/>')
NUM = re.compile(r"-?\d+\.?\d*")

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _font(px):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, max(4, int(px)))
        except OSError:
            continue
    return ImageFont.load_default()


def _attr(rest, name, default=None):
    found = re.search(r'%s="([^"]+)"' % name, rest)
    return found.group(1) if found else default


def rasterize(svg: str, scale: float = 1.0, background: str = "#FFFFFF"):
    view = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', svg)
    if not view:
        raise ValueError("svg has no viewBox")
    vx, vy, vw, vh = (float(g) for g in view.groups())
    width, height = int(vw * scale), int(vh * scale)
    img = Image.new("RGB", (max(1, width), max(1, height)), background)
    draw = ImageDraw.Draw(img)

    body = svg.split("</defs>", 1)[1] if "</defs>" in svg else svg
    tx = lambda x: (float(x) - vx) * scale
    ty = lambda y: (float(y) - vy) * scale

    for m in RECT_RE.finditer(body):
        x, y, w, h, rest = m.groups()
        fill = _attr(rest, "fill", "none")
        stroke = _attr(rest, "stroke", "none")
        box = [tx(x), ty(y), tx(float(x) + float(w)), ty(float(y) + float(h))]
        if fill not in ("none", "transparent"):
            draw.rectangle(box, fill=fill)
        if stroke not in ("none", "transparent"):
            draw.rectangle(box, outline=stroke, width=max(1, int(round(float(_attr(rest, "stroke-width", 0.01)) * scale))))

    for m in PATH_RE.finditer(body):
        d, rest = m.groups()
        fill = _attr(rest, "fill", "none")
        stroke = _attr(rest, "stroke", "none")
        if fill == "none" and stroke in ("none", "transparent"):
            continue
        nums = [float(n) for n in NUM.findall(d)]
        pts = [(tx(nums[i]), ty(nums[i + 1])) for i in range(0, len(nums) - 1, 2)]
        if len(pts) < 2:
            continue
        closed = d.rstrip().endswith("Z")
        if fill not in ("none", "transparent") and (closed or len(pts) > 2):
            draw.polygon(pts, fill=fill)
        if stroke not in ("none", "transparent"):
            width_attr = _attr(rest, "stroke-width", "0.01")
            if "non-scaling-stroke" in rest:
                wpx = max(1, int(round(float(width_attr))))
            else:
                wpx = max(1, int(round(float(width_attr) * scale)))
            draw.line(pts, fill=stroke, width=wpx, joint="curve")
        if "marker-end" in rest:
            (ax, ay), (bx, by) = pts[-2], pts[-1]
            angle = math.atan2(by - ay, bx - ax)
            size = max(4.0, 0.055 * scale)
            draw.polygon([
                (bx, by),
                (bx - size * math.cos(angle - 0.42), by - size * math.sin(angle - 0.42)),
                (bx - size * math.cos(angle + 0.42), by - size * math.sin(angle + 0.42)),
            ], fill=stroke)

    for m in TEXT_RE.finditer(body):
        x, y, size, color, rest, raw = m.groups()
        text = (raw.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&apos;", "'"))
        px = float(size) * scale
        font = _font(px)
        weight = _attr(rest, "font-weight", "")
        if weight in ("600", "700", "bold"):
            try:
                font = ImageFont.truetype(FONT_CANDIDATES[1], max(4, int(px)))
            except OSError:
                pass
        box = draw.textbbox((0, 0), text, font=font)
        text_w = box[2] - box[0]
        anchor = _attr(rest, "text-anchor", "start")
        left = tx(x) - (text_w / 2.0 if anchor == "middle" else (text_w if anchor == "end" else 0))
        draw.text((left, ty(y) - px * 0.52), text, fill=color, font=font)

    return img
