// Off-device harness for the Desktop half's behaviour tests (tests/test_desktop_*.mjs): bundles
// desktop/src with esbuild into one module whose three allowed imports (@hermes/plugin-sdk, react,
// react/jsx-runtime) are small stand-ins, and gives each case a fresh copy of it with a fake backend
// that answers like dashboard/api.py (409 not_running / running, op_id dedupe, /health, injected 500s,
// and a network failure as an error without an HTTP status, the way Electron's IPC rejects).
// It proves module logic and call order, not the real Radix components or Desktop's pane layout.
import fs from 'fs'
import { createRequire } from 'module'
import path from 'path'
import { fileURLToPath, pathToFileURL } from 'url'

const here = path.dirname(fileURLToPath(import.meta.url))
export const SRC = path.resolve(here, '..', 'desktop', 'src')
// The version the bundle under test carries (core.js VERSION); the fake /health answers `server.version`.
export const HARNESS_VERSION = '0.2.1'

const SDK = `
const listeners = new Map()
export function atom(value) {
  const subs = new Set()
  return {
    get: () => value,
    set: next => { value = next; subs.forEach(fn => fn(value)) },
    listen: fn => { subs.add(fn); return () => subs.delete(fn) },
    subscribe: fn => { subs.add(fn); fn(value); return () => subs.delete(fn) },
  }
}
export const calls = []
const any = () => null
export const useValue = a => a.get()
export const useQuery = () => ({})
// React Query's client as far as the plugin uses it outside components: the cache answers what was set
// or fetched last, and every success is announced to cache subscribers in TanStack v5's event shape
// ({ type: 'updated', action: { type: 'success' }, query }). fetchQuery always calls queryFn (no staleTime).
const cache = new Map()
const cacheSubs = new Set()
const announce = (queryKey, data) => cacheSubs.forEach(fn => fn({ type: 'updated', action: { type: 'success' }, query: { queryKey, state: { data } } }))
export const queryClient = {
  getQueryData: k => cache.get(JSON.stringify(k)),
  setQueryData: (k, d) => { cache.set(JSON.stringify(k), d); announce(k, d); return d },
  fetchQuery: async ({ queryKey, queryFn }) => { const d = await queryFn(); cache.set(JSON.stringify(queryKey), d); announce(queryKey, d); return d },
  invalidateQueries: () => Promise.resolve(),
  getQueryCache: () => ({ subscribe: fn => { cacheSubs.add(fn); return () => cacheSubs.delete(fn) } }),
}
export const useQueryClient = () => queryClient
export const Switch = any, Input = any, Popover = any, PopoverTrigger = any, PopoverContent = any
export const DropdownMenu = any, DropdownMenuContent = any, DropdownMenuItem = any, DropdownMenuSeparator = any, DropdownMenuTrigger = any
export const Codicon = any
export const KEYBINDS_AREA = 'keybinds', PALETTE_AREA = 'palette', ROUTES_AREA = 'routes', SIDEBAR_NAV_AREA = 'nav'
export const STATUSBAR_AREAS = { right: 'statusbar' }
export const pluginSettingsHref = () => '/settings'
// openWorkspace and revealPane behave like Desktop's sdk/index.ts: re-opening one id replaces the
// registration in place, the returned disposer closes the tab and runs options.onClose.
const panes = new Map()
export const host = {
  state: { profile: atom('p1') },
  notify: n => calls.push(['notify', n]),
  navigate: p => calls.push(['navigate', p]),
  revealPane: id => calls.push(['revealPane', id]),
  openWorkspace: (id, o) => {
    calls.push(['openWorkspace', id])
    const close = () => { calls.push(['closeWorkspace', id]); panes.delete(id); o.onClose && o.onClose() }
    panes.set(id, { options: o, close })
    return close
  },
  panes,
}
`
const REACT = `
export const useState = v => [typeof v === 'function' ? v() : v, () => {}]
export const useEffect = () => {}
export const useMemo = fn => fn()
export const useRef = v => ({ current: v })
export class Component { constructor(props) { this.props = props } }
`
const JSX = `
export const jsx = (type, props) => ({ type, props })
export const jsxs = jsx
`

