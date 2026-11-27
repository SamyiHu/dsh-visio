/**
 * End-to-end: drive the real visio tool handlers against the real Python engine,
 * the way the agent would.  Needs python on PATH (or DSH_VISIO_PYTHON).
 *
 * Run:  node tests/test_tool_integration.mjs
 */
import { mkdtempSync, readdirSync, rmSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { internals } from '../index.js'

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

const folder = mkdtempSync(join(tmpdir(), 'dshv-tool-'))
const ctx = { get: () => undefined }
const config = { defaultFolder: folder }
const tool = internals.buildHandlers(ctx, config)
let path = ''

await check('create: writes a new drawing and reports it', async () => {
  const out = await tool.create({ dir: folder, title: 'Integration', overwrite: true })
  assert(/created: .*\.vsdx/.test(out.text), out.text)
  path = out.text.split('created:')[1].trim()
  assert(existsSync(path), 'the tool reported a file that does not exist')
})

await check('add_shape: the fill/line styling that used to be unreachable lands in the file', async () => {
  await tool.add_shape({ path, kind: 'rect', x: 1, y: 6, w: 2.4, h: 1, text: 'Node A',
    fill: '#17365D', line: '#17365D', font_color: '#FFFFFF' })
  await tool.add_shape({ path, kind: 'roundrect', x: 5, y: 6, w: 2.4, h: 1, text: 'Node B',
    fill: '#2F6B4F', line: '#2F6B4F', font_color: '#FFFFFF' })
  const shapes = await tool.open({ path })
  assert(shapes.text.includes('Node A') && shapes.text.includes('Node B'), shapes.text.slice(0, 400))
  assert(/shapes on this page: [2-9]/.test(shapes.text), shapes.text.slice(0, 200))
})

await check('get_shape: reports the cell we set', async () => {
  const listing = await tool.open({ path })
  const line = listing.text.split('\n').find((row) => row.includes('Node A'))
  assert(line, 'Node A is missing from the listing: ' + listing.text.slice(0, 300))
  const shapeId = (line.match(/- #(\d+)/) || [])[1]
  assert(shapeId, 'no shape id on the Node A line: ' + line)
  const detail = await tool.get_shape({ path, shape_id: shapeId })
  assert(detail.text.includes('FillForegnd'), detail.text.slice(0, 300))
  assert(/17365D|2F6B4F/.test(detail.text), 'the fill colour is not in the ShapeSheet: ' + detail.text.slice(0, 400))
})

await check('connect + validate: a wired pair produces no error', async () => {
  const listing = await tool.open({ path })
  const ids = [...listing.text.matchAll(/- #(\d+)/g)].map((m) => m[1])
  assert(ids.length >= 2, 'need two shapes')
  await tool.connect({ path, from: ids[0], to: ids[1], label: 'flows' })
  const audit = await tool.validate({ path })
  assert(/errors 0/.test(audit.text), audit.text)
})

await check('snapshot: review=true now comes back with a report', async () => {
  const out = await tool.snapshot({ path, review: true })
  assert(/rendered 1 page/.test(out.text), out.text)
  assert(/review: errors \d+/.test(out.text), 'no review report: ' + out.text)
})

await check('export: svg lands next to the drawing', async () => {
  const out = await tool.export({ path, format: 'svg' })
  const file = out.text.replace('exported:', '').trim()
  assert(file.endsWith('.svg') && existsSync(file), out.text)
})

await check('undo: the last edit is really reverted', async () => {
  const before = (await tool.text({ path })).text
  await tool.add_shape({ path, kind: 'diamond', x: 1, y: 4, w: 1.5, h: 1, text: 'Temp gate' })
  const mid = (await tool.text({ path })).text
  assert(mid.includes('Temp gate'), 'the shape was not added')
  await tool.undo({ path })
  const after = (await tool.text({ path })).text
  assert(!after.includes('Temp gate'), 'undo left the shape behind')
  assert(after === before, 'undo did not restore the previous state')
})

await check('a bad action name is a tool error, not a cheerful result', async () => {
  let captured = null
  internals.registerTool({ get: () => ({ register: (def) => { captured = def; return () => {} } }) }, config)
  let threw = false
  try {
    await captured.execute({ action: 'probe-everything' })
  } catch {
    threw = true
  }
  assert(threw, 'unknown action resolved normally')
})

internals.disposePools()

await check('the folder kept its backups and no stray .tmp files', () => {
  const names = readdirSync(folder)
  assert(names.some((n) => n.includes('.bak-')), 'no backup was written')
  assert(!names.some((n) => n.endsWith('.tmp')), 'a .tmp file was left behind')
})

let bad = 0
for (const [ok, name, message] of results) {
  console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : '  <- ' + message))
  bad += ok ? 0 : 1
}
console.log('\n' + (results.length - bad) + '/' + results.length + ' ok')
rmSync(folder, { recursive: true, force: true })
process.exit(bad ? 1 : 0)
