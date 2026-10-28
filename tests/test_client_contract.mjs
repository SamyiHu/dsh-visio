/**
 * Contract test for the browser half without a browser.
 *
 * Loads client.js in a bare VM (with a stubbed module loader and React), then:
 *  • checks the plugin object shape and that apply() registers the panel + icon,
 *  • checks every t('key') used by the UI exists in both dictionaries,
 *  • checks the sidebar entry and the main panel share one id.
 *
 *   node tests/test_client_contract.mjs
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
  setTimeout,
  clearTimeout,
  URL,
}
vm.runInNewContext(source, sandbox)
// The footer badge must not lie about which build is running.
{
  const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
  const build = /const CLIENT_BUILD = '([^']+)'/.exec(readFileSync(new URL('../client.js', import.meta.url), 'utf8'))
  assert.equal(build && build[1], pkg.version, 'CLIENT_BUILD must match package.json version')
}

assert.ok(loaded, 'window.__ModuleLoader__.load was never called')

const noop = () => {}
const React = {
  createElement: (...args) => ({ args }),
  useState: (v) => [v, noop],
  useEffect: noop,
  useRef: (v) => ({ current: v }),
  useMemo: (fn) => fn(),
  useCallback: (fn) => fn,
}
const plugin = loaded.factory((id) => {
  if (id === 'react') return React
  throw new Error(`unexpected require(${id})`)
})

assert.equal(loaded.id, '@local/dsh-visio')
assert.equal(JSON.stringify(plugin.inject), JSON.stringify(['slots', 'locale']))
assert.equal(typeof plugin.apply, 'function')

const calls = { effects: 0, slots: [], locales: [], dictionaries: null }
function makeContext() {
  const ctx = {
    effect(fn) {
      calls.effects += 1
      const dispose = fn()
      return typeof dispose === 'function' ? dispose : noop
    },
    get: () => undefined,
    inject: () => {},
    logger: () => ({ warn: noop }),
    locale: {
      register(namespace, dictionaries) {
        calls.locales.push(namespace)
        calls.dictionaries = dictionaries
        return noop
      },
      bind: (namespace) => (key, params) => {
        const dict = calls.dictionaries?.zh ?? {}
        let value = dict[key] ?? key
        for (const [name, replacement] of Object.entries(params ?? {})) {
          value = value.replaceAll(`{${name}}`, String(replacement))
        }
        return value
      },
    },
    slots: {
      inject: (_name, callback) => callback(),
      register(spec, component) {
        calls.slots.push({ name: spec.name, id: spec.key ?? spec.id, component })
        assert.equal(typeof component, 'function', `${spec.name} component must be a function`)
        return noop
      },
    },
  }
  return ctx
}

plugin.apply(makeContext())

assert.equal(calls.effects, 1, 'apply must register exactly one dispose effect')
assert.ok(calls.locales.includes('@local/dsh-visio'), 'locale namespace not registered')
assert.ok(calls.dictionaries?.zh && calls.dictionaries?.en, 'zh/en dictionaries missing')

const main = calls.slots.find((slot) => slot.name === 'main')
const sidebar = calls.slots.find((slot) => slot.name === 'sidebar.panellist')
assert.ok(main, 'main panel not registered')
assert.ok(sidebar, 'sidebar entry not registered')
assert.equal(main.id, 'dsh-visio')
assert.equal(sidebar.id, main.id, 'sidebar id must match the main panel key')
assert.equal(sidebar.id, 'dsh-visio')

// Every literal t('key') in the UI must exist in both dictionaries.
const used = new Set([...source.matchAll(/\bt\('([a-zA-Z][a-zA-Z0-9]*)'/g)].map((match) => match[1]))
assert.ok(used.size > 40, `expected many translation keys, found ${used.size}`)
for (const key of used) {
  for (const lang of ['zh', 'en']) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(calls.dictionaries[lang], key),
      `missing ${lang} translation for "${key}"`,
    )
  }
}

// The panel tree must be renderable: evaluate the component function shape only.
assert.equal(VisioHasHooks(main.component), true, 'panel should be a function component')

function VisioHasHooks(component) {
  return typeof component === 'function' && component.length <= 1
}

console.log(`ok — ${used.size} translation keys, slots: ${calls.slots.map((s) => `${s.name}:${s.id}`).join(', ')}`)
