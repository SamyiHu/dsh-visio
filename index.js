/**
 * DSH Visio — Host half.
 *
 * Wraps the visio-skill engine (pure-Python .vsdx reader / editor / renderer) in two
 * Host surfaces:
 *   • a `visio` agent tool, so the model can inspect, edit and create drawings;
 *   • two same-origin HTTP routes used by the browser panel:
 *       GET  /dsh-visio/config → default folder + engine probe
 *       POST /dsh-visio/op     → one bridge request, e.g. {action:"open", path}
 *
 * Every operation spawns `python engine/visio_bridge.py`, writes one JSON request
 * on stdin and reads one JSON response from stdout. The bridge saves in place and
 * returns the refreshed render, so the panel redraws from a single round trip.
 */
import { spawn } from 'node:child_process'
import { access } from 'node:fs/promises'
import { readdirSync, statSync, readFileSync } from 'node:fs'
import { dirname, isAbsolute, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROUTE_PREFIX = '/dsh-visio'
const BODY_LIMIT = 1024 * 1024
const STDOUT_LIMIT = 32 * 1024 * 1024
const ENGINE_TIMEOUT_MS = 30000

const here = dirname(fileURLToPath(import.meta.url))
// Read the manifest once so /config reports the same build as the panel footer.
const pkg = JSON.parse(readFileSync(join(here, 'package.json'), 'utf8'))
const BRIDGE = join(here, 'engine', 'visio_bridge.py')

// Every engine module, discovered instead of hand-listed: the hand-kept list had
// drifted (svg_raster.py, which decides the PNG output, was missing, while the
// unused vsdx_png.py was in it), so an edited renderer kept serving stale code.
function engineFiles() {
  try {
    return readdirSync(join(here, 'engine'))
      .filter((name) => name.endsWith('.py') || name.endsWith('.json'))
      .sort()
  } catch {
    return []
  }
}


/**
 * mtime+size of every engine module. The bridge pool keeps one Python child
 * alive for speed, so an edited engine would otherwise keep serving the code it
 * imported at spawn time — the panel would silently render with stale logic.
 */
function engineFingerprint() {
  try {
    return engineFiles().map((name) => {
      const info = statSync(join(here, 'engine', name))
      return name + ':' + Math.round(info.mtimeMs) + ':' + info.size
    }).join('|') || 'empty'
  } catch (error) {
    return 'missing'
  }
}

class BadRequest extends Error {}

function messageOf(error) {
  return error instanceof Error ? error.message : String(error)
}

function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Resolve the Python executable once per request so a config edit takes effect. */
function pythonOf(config) {
  if (typeof config?.pythonPath === 'string' && config.pythonPath.trim()) return config.pythonPath.trim()
  if (typeof process.env.DSH_VISIO_PYTHON === 'string' && process.env.DSH_VISIO_PYTHON.trim()) {
    return process.env.DSH_VISIO_PYTHON.trim()
  }
  return process.platform === 'win32' ? 'python' : 'python3'
}

/** Run one bridge request. Rejects with the bridge's own message on ok:false. */
/**
 * One long-lived bridge process per Python interpreter. The engine is a
 * line-oriented daemon (`visio_bridge.py --serve`), so repeated reads cost
 * milliseconds instead of a process start plus a full .vsdx parse. Requests
 * are serialised: the engine mutates a document in memory and must not be
 * re-entered.
 */
const pools = new Map()

class BridgePool {
  constructor(python) {
    this.python = python
    this.child = null
    this.buffer = ''
    this.stderr = ''
    this.queue = []
    this.current = null
  }

  request(payload) {
    return new Promise((resolve, reject) => {
      this.queue.push({ payload, resolve, reject, timer: null })
      this.pump()
    })
  }

  pump() {
    if (this.current || this.queue.length === 0) return
    const job = this.queue.shift()
    this.current = job
    let child
    try {
      child = this.ensure()
    } catch (error) {
      this.settle(job, error)
      return
    }
    job.timer = setTimeout(() => {
      this.restart()
      this.settle(job, new Error(`Visio engine timed out after ${ENGINE_TIMEOUT_MS / 1000}s.`))
    }, ENGINE_TIMEOUT_MS)
    try {
      child.stdin.write(`${JSON.stringify(job.payload)}
`)
    } catch (error) {
      this.settle(job, new Error(`cannot write to the Visio engine: ${messageOf(error)}`))
    }
  }

  ensure() {
    const fingerprint = engineFingerprint()
    if (this.child && !this.child.killed && this.child.exitCode === null) {
      if (this.fingerprint === fingerprint) return this.child
      this.restart()
    }
    if (this.child && !this.child.killed && this.child.exitCode === null) return this.child
    const child = spawn(this.python, [BRIDGE, '--serve'], {
      cwd: here,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.fingerprint = fingerprint
    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk) => this.onData(chunk))
    child.stderr.on('data', (chunk) => {
      this.stderr = (this.stderr + chunk).slice(-4000)
    })
    child.on('error', (error) => {
      this.child = null
      this.fail(new Error(
        `cannot start ${this.python}: ${messageOf(error)}. Set pythonPath in the plugin config or DSH_VISIO_PYTHON.`,
      ))
    })
    child.on('exit', (code) => {
      this.child = null
      if (this.current) {
        const detail = this.stderr.trim()
        this.fail(new Error(`Visio engine exited with code ${code}${detail ? `: ${detail}` : ''}`))
      }
    })
    this.child = child
    this.buffer = ''
    return child
  }

  onData(chunk) {
    this.buffer += chunk
    if (this.buffer.length > STDOUT_LIMIT) {
      this.restart()
      this.fail(new Error('Visio engine produced too much output.'))
      return
    }
    let index = this.buffer.indexOf('\n')
    while (index >= 0) {
      const line = this.buffer.slice(0, index).trim()
      this.buffer = this.buffer.slice(index + 1)
      if (line) this.deliver(line)
      index = this.buffer.indexOf('\n')
    }
  }

  deliver(line) {
    const job = this.current
    this.current = null
    if (!job) return
    let parsed
    try {
      parsed = JSON.parse(line)
    } catch {
      this.settle(job, new Error(`Visio engine returned invalid JSON: ${line.slice(0, 300)}`))
      this.pump()
      return
    }
    if (isRecord(parsed) && parsed.ok === false) {
      this.settle(job, new BadRequest(String(parsed.error ?? 'Visio engine failed')))
    } else {
      this.settle(job, null, parsed)
    }
    this.pump()
  }

  fail(error) {
    const job = this.current
    this.current = null
    if (job) this.settle(job, error)
    while (this.queue.length > 0) {
      const queued = this.queue.shift()
      this.settle(queued, new Error(messageOf(error)))
    }
  }

  settle(job, error, value) {
    if (job.timer) clearTimeout(job.timer)
    job.timer = null
    if (error) job.reject(error)
    else job.resolve(value)
  }

  restart() {
    const child = this.child
    this.child = null
    this.buffer = ''
    if (child) {
      try {
        child.kill()
      } catch {
        /* already gone */
      }
    }
  }

  dispose() {
    this.restart()
    this.fail(new Error('Visio engine disposed'))
  }
}

function poolFor(config) {
  const python = pythonOf(config)
  let pool = pools.get(python)
  if (!pool) {
    pool = new BridgePool(python)
    pools.set(python, pool)
  }
  return pool
}

function disposePools() {
  for (const pool of pools.values()) pool.dispose()
  pools.clear()
}

function runBridge(config, payload) {
  return poolFor(config).request(payload)
}

function runBridgeOnce(config, payload) {
  const python = pythonOf(config)
  return new Promise((resolvePromise, rejectPromise) => {
    let settled = false
    let child
    const finish = (fn, value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      fn(value)
    }
    const timer = setTimeout(() => {
      try {
        child?.kill()
      } catch {
        /* already gone */
      }
      finish(rejectPromise, new Error(`Visio engine timed out after ${ENGINE_TIMEOUT_MS / 1000}s.`))
    }, ENGINE_TIMEOUT_MS)

    try {
      child = spawn(python, [BRIDGE], {
        cwd: here,
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      })
    } catch (error) {
      finish(rejectPromise, new Error(`cannot start ${python}: ${messageOf(error)}`))
      return
    }

    let stdout = ''
    let stderr = ''
    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk) => {
      stdout += chunk
      if (stdout.length > STDOUT_LIMIT) {
        try {
          child.kill()
        } catch {
          /* ignore */
        }
        finish(rejectPromise, new Error('Visio engine produced too much output.'))
      }
    })
    child.stderr.on('data', (chunk) => {
      stderr = (stderr + chunk).slice(-4000)
    })
    child.on('error', (error) => {
      finish(rejectPromise, new Error(
        `cannot start ${python}: ${messageOf(error)}. Set pythonPath in the plugin config or DSH_VISIO_PYTHON.`,
      ))
    })
    child.on('close', (code) => {
      if (settled) return
      const body = stdout.trim()
      if (!body) {
        finish(rejectPromise, new Error(
          `Visio engine exited with code ${code}${stderr ? `: ${stderr.trim()}` : ''}`,
        ))
        return
      }
      let parsed
      try {
        parsed = JSON.parse(body)
      } catch {
        finish(rejectPromise, new Error(`Visio engine returned invalid JSON: ${body.slice(0, 300)}`))
        return
      }
      if (isRecord(parsed) && parsed.ok === false) {
        finish(rejectPromise, new BadRequest(String(parsed.error ?? 'Visio engine failed')))
        return
      }
      finish(resolvePromise, parsed)
    })

    try {
      child.stdin.end(JSON.stringify(payload))
    } catch (error) {
      finish(rejectPromise, new Error(`cannot write to the Visio engine: ${messageOf(error)}`))
    }
  })
}

