// The Desktop surfaces against a fake backend (tests/desktop_harness.mjs): "Open beside chat" twice and
// the keybind after it (X15), the pane closed on dispose without clearing the setting, the "start a
// pomodoro" palette row only while the pomodoro is on (X14), and the Regex tester's worker with its
// time limit (X13). The worker runs as a node worker thread fed from the same Blob URL Desktop uses.
// Run by tests/test_desktop_build.py: node test_desktop_surfaces.mjs <desktop/build/node_modules>
// Prints one JSON line { cases, failed, failures }; exit 1 on a failure.
import assert from 'assert'
import { resolveObjectURL } from 'buffer'
import { Worker as NodeWorker } from 'worker_threads'

import { bundle, fresh, suite, tick } from './desktop_harness.mjs'

globalThis.window = globalThis

// A web Worker on node's worker threads: the source comes from the Blob URL, `self.onmessage` and
// `postMessage` map onto parentPort, and terminate() stops the thread mid-run like Chromium does.
const PRELUDE = "const { parentPort } = require('worker_threads'); globalThis.self = globalThis;" +
  'globalThis.postMessage = m => parentPort.postMessage(m); parentPort.on("message", data => self.onmessage({ data }));\n'
globalThis.__workers = 0
globalThis.Worker = class {
  constructor(url) {
    globalThis.__workers++
    this.ready = resolveObjectURL(url).text().then(src => {
      const w = new NodeWorker(PRELUDE + src, { eval: true })
      w.on('message', data => this.onmessage && this.onmessage({ data }))
      w.on('error', error => this.onerror && this.onerror(error))
      return w
    })
  }
  postMessage(m) { this.ready.then(w => w.postMessage(m)) }
  terminate() { this.ready.then(w => w.terminate()) }
}

const file = await bundle(process.argv[2])
const t = suite()
const PANE = 'plugin-workspace:eselsbruecke-beside'

async function registered() {
  const env = await fresh(file)
  env.M.plugin.register(env.ctx)
  await tick(30)
  return env
}

await t.test('X15: a second "Open beside chat" keeps the pane and the setting', async () => {
  const { M, store, contributions } = await registered()
  const openBeside = contributions.find(c => c.id === 'chip').render().props.onBeside
  openBeside()
  openBeside()
  assert.strictEqual(store.get('openBeside'), 'true', 'the setting was cleared by the second open')
  const shown = M.calls.filter(c => c[0] !== 'notify')
  assert.ok(!shown.some(c => c[0] === 'closeWorkspace'), `the pane was closed and reopened: ${JSON.stringify(shown)}`)
  assert.ok(shown.some(c => c[0] === 'revealPane' && c[1] === PANE), `the open pane was not brought to the front: ${JSON.stringify(shown)}`)
  const mark = M.calls.length
  contributions.find(c => c.id === 'open').data.run()
  const after = M.calls.slice(mark).filter(c => c[0] !== 'notify')
  assert.ok(!after.some(c => c[0] === 'navigate'), `the keybind navigated the main view: ${JSON.stringify(after)}`)
  assert.ok(!after.some(c => c[0] === 'closeWorkspace'), 'the keybind closed the pane (typed text lost)')
  assert.ok(M.host.panes.has('eselsbruecke-beside'), 'the pane is gone')
})

await t.test('X15: closing the pane clears the setting; disposing the plugin closes it and keeps it', async () => {
  const { M, store, contributions, disposers } = await registered()
  const openBeside = contributions.find(c => c.id === 'chip').render().props.onBeside
  openBeside()
  assert.ok(disposers.length, 'no ctx.onDispose was registered')
  disposers.forEach(fn => fn())
  assert.ok(!M.host.panes.has('eselsbruecke-beside'), 'the pane outlived the plugin')
  assert.strictEqual(store.get('openBeside'), 'true', 'a disable or reload cleared the user setting')
  const again = await registered()
  const open2 = again.contributions.find(c => c.id === 'chip').render().props.onBeside
  open2()
  again.M.host.panes.get('eselsbruecke-beside').close() // the user closes the tab
  assert.strictEqual(again.store.get('openBeside'), 'false')
})

