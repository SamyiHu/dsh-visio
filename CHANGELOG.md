# Changelog

## 1.20.0
- **Fixed the segment handles never appearing**: they were appended after `</svg>`, so the
  browser never rendered them. That is why dragging a connector did nothing.
- Every connector end now has a red square handle; dragging it re-glues that end to the
  nearest shape (`reglue`, which writes the page-level `<Connects>` row Visio actually uses).
- A **connect tool** in the toolbar: click a shape, then a second one, and a connector is
  created between them.


## 1.19.1
- Connector editing now works the way Visio does: every run of a selected connector gets a
  handle at its middle, and dragging it slides that run (horizontal runs move up/down,
  vertical runs move sideways). The two ends never move.
- Dragging a straight connector for the first time splits it into a detour so there is a
  corner to slide.
- The up/down/left/right buttons are gone; they were an invention of mine, not Visio.


## 1.19.0
- Connector routing can be edited by hand. Select a connector and the inspector shows a
  **走线** section: over / under / left / right, or auto. The polyline is written into the
  connector's `Geometry` section, and a hand-routed connector is no longer touched by the
  automatic router.
- A blue dot on the selected connector can be dragged to add a bend (`bend`), so the line
  can be shaped point by point.
- A detour that would fold back on itself is redirected to a sideways lane instead.


## 1.18.4
- Fixed the reset and close buttons of the floating window: a pointerdown on the title bar
  called `preventDefault()`, which swallowed the click that followed.
- The title bar is kept below the app chrome (y >= 48), and the left move handle is now a
  thin strip that appears on hover, so it no longer blocks the panel underneath.


## 1.18.3
- The floating canvas can no longer be dragged under the app chrome: the title bar always
  stays reachable, and a geometry saved on a larger screen is clamped when it opens.
- `Esc` closes the floating window, and a reset button (top right) puts it back on screen,
  so a stuck window is always recoverable.


## 1.18.2
- The floating canvas window can be moved from a dedicated handle on its left edge, not
  only by its title bar.
- The bottom-right launcher is draggable; its position is remembered, and a drag no longer
  toggles the window (only a click does).


## 1.18.1
- Dragging a shape **snaps to the other shapes**: left/right/top/bottom edges and centre
  lines within 0.35in, with red dashed guide lines showing which line it locked onto.
- With nothing to align to, the move falls back to a 0.25in grid (`Alt` turns that off).


## 1.18.0
- Guide arrows on the four sides of a selected shape. Clicking one **connects** to an
  aligned neighbour (`probe` finds it), or **duplicates** the shape in that direction and
  links the copy when nothing is aligned.
- `Delete` / `Backspace` deletes the selection without a dialog (undo covers it), `Esc`
  clears the selection; typing in a field still never triggers them.
- New engine actions `probe` and `duplicate`, also exposed to the `visio` tool.


## 1.17.0
- Connectors are laid out from Visio's **connection points**: `Section N="Connection"`
  rows when a shape defines them (X/Y plus the DirX/DirY normal), otherwise the four edge
  midpoints a plain 2-D shape gets by default.
- One connection point carries at most one connector (`anchor-shared`), a line leaves and
  enters along the port normal (`dir-mismatch`), and a decision's branches spread over
  different points, preferring the side opposite its entry (`branch-ports`).


## 1.16.3
- Connectors are laid out from the **relationship graph**, not drawn straight from the
  stored cells: `engine/route_grammar.py` builds nodes/edges, gives every connector end its
  own side, and routes orthogonally around obstacles.
- The same module **checks the grammar** (axis-aligned, on-boundary, no crossing, no shared
  port, decisions spread their branches over distinct sides) and reports violations instead
  of shipping a broken picture.


## 1.16.2
- Connectors attach to the **middle of the facing side** and route at right angles, so a line
  never stops short of a shape, dives into it at an angle, or leaves a dangling stub.


## 1.16.1
- Dynamic connectors are drawn with **right-angle routing**, the way Visio shows them,
  instead of the straight diagonal stored in the file.
- `validate` also reports connectors that **run through an unrelated shape** — before, it
  only checked that Connect rows existed, so a visibly broken page could still pass.


## 1.15.3
- The inspector has an **occlusion** switch for the text block (`TextBkgnd`): on = an opaque
  white block behind the text, so lines underneath are hidden.


## 1.15.1
- Dragging a connector label moves only the text block (`TxtPinX/TxtPinY`); the line keeps
  its endpoints.
- Connector labels resolve their colour like any other text (Character runs / style / theme)
  instead of a hardcoded grey.


## 1.15.0
- Connectors move by their endpoints: dragging a connector (or its label) no longer
  rewrites Width/Height, which used to collapse the line.
- Editing text keeps the Character runs, so per-line colours survive a text edit.
- LinePattern 0 means no outline; connectors are drawn behind shapes so labels stay readable.
- `tests/make_uicheck.mjs`: renders the inspector in a real browser and measures the boxes.


## 1.14.4
- The text box spans the full inspector width (it was sized by the browser's default `cols`),
  and its height dropped to 74px (3 rows), still resizable.


## 1.14.3
- The panel footer shows the client build (`v1.14.3`), so a stale bundle is visible at a glance.


## 1.14.2
- Geometry fields share one 4-column grid: no field can grow wider than its neighbours.
- The text box is 104px tall (was 64px) and resizable.


## 1.14.1
- Geometry is kept inside the page: drag clamps to the page box, and typing X/Y/W/H clamps too.
- The inspector shows a red "outside the page" warning with a one-click "bring back" action.


## 1.14.0
- `stencil_info`: name, prompt, keywords, size, shape count and sample text per master.
- `stencil_sheet`: PNG contact sheet of every master in a `.vssx`/`.vstx`.
- `snapshot`: renders every page to PNG **through the same SVG the panel shows**
  (`engine/svg_raster.py`), so exports and preview can no longer drift.
- `capabilities`: machine-readable list of actions, kinds and notes.
- `examples/basic-shapes.vssx` + `tests/make_vssx.py` fixture builder.


## 1.13.2
- Drag: `pointercancel` / window `blur` end the drag, so a release outside the window no
  longer leaves a shape at 85% opacity with a stale selection box.
- Selection survives the post-drop refresh (`render` with `selected` instead of `svg`).
- Polling pauses while the right pane has focus, so typing is never overwritten.
- SVG root and page container no longer clip: a shape dragged past the page edge stays visible.


## 1.12.0
- Relationship audit (`validate`): empty connectors, dangling ids, floating endpoints,
  zero-size shapes, connector labels.
- Text: per-run colours, `TxtWidth` soft wrap, centred blocks, optional `TextBkgnd` fill.
- Shape fill translucency (`FillForegndTrans`) honoured.
- Connectors: real line colour/weight, begin+end arrow markers.
- Engine hot-restart when `engine/*.py` changes.

## 1.10.0
- Master outline fallback when a master instance carries broken local geometry.

## 1.8.0
- 16 built-in kinds, `.vssx` stencil import, floating canvas, zoom/pan, undo/redo.

## 1.0.0
- First working panel: file browser, SVG preview, text/cell editing, create/new.