function defaultFolder(ctx, config) {
  if (typeof config?.defaultFolder === 'string' && config.defaultFolder.trim()) return config.defaultFolder.trim()
  try {
    const working = ctx.get('workingDirectory')
    if (typeof working?.defaultDirectory === 'string' && working.defaultDirectory) return working.defaultDirectory
  } catch {
    /* optional service */
  }
  return process.cwd()
}

/* -------------------------------------------------------------- path guard */

/**
 * Folders the user has actually reached through the panel: the default folder,
 * plus anything they listed, opened or created in.  The /op route is same-origin
 * only, but it used to accept any absolute path for reads AND writes, so a
 * script injected into the panel could drop an SVG on top of any file on the
 * machine, or make directories anywhere.  Reads stay permissive (the engine
 * still refuses anything that is not .vsdx/.vsdm/.vssx/.vstx); writes are
 * confined to these folders and to the matching file extension.
 */
class PathStops {
  constructor() {
    this.folders = new Set()
  }

  add(target) {
    if (typeof target !== 'string' || !target.trim()) return
    try {
      this.folders.add(resolve(target).toLowerCase())
    } catch {
      /* a path the OS refuses is a path we cannot protect */
    }
  }

  addFile(file) {
    if (typeof file === 'string' && file.trim()) this.add(dirname(resolve(file)))
  }

