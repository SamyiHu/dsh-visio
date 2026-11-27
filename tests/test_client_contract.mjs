/**
 * Client contract tests: translation keys, and the residue of old bugs that a
 * bundler cannot catch.  No DOM needed.
 *
 * Run:  node tests/test_client_contract.mjs
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(HERE, '..', 'client.js'), 'utf8')
const results = []

function check(name, fn) {
  try {
    fn()
    results.push([true, name, ''])
  } catch (error) {
    results.push([false, name, error instanceof Error ? error.message : String(error)])
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

/** Slice a top-level object literal out of the source by brace counting. */
function objectAt(startIndex) {
  const open = source.indexOf('{', startIndex)
  let depth = 0
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1
    else if (source[i] === '}') {
      depth -= 1
      if (depth === 0) return source.slice(open, i + 1)
    }
  }
  throw new Error('unbalanced dictionary literal')
}

const zhStart = source.indexOf('const zh = {')
const enStart = source.indexOf('const en = {')
const zhBlock = objectAt(zhStart)
const enBlock = objectAt(enStart)

const keysOf = (block) => new Set([...block.matchAll(/^\s{4,8}([A-Za-z_][A-Za-z0-9_]*)\s*:/gm)].map((m) => m[1]))
const zhKeys = keysOf(zhBlock)
const enKeys = keysOf(enBlock)

check('i18n: zh and en carry exactly the same keys', () => {
  const missingEn = [...zhKeys].filter((key) => !enKeys.has(key))
  const missingZh = [...enKeys].filter((key) => !zhKeys.has(key))
  assert(missingEn.length === 0, 'missing in en: ' + missingEn.join(', '))
  assert(missingZh.length === 0, 'missing in zh: ' + missingZh.join(', '))
})

check('i18n: every t(key) resolves to a dictionary entry', () => {
  // a key is a literal followed by the closing paren or an options object;
  // t('side_' + dir) is a computed key and is resolved by the dictionaries below it
  const used = new Set([...source.matchAll(/\bt\('([A-Za-z_][A-Za-z0-9_]*)'\s*[,)]/g)].map((m) => m[1]))
  const unknown = [...used].filter((key) => !zhKeys.has(key))
  assert(unknown.length === 0, 'no translation for: ' + unknown.join(', '))
})

check('i18n: no Chinese literals outside the dictionaries', () => {
  const spans = [[zhStart, zhStart + zhBlock.length], [enStart, enStart + enBlock.length]]
  const offenders = []
  let offset = 0
  for (const line of source.split('\n')) {
    const start = offset
    offset += line.length + 1
    if (!/[\u4e00-\u9fff]/.test(line)) continue
    if (spans.some(([from, to]) => start >= from && start <= to)) continue
    // the shape-kind palette is bilingual data, not a literal typed into the UI
    if (/zh: '.*', en: '/.test(line)) continue
    offenders.push(line.trim().slice(0, 80))
  }
  assert(offenders.length === 0, 'hard-coded Chinese in the UI code: ' + offenders.join(' | '))
})

check('no debug hooks left on the window object', () => {
  assert(!/window\.__[A-Za-z0-9_$]*\s*=/.test(source),
    'a window.__ hook is still assigning state onto the page global')
})

check('Ctrl+D performs a duplicate instead of only consuming the shortcut', () => {
  assert(/duplicateSelection\(\)/.test(source), 'Ctrl+D no longer calls the duplicate path')
  assert(/action: 'duplicate'/.test(source), 'nothing calls the duplicate action')
})

check('the SVG preview is injected through exactly one place', () => {
  const hits = [...source.matchAll(/dangerouslySetInnerHTML/g)]
  assert(hits.length === 1, 'found ' + hits.length + ' raw-HTML injections; each one needs escaping')
})

// ---- build / manifest contract (carried over from the master-side suite) ---
// The footer badge must not lie about which build is running, and the manifest
// must keep declaring the compatibility floors the host does not enforce.
check('CLIENT_BUILD matches package.json version', () => {
  const pkg = JSON.parse(readFileSync(join(HERE, '..', 'package.json'), 'utf8'))
  const build = /const CLIENT_BUILD = '([^']+)'/.exec(source)
  assert(build && build[1] === pkg.version,
    `CLIENT_BUILD=${build ? build[1] : '(missing)'} != package.json ${pkg.version}`)
})

check('package.json declares the compatibility floors', () => {
  const pkg = JSON.parse(readFileSync(join(HERE, '..', 'package.json'), 'utf8'))
  assert(pkg.engines && pkg.engines.node === '>=18', 'engines.node must declare the Node floor')
  assert(pkg.engines && pkg.engines.dsh === '>=0.2.1-rc.1 <0.3.0-0',
    'engines.dsh must declare the DSH host floor')
  assert(pkg.dsh && pkg.dsh.engines && pkg.dsh.engines.dsh === '>=0.2.1-rc.1 <0.3.0-0',
    'dsh.engines.dsh must declare the DSH host floor')
  const peer = pkg.peerDependencies && pkg.peerDependencies['@deepseek-ai/dsh']
  assert(peer && /0\.2\.2-rc\.1/.test(peer) && /0\.1\.7-rc\.2/.test(peer),
    'peerDependencies must explicitly cover the guaranteed 0.2.2-rc.1 and the early 0.1.7-rc.2 prerelease')
  assert(peer && peer.includes('||'),
    'peer range must use explicit prerelease branches, per the awesome-list contributing guide')
})

let bad = 0
for (const [ok, name, message] of results) {
  console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : '  <- ' + message))
  bad += ok ? 0 : 1
}
console.log('\n' + (results.length - bad) + '/' + results.length + ' ok')
process.exit(bad ? 1 : 0)
