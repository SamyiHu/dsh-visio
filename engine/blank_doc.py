"""blank_doc - build a new, empty Visio .vsdx drawing from scratch.

The package follows the Visio 2013+ OOXML layout (OPC zip):
  [Content_Types].xml, _rels/.rels, visio/document.xml, visio/pages/pages.xml,
  visio/pages/page1.xml, visio/windows.xml and docProps/*.
No master, theme or thumbnail parts are written: the drawing starts from the
built-in "No Style" sheet, so every shape created later carries its own cells.
"""
from __future__ import annotations

import os
import zipfile
from datetime import datetime, timezone

VISIO_NS = "http://schemas.microsoft.com/office/visio/2012/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>
<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>
<Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/>
<Relationship Id="rId2" Type="http://schemas.microsoft.com/visio/2010/relationships/windows" Target="windows.xml"/>
</Relationships>
"""

PAGES_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/>
</Relationships>
"""

STYLE_SHEET_CELLS = (
    ("EnableLineProps", "1"), ("EnableFillProps", "1"), ("EnableTextProps", "1"), ("HideForApply", "0"),
    ("LineWeight", "0.01041666666666667"), ("LineColor", "0"), ("LinePattern", "1"), ("Rounding", "0"),
    ("EndArrowSize", "2"), ("BeginArrow", "0"), ("EndArrow", "0"), ("LineCap", "0"),
    ("BeginArrowSize", "2"), ("LineColorTrans", "0"), ("CompoundType", "0"),
    ("FillForegnd", "1"), ("FillBkgnd", "0"), ("FillPattern", "1"), ("ShdwForegnd", "0"), ("ShdwPattern", "0"),
    ("FillForegndTrans", "0"), ("FillBkgndTrans", "0"), ("ShdwForegndTrans", "0"),
    ("LeftMargin", "0"), ("RightMargin", "0"), ("TopMargin", "0"), ("BottomMargin", "0"),
    ("VerticalAlign", "1"), ("TextBkgnd", "0"), ("DefaultTabStop", "0.5"), ("TextDirection", "0"), ("TextBkgndTrans", "0"),
    ("LockTextEdit", "0"), ("LockFormat", "0"), ("LockMoveX", "0"), ("LockMoveY", "0"), ("LockAspect", "0"),
    ("LockDelete", "0"), ("LockBegin", "0"), ("LockEnd", "0"), ("LockRotate", "0"), ("LockCrop", "0"),
    ("LockVtxEdit", "0"), ("LockNoSelect", "0"),
)


def _document_xml() -> str:
    cells = "".join('<Cell N="%s" V="%s"/>' % (name, value) for name, value in STYLE_SHEET_CELLS)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<VisioDocument xmlns="%s" xmlns:r="%s" xml:space="preserve">'
        '<DocumentSettings TopPage="0" DefaultTextStyle="0" DefaultLineStyle="0" DefaultFillStyle="0" DefaultGuideStyle="0">'
        '<GlueSettings>9</GlueSettings><SnapSettings>65847</SnapSettings><SnapExtensions>34</SnapExtensions><SnapAngles/>'
        '<DynamicGridEnabled>1</DynamicGridEnabled><ProtectStyles>0</ProtectStyles><ProtectShapes>0</ProtectShapes>'
        '<ProtectMasters>0</ProtectMasters><ProtectBkgnds>0</ProtectBkgnds></DocumentSettings>'
        '<Colors><ColorEntry IX="0" RGB="#000000"/><ColorEntry IX="1" RGB="#FFFFFF"/>'
        '<ColorEntry IX="24" RGB="#7F7F7F"/><ColorEntry IX="25" RGB="#FFFFFF"/></Colors>'
        '<FaceNames><FaceName NameU="Calibri" UnicodeRanges="-469750017 -1073732485 9 0" CharSets="536871423 0" '
        'Panose="2 15 5 2 2 2 4 3 2 4" Flags="325"/></FaceNames>'
        '<StyleSheets><StyleSheet ID="0" NameU="No Style" IsCustomNameU="1" Name="No Style" IsCustomName="1">%s</StyleSheet></StyleSheets>'
        '</VisioDocument>' % (VISIO_NS, REL_NS, cells)
    )


