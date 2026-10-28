# dsh-visio

[![CI](https://github.com/SamyiHu/dsh-visio/actions/workflows/ci.yml/badge.svg)](https://github.com/SamyiHu/dsh-visio/actions/workflows/ci.yml)

A native **Visio (.vsdx) viewer and editor for the DeepSeek Harness (DSH) Web UI**, with a
live preview, shape editing and a `visio` agent tool.  Pure Python engine, no Visio install,
no Office dependency.

![status](https://img.shields.io/badge/status-beta-yellow)
![license](https://img.shields.io/badge/license-MIT-blue)
![engine](https://img.shields.io/badge/engine-python--stdlib-green)

## Features

- **Live preview** – the panel renders the `.vsdx` page to SVG and repaints after every edit.
- **Edit in place** – move / resize, text, fill, line, per-run text colour, shape data.
- **Shape library** – 16 built-in kinds (process, decision, terminator, …) plus
  `.vssx`/`.vstx` stencil import; drawn from real Visio masters, not stacked lines.
- **Connectors** – add, label, delete; connectors keep their own line colour, weight and
  arrow heads, and their labels are read from the 1-D shape text.
- **Relationship audit** – `validate` finds empty links (connectors with no `Connect` rows),
  dangling ids, floating endpoints and zero-size shapes.
- **Multi-page, zoom, pan, grid, undo/redo**, external-change detection.
- **Agent tool** – the same operations are exposed to the model as a `visio` tool, including
  stencil discovery (`stencil_info`, `stencil_sheet`), whole-drawing snapshots (`snapshot`)
  and a self-describing `capabilities` action.

## Install

```bash
# 1. clone next to your other local bundles
git clone https://github.com/SamyiHu/dsh-visio.git
# 2. install into the running Harness (Reload DSH afterwards)
dsh plugin install /absolute/path/to/dsh-visio
```

Manual equivalent: add `"@local/dsh-visio": "link:/absolute/path/to/dsh-visio"` to the profile
`package.json`, run `pnpm install`, then reload the app.  The bundle patch
`cordis.patch.yml` inserts the plugin automatically.

Requires Python 3.9+ on `PATH` (or set `pythonPath` in the plugin config / `DSH_VISIO_PYTHON`).

## Usage

- Sidebar → **Visio 图纸** opens the panel; the floating canvas button opens the same
  drawing in a draggable window.
- Pick a folder, click a `.vsdx`; the left tree lists pages and shapes, the right pane edits
  the selection.
- From the agent side: ask for a drawing and the model calls the `visio` tool
  (`open`, `text`, `get_shape`, `list`, `create`, `add_shape`, `move`, `set_text`, `set_cell`,
  `set_prop`, `connect`, `delete`, `validate`, `kinds`, `stencils`, `stencil_info`,
  `stencil_sheet`, `stencil_add`, `snapshot`, `capabilities`, `undo`, `redo`, `normalize`,
  `export`).  `examples/basic-shapes.vssx` is a three-master stencil used by the tests.

## Configuration

| key | default | meaning |
|---|---|---|
| `pythonPath` | `python` | interpreter used for the engine |
| `defaultFolder` | workspace dir | where the file browser starts |

## Architecture

```
index.js            Host half: `visio` tool + same-origin routes, bridge pool
client.js           Client half: panel, floating window, inspector, i18n
engine/vsdx_core.py Reader/editor/renderer (OPC + XML, stdlib only)
engine/visio_bridge.py  JSON line protocol used by the Host
engine/blank_doc.py     Creates a minimal valid .vsdx from scratch
engine/kinds.py         16 built-in shape kinds (real master geometry)
engine/stencil.py       .vssx/.vstx import
tests/                  engine, client-render, client-contract, host-contract
```

The Host keeps one engine child process per interpreter and **restarts it when any
`engine/*.py` file changes** (mtime + size fingerprint), so edits never run on stale code.

## Development

```bash
python tests/test_engine.py          # 13 engine cases (incl. validate + text runs)
node tests/test_client_render.mjs    # renders panel/inspector/dialog headlessly
node tests/test_client_contract.mjs  # i18n keys + slot contract
node tests/test_host_contract.mjs    # tool schema + routes + bridge round trip
```

## Limitations

- SVG preview approximates Visio typography (line breaking by width estimate).
- Themes/masters are honoured for geometry and colour, not for every style inheritance rule.
- `.vsdm` macros are not executed.

## Licence

MIT — see [LICENSE](LICENSE).  No third-party fixtures are bundled; tests build their own documents.


## CI

`.github/workflows/ci.yml` runs on every push/PR across Linux and Windows:

- `node --check` on both halves, `py_compile` on the engine
- `tests/test_engine.py` (15 cases: edit, connectors, stencils, snapshots)
- `tests/test_client_render.mjs` and `tests/test_client_contract.mjs` (slots + 94 translations)
- `tests/test_host_contract.mjs` (tool schema, routes, bridge round trip)

`release.yml` publishes a zip on every `v*` tag, after the same test suite, and refuses a tag
that does not match `package.json` version.
