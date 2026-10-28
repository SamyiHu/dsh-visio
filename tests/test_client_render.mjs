/**
 * Render smoke test for the Visio panel without a browser.
 *
 * Runs the real component tree with a tiny React stand-in: createElement builds
 * plain nodes, function components are invoked, hooks return their initial value
 * (state slots can be pre-seeded, mirroring the panel's fixed hook order).
 * It catches typos and null-guard mistakes that syntax checks cannot.
 *
 *   node tests/test_client_render.mjs
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(here, '..', 'client.js'), 'utf8')

let loaded = null
const sandbox = {
  window: { __ModuleLoader__: { load: (module) => { loaded = module } }, localStorage: null },
  document: { baseURI: 'http://127.0.0.1/' },
  console,
  setTimeout: (fn) => setTimeout(fn, 0),
  clearTimeout,
  URL,
}
vm.runInNewContext(source, sandbox)
assert.ok(loaded, 'module loader was not called')

let scheduled = []
let stateIndex = 0
let seeded = []

const React = {
  createElement(type, props, ...children) {
    const flat = children.flat(Infinity).filter((child) => child !== undefined && child !== null && child !== false)
    return { type, props: { ...(props || {}), children: flat.length === 1 ? flat[0] : flat } }
  },
  Fragment: 'fragment',
  useState(initial) {
    const value = stateIndex < seeded.length ? seeded[stateIndex] : initial
    stateIndex += 1
    return [value, () => {}]
  },
  useEffect(fn) { scheduled.push(fn) },
  useRef(value) { return { current: value } },
  useMemo(fn) { return fn() },
  useCallback(fn) { return fn },
}

const plugin = loaded.factory((id) => {
  if (id === 'react') return React
  throw new Error(`unexpected require(${id})`)
})

/** Render a component to a plain node tree, invoking function components. */
function render(component, props) {
  stateIndex = 0
  return walk(component(props))
}

function walk(node) {
  if (node === null || node === undefined || typeof node !== 'object') return node
  if (Array.isArray(node)) return node.map(walk)
  if (typeof node.type === 'function') return walk(node.type(node.props))
  return { type: node.type, props: { ...node.props, children: walk(node.props.children) } }
}

/** Collect every node whose props match a predicate. */
function findAll(node, predicate, out = []) {
  if (node === null || node === undefined || typeof node !== 'object') return out
  if (Array.isArray(node)) {
    for (const child of node) findAll(child, predicate, out)
    return out
  }
  if (predicate(node)) out.push(node)
  findAll(node.props?.children, predicate, out)
  return out
}

function textOf(node) {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (node === null || node === undefined || typeof node !== 'object') return ''
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (typeof node.type === 'string' && node.type !== 'style') {
    return textOf(node.props?.children)
  }
  if (typeof node.type === 'string') return ''
  return textOf(node.props?.children)
}

const calls = { slots: [] }
const pluginContext = {
  effect(fn) { const dispose = fn(); return typeof dispose === 'function' ? dispose : () => {} },
  get: () => undefined,
  inject: () => {},
  logger: () => ({ warn: () => {} }),
  locale: {
    register: () => () => {},
    bind: () => (key, params) => {
      let value = key
      for (const [name, replacement] of Object.entries(params ?? {})) value += `:${name}=${replacement}`
      return value
    },
  },
  slots: {
    inject: (_name, callback) => callback(),
    register(spec, component) { calls.slots.push({ name: spec.name, id: spec.key ?? spec.id, component }); return () => {} },
  },
}
plugin.apply(pluginContext)
const panel = calls.slots.find((slot) => slot.name === 'main')?.component
assert.ok(panel, 'panel component not captured')

// ---- 1. empty state -------------------------------------------------------
seeded = []
const empty = render(panel, { t: (key) => key, pickFolder: async () => null })
const emptyText = textOf(empty)
assert.ok(emptyText.includes('noDocTitle'), 'empty state should show the "no document" title')
assert.ok(findAll(empty, (n) => n.props?.className === 'dshv-empty').length >= 1)

// ---- 2. loaded drawing + inspector ---------------------------------------
const state = {
  ok: true,
  path: '/tmp/demo.vsdx',
  name: 'demo.vsdx',
  folder: '/tmp',
  page: 1,
  pageCount: 1,
  pageName: 'Page-1',
  pageSize: { w: 11, h: 8.5 },
  pages: [{ index: 1, name: 'Page-1', width: 11, height: 8.5 }],
  masters: [],
  shapes: [
    { id: '1', text: 'Start', type: 'Shape', master: null, parent: null, depth: 0, connector: false, geometry: ['MoveTo', 'LineTo'], bbox: { x: 1, y: 5, w: 2, h: 1 }, connects: [], props: {} },
    { id: '2', text: 'Next', type: 'Shape', master: null, parent: null, depth: 0, connector: false, geometry: ['Ellipse'], bbox: { x: 5, y: 5, w: 2, h: 1 }, connects: [{ to: '1' }], props: {} },
  ],
  detail: {
    id: '1', type: 'Shape', master: '', text: 'Start', cells: {},
    props: { Owner: 'Example Owner' },
    style: { fill: '#EAF2FF', line: '#2F6FBF', text: null, font_pt: null, weight: 0.0104, end_arrow: '0' },
    sections: [],
  },
  svg: '<svg width="1056" height="816"><g data-shape-id="1"><rect x="1" y="2.5" width="2" height="1"/></g></svg>',
  saved: true, notice: '', mtime: 1, engine: '1.0.0',
}

