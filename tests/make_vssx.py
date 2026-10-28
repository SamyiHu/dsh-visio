# -*- coding: utf-8 -*-
"""Build a small but valid .vssx stencil (rect / diamond / arrow) for tests and demos."""
import os
import zipfile

NS = 'xmlns="http://schemas.microsoft.com/office/visio/2012/main"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Override PartName="/visio/masters/masters.xml" ContentType="application/vnd.ms-visio.masters+xml"/>
{overrides}
<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
</Types>"""

MASTERS = """<?xml version="1.0" encoding="UTF-8"?>
<Masters {ns} {rns}>
{items}
</Masters>"""

MASTER_ITEM = ('<Master ID="{id}" NameU="{name}" Name="{name}" Prompt="{prompt}" Icon="1">'
               '<PageSheet><Cell N="PageWidth" V="8.5"/><Cell N="PageHeight" V="11"/></PageSheet>'
               '<Rel r:id="rId{id}"/></Master>')

MASTER_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/master" Target="master1.xml"/>
<Relationship Id="rId2" Type="http://schemas.microsoft.com/visio/2010/relationships/master" Target="master2.xml"/>
<Relationship Id="rId3" Type="http://schemas.microsoft.com/visio/2010/relationships/master" Target="master3.xml"/>
</Relationships>"""

MASTER_PART = """<?xml version="1.0" encoding="UTF-8"?>
<MasterContents {ns}>
<Shapes>
<Shape ID="1" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0" NameU="{name}">
<Cell N="PinX" V="{w2}"/><Cell N="PinY" V="{h2}"/>
<Cell N="Width" V="{w}"/><Cell N="Height" V="{h}"/>
<Cell N="LocPinX" V="{w2}"/><Cell N="LocPinY" V="{h2}"/>
<Cell N="FillForegnd" V="#DCE6F5"/><Cell N="LineColor" V="#355694"/>
<Cell N="LineWeight" V="0.0104"/>
<Section N="Geometry" IX="0">
{rows}
</Section>
<Text>{name}</Text>
</Shape>
</Shapes>
</MasterContents>"""

SHAPES = {
    "Rectangle": (1.5, 1.0, [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
    "Diamond": (1.2, 1.2, [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5), (0.5, 0)]),
    "Arrow Right": (1.6, 0.8, [(0, 0.25), (0.6, 0.25), (0.6, 0), (1, 0.5), (0.6, 1), (0.6, 0.75), (0, 0.75), (0, 0.25)]),
}
PROMPTS = {
    "Rectangle": "Process step",
    "Diamond": "Decision",
    "Arrow Right": "Direction indicator",
}


def build(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        overrides = "\n".join(
            '<Override PartName="/visio/masters/master%d.xml" '
            'ContentType="application/vnd.ms-visio.master+xml"/>' % i for i in (1, 2, 3))
        zf.writestr("[Content_Types].xml", CONTENT_TYPES.format(overrides=overrides))
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                   '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/masters" Target="visio/masters/masters.xml"/></Relationships>')
        items, idx = [], 1
        for name, (w, h, pts) in SHAPES.items():
            items.append(MASTER_ITEM.format(id=idx, name=name, prompt=PROMPTS[name]))
            rows = []
            for i, (x, y) in enumerate(pts):
                rows.append('<Row T="%s" IX="%d"><Cell N="X" V="%s"/><Cell N="Y" V="%s"/></Row>'
                            % ("MoveTo" if i == 0 else "LineTo", i, round(x * w, 6), round(y * h, 6)))
            zf.writestr("visio/masters/master%d.xml" % idx,
                        MASTER_PART.format(ns=NS, name=name, w=w, h=h, w2=w / 2, h2=h / 2, rows="".join(rows)))
            idx += 1
        zf.writestr("visio/masters/masters.xml", MASTERS.format(ns=NS, rns=RNS, items="".join(items)))
        zf.writestr("visio/masters/_rels/masters.xml.rels", MASTER_RELS)
        zf.writestr("visio/document.xml", '<?xml version="1.0"?><VisioDocument %s/>' % NS)


if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "basic-shapes.vssx")
    build(target)
    print("wrote", target)