def _pages_xml(page_name: str, width: float, height: float) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Pages xmlns="%s" xmlns:r="%s" xml:space="preserve">'
        '<Page ID="0" NameU="%s" Name="%s" ViewScale="-1" ViewCenterX="%0.4f" ViewCenterY="%0.4f">'
        '<PageSheet LineStyle="0" FillStyle="0" TextStyle="0">'
        '<Cell N="PageWidth" V="%0.6f"/><Cell N="PageHeight" V="%0.6f"/>'
        '<Cell N="ShdwOffsetX" V="0.1181102362204724"/><Cell N="ShdwOffsetY" V="-0.1181102362204724"/>'
        '<Cell N="PageScale" V="0.03937007874015748" U="MM"/><Cell N="DrawingScale" V="0.03937007874015748" U="MM"/>'
        '<Cell N="DrawingSizeType" V="0"/><Cell N="DrawingScaleType" V="0"/><Cell N="InhibitSnap" V="0"/>'
        '<Cell N="PageLockReplace" V="0" U="BOOL"/><Cell N="PageLockDuplicate" V="0" U="BOOL"/>'
        '<Cell N="UIVisibility" V="0"/><Cell N="ShdwType" V="0"/><Cell N="ShdwObliqueAngle" V="0"/>'
        '<Cell N="ShdwScaleFactor" V="1"/><Cell N="DrawingResizeType" V="1"/><Cell N="PageShapeSplit" V="1"/>'
        '<Section N="Layer"><Row IX="0"><Cell N="Name" V="Connector"/><Cell N="Color" V="255"/>'
        '<Cell N="Status" V="0"/><Cell N="Visible" V="1"/><Cell N="Print" V="1"/><Cell N="Active" V="0"/>'
        '<Cell N="Lock" V="0"/><Cell N="Snap" V="1"/><Cell N="Glue" V="1"/><Cell N="NameUniv" V="Connector"/>'
        '<Cell N="ColorTrans" V="0"/></Row></Section></PageSheet><Rel r:id="rId1"/></Page></Pages>'
        % (VISIO_NS, REL_NS, page_name, page_name, width / 2.0, height / 2.0, width, height)
    )


def _windows_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Windows xmlns="%s" ClientWidth="1600" ClientHeight="900">'
        '<Window ID="0" WindowType="Drawing" WindowState="1073741824" WindowLeft="0" WindowTop="0" '
        'WindowWidth="1600" WindowHeight="900" ContainerType="Page" Page="0" ViewScale="-1" '
        'ViewCenterX="4.25" ViewCenterY="5.5"/></Windows>' % VISIO_NS
    )


def _core_xml(title: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>%s</dc:title><dc:creator>DSH Visio</dc:creator>'
        '<cp:lastModifiedBy>DSH Visio</cp:lastModifiedBy>'
        '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
        '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
        '</cp:coreProperties>' % (safe, now, now)
    )


APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Microsoft Visio</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>
<Template/><Manager/><Company/><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc>
<HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion></Properties>
"""


def create(path: str, width: float = 11.0, height: float = 8.5, page_name: str = "Page-1",
           title: str = "") -> str:
    """Write a new .vsdx with one empty page. `width`/`height` are inches."""
    width = float(width)
    height = float(height)
    if not (0.5 <= width <= 200 and 0.5 <= height <= 200):
        raise ValueError("page size out of range")
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        raise ValueError("folder does not exist: %s" % folder)
    parts = [
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", ROOT_RELS),
        ("visio/document.xml", _document_xml()),
        ("visio/_rels/document.xml.rels", DOCUMENT_RELS),
        ("visio/pages/pages.xml", _pages_xml(page_name or "Page-1", width, height)),
        ("visio/pages/_rels/pages.xml.rels", PAGES_RELS),
        ("visio/pages/page1.xml",
         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
         '<PageContents xmlns="%s" xmlns:r="%s" xml:space="preserve"><Shapes/></PageContents>'
         % (VISIO_NS, REL_NS)),
        ("visio/windows.xml", _windows_xml()),
        ("docProps/core.xml", _core_xml(title or os.path.splitext(os.path.basename(path))[0])),
        ("docProps/app.xml", APP_XML),
    ]
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts:
            z.writestr(name, text.encode("utf-8"))
    os.replace(tmp, path)
    return path