  covers(target) {
    if (typeof target !== 'string' || !target.trim()) return false
    let full
    try {
      full = resolve(target).toLowerCase()
    } catch {
      return false
    }
    for (const folder of this.folders) {
      if (full === folder) return true
      if (full.startsWith(folder.endsWith(sep) ? folder : folder + sep)) return true
    }
    return false
  }

  get size() {
    return this.folders.size
  }
}

/** Actions whose "out" is a file the engine writes. */
const OUT_IS_FILE = new Set(['export', 'stencil_sheet'])

/**
 * Normalise and police one /op payload before it reaches the engine.
 * Mutates the body (a relative "out" is anchored next to the drawing) and
 * throws BadRequest for anything that would write outside the user's folders.
 */
function guardRequest(stops, body, ctx, config) {
  const action = body.action
  if (OUT_IS_FILE.has(action) && typeof body.out === 'string' && body.out.trim()
      && !isAbsolute(body.out)) {
    const anchor = typeof body.path === 'string' && body.path
      ? dirname(body.path)
      : defaultFolder(ctx, config)
    body.out = resolve(anchor, body.out)
  }

  if (action === 'export' && typeof body.out === 'string' && body.out.trim()) {
    const want = String(body.format || 'svg').toLowerCase() === 'png' ? '.png' : '.svg'
    if (!body.out.toLowerCase().endsWith(want)) {
      throw new BadRequest('export out must end with ' + want)
    }
  }
  if (action === 'stencil_sheet' && typeof body.out === 'string' && body.out.trim()
      && !body.out.toLowerCase().endsWith('.png')) {
    throw new BadRequest('stencil_sheet out must end with .png')
  }

  const writes = []
  if (action === 'create' && typeof body.dir === 'string' && body.dir.trim()) {
    writes.push(['dir', body.dir])
  }
  if (typeof body.out === 'string' && body.out.trim()) writes.push(['out', body.out])
  for (const pair of writes) {
    if (!stops.covers(pair[1])) {
      throw new BadRequest('refusing to write outside the folders opened in the panel ('
        + pair[0] + '): ' + pair[1])
    }
  }

  return body
}

/** Remember every folder a successful request proved the user can reach. */
function rememberPaths(stops, result) {
  if (!isRecord(result)) return
  if (typeof result.path === 'string') stops.addFile(result.path)
  if (typeof result.folder === 'string') stops.add(result.folder)
  if (typeof result.dir === 'string') stops.add(result.dir)
  if (typeof result.out === 'string') stops.addFile(result.out)
  if (Array.isArray(result.files)) for (const file of result.files) stops.addFile(file)
}

/* ------------------------------------------------------------------ routes */

function json(response, status, payload) {
  response.writeHead(status, {
    'cache-control': 'no-store',
    'content-type': 'application/json; charset=utf-8',
  })
  response.end(JSON.stringify(payload))
}

/** Answer with the host's own rejection when it has one (browser login / untrusted origin). */
function refuseUnadmitted(ctx, request, response) {
  const connection = ctx.get('connection')
  const gate = connection?.requestRejection
  if (typeof gate !== 'function') return false
  let status
  try {
    status = gate.call(connection, request)
  } catch {
    status = 403
  }
  if (status === undefined) return false
  json(response, status, {
    error: status === 401
      ? 'The DSH session is not signed in; reopen the URL printed when dsh web started.'
      : 'This request came from an untrusted origin and was refused.',
  })
  return true
}

/** Reject a mutating request whose Origin does not match the Host it reached. */
function sameOrigin(request) {
  const origin = request.headers.origin
  if (origin === undefined) return true
  try {
    return new URL(origin).host === request.headers.host
  } catch {
    return false
  }
}

async function readBody(request) {
  const chunks = []
  let size = 0
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    size += buffer.length
    if (size > BODY_LIMIT) throw new BadRequest('Request body is too large.')
    chunks.push(buffer)
  }
  if (chunks.length === 0) return {}
  let parsed
  try {
    parsed = JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } catch {
    throw new BadRequest('Request body must be JSON.')
  }
  if (!isRecord(parsed)) throw new BadRequest('Request body must be a JSON object.')
  return parsed
}

function route(ctx, path, methods, handler) {
  return {
    kind: 'exact',
    path,
    handler: async (request, response) => {
      if (refuseUnadmitted(ctx, request, response)) return
      const method = request.method ?? 'GET'
      if (!methods.includes(method)) {
        response.writeHead(405, { allow: methods.join(', ') })
        response.end()
        return
      }
      try {
        await handler({ method, request, response })
      } catch (error) {
        const status = error instanceof BadRequest ? 400 : 500
        json(response, status, { ok: false, error: messageOf(error) })
      }
    },
  }
}

/* -------------------------------------------------------------------- tool */

/**
 * Parameters shared by every visio action.  Advertised keys are the single
 * source of truth: anything a handler reads must be declared here (the schema
 * is additionalProperties:false, so an undeclared name never reaches a handler).
 */
