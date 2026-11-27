/**
 * Host contract tests: the tool schema, the action table, the /op path guard and
 * the bridge payloads.  No DSH host and no Python needed.
 *
 * Run:  node tests/test_host_contract.mjs
 */
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { internals } from '../index.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = dirname(HERE)
const results = []

async function check(name, fn) {
  try {
    await fn()
    results.push([true, name, ''])
  } catch (error) {
    results.push([false, name, error instanceof Error ? error.message : String(error)])
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

const ctx = { get: () => undefined }
const config = {}
const handlers = internals.buildHandlers(ctx, config)
const actions = Object.keys(handlers)

/** Collect the bridge actions the engine actually implements. */
function bridgeActions() {
  const source = readFileSync(join(ROOT, 'engine', 'visio_bridge.py'), 'utf8')
  const block = source.slice(source.indexOf('ACTIONS = {'))
  const body = block.slice(0, block.indexOf('\n}'))
  return new Set([...body.matchAll(/^\s*"([a-z_]+)":/gm)].map((m) => m[1]))
}

await check('action table: the schema enum is generated from the handlers', () => {
  const schema = internals.toolParameters(actions)
  const advertised = schema.properties.action.enum
  assert(Array.isArray(advertised) && advertised.length === actions.length,
    'enum length ' + (advertised || []).length + ' != ' + actions.length)
  assert(new Set(advertised).size === advertised.length, 'duplicate action in the enum')
  assert(!advertised.includes('connect_styled') || actions.includes('connect_styled'),
    'schema advertises an action with no handler')
  assert(schema.additionalProperties === false, 'schema must stay strict')
})

await check('action table: every advertised action exists in the engine', () => {
  const available = bridgeActions()
  const alias = {
    set_cell: 'set_cells',
    add_freeform: 'add_shape',
    audit_full: 'audit_full',
  }
  const missing = actions
    .map((action) => alias[action] || action)
    .filter((action) => !available.has(action))
  assert(missing.length === 0, 'advertised but not implemented by the bridge: ' + missing.join(', '))
})

await check('action table: every args.X a handler reads is declared in the schema', () => {
  const source = internals.buildHandlers.toString()
  const used = new Set([...source.matchAll(/args\.([A-Za-z_][A-Za-z0-9_]*)/g)].map((m) => m[1]))
  const declared = new Set(Object.keys(internals.TOOL_PARAMS))
  const undeclared = [...used].filter((name) => !declared.has(name))
  assert(undeclared.length === 0,
    'read by a handler but dropped by additionalProperties:false -> ' + undeclared.join(', '))
  assert(declared.has('fill') && declared.has('line') && declared.has('which') && declared.has('review'),
    'the parameters that used to be missing are still missing')
})

await check('snapshot: review and dpi reach the engine', async () => {
  let sent = null
  await handlers.snapshot({ path: 'C:/x/y.vsdx', page: 1, review: true, dpi: 200 },
    { call: async (payload) => { sent = payload; return { pages: 1, files: ['a.png'], report: { counts: { error: 0, warn: 0, info: 0 }, issues: [] } } } })
  assert(sent, 'no bridge call')
  assert(sent.review === true, 'review was dropped before the engine saw it')
  assert(sent.dpi === 200, 'dpi was dropped')
})

await check('snapshot: the review report is rendered into the tool text', async () => {
  const out = await handlers.snapshot({ path: 'C:/x/y.vsdx', review: true },
    { call: async () => ({ pages: 1, files: ['a.png'], report: { counts: { error: 1, warn: 0, info: 0 }, issues: [{ level: 'error', code: 'overlap', shape: '3', message: 'overlaps #4' }] } }) })
  assert(out.text.includes('review: errors 1'), out.text)
  assert(out.text.includes('overlap'), out.text)
})

await check('add_shape: fill/line/font styling reaches the engine', async () => {
  let sent = null
  await handlers.add_shape({ path: 'C:/x/y.vsdx', kind: 'rect', x: 1, y: 1, w: 2, h: 1,
    fill: '#17365D', line: '#8A3D12', font_color: '#FFFFFF', text_bg: true, bold: true },
  { call: async (payload) => { sent = payload; return { notice: '', pages: [], shapes: [], page: 1, pageCount: 1, pageName: 'p', pageSize: { w: 1, h: 1 }, path: 'C:/x/y.vsdx' } } })
  assert(sent.fill === '#17365D' && sent.line === '#8A3D12', JSON.stringify(sent))
})

await check('errors: a failed edit rejects instead of returning text', async () => {
  let threw = false
  try {
    await handlers.set_text({ path: 'C:/x/y.vsdx', shape_id: '9', text: 'x' },
      { call: async () => { throw new Error('shape 9 not found') } })
  } catch {
    threw = true
  }
  assert(threw, 'a failing bridge call resolved as success')
})

await check('errors: the registered tool throws on an unknown action', async () => {
  let definition = null
  const toolsCtx = {
    get: () => ({ register: (def) => { definition = def; return () => {} } }),
    effect: (fn) => fn(),
    logger: () => ({ warn: () => {} }),
  }
  internals.registerTool(toolsCtx, config)
  assert(definition, 'the tool was not registered')
  assert(JSON.stringify(definition.parameters.properties.action.enum)
    === JSON.stringify(Object.keys(internals.buildHandlers(toolsCtx, config))),
  'registered enum drifted from the handler table')
  let threw = false
  try {
    await definition.execute({ action: 'nope' })
  } catch {
    threw = true
  }
  assert(threw, 'unknown action resolved as a normal result')
})

await check('fingerprint: every engine module is watched', () => {
  const files = readdirSync(join(ROOT, 'engine')).filter((n) => n.endsWith('.py') || n.endsWith('.json'))
  const fingerprint = internals.engineFingerprint()
  const missing = files.filter((name) => !fingerprint.includes(name + ':'))
  assert(missing.length === 0, 'not watched, so an edit would keep serving stale code: ' + missing.join(', '))
})

await check('path guard: writes stay inside the folders the user opened', () => {
  const stops = new internals.PathStops()
  stops.add('C:/work/drawings')
  assert(stops.covers('C:/work/drawings/a.vsdx'), 'a file in the opened folder must be allowed')
  assert(stops.covers('C:/work/drawings/sub/a.vsdx'), 'a subfolder must be allowed')
  assert(!stops.covers('C:/work/other/a.vsdx'), 'a sibling folder must not be allowed')
  assert(!stops.covers('C:/work/drawings/../other/a.vsdx'), '.. must not escape the folder')
  assert(!stops.covers('C:/Windows/System32/x.svg'), 'an unrelated folder must not be allowed')
})

await check('path guard: export refuses another suffix and an outside folder', () => {
  const stops = new internals.PathStops()
  stops.add('C:/work/drawings')
  const bad = [
    { action: 'export', path: 'C:/work/drawings/a.vsdx', format: 'svg', out: 'C:/work/drawings/a.txt' },
    { action: 'export', path: 'C:/work/drawings/a.vsdx', format: 'png', out: 'C:/work/drawings/a.svg' },
    { action: 'export', path: 'C:/work/drawings/a.vsdx', format: 'svg', out: 'C:/Windows/x.svg' },
    { action: 'create', dir: 'C:/Windows/System32', name: 'x' },
    { action: 'snapshot', path: 'C:/work/drawings/a.vsdx', out: 'C:/Windows' },
  ]
  for (const body of bad) {
    let threw = false
    try {
      internals.guardRequest(stops, body, ctx, config)
    } catch {
      threw = true
    }
    assert(threw, 'allowed: ' + JSON.stringify(body))
  }
  const ok = { action: 'export', path: 'C:/work/drawings/a.vsdx', format: 'svg', out: 'preview.svg' }
  internals.guardRequest(stops, ok, ctx, config)
  assert(/[/\\]work[/\\]drawings[/\\]preview\.svg$/i.test(ok.out),
    'a relative out must be anchored next to the drawing, got ' + ok.out)
})

await check('path guard: only a successful listing widens the write surface', () => {
  const stops = new internals.PathStops()
  const listBody = { action: 'list', dir: 'C:/work/picked' }
  internals.guardRequest(stops, listBody, ctx, config)
  let refused = false
  try {
    internals.guardRequest(stops, { action: 'create', dir: 'C:/work/picked', name: 'fresh' }, ctx, config)
  } catch {
    refused = true
  }
  assert(refused, 'an attempted (not yet successful) listing already unlocked the folder')
  internals.rememberPaths(stops, { dir: 'C:/work/picked' })
  internals.guardRequest(stops, { action: 'create', dir: 'C:/work/picked', name: 'fresh' }, ctx, config)
  assert(stops.covers('C:/work/picked/fresh.vsdx'), 'create was refused after a successful listing')
})

let bad = 0
for (const [ok, name, message] of results) {
  console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : '  <- ' + message))
  bad += ok ? 0 : 1
}
console.log('\n' + (results.length - bad) + '/' + results.length + ' ok')
process.exit(bad ? 1 : 0)
