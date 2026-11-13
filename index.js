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
import { statSync, readFileSync } from 'node:fs'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROUTE_PREFIX = '/dsh-visio'
const BODY_LIMIT = 1024 * 1024
const STDOUT_LIMIT = 32 * 1024 * 1024
const ENGINE_TIMEOUT_MS = 30000

const here = dirname(fileURLToPath(import.meta.url))
// Read the manifest once so /config reports the same build as the panel footer.
const pkg = JSON.parse(readFileSync(join(here, 'package.json'), 'utf8'))
const BRIDGE = join(here, 'engine', 'visio_bridge.py')

const ENGINE_FILES = ['vsdx_core.py', 'visio_bridge.py', 'kinds.py', 'stencil.py', 'blank_doc.py', 'vsdx_png.py']


/**
 * mtime+size of every engine module. The bridge pool keeps one Python child
 * alive for speed, so an edited engine would otherwise keep serving the code it
 * imported at spawn time — the panel would silently render with stale logic.
 */
function engineFingerprint() {
  try {
    return ENGINE_FILES.map((name) => {
      const info = statSync(join(here, 'engine', name))
      return `${name}:${Math.round(info.mtimeMs)}:${info.size}`
    }).join('|')
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

const TOOL_PARAMETERS = {
  type: 'object',
  properties: {
    action: {
      type: 'string',
      enum: ['open', 'text', 'get_shape', 'create', 'list', 'set_text', 'set_cell', 'set_prop',
        'add_shape', 'move', 'connect', 'probe', 'duplicate', 'route_style', 'bend',
        'clear_route', 'delete', 'validate', 'kinds', 'stencils',
        'add_anchor', 'swimlane', 'move_endpoint', 'set_end_direction', 'stencil_add', 'stencil_info', 'stencil_sheet', 'snapshot', 'capabilities',
        'undo', 'redo', 'normalize', 'export'],
      description:
        'open reads a drawing (pages, page size, shapes with ids/text/bbox, and a text outline); '
        + 'text dumps every page as markdown; get_shape returns every ShapeSheet cell of one shape; '
        + 'list lists .vsdx/.vsdm files in a folder; create builds a new blank drawing; '
        + 'set_text / set_cell / set_prop / add_shape / move / connect / delete modify the file in place; '
        + 'validate audits relationships (empty links, floating endpoints, dangling ids); '
        + 'kinds lists the 16 built-in shape kinds; stencils / stencil_info / stencil_sheet / stencil_add '
        + 'list, describe, contact-sheet and import a .vssx/.vstx master; '
        + 'snapshot renders every page to PNG; capabilities lists this surface; '
        + 'undo / redo step through the edit history (25 steps); export writes an SVG or PNG preview.',
    },
    path: { type: 'string', description: 'Absolute path to the .vsdx/.vsdm file.' },
    page: { type: 'integer', description: '1-based page number; defaults to 1.' },
    shape_id: { type: 'string', description: 'Shape ID as reported by open/get_shape.' },
    text: { type: 'string', description: 'New shape text for set_text, or the label of a new shape/connector.' },
    cell: { type: 'string', description: 'ShapeSheet cell name for set_cell, e.g. FillForegnd, LineColor, LineWeight, PinX, Width.' },
    name: { type: 'string', description: 'Shape-data property name for set_prop.' },
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
    direction: { type: 'string', enum: ['right', 'left', 'up', 'down'],
      description: 'probe / duplicate: which side of the shape to look at or copy onto.' },
    gap: { type: 'number', description: 'duplicate: inches between the source and the copy (default 0.4).' },
    connect: { type: 'boolean', description: 'duplicate: glue a connector to the copy (default true).' },
    style: { type: 'string', enum: ['auto', 'up', 'down', 'left', 'right'],
      description: 'route_style: which way a connector should detour (auto = back to automatic routing).' },
    file: { type: 'string', description: 'Path to a .vssx/.vstx stencil for stencil_info / stencil_sheet / stencils.' },
    all: { type: 'boolean', description: 'snapshot: render every page (default: current page only).' },
    dpi: { type: 'number', description: 'snapshot: pixels per inch (default 110).' },
    x: { type: 'number', description: 'Left edge in inches (origin bottom-left) for add_shape.' },
    y: { type: 'number', description: 'Bottom edge in inches for add_shape.' },
    w: { type: 'number', description: 'Width in inches for add_shape.' },
    h: { type: 'number', description: 'Height in inches for add_shape.' },
    from: { type: 'string', description: 'Source shape id for connect.' },
    to: { type: 'string', description: 'Target shape id for connect.' },
    from_port: { type: 'array', items: { type: 'number' }, description: 'connect / connect_styled: [x,y] in sheet inches that pins the START to an exact point (read a connection point with get_shape) instead of letting the router choose a side.' },
    to_port: { type: 'array', items: { type: 'number' }, description: 'connect / connect_styled: [x,y] in sheet inches that pins the END to an exact point — use it so an arrow lands dead-centre on a border instead of diving inside the shape.' },
    label: { type: 'string', description: 'Optional text on the new connector.' },
    side: { type: 'string', enum: ['top', 'bottom', 'left', 'right'], description: 'add_anchor: which side of the shape to hang the invisible anchor on (default top).' },
    nodes: { type: 'array', items: { type: 'string' }, description: 'swimlane: shape ids that belong to the row. The band is sized from their bounding box, so it can never clip them.' },
    owner: { type: 'string', description: 'swimlane: owner line next to the title, e.g. ｜市场 PM · 库制作人.' },
    pad_x: { type: 'number', description: 'swimlane: horizontal padding around the nodes (default 0.45in).' },
    pad_bottom: { type: 'number', description: 'swimlane: space under the nodes (default 0.30in).' },
    head: { type: 'number', description: 'swimlane: header height above the nodes (default 0.42in).' },
    orthogonal: { type: 'boolean', description: 'connect_styled: reject diagonal segments instead of drawing them (default true). Pass false only for a deliberate diagonal.' },
    within: { type: 'array', items: { type: 'number' }, description: 'connect_styled: [x, y, w, h] in inches. Every waypoint must stay inside this box (e.g. a lane) or the call is rejected.' },
    label_pos: { description: 'connect_styled: where the label goes — auto | above | below | left | right | [x, y] in inches. Non-auto modes nudge the label off any shape it would cover.' },
    allow_cross_shapes: { type: 'boolean', description: 'connect_styled: allow a segment to pass through an unrelated shape. Requires user_approved=true — ask the user first.' },
    allow_off_midpoint: { type: 'boolean', description: 'connect_styled: allow an end to sit on a shape border away from the four side midpoints. Requires user_approved=true — ask the user first and quote their approval.' },
    user_approved: { type: 'boolean', description: 'Set only after the user explicitly agreed to bypass the midpoint rule in this conversation.' },
    strict: { type: 'boolean', description: 'audit_full: fail (ok=false) when any error or warning remains.' },
    dir: { type: 'string', description: 'Folder to list, or to create the new drawing in.' },
    title: { type: 'string', description: 'Document title for create; also drawn as the heading.' },
    width: { type: 'number', description: 'Page width in inches for create (default 11).' },
    height: { type: 'number', description: 'Page height in inches for create (default 8.5).' },
    format: { type: 'string', enum: ['svg', 'png'], description: 'Export format for export; default svg.' },
    out: { type: 'string', description: 'Output path for export; defaults next to the drawing.' },
    geometry: { type: 'array', description: 'add_shape escape hatch: [[x,y],...] vertices in 0..1 fractions of w/h (or absolute inches >1.5). Overrides kind; use it to compose ANY silhouette (arrow heads, gates) when the 16 kinds and shape library are not enough.' },
    font_color: { type: 'string', description: 'add_shape: #RRGGBB text colour. White on a dark fill gives the professional two-line look.' },
    font_size: { type: 'number', description: 'add_shape: font size in points (default 11).' },
    bold: { type: 'boolean', description: 'add_shape: bold first text line (default true).' },
    line_pattern: { type: 'integer', description: 'add_shape: 1 solid, 2 dashed, 0 none.' },
    line_width: { type: 'number', description: 'add_shape / connect: line width in inches. Use ~0.02 on a generated diagram so short arrows stay visible.' },
    line_color: { type: 'string', description: 'connect: #RRGGBB line colour. Use different colours for normal flow / rework / cross-lane links.' },
    points: { type: 'array', description: 'connect_styled / set_route: orthogonal waypoints [[x,y],...] in sheet inches for a deliberate cross-lane route.' },
    text_bg: { type: 'boolean', description: 'add_shape: true = white text background, false = transparent. Use true on labels over lines; leave false on dark filled nodes.' },
    angle: { type: 'number', description: 'add_shape/move: rotation in degrees, counter-clockwise.' },
    shape_ids: { type: 'array', description: 'align: list of shape ids to snap together.' },
    mode: { type: 'string', enum: ['edges', 'centres', 'ports'], description: 'align: which reference lines to snap to.' },
    end: { type: 'string', enum: ['start', 'end'], description: 'move_endpoint / set_end_direction: which end of the connector to adjust.' },
    direction: { type: 'string', enum: ['top', 'bottom', 'left', 'right'], description: 'set_end_direction: which side of the shape the connector end should leave from.' },
    shape: { type: 'object', description: 'shape_save: the shape spec to cache (must contain kind or geometry).' },
    review: { type: 'boolean', description: 'snapshot: attach a structured overlap/out-of-page/text-overflow/connectivity report. Use review=true as the CHECK STAGE of every drawing task.' },
  },
  required: ['action'],
  additionalProperties: false,
}

function formatState(state) {
  const lines = []
  const pages = state.pages ?? []
  lines.push(`file: ${state.path}`)
  lines.push(`page ${state.page}/${state.pageCount} "${state.pageName}" — ${state.pageSize.w.toFixed(2)} x ${state.pageSize.h.toFixed(2)} in`)
  lines.push(`pages: ${pages.map((p) => `${p.index}:${p.name}`).join(', ')}`)
  if (Array.isArray(state.masters) && state.masters.length) {
    lines.push(`masters: ${state.masters.map((m) => m.name).filter(Boolean).join(', ')}`)
  }
  const shapes = state.shapes ?? []
  lines.push(`shapes on this page: ${shapes.length}`)
  for (const shape of shapes.slice(0, 60)) {
    const bb = shape.bbox ?? {}
    const kind = shape.connector ? 'connector' : (shape.master || shape.geometry?.[0] || 'shape')
    lines.push(
      `- #${shape.id} [${kind}] ${JSON.stringify(shape.text ?? '')} `
      + `bbox ${bb.x},${bb.y} ${bb.w}x${bb.h}`
      + (shape.connects?.length ? ` -> ${shape.connects.map((c) => c.to).join(',')}` : ''),
    )
  }
  if (shapes.length > 60) lines.push(`… ${shapes.length - 60} more shapes`)
  if (state.notice) lines.push('', `notice: ${state.notice}`)
  return lines.join('\n')
}

function registerAgentTool(ctx, config) {
  const tools = ctx.get('tools') ?? ctx.tools
  if (typeof tools?.register !== 'function') return undefined
  return tools.register({
    name: 'visio',
    description:
      'Read, edit, create and export Microsoft Visio .vsdx drawings without Visio installed. '
      + 'Coordinates are inches with the origin at the bottom-left of the page; shape bbox = {x,y,w,h}. '
      + 'open returns pages, page size, shape ids with text and bbox, and a text outline. '
      + 'Edits save in place and keep a bounded .bak-<timestamp> history. '
      + 'The DSH Visio panel in the sidebar edits the same files visually.',
    parameters: TOOL_PARAMETERS,
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
      const action = args?.action
      try {
        if (action === 'open') {
          const state = await runBridge(config, { action: 'open', path: args.path, page: args.page })
          const outline = await runBridge(config, { action: 'text', path: args.path })
          return { text: `${formatState(state)}\n\n${outline.text}` }
        }
        if (action === 'text') {
          const result = await runBridge(config, { action: 'text', path: args.path })
          return { text: result.text }
        }
        if (action === 'get_shape') {
          const result = await runBridge(config, {
            action: 'get_shape',
            path: args.path,
            page: args.page,
            shape_id: args.shape_id,
          })
          return { text: JSON.stringify(result.detail, null, 2) }
        }
        if (action === 'list') {
          const result = await runBridge(config, { action: 'list', dir: args.dir ?? defaultFolder(ctx, config) })
          const files = result.files ?? []
          return {
            text: files.length
              ? files.map((file) => `${file.name}\t${file.size} bytes\t${file.path}`).join('\n')
              : `no .vsdx/.vsdm files in ${result.dir}`,
          }
        }
        if (action === 'create') {
          const result = await runBridge(config, {
            action: 'create',
            dir: args.dir ?? defaultFolder(ctx, config),
            name: args.title || 'drawing',
            title: args.title,
            width: args.width,
            height: args.height,
          })
          return { text: `${formatState(result)}\n\ncreated: ${result.path}` }
        }
        if (action === 'set_text' || action === 'set_cell' || action === 'set_prop' || action === 'delete') {
          const bridgeAction = action === 'set_cell' ? 'set_cells' : action
          const payload = { action: bridgeAction, path: args.path, page: args.page, shape_id: args.shape_id }
          if (action === 'set_text') payload.text = args.text
          if (action === 'set_cell') {
            payload.cells = { [String(args.cell)]: String(args.value ?? '') }
          }
          if (action === 'set_prop') {
            payload.name = args.name
            payload.value = String(args.value ?? '')
          }
          const state = await runBridge(config, payload)
          return { text: `${state.notice}\n\n${formatState(state)}` }
        }
        if (action === 'add_shape') {
          const state = await runBridge(config, {
            action: 'add_shape',
            path: args.path,
            page: args.page,
            kind: args.kind ?? 'rect',
            x: args.x ?? 1,
            y: args.y ?? 1,
            w: args.w ?? 1.6,
            h: args.h ?? 0.8,
            text: args.text ?? '',
            // Styling used to exist only on add_freeform, so every coloured node
            // had to go through the escape hatch.  One shape API, not two.
            fill: args.fill, line: args.line,
            font_color: args.font_color, font_size: args.font_size, bold: args.bold,
            line_pattern: args.line_pattern, line_width: args.line_width,
            angle: args.angle, text_bg: args.text_bg,
          })
          return { text: `${state.notice}\n\n${formatState(state)}` }
        }
        if (action === 'connect') {
          const state = await runBridge(config, {
            action: 'connect',
            path: args.path,
            page: args.page,
            from: args.from,
            to: args.to,
            label: args.label ?? args.text ?? '',
            from_port: args.from_port,
            to_port: args.to_port,
          })
          return { text: `${state.notice}\n\n${formatState(state)}` }
        }
        if (action === 'normalize') {
          const state = await runBridge(config, { action: 'normalize', path: args.path, page: args.page })
          return { text: `${state?.notice ?? 'units normalised'}
${formatState(state)}`.trim() }
        }
        if (action === 'validate') {
          const result = await runBridge(config, { action: 'validate', path: args.path, page: args.page })
          const lines = result.issues.map((item) =>
            [item.level.toUpperCase(), item.code, '#' + item.shape, item.message].join(' | '))
          const head = [
            'errors ' + result.counts.error + ', warnings ' + result.counts.warn + ', info ' + result.counts.info,
            'shapes ' + result.shapes + ', connectors ' + result.connectors,
          ]
          return { text: head.concat(lines).join(String.fromCharCode(10)) }
        }
        if (action === 'kinds') {
          const result = await runBridge(config, { action: 'kinds' })
          const rows = (result.kinds || []).map((k) => String(k))
          return { text: rows.join(String.fromCharCode(10)) }
        }
        if (action === 'capabilities') {
          const result = await runBridge(config, { action: 'capabilities' })
          const rows = [
            'actions: ' + (result.actions || []).join(', '),
            'kinds: ' + (result.kinds || []).join(', '),
          ]
          return { text: rows.join(String.fromCharCode(10)) }
        }
        if (action === 'stencil_info') {
          const result = await runBridge(config, { action: 'stencil_info', file: args.file, master: args.master })
          const rows = (result.masters || []).map((m) => [
            '#' + m.id, m.name, m.prompt || '-', (m.width || '?') + 'x' + (m.height || '?') + 'in',
            m.shapes + ' shape(s)', m.text || '',
          ].join(' | '))
          return { text: [result.file, result.count + ' master(s)'].concat(rows).join(String.fromCharCode(10)) }
        }
        if (action === 'stencil_sheet') {
          const result = await runBridge(config, { action: 'stencil_sheet', file: args.file, out: args.out })
          return { text: 'contact sheet: ' + result.out + ' (' + result.masters + ' masters)' }
        }
        if (action === 'snapshot') {
          const result = await runBridge(config, {
            action: 'snapshot', path: args.path, page: args.page, all: args.all === true, dpi: args.dpi, out: args.out,
          })
          return { text: ['rendered ' + result.pages + ' page(s):'].concat(result.files).join(String.fromCharCode(10)) }
        }
        if (action === 'stencils') {
          const result = await runBridge(config, { action: 'stencil_list', file: args.file || args.path })
          const rows = (result.masters || []).map((m) => '#' + m.id + ' ' + m.name)
          return { text: rows.join(String.fromCharCode(10)) }
        }
        if (action === 'guide') {
          const g = await runBridge(config, { action: 'guide', which: args.which })
          return { text: JSON.stringify(g, null, 2) }
        }
        if (action === 'shape_list') {
          const r = await runBridge(config, { action: 'shape_list' })
          const rows = (r.shapes || []).map((x) => x.name + (x.builtin ? ' [builtin]' : ' [user]') + (x.label ? ' — ' + x.label : ''))
          return { text: ['shape library: ' + r.count + ' shape(s)', 'built-in: ' + r.builtin, 'user: ' + r.user, ''].concat(rows).join(String.fromCharCode(10)) }
        }
        if (action === 'shape_save') {
          const r = await runBridge(config, { action: 'shape_save', name: args.name, shape: args.shape })
          return { text: 'cached shape "' + r.name + '" (rendered=' + r.rendered + ') at ' + r.path }
        }
        if (action === 'audit_full' || action === 'validate') {
          const r = await runBridge(config, { action, path: args.path, page: args.page })
          const rows = (r.issues || []).map((i) => [i.level.toUpperCase(), i.code, '#' + i.shape, i.message].join(' | '))
          const head = ['errors ' + r.counts.error + ', warnings ' + r.counts.warn,
            action === 'audit_full' ? 'checks: ' + (r.checks || []).join(', ') : '']
          return { text: head.filter(Boolean).concat(rows).join(String.fromCharCode(10)) }
        }
        if (action === 'connect_styled') {
          const r = await runBridge(config, { action: 'connect_styled', path: args.path, page: args.page,
            from: args.from, to: args.to, label: args.label ?? args.text ?? '',
            points: args.points, line_color: args.line_color, line_pattern: args.line_pattern,
            line_width: args.line_width,
            line_width: args.line_width, from_port: args.from_port, to_port: args.to_port,
            orthogonal: args.orthogonal, within: args.within, label_pos: args.label_pos,
            allow_off_midpoint: args.allow_off_midpoint, allow_cross_shapes: args.allow_cross_shapes,
            user_approved: args.user_approved })
          return { text: 'connector #' + r.connector + ' (' + r.points + ' waypoints, ' + r.line_color + (r.dashed ? ', dashed' : '') + ')' }
        }
        if (action === 'add_anchor') {
          const r = await runBridge(config, { action: 'add_anchor', path: args.path, page: args.page,
            shape_id: args.shape_id, side: args.side, gap: args.gap })
          return { text: 'anchor #' + r.anchor + ' on #' + r.shape + ' (' + r.side + ') at '
            + r.x.toFixed(3) + ', ' + r.y.toFixed(3) }
        }
        if (action === 'swimlane') {
          const r = await runBridge(config, { action: 'swimlane', path: args.path, page: args.page,
            nodes: args.nodes, title: args.title, owner: args.owner, fill: args.fill, line: args.line,
            pad_x: args.pad_x, pad_bottom: args.pad_bottom, head: args.head })
          return { text: 'lane #' + r.lane + ' ' + JSON.stringify(r.bounds) + ' around '
            + r.nodes.length + ' node(s), pushed behind them' }
        }
        if (action === 'move_endpoint') {
          const state = await runBridge(config, { action: 'move_endpoint', path: args.path, page: args.page,
            shape_id: args.shape_id, end: args.end, x: args.x, y: args.y })
          return { text: `${state.notice}\n\n${formatState(state)}` }
        }
        if (action === 'set_end_direction') {
          const state = await runBridge(config, { action: 'set_end_direction', path: args.path, page: args.page,
            shape_id: args.shape_id, end: args.end, direction: args.direction })
          return { text: `${state.notice}\n\n${formatState(state)}` }
        }
        if (action === 'align') {
          const r = await runBridge(config, { action: 'align', path: args.path, page: args.page, shape_ids: args.shape_ids, mode: args.mode })
          return { text: 'aligned ' + r.moved.length + ' shape(s) by ' + r.mode + ': ' + JSON.stringify(r.moved) }
        }
        if (action === 'add_freeform') {
          const state = await runBridge(config, { action: 'add_shape', path: args.path, page: args.page,
            x: args.x, y: args.y, w: args.w, h: args.h, text: args.text, kind: args.kind || 'rect',
            geometry: args.geometry, fill: args.fill, line: args.line, font_color: args.font_color,
            font_size: args.font_size, bold: args.bold, line_pattern: args.line_pattern,
            line_width: args.line_width, angle: args.angle })
          return { text: state.notice + String.fromCharCode(10) + String.fromCharCode(10) + formatState(state) }
        }
        if (action === 'stencil_add') {
          const state = await runBridge(config, {
            action: 'stencil_add', path: args.path, page: args.page,
            stencil: args.stencil, master: args.master, x: args.x ?? 1, y: args.y ?? 1,
          })
          return { text: (state.notice || 'master inserted') + String.fromCharCode(10) + String.fromCharCode(10) + formatState(state) }
        }
        if (action === 'move') {
          const state = await runBridge(config, {
            action: 'move', path: args.path, page: args.page, shape_id: args.shape_id,
            x: args.x, y: args.y, w: args.w, h: args.h,
          })
          return { text: `${state.notice}

${formatState(state)}` }
        }
        if (action === 'undo' || action === 'redo') {
          const state = await runBridge(config, { action, path: args.path, page: args.page })
          return { text: `${state.notice ?? action}

${formatState(state)}` }
        }
        if (action === 'export') {
          const result = await runBridge(config, {
            action: 'export',
            path: args.path,
            page: args.page,
            format: args.format ?? 'svg',
            out: args.out,
          })
          return { text: `exported: ${result.out}` }
        }
        return { text: 'Unknown action.' }
      } catch (error) {
        return { text: `visio failed: ${messageOf(error)}` }
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
        const result = await runBridge(config, body)
        json(response, 200, result)
      }),
    ]
    for (const entry of routes) {
      hostCtx.effect(() => webServer.register(entry), `dsh-visio: ${entry.path}`)
    }
  })
}

export const internals = {
  engineFingerprint, runBridge, formatState, pythonOf, defaultFolder, disposePools }