const TOOL_PARAMS = {
  path: { type: 'string', description: 'Absolute path to the .vsdx/.vsdm file.' },
  page: { type: 'integer', description: '1-based page number; defaults to 1.' },
  shape_id: { type: 'string', description: 'Shape ID as reported by open/get_shape.' },
  text: { type: 'string', description: 'New shape text for set_text, or the label of a new shape/connector.' },
  cell: { type: 'string', description: 'ShapeSheet cell name for set_cell, e.g. FillForegnd, LineColor, LineWeight, PinX, Width.' },
  name: { type: 'string', description: 'Shape-data property name for set_prop / shape_save.' },
  value: { type: 'string', description: 'Cell or property value for set_cell/set_prop (colors as #RRGGBB).' },
  kind: {
    type: 'string',
    enum: ['rect', 'roundrect', 'terminator', 'ellipse', 'diamond', 'triangle', 'parallelogram',
      'trapezoid', 'hexagon', 'chevron', 'arrow_right', 'arrow_left', 'arrow_up', 'arrow_down',
      'text', 'line'],
    description: 'Shape kind for add_shape (see action=kinds for the full list).',
  },
  stencil: { type: 'string', description: 'Path to a .vssx/.vstx stencil for stencil_add.' },
  master: { type: 'string', description: 'Master name or 0-based index inside the stencil.' },
  direction: { type: 'string', enum: ['right', 'left', 'up', 'down', 'top', 'bottom'],
    description: 'probe / duplicate / add_anchor: which side of the shape to look at or copy onto.' },
  gap: { type: 'number', description: 'duplicate / add_anchor: inches between the source and the copy (default 0.4).' },
  connect: { type: 'boolean', description: 'duplicate: glue a connector to the copy (default true).' },
  style: { type: 'string', enum: ['auto', 'up', 'down', 'left', 'right'],
    description: 'route_style: which way a connector should detour (auto = back to automatic routing).' },
  file: { type: 'string', description: 'Path to a .vssx/.vstx stencil for stencil_info / stencil_sheet / stencils.' },
  all: { type: 'boolean', description: 'snapshot: render every page (default: current page only).' },
  dpi: { type: 'number', description: 'snapshot / export png: pixels per inch (default 110, max 400).' },
  x: { type: 'number', description: 'Left edge in inches (origin bottom-left) for add_shape / move_endpoint / bend.' },
  y: { type: 'number', description: 'Bottom edge in inches for add_shape / move_endpoint / bend.' },
  w: { type: 'number', description: 'Width in inches for add_shape.' },
  h: { type: 'number', description: 'Height in inches for add_shape.' },
  from: { type: 'string', description: 'Source shape id for connect.' },
  to: { type: 'string', description: 'Target shape id for connect.' },
  from_port: { type: 'array', items: { type: 'number' }, description: 'connect / connect_styled: [x,y] in sheet inches that pins the START to an exact point instead of letting the router choose a side.' },
  to_port: { type: 'array', items: { type: 'number' }, description: 'connect / connect_styled: [x,y] in sheet inches that pins the END to an exact point - use it so an arrow lands dead-centre on a border instead of diving inside the shape.' },
  label: { type: 'string', description: 'Optional text on the new connector.' },
  side: { type: 'string', enum: ['top', 'bottom', 'left', 'right'], description: 'add_anchor: which side of the shape to hang the invisible anchor on (default top).' },
  nodes: { type: 'array', items: { type: 'string' }, description: 'swimlane: shape ids that belong to the row. The band is sized from their bounding box, so it can never clip them.' },
  owner: { type: 'string', description: 'swimlane: owner line next to the title.' },
  pad_x: { type: 'number', description: 'swimlane: horizontal padding around the nodes (default 0.45in).' },
  pad_bottom: { type: 'number', description: 'swimlane: space under the nodes (default 0.30in).' },
  head: { type: 'number', description: 'swimlane: header height above the nodes (default 0.42in).' },
  orthogonal: { type: 'boolean', description: 'connect_styled: reject diagonal segments instead of drawing them (default true). Pass false only for a deliberate diagonal.' },
  within: { type: 'array', items: { type: 'number' }, description: 'connect_styled: [x, y, w, h] in inches. Every waypoint must stay inside this box (e.g. a lane) or the call is rejected.' },
  label_pos: { description: 'connect_styled: where the label goes - auto | above | below | left | right | [x, y] in inches.' },
  allow_cross_shapes: { type: 'boolean', description: 'connect_styled: allow a segment to pass through an unrelated shape. Requires user_approved=true - ask the user first.' },
  allow_off_midpoint: { type: 'boolean', description: 'connect_styled: allow an end to sit on a shape border away from the four side midpoints. Requires user_approved=true - ask the user first and quote their approval.' },
  user_approved: { type: 'boolean', description: 'Set only after the user explicitly agreed to bypass the midpoint rule in this conversation.' },
  strict: { type: 'boolean', description: 'audit_full: fail (tool error) when any error or warning remains.' },
  dir: { type: 'string', description: 'Folder to list, or to create the new drawing in.' },
  title: { type: 'string', description: 'Document title for create; also drawn as the heading.' },
  width: { type: 'number', description: 'Page width in inches for create (default 11).' },
  height: { type: 'number', description: 'Page height in inches for create (default 8.5).' },
  overwrite: { type: 'boolean', description: 'create: overwrite an existing file of the same name (default false).' },
  format: { type: 'string', enum: ['svg', 'png'], description: 'Export format for export; default svg.' },
  out: { type: 'string', description: 'Output path for export / stencil_sheet (a folder for snapshot); defaults next to the drawing.' },
  geometry: { type: 'array', description: 'add_shape escape hatch: [[x,y],...] vertices in 0..1 fractions of w/h (or absolute inches >1.5). Overrides kind; use it to compose ANY silhouette when the 16 kinds and shape library are not enough.' },
  fill: { type: 'string', description: 'add_shape / swimlane: #RRGGBB fill colour.' },
  line: { type: 'string', description: 'add_shape / swimlane: #RRGGBB border colour (line_color is the connector equivalent).' },
  font_color: { type: 'string', description: 'add_shape: #RRGGBB text colour. White on a dark fill gives the professional two-line look.' },
  font_size: { type: 'number', description: 'add_shape: font size in points (default 11).' },
  bold: { type: 'boolean', description: 'add_shape: bold first text line (default true).' },
  line_pattern: { type: 'integer', description: 'add_shape: 1 solid, 2 dashed, 0 none.' },
  line_width: { type: 'number', description: 'add_shape / connect_styled: line width in inches. Use ~0.02 on a generated diagram so short arrows stay visible.' },
  line_color: { type: 'string', description: 'connect_styled: #RRGGBB line colour.' },
  points: { type: 'array', description: 'connect_styled / set_route: orthogonal waypoints [[x,y],...] in sheet inches for a deliberate cross-lane route.' },
  text_bg: { type: 'boolean', description: 'add_shape: true = white text background, false = transparent.' },
  angle: { type: 'number', description: 'add_shape/move: rotation in degrees, counter-clockwise.' },
  shape_ids: { type: 'array', description: 'align: list of shape ids to snap together.' },
  mode: { type: 'string', enum: ['edges', 'centres', 'ports'], description: 'align: which reference lines to snap to.' },
  end: { type: 'string', enum: ['start', 'end'], description: 'move_endpoint / set_end_direction: which end of the connector to adjust.' },
  shape: { type: 'object', description: 'shape_save: the shape spec to cache (must contain kind or geometry).' },
  which: { type: 'string', description: 'guide: ask for one topic instead of the whole playbook (e.g. "swimlane", "connectors", "colour").' },
  review: { type: 'boolean', description: 'snapshot: attach a structured overlap/out-of-page/text-overflow/connectivity report. Use review=true as the CHECK STAGE of every drawing task.' },
  tol: { type: 'number', description: 'probe: tolerance in inches for "in the way" (default 0.35).' },
  reach: { type: 'number', description: 'probe: how far to search in inches (default 3.0).' },
}