// Hook order of VisioPanel: config, configError, folder, folderDraft, files, filesBusy,
// filesError, doc, selected, busy, error, notice, tab, createOpen.
const config = { ok: true, defaultFolder: state.folder, folderOk: true, python: 'python', pythonOk: true, engine: 'visio_bridge/1.0.0' }
seeded = [config, '', state.folder, state.folder, [], false, '', state, '1', false, '', '', 'shapes', true, false, false]
const loadedTree = render(panel, { t: (key) => key, pickFolder: async () => null })
const loadedText = textOf(loadedTree)
assert.ok(loadedText.includes('demo.vsdx'), 'header should show the file name')
assert.ok(loadedText.includes('shapeData'), 'inspector sections should render')
assert.ok(findAll(loadedTree, (n) => n.props?.className === 'dshv-page').length >= 1, 'preview page missing')
const injected = findAll(loadedTree, (n) => n.props?.dangerouslySetInnerHTML?.__html?.includes('data-shape-id'))
assert.equal(injected.length, 1, 'preview svg should be injected once')
assert.equal(findAll(loadedTree, (n) => n.props?.className === 'dshv-zoom').length, 1, 'zoom toolbar missing')
const selectedSvg = injected[0].props.dangerouslySetInnerHTML.__html
assert.ok(selectedSvg.includes('stroke-dasharray="5 3"'), 'selection box should be drawn inside the page svg')
const textareas = findAll(loadedTree, (n) => n.type === 'textarea')
assert.equal(textareas.length, 1, 'text editor missing')
assert.equal(textareas[0].props.value, 'Start', 'text editor should hold the shape text')
const propInputs = findAll(loadedTree, (n) => n.type === 'input' && n.props?.defaultValue === 'Example Owner')
assert.equal(propInputs.length, 1, 'shape-data row missing')

// ---- 3. create dialog -----------------------------------------------------
seeded = [config, '', state.folder, state.folder, [], false, '', null, null, false, '', '', 'shapes', true, false, true]
const dialogTree = render(panel, { t: (key) => key, pickFolder: async () => null })
assert.ok(findAll(dialogTree, (n) => n.props?.className === 'dshv-dialog').length === 1, 'create dialog missing')
assert.ok(textOf(dialogTree).includes('createTitle'))

// ---- 4. sidebar icon renders ---------------------------------------------
const icon = calls.slots.find((slot) => slot.name === 'sidebar.panellist')?.component
const iconTree = render(icon, { size: 16, active: false })
assert.ok(findAll(iconTree, (n) => n.type === 'svg').length >= 1, 'sidebar icon should draw an svg')

console.log('ok — panel, inspector, dialog and icon all render')

// ---- 5. floating canvas window -------------------------------------------
const floatComp = calls.slots.find((slot) => slot.name === 'shell.overlay')?.component
assert.ok(floatComp, 'floating canvas component not captured')
seeded = [true, { x: 40, y: 60, w: 720, h: 480 }]
const floated = render(floatComp, { t: (key) => key, pickFolder: async () => null })
assert.equal(findAll(floated, (node) => node.props?.className === 'dshv-floatBar').length, 1, 'floating title bar missing')
assert.equal(findAll(floated, (node) => node.props?.className === 'dshv-float').length, 1, 'floating window missing')

seeded = [false, { x: 0, y: 0, w: 600, h: 400 }]
const fabOnly = render(floatComp, { t: (key) => key, pickFolder: async () => null })
assert.equal(findAll(fabOnly, (node) => node.props?.className === 'dshv-float').length, 0, 'closed window should not render')
assert.equal(findAll(fabOnly, (node) => node.props?.className === 'dshv-fab').length, 1, 'launcher missing')

const canvasWrap = findAll(loadedTree, (n) => String(n.props?.className || '').includes('dshv-canvasWrap'))[0]
assert.ok(canvasWrap, 'canvas wrap missing')
assert.match(String(canvasWrap.props.style.backgroundImage), /linear-gradient/, 'grid gradient missing')
assert.match(String(canvasWrap.props.style.backgroundSize), /\d+px \d+px/, 'grid size missing')

console.log('ok — zoom toolbar renders')
console.log('ok — floating canvas window renders')
