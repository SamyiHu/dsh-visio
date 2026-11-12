# Changelog

## 1.23.0 — 2026-11-12

Connector interaction polish, keyboard shortcuts and a full-workspace grid.

- **Connector drags no longer judder.** The hover handler rebuilt four connection dots
  on every `pointermove` during a drag; they also sat under `elementFromPoint` and
  made the drop target flicker. Hover work is now suspended for the whole gesture, and
  drop-target groups are cached once instead of queried every frame.
- **The connect preview has an arrow head and distinct ends**: a hollow start dot and a
  filled arrow head at the target, so direction is obvious before releasing. Hover dots
  are green (start), the tooltip reads `起点 #A → 终点 #B`, and re-glue says 新起点/新终点.
- **Grabbing an existing line moves the whole connector** (a plain `move`) instead of
  bending one run (`move_segment`). Only the blue segment dot adjusts a run now, so a
  click-and-drag on a line can no longer silently turn it into a jog.
- **Right-button drag pans the canvas** in any tool, and the native context menu is
  suppressed on the canvas.
- **Keyboard shortcuts**: `Del`/`Backspace` delete, `Ctrl+Z` undo, `Ctrl+Shift+Z` /
  `Ctrl+Y` redo, `Esc` deselect. A hint sits in the status bar so they are discoverable.