const ACTION_HELP =
  'Open, edit, audit, render and export Microsoft Visio .vsdx/.vsdm drawings without Visio installed. '
  + 'Coordinates are inches with the origin at the bottom-left of the page; shape bbox = {x,y,w,h}. '
  + 'open returns pages, page size, shape ids with text and bbox, and a text outline. '
  + 'Edits save in place and keep a bounded .bak-<timestamp> history. '
  + 'The DSH Visio panel in the sidebar edits the same files visually. '
  + 'A failed call is reported as a tool error, never as a successful text result.'

/** Build the tool schema for exactly the actions this build implements. */
function toolParameters(actions) {
  return {
    type: 'object',
    properties: Object.assign({
      action: {
        type: 'string',
        enum: actions,
        description: 'The operation to run. ' + actions.join(', ') + '.',
      },
    }, TOOL_PARAMS),
    required: ['action'],
    additionalProperties: false,
  }
}

function formatState(state) {
  const lines = []
  const pages = state.pages ?? []
  lines.push('file: ' + state.path)
  lines.push('page ' + state.page + '/' + state.pageCount + ' "' + state.pageName + '" - '
    + state.pageSize.w.toFixed(2) + ' x ' + state.pageSize.h.toFixed(2) + ' in')
  lines.push('pages: ' + pages.map((p) => p.index + ':' + p.name).join(', '))
  if (Array.isArray(state.masters) && state.masters.length) {
    lines.push('masters: ' + state.masters.map((m) => m.name).filter(Boolean).join(', '))
  }
  const shapes = state.shapes ?? []
  lines.push('shapes on this page: ' + shapes.length)
  for (const shape of shapes.slice(0, 60)) {
    const bb = shape.bbox ?? {}
    const kind = shape.connector ? 'connector' : (shape.master || shape.geometry?.[0] || 'shape')
    lines.push(
      '- #' + shape.id + ' [' + kind + '] ' + JSON.stringify(shape.text ?? '') + ' '
      + 'bbox ' + bb.x + ',' + bb.y + ' ' + bb.w + 'x' + bb.h
      + (shape.connects?.length ? ' -> ' + shape.connects.map((c) => c.to).join(',') : ''),
    )
  }
  if (shapes.length > 60) {
    lines.push('... ' + (shapes.length - 60) + ' more shapes not listed here '
      + '(their bbox/text exist: use action=get_shape, or action=text for the whole outline)')
  }
  if (state.notice) lines.push('', 'notice: ' + state.notice)
  return lines.join('\n')
}

/**
 * One handler per advertised action, keyed by the action name the model passes.
 * The schema enum is generated from these keys, so "advertised but not
 * implemented" and "implemented but not advertised" can no longer drift apart.
 */