await t.test('X14: the "start a pomodoro" palette row exists only while the pomodoro is on', async () => {
  const on = await registered()
  assert.ok(on.contributions.some(c => c.id === 'pomodoro-start'), 'missing while on')
  const env = await fresh(file)
  env.server.tools = [{ id: 'pad', on: true, surfaces: ['page', 'palette'] }, { id: 'pomodoro', on: false, surfaces: ['page', 'palette'] }]
  env.M.plugin.register(env.ctx)
  await tick(30)
  assert.ok(!env.contributions.some(c => c.id === 'pomodoro-start'), 'registered while the pomodoro is off')
})

await t.test('X13: a catastrophic pattern is stopped by the time limit and the renderer stays free', async () => {
  const { M } = await fresh(file)
  assert.strictEqual(typeof M.regexRun.runRegex, 'function', 'regex_run.js runRegex is missing')
  let beats = 0
  const beat = setInterval(() => beats++, 20)
  const t0 = Date.now()
  const out = await M.regexRun.runRegex('(a+)+$', `${'a'.repeat(28)}!`, '', { timeoutMs: 300 })
  const ms = Date.now() - t0
  clearInterval(beat)
  assert.strictEqual(out.ok, false)
  assert.strictEqual(out.timeout, true, JSON.stringify(out))
  assert.ok(ms < 2000, `took ${ms} ms`)
  assert.ok(beats >= 5, `the main thread was blocked (${beats} beats in ${ms} ms)`)
})

await t.test('X13: the worker answers like the engine, errors included', async () => {
  const { M } = await fresh(file)
  const good = await M.regexRun.runRegex('(\\d{4})-(\\d{2})', 'on 2026-11 and 2027-01', 'g')
  assert.deepStrictEqual(good, M.engines.regex('(\\d{4})-(\\d{2})', 'on 2026-11 and 2027-01', 'g'))
  const bad = await M.regexRun.runRegex('(', 'x', '')
  assert.strictEqual(bad.ok, false)
  assert.match(bad.error, /Invalid regular expression/)
})

await t.test('X13: a newer run supersedes a stuck one', async () => {
  const { M } = await fresh(file)
  const slow = M.regexRun.runRegex('(a+)+$', `${'a'.repeat(28)}!`, '', { timeoutMs: 5000 })
  await tick(50)
  const fast = await M.regexRun.runRegex('a', 'aa', 'g')
  const first = await slow
  assert.strictEqual(fast.ok, true)
  assert.strictEqual(fast.matches.length, 2)
  assert.strictEqual(first.ok, false)
  assert.strictEqual(first.cancelled, true)
})

// The rendered tree as text and as a flat list of elements (the harness jsx makes { type, props }).
const nodes = n => (n && typeof n === 'object' && !Array.isArray(n) && n.props
  ? [n, ...[].concat(n.props.children || []).flatMap(nodes)] : Array.isArray(n) ? n.flatMap(nodes) : [])
const text = n => (n == null || n === false ? '' : typeof n !== 'object' ? String(n)
  : Array.isArray(n) ? n.map(text).join('') : text(n.props && n.props.children))

await t.test('two-place install: the settings page names the Desktop-side update unless Hermes is local', async () => {
  const { M } = await registered()
  assert.strictEqual(typeof M.settings.TwoPlaceNote, 'function', 'settings.js exports no TwoPlaceNote')
  const shown = M.settings.TwoPlaceNote()
  assert.ok(shown, 'no line when Desktop does not say where Hermes runs')
  assert.match(text(shown), /Hermes on another computer\? Update this plugin on both\. Here: hermes plugins update eselsbruecke, then Rescan\./)
  M.host.state.connectionId = { get: () => 'remote-1' }
  assert.ok(M.settings.TwoPlaceNote(), 'no line for a remote Hermes')
  M.host.state.connectionId = { get: () => 'local' }
  assert.strictEqual(M.settings.TwoPlaceNote(), null, 'the line shows for this computer\'s own Hermes')
  delete M.host.state.connectionId
})

