# Changelog

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