/** Bundle desktop/src once; returns the bundle path. `nm` is desktop/build/node_modules. */
export async function bundle(nmArg) {
  const nm = nmArg ? path.resolve(nmArg) : null
  if (!nm || !fs.existsSync(path.join(nm, 'esbuild'))) {
    throw new Error('usage: node <test>.mjs <desktop/build/node_modules> (run npm ci in desktop/build first)')
  }
  const esbuild = createRequire(path.join(nm, 'x.js'))('esbuild')
  const dir = fs.mkdtempSync(path.join(process.env.TMPDIR || '/tmp', 'esb-desktop-'))
  const stub = (name, text) => {
    const file = path.join(dir, name)
    fs.writeFileSync(file, text)
    return file
  }
  // A module a case needs but the tree under test lacks becomes an empty namespace, so that case fails
  // on its own instead of the whole bundle failing to build.
  const ns = (name, file) => (fs.existsSync(path.join(SRC, file))
    ? `export * as ${name} from ${JSON.stringify(path.join(SRC, file))}`
    : `export const ${name} = {}`)
  const entry = stub('entry.js', [
    `export { default as plugin } from ${JSON.stringify(path.join(SRC, 'index.js'))}`,
    ...['core.js', 'outbox.js', 'live.js', 'timer.js'].map(f => `export * from ${JSON.stringify(path.join(SRC, f))}`),
    ns('regexRun', 'regex_run.js'),
    ns('engines', 'engines.js'),
    ns('chip', 'chip.js'),
    ns('settings', 'settings.js'),
    ns('pad', 'tools/pad.js'),
    ns('clockmath', 'clockmath.js'),
    ns('detect', 'detect.js'),
    ns('drafts', 'drafts.js'),
    ns('dashboard', 'dashboard.js'),
    ns('page', 'page.js'),
    ns('ui', 'ui.js'),
    ns('clockTool', 'tools/clock.js'),
    ns('timelogTool', 'tools/timelog.js'),
    ns('sidebar', 'sidebar.js'),
    ns('visibility', 'visibility.js'),
    `export { host, calls, queryClient } from '@hermes/plugin-sdk'`,
  ].join('\n'))
  const out = path.join(dir, 'desktop.mjs')
  await esbuild.build({
    entryPoints: [entry], bundle: true, format: 'esm', platform: 'node', outfile: out, nodePaths: [nm], minify: true,
    alias: { '@hermes/plugin-sdk': stub('sdk.js', SDK), react: stub('react.js', REACT), 'react/jsx-runtime': stub('jsx.js', JSX) },
    loader: { '.txt': 'text' }, logLevel: 'error', define: { __ESB_VERSION__: JSON.stringify(HARNESS_VERSION) },
  })
  return out
}

const ipc = (status, body) => new Error(`Error invoking remote method 'hermes:api': Error: ${status}: ${JSON.stringify(body)}`)

