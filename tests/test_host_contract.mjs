/**
 * Contract test for the Host half: tool registration, both HTTP routes, and a real
 * round trip through the Python bridge (spawned exactly as the plugin spawns it).
 *
 *   node tests/test_host_contract.mjs
 */
import { existsSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

import { apply, internals } from '../index.js'

const here = dirname(fileURLToPath(import.meta.url))
const out = join(here, '_out')
rmSync(out, { recursive: true, force: true })
mkdirSync(out, { recursive: true })

const tools = []
const routes = []
const context = {
  get(name) {
    if (name === 'tools') return { register: (definition) => { tools.push(definition); return () => {} } }
    if (name === 'workingDirectory') return { defaultDirectory: out }
    return undefined
  },
  inject(deps, callback) {
    assert.ok(deps.includes('tools') || deps.includes('webServer'), `unexpected inject ${deps}`)
    callback(context)
  },
  effect(fn) { const dispose = fn(); return typeof dispose === 'function' ? dispose : () => {} },
  logger: () => ({ warn: () => {} }),
  webServer: { register: (route) => { routes.push(route); return () => {} } },
}

apply(context, {})

// ---- tool contract --------------------------------------------------------
assert.equal(tools.length, 1, 'exactly one tool should register')
const tool = tools[0]
assert.equal(tool.name, 'visio')
assert.ok(tool.description.includes('.vsdx'))
const actions = tool.parameters.properties.action.enum
for (const action of ['open', 'text', 'get_shape', 'create', 'list', 'set_text', 'set_cell', 'set_prop', 'add_shape', 'connect', 'delete', 'export']) {
  assert.ok(actions.includes(action), `tool is missing action ${action}`)
}
assert.deepEqual(Object.keys(tool.parameters.properties).sort(), [
  'action', 'all', 'cell', 'dpi', 'dir', 'file', 'format', 'from', 'h', 'height', 'kind', 'label',
  'master', 'name', 'out', 'page', 'path', 'shape_id', 'stencil', 'text', 'title', 'to', 'value',
  'w', 'width', 'x', 'y',
].sort())

const call = async (args) => {
  const result = await tool.execute(args)
  assert.equal(typeof result.text, 'string')
  return result.text
}

const created = await call({ action: 'create', dir: out, title: 'Host contract', width: 11, height: 8.5 })
assert.ok(created.includes('created:'), created)
const drawing = join(out, 'Host contract.vsdx')
assert.ok(existsSync(drawing))

const listed = await call({ action: 'list', dir: out })
assert.ok(listed.includes('Host contract.vsdx'), listed)

const opened = await call({ action: 'open', path: drawing })
assert.ok(opened.includes('shapes on this page: 1'), opened)

const added = await call({ action: 'add_shape', path: drawing, kind: 'rect', x: 1, y: 4, w: 2, h: 1, text: 'Node A' })
assert.ok(added.includes('已添加形状'), added)

const second = await call({ action: 'add_shape', path: drawing, kind: 'ellipse', x: 5, y: 4, w: 2, h: 1, text: 'Node B' })
const idB = /#(\d+) \[/.exec(second.split('\n').filter((line) => line.startsWith('- #')).at(-1))[1]

await call({ action: 'connect', path: drawing, from: '2', to: idB, label: 'ok' })
const textSet = await call({ action: 'set_text', path: drawing, shape_id: idB, text: '已改名' })
assert.ok(textSet.includes('已改名'), textSet)
const cellSet = await call({ action: 'set_cell', path: drawing, shape_id: '2', cell: 'FillForegnd', value: '#FFE7C2' })
assert.ok(cellSet.includes('已更新 1 个单元格'), cellSet)
const exported = await call({ action: 'export', path: drawing, format: 'svg' })
assert.ok(exported.includes('.svg'), exported)

const kinds = await call({ action: 'kinds' })
assert.ok(kinds.split(String.fromCharCode(10)).length >= 16, kinds)

const moved = await call({ action: 'move', path: drawing, shape_id: '2', x: 2, y: 2, w: 2, h: 1 })
assert.ok(moved.length > 0, moved)
const undone = await call({ action: 'undo', path: drawing })
assert.ok(undone.length > 0, undone)
const redone = await call({ action: 'redo', path: drawing })
assert.ok(redone.length > 0, redone)

const audit = await call({ action: 'validate', path: drawing })
assert.ok(audit.includes('connectors 1'), audit)
assert.ok(audit.includes('errors 0'), audit)

// ---- routes ---------------------------------------------------------------
const configRoute = routes.find((route) => route.path === '/dsh-visio/config')
const opRoute = routes.find((route) => route.path === '/dsh-visio/op')
assert.ok(configRoute && opRoute, 'both routes must register')
assert.equal(configRoute.kind, 'exact')
assert.equal(opRoute.kind, 'exact')

function fakeResponse() {
  return {
    status: 0,
    headers: {},
    body: '',
    writeHead(status, headers) { this.status = status; Object.assign(this.headers, headers ?? {}) },
    end(body) { this.body = body ?? '' },
  }
}

async function invoke(route, request) {
  const response = fakeResponse()
  await route.handler(request, response)
  let parsed
  try { parsed = JSON.parse(response.body) } catch { parsed = response.body }
  return { status: response.status, body: parsed, headers: response.headers }
}

const configResult = await invoke(configRoute, { method: 'GET', headers: {} })
assert.equal(configResult.status, 200)
assert.equal(configResult.body.ok, true)
assert.equal(configResult.body.defaultFolder, out)
assert.equal(configResult.body.pythonOk, true, 'the bridge ping must succeed')
assert.match(configResult.body.engine, /visio_bridge/)

const post = (body, headers = {}) => ({
  method: 'POST',
  headers: { host: '127.0.0.1:60764', ...headers },
  async *[Symbol.asyncIterator]() { yield Buffer.from(JSON.stringify(body)) },
})

const ok = await invoke(opRoute, post({ action: 'open', path: drawing }))
assert.equal(ok.status, 200)
assert.equal(ok.body.ok, true)
assert.ok(ok.body.svg.includes('data-shape-id'))

const crossOrigin = await invoke(opRoute, post({ action: 'open', path: drawing }, { origin: 'http://evil.example' }))
assert.equal(crossOrigin.status, 403)

const badJson = await invoke(opRoute, {
  method: 'POST',
  headers: { host: '127.0.0.1:60764' },
  async *[Symbol.asyncIterator]() { yield Buffer.from('{ not json') },
})
assert.equal(badJson.status, 400)

const missingPath = await invoke(opRoute, post({ action: 'open' }))
assert.equal(missingPath.status, 400)
assert.match(missingPath.body.error, /path is required/)

const wrongMethod = await invoke(configRoute, { method: 'POST', headers: {} })
assert.equal(wrongMethod.status, 405)

// relative path resolves against the default folder
const relative = await invoke(opRoute, post({ action: 'open', path: 'Host contract.vsdx' }))
assert.equal(relative.status, 200)
assert.equal(relative.body.name, 'Host contract.vsdx')

// ---- internals ------------------------------------------------------------
assert.equal(typeof internals.pythonOf({}), 'string')
assert.equal(internals.formatState({
  path: 'x.vsdx', page: 1, pageCount: 1, pageName: 'P', pageSize: { w: 11, h: 8.5 },
  pages: [{ index: 1, name: 'P' }], masters: [], shapes: [],
}).includes('shapes on this page: 0'), true)

internals.disposePools()
console.log('ok — tool + routes + bridge round trip verified')