function buildHandlers(ctx, config) {
  const withDeps = (fn) => async (args, overrides) => fn(args, Object.assign({
    call: (payload) => runBridge(config, payload),
    ctx,
    config,
  }, overrides || {}))

  const noticeState = (result) => [result?.notice ?? '', formatState(result)].join('\n\n').trim()

  return {
    open: withDeps(async (args, { call }) => {
      const state = await call({ action: 'open', path: args.path, page: args.page })
      const outline = await call({ action: 'text', path: args.path })
      return { text: formatState(state) + '\n\n' + outline.text }
    }),

    text: withDeps(async (args, { call }) => {
      const result = await call({ action: 'text', path: args.path })
      return { text: result.text }
    }),

    get_shape: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'get_shape', path: args.path, page: args.page, shape_id: args.shape_id,
      })
      return { text: JSON.stringify(result.detail, null, 2) }
    }),

    list: withDeps(async (args, { call }) => {
      const result = await call({ action: 'list', dir: args.dir ?? defaultFolder(ctx, config) })
      const files = result.files ?? []
      return {
        text: files.length
          ? files.map((file) => file.name + '\t' + file.size + ' bytes\t' + file.path).join('\n')
          : 'no .vsdx/.vsdm files in ' + result.dir,
      }
    }),

    create: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'create',
        dir: args.dir ?? defaultFolder(ctx, config),
        name: args.title || 'drawing',
        title: args.title,
        width: args.width,
        height: args.height,
        overwrite: args.overwrite,
      })
      return { text: formatState(result) + '\n\ncreated: ' + result.path }
    }),

    set_text: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'set_text', path: args.path, page: args.page,
        shape_id: args.shape_id, text: args.text,
      })
      return { text: noticeState(state) }
    }),

    set_cell: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'set_cells', path: args.path, page: args.page, shape_id: args.shape_id,
        cells: { [String(args.cell)]: String(args.value ?? '') },
      })
      return { text: noticeState(state) }
    }),

    set_prop: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'set_prop', path: args.path, page: args.page, shape_id: args.shape_id,
        name: args.name, value: String(args.value ?? ''),
      })
      return { text: noticeState(state) }
    }),

    delete: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'delete', path: args.path, page: args.page, shape_id: args.shape_id,
      })
      return { text: noticeState(state) }
    }),

    add_shape: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'add_shape', path: args.path, page: args.page,
        kind: args.kind ?? 'rect',
        x: args.x ?? 1, y: args.y ?? 1, w: args.w ?? 1.6, h: args.h ?? 0.8,
        text: args.text ?? '',
        fill: args.fill, line: args.line,
        font_color: args.font_color, font_size: args.font_size, bold: args.bold,
        line_pattern: args.line_pattern, line_width: args.line_width,
        angle: args.angle, text_bg: args.text_bg,
      })
      return { text: noticeState(state) }
    }),

    add_freeform: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'add_shape', path: args.path, page: args.page,
        x: args.x, y: args.y, w: args.w, h: args.h, text: args.text,
        kind: args.kind || 'rect', geometry: args.geometry,
        fill: args.fill, line: args.line, font_color: args.font_color,
        font_size: args.font_size, bold: args.bold, line_pattern: args.line_pattern,
        line_width: args.line_width, angle: args.angle,
      })
      return { text: noticeState(state) }
    }),

    move: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'move', path: args.path, page: args.page, shape_id: args.shape_id,
        x: args.x, y: args.y, w: args.w, h: args.h, angle: args.angle,
      })
      return { text: noticeState(state) }
    }),

    move_endpoint: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'move_endpoint', path: args.path, page: args.page,
        shape_id: args.shape_id, end: args.end, x: args.x, y: args.y,
      })
      return { text: noticeState(state) }
    }),

    set_end_direction: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'set_end_direction', path: args.path, page: args.page,
        shape_id: args.shape_id, end: args.end, direction: args.direction,
      })
      return { text: noticeState(state) }
    }),

    align: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'align', path: args.path, page: args.page,
        shape_ids: args.shape_ids, mode: args.mode,
      })
      return {
        text: 'aligned ' + result.moved.length + ' shape(s) by ' + result.mode + ': '
          + JSON.stringify(result.moved),
      }
    }),

    connect: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'connect', path: args.path, page: args.page, from: args.from, to: args.to,
        label: args.label ?? args.text ?? '',
        from_port: args.from_port, to_port: args.to_port,
      })
      return { text: noticeState(state) }
    }),

    connect_styled: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'connect_styled', path: args.path, page: args.page,
        from: args.from, to: args.to, label: args.label ?? args.text ?? '',
        points: args.points, line_color: args.line_color, line_pattern: args.line_pattern,
        line_width: args.line_width, from_port: args.from_port, to_port: args.to_port,
        orthogonal: args.orthogonal, within: args.within, label_pos: args.label_pos,
        allow_off_midpoint: args.allow_off_midpoint, allow_cross_shapes: args.allow_cross_shapes,
        user_approved: args.user_approved,
      })
      return {
        text: 'connector #' + result.connector + ' (' + result.points + ' waypoints, '
          + result.line_color + (result.dashed ? ', dashed' : '') + ')',
      }
    }),

    probe: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'probe', path: args.path, page: args.page, shape_id: args.shape_id,
        direction: args.direction, gap: args.gap, tol: args.tol, reach: args.reach,
      })
      return { text: JSON.stringify(result, null, 2) }
    }),

    duplicate: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'duplicate', path: args.path, page: args.page, shape_id: args.shape_id,
        direction: args.direction, gap: args.gap, connect: args.connect,
      })
      return { text: noticeState(state) }
    }),

    route_style: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'route_style', path: args.path, page: args.page,
        shape_id: args.shape_id, style: args.style,
      })
      return { text: noticeState(state) }
    }),

    set_route: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'set_route', path: args.path, page: args.page,
        shape_id: args.shape_id, points: args.points,
      })
      return { text: noticeState(state) }
    }),

    bend: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'bend', path: args.path, page: args.page,
        shape_id: args.shape_id, x: args.x, y: args.y,
      })
      return { text: noticeState(state) }
    }),

    clear_route: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'clear_route', path: args.path, page: args.page, shape_id: args.shape_id,
      })
      return { text: noticeState(state) }
    }),

    add_anchor: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'add_anchor', path: args.path, page: args.page,
        shape_id: args.shape_id, side: args.side, gap: args.gap,
      })
      return {
        text: 'anchor #' + result.anchor + ' on #' + result.shape + ' (' + result.side + ') at '
          + result.x.toFixed(3) + ', ' + result.y.toFixed(3),
      }
    }),

    swimlane: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'swimlane', path: args.path, page: args.page, nodes: args.nodes,
        title: args.title, owner: args.owner, fill: args.fill, line: args.line,
        pad_x: args.pad_x, pad_bottom: args.pad_bottom, head: args.head,
      })
      return {
        text: 'lane #' + result.lane + ' ' + JSON.stringify(result.bounds) + ' around '
          + result.nodes.length + ' node(s), pushed behind them',
      }
    }),

    normalize: withDeps(async (args, { call }) => {
      const state = await call({ action: 'normalize', path: args.path, page: args.page })
      return { text: noticeState(state) }
    }),

    validate: withDeps(async (args, { call }) => {
      const result = await call({ action: 'validate', path: args.path, page: args.page })
      const lines = result.issues.map((item) =>
        [item.level.toUpperCase(), item.code, '#' + item.shape, item.message].join(' | '))
      const head = [
        'errors ' + result.counts.error + ', warnings ' + result.counts.warn
          + ', info ' + result.counts.info,
        'shapes ' + result.shapes + ', connectors ' + result.connectors,
      ]
      return { text: head.concat(lines).join('\n') }
    }),

    audit_full: withDeps(async (args, { call }) => {
      const result = await call({ action: 'audit_full', path: args.path, page: args.page })
      const rows = (result.issues || []).map((item) =>
        [item.level.toUpperCase(), item.code, '#' + item.shape, item.message].join(' | '))
      const head = ['errors ' + result.counts.error + ', warnings ' + result.counts.warn,
        'checks: ' + (result.checks || []).join(', ')]
      const body = head.concat(rows).join('\n')
      if (args.strict && (result.counts.error > 0 || result.counts.warn > 0)) {
        throw new Error('strict audit failed\n' + body)
      }
      return { text: body }
    }),

    kinds: withDeps(async (_args, { call }) => {
      const result = await call({ action: 'kinds' })
      return { text: (result.kinds || []).map((k) => String(k)).join('\n') }
    }),

    capabilities: withDeps(async (_args, { call }) => {
      const result = await call({ action: 'capabilities' })
      return {
        text: ['actions: ' + (result.actions || []).join(', '),
          'kinds: ' + (result.kinds || []).join(', ')].join('\n'),
      }
    }),

    guide: withDeps(async (args, { call }) => {
      const guide = await call({ action: 'guide', which: args.which })
      return { text: JSON.stringify(guide, null, 2) }
    }),

    shape_list: withDeps(async (_args, { call }) => {
      const result = await call({ action: 'shape_list' })
      const rows = (result.shapes || []).map((item) => item.name
        + (item.builtin ? ' [builtin]' : ' [user]') + (item.label ? ' - ' + item.label : ''))
      return {
        text: ['shape library: ' + result.count + ' shape(s)',
          'built-in: ' + result.builtin, 'user: ' + result.user, ''].concat(rows).join('\n'),
      }
    }),

    shape_save: withDeps(async (args, { call }) => {
      const result = await call({ action: 'shape_save', name: args.name, shape: args.shape })
      return {
        text: 'cached shape "' + result.name + '" (rendered=' + result.rendered + ') at ' + result.path,
      }
    }),

    stencils: withDeps(async (args, { call }) => {
      const result = await call({ action: 'stencils', file: args.file || args.path })
      return { text: (result.masters || []).map((m) => '#' + m.id + ' ' + m.name).join('\n') }
    }),

    stencil_info: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'stencil_info', file: args.file, master: args.master,
      })
      const rows = (result.masters || []).map((m) => [
        '#' + m.id, m.name, m.prompt || '-',
        (m.width || '?') + 'x' + (m.height || '?') + 'in',
        m.shapes + ' shape(s)', m.text || '',
      ].join(' | '))
      return { text: [result.file, result.count + ' master(s)'].concat(rows).join('\n') }
    }),

    stencil_sheet: withDeps(async (args, { call }) => {
      const result = await call({ action: 'stencil_sheet', file: args.file, out: args.out })
      return { text: 'contact sheet: ' + result.out + ' (' + result.masters + ' masters)' }
    }),

    stencil_add: withDeps(async (args, { call }) => {
      const state = await call({
        action: 'stencil_add', path: args.path, page: args.page,
        stencil: args.stencil, master: args.master, x: args.x ?? 1, y: args.y ?? 1,
      })
      return { text: noticeState(state) }
    }),

    snapshot: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'snapshot', path: args.path, page: args.page,
        all: args.all === true, dpi: args.dpi, out: args.out,
        review: args.review === true,
      })
      const lines = ['rendered ' + result.pages + ' page(s):'].concat(result.files)
      if (result.report) {
        lines.push('', 'review: errors ' + result.report.counts.error
          + ', warnings ' + result.report.counts.warn
          + (result.report.counts.info ? ', info ' + result.report.counts.info : ''))
        for (const item of result.report.issues) {
          lines.push([item.level.toUpperCase(), item.code, '#' + item.shape, item.message].join(' | '))
        }
      }
      return { text: lines.join('\n') }
    }),

    export: withDeps(async (args, { call }) => {
      const result = await call({
        action: 'export', path: args.path, page: args.page,
        format: args.format ?? 'svg', out: args.out, dpi: args.dpi,
      })
      return { text: 'exported: ' + result.out }
    }),

    undo: withDeps(async (args, { call }) => {
      const state = await call({ action: 'undo', path: args.path, page: args.page })
      return { text: noticeState(state) }
    }),

    redo: withDeps(async (args, { call }) => {
      const state = await call({ action: 'redo', path: args.path, page: args.page })
      return { text: noticeState(state) }
    }),
  }
}