/** A fresh module copy wired to a fake backend and an in-memory ctx.storage. */
export async function fresh(file) {
  const M = await import(`${pathToFileURL(file).href}?${Math.random()}`)
  const server = { timer: null, applied: new Set(), down: false, fail500: false, slowMs: 0, log: [],
    version: HARNESS_VERSION, saves: [],
    tools: [{ id: 'pad', title: "Today's pad", group: 'daily', on: true, dashboard: 'widget', surfaces: ['page', 'palette'] },
      { id: 'pomodoro', title: 'Pomodoro', group: 'daily', on: true, dashboard: 'widget', surfaces: ['page', 'palette'] },
      { id: 'timezones', title: 'World clock', group: 'daily', on: true, dashboard: 'widget', surfaces: ['page', 'palette'] },
      { id: 'formatter', title: 'Formatter', group: 'code', on: true, dashboard: 'tile', surfaces: ['page', 'palette'] }],
    toolbox: { schema: 2, first_run: false, dashboard: ['timezones', 'pad', 'pomodoro', 'formatter'], clocks: [{ zone: 'Asia/Tokyo', label: 'Tokyo' }],
      layout: { chip: 'auto', chip_visible: true }, pomodoro: { rhythm: '25/5', work: 25, short: 5, long: 15, cycles: 4 }, tips: [], alerts: { while_closed: false } } }
  const store = new Map()
  const disposers = []
  const contributions = []
  const ctx = {
    storage: { get: (k, f) => (store.has(k) ? JSON.parse(store.get(k)) : f), set: (k, v) => store.set(k, JSON.stringify(v)), remove: k => store.delete(k) },
    os: { notify: () => {}, writeClipboard: async () => true },
    setInterval: () => () => {},
    addEventListener: () => () => {},
    onDispose: fn => disposers.push(fn),
    register: c => { contributions.push(c); return () => { const i = contributions.indexOf(c); if (i >= 0) contributions.splice(i, 1) } },
    registerSettingsPage: () => () => {},
    rest: async (p, o = {}) => {
      const method = o.method || 'GET'
      if (server.slowMs && p === '/timer' && method === 'POST' && o.body.op === 'start') await new Promise(r => setTimeout(r, server.slowMs))
      if (server.down) throw new Error("Error invoking remote method 'hermes:api': Error: connect ECONNREFUSED 127.0.0.1:9119")
      server.log.push(`${method} ${p}${o.body && o.body.op ? ` ${o.body.op}` : ''}`)
      if (p === '/health') return { ok: true, plugin: 'eselsbruecke', version: server.version }
      if (p === '/presence' || p === '/alerts/reconcile') return { ok: true }
      if (p === '/toolbox' && method === 'POST') {
        // like api.py toolbox_post: `save` replaces the file, `switch` flips one tool; every save is kept in server.saves
        server.saves.push(o.body)
        if (o.body.op === 'save') server.toolbox = o.body.toolbox
        if (o.body.op === 'switch') server.tools = server.tools.map(t => (t.id === o.body.module ? { ...t, on: o.body.on } : t))
        return { ok: true, tools: server.tools, toolbox: server.toolbox, hash: `h${server.saves.length}` }
      }
      if (p === '/toolbox') return { ok: true, tools: server.tools, toolbox: server.toolbox, hash: `h${server.saves.length}` }
      if (p === '/timelog' || p === '/pad') return { ok: true }
      if (p === '/timer' && method === 'GET') return { ok: true, timer: server.timer }
      if (p === '/timer') {
        const b = o.body
        if (server.fail500) throw ipc(500, { ok: false, error: 'store', message: 'database is locked' })
        if (server.applied.has(b.op_id)) return { ok: true, duplicate: true, timer: server.timer }
        if (b.op === 'start') {
          if (server.timer) throw ipc(409, { ok: false, error: 'running', message: 'a timer is running' })
          server.timer = { id: 't1', kind: b.kind || 'pomodoro', plan: b.plan, started: b.at, paused: [] }
        } else if (b.op === 'pause') {
          if (!server.timer) throw ipc(409, { ok: false, error: 'not_running', message: 'no timer is running' })
          server.timer.paused.push([b.at, null])
        } else if (b.op === 'stop') {
          if (!server.timer) throw ipc(409, { ok: false, error: 'not_running', message: 'no timer is running' })
          server.timer = null
        }
        server.applied.add(b.op_id)
        return { ok: true, applied: true, timer: server.timer }
      }
      throw ipc(404, { detail: 'Not Found' })
    },
  }
  M.setCtx(ctx)
  M.calls.length = 0
  const toasts = () => M.calls.filter(c => c[0] === 'notify').map(c => c[1].message)
  return { M, server, store, ctx, contributions, disposers, toasts }
}

export const tick = ms => new Promise(r => setTimeout(r, ms))

/** Collect named cases; print one JSON line { cases, failed, failures }; exit 1 on a failure. */
export function suite() {
  const failures = []
  let n = 0
  return {
    async test(name, fn) {
      n++
      try {
        await fn()
      } catch (error) {
        failures.push({ name, message: String((error && error.message) || error).slice(0, 800) })
      }
    },
    done() {
      console.log(JSON.stringify({ cases: n, failed: failures.length, failures }))
      process.exit(failures.length ? 1 : 0)
    },
  }
}