await t.test('sidebar rows: the row reads Eselsbrücke at 51, and "Open Eselsbrücke" opens the dashboard from the palette', async () => {
  const { M, contributions } = await registered()
  const nav = contributions.filter(c => c.area === 'nav')
  assert.strictEqual(nav.length, 1, 'one sidebar row')
  assert.strictEqual(nav[0].id, 'nav')
  assert.strictEqual(nav[0].order, 51)
  assert.deepStrictEqual(nav[0].data, { codicon: 'tools', label: 'Eselsbrücke', path: '/eselsbruecke' })
  const open = contributions.find(c => c.area === 'palette' && c.data.label === 'Open Eselsbrücke')
  assert.ok(open, 'no palette row "Open Eselsbrücke"')
  M.calls.length = 0
  open.data.run()
  assert.ok(M.calls.some(c => c[0] === 'navigate' && c[1] === '/eselsbruecke'), JSON.stringify(M.calls))
})

await t.test('sidebar rows: a stored choice hides the row at start; the settings block shows it again', async () => {
  const env = await fresh(file)
  env.store.set('sidebar', JSON.stringify({ show: false, position: 60 }))
  env.M.plugin.register(env.ctx)
  await tick(30)
  assert.strictEqual(env.contributions.filter(c => c.area === 'nav').length, 0, 'a hidden row was registered')
  const block = env.M.sidebar.SidebarBlock()
  const tree = block.type(block.props)
  assert.match(text(tree), /^SidebarShow in the sidebarPositionLower numbers sit higher\. Kanban is 50\.Open it from the command palette: Open Eselsbrücke\.$/)
  nodes(tree).find(n => n.props['aria-label'] === 'Show in the sidebar').props.onCheckedChange(true)
  const nav = env.contributions.filter(c => c.area === 'nav')
  assert.strictEqual(nav.length, 1)
  assert.strictEqual(nav[0].order, 60)
  assert.deepStrictEqual(JSON.parse(env.store.get('sidebar')), { show: true, position: 60 })
})

await t.test('sidebar rows: the settings view draws the Sidebar block', async () => {
  const { M } = await registered()
  const view = M.settings.SettingsView({ data: { tools: [], toolbox: { layout: { chip: 'auto', chip_visible: true }, pomodoro: {}, alerts: {} } }, health: null, save: () => {} })
  const kids = [].concat(view.props.children)
  const at = kids.findIndex(k => k && k.type === M.sidebar.SidebarBlock)
  assert.ok(at > 0, 'no Sidebar block on the settings page')
  assert.ok(at < kids.findIndex(k => k && k.type === M.settings.TwoPlaceNote), 'the Sidebar block sits above the two-place note')
})

await t.test('S4: pad checkboxes are named by their line, and the actions button says whether its menu is open', async () => {
  const { M } = await registered()
  assert.strictEqual(typeof M.pad.Line, 'function', 'tools/pad.js exports no Line')
  const line = { id: 'l1', kind: 'todo', text: 'Call the bank', done: false }
  const tree = M.pad.Line({ line, date: '2026-11-11', act: () => {}, readOnly: false })
  const box = nodes(tree).find(n => n.type === 'input' && n.props.type === 'checkbox')
  assert.strictEqual(box.props['aria-label'], 'Done: Call the bank')
  const menuButton = nodes(tree).find(n => n.props['aria-label'] === 'Line actions')
  assert.strictEqual(menuButton.props['aria-expanded'], false)
  assert.strictEqual(menuButton.props['aria-haspopup'], 'menu')
})

await t.test('S4: Enter adds a pad line, but not while an input method is still composing', async () => {
  const { M } = await registered()
  assert.strictEqual(typeof M.pad.enterAdds, 'function', 'tools/pad.js exports no enterAdds')
  assert.strictEqual(M.pad.enterAdds({ key: 'Enter', nativeEvent: {} }), true)
  assert.strictEqual(M.pad.enterAdds({ key: 'a', nativeEvent: {} }), false)
  assert.strictEqual(M.pad.enterAdds({ key: 'Enter', nativeEvent: { isComposing: true } }), false)
  assert.strictEqual(M.pad.enterAdds({ key: 'Enter', keyCode: 229, nativeEvent: {} }), false)
})

t.done()