function registerAgentTool(ctx, config) {
  const tools = ctx.get('tools') ?? ctx.tools
  if (typeof tools?.register !== 'function') return undefined
  const handlers = buildHandlers(ctx, config)
  return tools.register({
    name: 'visio',
    description: ACTION_HELP,
    parameters: toolParameters(Object.keys(handlers)),
    output: {
      schema: {
        type: 'object',
        properties: { text: { type: 'string' } },
        required: ['text'],
        additionalProperties: false,
      },
      render: (_args, value) => [{ type: 'text', text: String(value?.text ?? '') }],
    },
    async execute(args) {
      const action = typeof args?.action === 'string' ? args.action : ''
      const handler = handlers[action]
      if (!handler) {
        throw new Error('visio: unknown action "' + action + '". Available: '
          + Object.keys(handlers).join(', '))
      }
      try {
        return await handler(args)
      } catch (error) {
        // A failed drawing edit must fail the tool call: returning "visio failed: ..."
        // as ordinary output made the model believe the edit had been applied.
        throw new Error('visio ' + action + ' failed: ' + messageOf(error))
      }
    },
  })
}

/* -------------------------------------------------------------------- apply */

export function apply(ctx, config = {}) {
  ctx.effect(() => () => disposePools(), 'dsh-visio: bridge pool')
  ctx.inject(['tools'], (toolCtx) => {
    toolCtx.effect(() => {
      try {
        const dispose = registerAgentTool(toolCtx, config)
        return typeof dispose === 'function' ? dispose : () => {}
      } catch (error) {
        try {
          toolCtx.logger('dsh-visio').warn(`agent tool not registered: ${messageOf(error)}`)
        } catch {
          /* logging is optional */
        }
        return () => {}
      }
    }, 'dsh-visio: agent tool')
  })

  ctx.inject(['webServer'], (hostCtx) => {
    const webServer = hostCtx.webServer
    if (typeof webServer?.register !== 'function') return
    const stops = new PathStops()
    stops.add(defaultFolder(ctx, config))
    const routes = [
      route(ctx, `${ROUTE_PREFIX}/config`, ['GET'], async ({ response }) => {
        const folder = defaultFolder(ctx, config)
        let pythonOk = true
        try {
          await runBridge(config, { action: 'ping' })
        } catch {
          pythonOk = false
        }
        let folderOk = true
        try {
          await access(folder)
        } catch {
          folderOk = false
        }
        json(response, 200, {
          ok: true,
          defaultFolder: folder,
          folderOk,
          python: pythonOf(config),
          pythonOk,
          engine: `visio_bridge/${pkg.version}`,
        })
      }),
      route(ctx, `${ROUTE_PREFIX}/op`, ['POST'], async ({ request, response }) => {
        if (!sameOrigin(request)) {
          json(response, 403, { ok: false, error: 'Cross-origin request refused.' })
          return
        }
        const body = await readBody(request)
        if (typeof body.action !== 'string' || !body.action) throw new BadRequest('action is required.')
        if (body.path !== undefined && typeof body.path === 'string' && !isAbsolute(body.path)) {
          body.path = resolve(defaultFolder(ctx, config), body.path)
        }
        guardRequest(stops, body, ctx, config)
        const result = await runBridge(config, body)
        rememberPaths(stops, result)
        json(response, 200, result)
      }),
    ]
    for (const entry of routes) {
      hostCtx.effect(() => webServer.register(entry), `dsh-visio: ${entry.path}`)
    }
  })
}

export const internals = {
  engineFingerprint, runBridge, formatState, pythonOf, defaultFolder, disposePools,
  toolParameters, buildHandlers, PathStops, guardRequest, rememberPaths, TOOL_PARAMS,
  registerTool: registerAgentTool }