- **The grid is one continuous net across the whole workspace, including inside the
  page.** It is a measuring aid for comparing shape sizes, so it must stay visible
  over the paper rather than stopping at its edge. The page is now transparent with
  only a size border; the grid lives in the scrolling content layer (so panning
  cannot shift it against the shapes) and its offset is a multiple of the cell size
  (so a grid line always lands exactly on the page's SVG origin at any zoom).
  Cells stay a quarter inch of the drawing. The cell size and the page element's
  aspect ratio are derived from the SVG `viewBox` (which the engine pads by 0.25in and
  may extend for off-page shapes), not from the paper size: using two different scales
  made the grid drift against the shapes and stretch the drawing on the y axis. Grid
  origin also compensates for the `viewBox.x/y` padding. Verified at 64% / 100% / 195%:
  x and y px-per-inch agree within 0.001%, and a 2.2 x 0.9in shape always spans
  8.8 x 3.6 cells.
- `ENGINE_VERSION` and the `/config` engine string now read `package.json` instead of
  a hard-coded `1.0.0`, so the build shown in the panel and reported by the engine
  agree. `tests/test_client_contract.mjs` asserts `CLIENT_BUILD === package.version`.
- **Compatibility declared the way the awesome-list expects.** Its `contributing.md`
  requires official `@deepseek-ai/*` packages as `peerDependencies` and warns that a
  peer range without explicit prerelease branches silently excludes every prerelease
  harness build. `package.json` now has `engines.node >=18`, `dsh.engines.dsh
  >=0.1.7-rc.2`, and `peerDependencies["@deepseek-ai/dsh"]` with explicit `||`
  branches (`^0.1.7-rc.2 || ^0.2.0-rc.1 || ^0.2.1-rc.1 || ^0.2.2-rc.1`). Verified with
  node-semver: `0.2.2-rc.1` (the guaranteed host) and the early `0.1.7-rc.2` both match,
  `0.3.0` does not. Both READMEs gained a Compatibility section distinguishing the
  guaranteed version, the first-build version, and earlier builds that are not guaranteed;
  `tests/test_client_contract.mjs` asserts the fields stay present.
- **Dependency documentation corrected** after upstream review: the core engine is
  stdlib-only, but PNG export, `snapshot` and stencil previews need Pillow. Both READMEs
  (and the awesome-list entry) now state Python 3.9+ on `PATH` and Pillow for those paths.
- `.gitattributes` pins LF so editor CRLF churn no longer shows whole-file diffs.
- Client render test updated for the workspace grid; browser harness grew to 37 assertions
  (preview direction, line-body drag, right-button pan, grid coverage).

## 1.22.1 — 2026-11-02

- **A new shape no longer lands on top of the previous one.** Every insert was placed at
  the exact centre of the page, so clicking 矩形 twice produced two identical boxes stacked
  on each other: the canvas did not change and the click looked like it had failed. New
  shapes now cascade to the first free spot on the page.
- **A new shape is selected immediately**, so its eight handles and the inspector are there
  without a second click.

## 1.22.0 — 2026-11-02

- **Resize a shape by its handles.** A selected shape now shows eight scale handles
  (four corners, four edges). Dragging one rewrites Width/Height and keeps the opposite
  edge anchored; Shift on a corner keeps the aspect ratio; a dashed box previews the
  result while dragging.
- **Rotation.** A knob above the shape sets the Angle cell (Shift snaps to 15°), the value
  is editable in the inspector, and the renderer now applies it — the Angle cell used to be
  ignored, so a rotated shape in a real drawing came out upright.
- **Connector ends are round dots**, not red squares: an end is a point you drop on a port,
  not a shape handle.
- Browser harness: 30 assertions (+6) covering the handles, resizing and rotation.

## 1.21.2 — 2026-11-02

Repository hygiene only, no behaviour change.

- The repository root had collected 95 scratch files (throw-away drawings, probe scripts,
  screenshots), 40 of which had been committed by accident, plus 40 `*.bak-*` backup copies.
  All of them are gone; the root now holds only project files.
- `.gitignore` is regrouped and refuses anything matching `/_*`, so a probe script or a
  screenshot dropped in the root can never be committed again. Scratch output belongs in
  `tests/_out/`, which is ignored.

## 1.21.1 — 2026-11-02

- **The background grid did not scale with the shapes.** The cell size was a fixed
  `18px * zoom` while the page was `fitBox * zoom`, so grid and drawing ran on two
  unrelated scales and slid against each other when zooming. A cell is now a quarter
  inch of the drawing (`pageBox / pageWidth * 0.25`) and the grid is painted on the page
  element itself, so it shares the page origin: an 11in page is 44 cells wide at every
  zoom level.
- The grid now covers the page only (as Visio does) instead of the whole scroll area.
- The page no longer shrinks below its zoomed width (`max-width:100%` used to squeeze it
  inside the scroll box, which also desynchronised the grid from the SVG).
- Browser harness: one more assertion that the cell count stays constant across a
  two-step zoom (24 assertions total).

## 1.21.0 — 2026-11-02

- **A line is a line, not a shape.** The 直线 tool used to drop a 2x1.2in box with a diagonal
  drawn inside it: it had a fill, eight scale handles and took part in shape alignment. It now
  creates a 1-D line (Begin/End cells), is drawn by its own renderer pass (a horizontal line
  has a zero-height box and used to disappear entirely), is selected with two end dots instead
  of a dashed box, and the inspector edits X1/Y1/X2/Y2 instead of width/height. The tool also
  arms the canvas: drag to draw the line, hold Shift for a perfect horizontal or vertical.
- **Connection points are a second alignment dimension.** Dragging a shape now first tries to
  line one of its four connection points up with a connection point of another shape, on both
  axes, and shows a short blue guide between the two points that matched. Box edges and centre
  lines still work as before and are drawn in red; connections win when both apply.
- **Drag-to-connect.** Hovering a shape reveals its connection dots; dragging from one dot to
  another shape creates the connector and glues it to the port it was released near. This is one
  gesture instead of arming a tool and clicking two shapes (the tool is still there).
- `connect` accepts explicit `from_port` / `to_port`, and the router now honours the ports a
  connector is already glued to instead of picking a nicer side, so a dropped end stays where
  the drop marker said it would.
- Moving a shape commits through the ordinary response instead of a "light" one plus a second
  render request: between the two, handles were placed from the new coordinates into the old
  picture and could sit inches away from the shape they belonged to.
- 4 more engine tests (35 total) for 1-D lines, explicit ports and pin-preserving routing; the
  browser harness grew to 23 assertions covering the line tool, connection-point guides and
  drag-to-connect.
- Connector handles were positioned from the stored Begin/End points while the picture drew
  the automatic route, so they floated away from the line. The panel now receives the
  polyline that is actually rendered.
- Dragging a connector segment used the same two-point stub, so the first drag replaced the
  automatic route with a two-point detour. It now starts from the drawn polyline.
- A dragged connector end now **snaps to the nearest connection point** of the target shape
  (four edge midpoints, or the shape's own `Connection` rows), so the end is glued to a real
  port instead of floating where the mouse was released.
- Connector handles are larger with a screen-pixel outline, so they stay visible when zoomed
  out.
- The whole connector is now grabbable: a wide invisible band follows the line, so dragging
  the line itself works instead of only the small dots.
- The drag axis follows the run (horizontal runs move up/down, vertical runs move sideways),
  which is why a sideways drag on a horizontal line used to do nothing.
- Collinear points are dropped before the handles are built, so one run is one corner.
- Dragging a connector end now shows a **drop preview**: a green dot marks the port it will
  glue to, a dashed line joins it to the cursor, and the tooltip names the target shape.
  Releasing with no target reports it instead of silently doing nothing.
- **Fixed dragging the line itself doing nothing**: the grab band sent `shape_id: null`
  (it read `data-route-handle` off an element that has `data-route-band`), so the engine
  rejected every request. Both handles now resolve the connector the same way.
- **Fixed an end dropped onto one shape landing on its neighbour**: the pointer was mapped
  through the viewBox as if it started at the origin, but the engine pads the view box by
  0.25in. The offset is now applied, so a release lands on the port under the cursor.
- **Fixed a re-glued end leaving the line behind**: `reglue` rewrote the glue rows and the
  Begin/End cells but not the hand-drawn polyline, so the picture kept the old corner. The
  route's end point now moves too, and keeps the run axis aligned.
- **Fixed the segment drag pulling the ends**: `move_segment` shifted the neighbouring
  corners as well, so a run that touched an end dragged that end with it, and a two-point
  line came back as a non-orthogonal three-point stub. Ends are now fixed, only the run
  under the cursor travels, and a straight line grows a proper jog first.
- A hand-drawn route of exactly two points now stays manual (`drawn_points` used to need
  more than two points, so straightening a connector handed it back to the router).
- The zoom toolbar moved out of the drawing into a dock row under it: floating over the
  page it could cover a connector handle near the bottom edge and swallow the click.
- **Fixed a connector drawn straight through a shape**: the router crashed in `assign()`
  (`StopIteration` on shapes that carry their own `Connection` rows), returned no routes,
  and every connector fell back to a two-point stub across the page. The fallback now uses
  the node's real anchors.
- **Connectors route around shapes, not through them.** The candidate search only nudged the
  join by a few tenths of an inch, so two ends on opposite sides of a box had no way around
  it. Routing now also tries lanes just outside every box, which is what actually gets the
  line around a shape. A matrix of all 26 single-end reglue combinations in `examples/demo.vsdx`
  went from 12 crossings to 0.
- **A re-glued end no longer keeps a hand-drawn route that cuts through a shape.** Hand-drawn
  geometry wins over the router, so dragging an end across the diagram parked the crossing
  permanently. `reglue` now drops that route and lets the router re-route it.
- **The drop marker now matches where the end lands** (what you see is what you get). The green
  marker was positioned through a second transform that mixed the viewBox origin into sheet
  coordinates, so it promised a port 0.25in away from the one the drop glued to. The panel
  also uses the engine's real `Connection` points instead of guessing four bbox midpoints,
  and the tooltip names the exact coordinate it will commit.
- **Alignment assist while dragging a connector run**: the run snaps to the edges and centre
  lines of the nearby shapes, a blue dashed guide shows the line it aligned to, and the tooltip
  says `[对齐]`. Hold Alt to drag free. Shape drags use the same guide code.
- **Zero-length connectors are marked, not drawn**: a connector whose two ends coincide was
  painted as a bare arrow head floating in mid-air with no line to grab. It is now drawn as a
  dashed marker with a warning, keeps a click target, and `set_route` refuses to create one.
- **Micro steps in a route are collapsed**: a router landing 0.017in beside its port left a step
  that reads as a kink at high zoom and gives the segment handles a useless extra run. Steps
  under 0.02in are removed without moving either glued end.
- Rendering now draws exactly `drawn_points()` — the polyline the panel shows — instead of the
  raw Geometry rows, so the picture and the handles can no longer disagree.
- New regression tests: 16 engine tests for `reglue` / `move_segment` / `_simplify` /
  `drawn_points` / degenerate connectors / route rendering, plus `tests/interactive.html` — a
  real-browser harness that drives the actual panel against the actual engine and asserts the
  connector gestures, including that the drop marker and the committed end agree.


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
