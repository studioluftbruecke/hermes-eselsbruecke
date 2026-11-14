// The dashboard, the status-bar chip, the settings page and the page shell against a fake backend (tests/desktop_harness.mjs).
// The harness React renders nothing: the cases test what the modules decide (their exported pure
// functions), and walk the element trees the components return to see what would be drawn.
// Run by tests/test_desktop_build.py: node test_desktop_dashboard.mjs <desktop/build/node_modules>
// Prints one JSON line { cases, failed, failures }; exit 1 on a failure.
import assert from 'assert'

import { bundle, fresh, suite, tick } from './desktop_harness.mjs'

globalThis.window = globalThis
const info = console.info
console.info = () => {} // the plugin logs each registration; the result line is what the caller reads

const file = await bundle(process.argv[2])
const t = suite()

async function registered(change) {
  const env = await fresh(file)
  if (change) change(env.server)
  env.M.plugin.register(env.ctx)
  await tick(30)
  env.M.calls.length = 0
  return env
}

// The /toolbox answer the way api.py gives it for a fresh install: every tool on, the default dashboard.
const ROWS = [
  ['pad', "Today's pad", 'daily', 'widget', 'eselsbruecke_pad'], ['pomodoro', 'Pomodoro', 'daily', 'widget', 'eselsbruecke_timer'],
  ['timelog', 'Time log', 'daily', 'widget', 'eselsbruecke_timelog'], ['timezones', 'World clock', 'daily', 'widget', 'eselsbruecke_convert'],
  ['formatter', 'Formatter', 'code', 'tile', 'eselsbruecke_format'], ['diff', 'Text diff', 'code', 'tile', 'eselsbruecke_text'],
  ['regex', 'Regex tester', 'code', 'tile', 'eselsbruecke_text'], ['tokens', 'Token counter', 'code', 'tile', 'eselsbruecke_text'],
  ['cron', 'Cron explainer', 'code', 'tile', 'eselsbruecke_convert'], ['encode', 'Encode, decode', 'convert', 'tile', 'eselsbruecke_convert'],
  ['generate', 'UUID, password', 'convert', 'widget', 'eselsbruecke_generate'], ['colour', 'Colour picker', 'design', 'widget', 'eselsbruecke_convert'],
  ['qr', 'QR code', 'design', 'tile', null], ['calc', 'Calculator', 'engine', null, 'eselsbruecke_calc'],
]
const DEFAULT = ['timezones', 'pad', 'pomodoro', 'timelog', 'generate', 'colour', 'formatter', 'diff', 'encode']
function answer({ off = [], dashboard = DEFAULT, firstRun = false, layout = { chip: 'auto', chip_visible: true } } = {}) {
  const tools = ROWS.map(([id, title, group, kind, agent]) => ({ id, title, group, dashboard: kind, agent_tool: agent, blurb: `What ${title} does.`, on: !off.includes(id),
    options: {}, surfaces: kind ? ['page', 'palette'] : [] }))
  return { ok: true, schema: 2, hash: 'h0', tools, toolbox: { schema: 2, first_run: firstRun,
    modules: Object.fromEntries(tools.map((x, i) => [x.id, { on: x.on, order: i, options: {} }])), dashboard,
    clocks: [{ zone: 'UTC', label: 'UTC' }, { zone: 'America/New_York', label: 'New York' }, { zone: 'Asia/Tokyo', label: 'Tokyo' }],
    layout, pomodoro: { rhythm: '25/5', work: 25, short: 5, long: 15, cycles: 4 }, tips: [], alerts: { while_closed: false } } }
}

// The harness SDK's components are all `() => null`; a component of the plugin is called like React
// would call it (the harness hooks return their initial values), so the whole tree becomes plain elements.
const standIn = fn => /^\(\)\s*=>\s*null$/.test(String(fn))
function draw(node, stop = new Set()) {
  if (node == null || typeof node !== 'object') return node
  if (Array.isArray(node)) return node.map(n => draw(n, stop))
  const { type, props = {} } = node
  if (typeof type === 'function' && !stop.has(type) && !standIn(type)) return draw(type(props), stop)
  return { type: typeof type === 'function' ? (stop.has(type) ? 'tool' : 'sdk') : type, component: type, props: { ...props, children: draw(props.children, stop) } }
}
const nodes = n => (n && typeof n === 'object' && !Array.isArray(n) && n.props
  ? [n, ...[].concat(n.props.children == null ? [] : n.props.children).flatMap(nodes)] : Array.isArray(n) ? n.flatMap(nodes) : [])
const text = n => (n == null || n === false ? '' : typeof n !== 'object' ? String(n)
  : Array.isArray(n) ? n.map(text).join(' ') : text(n.props && n.props.children))
const has = (tree, cls) => nodes(tree).some(n => String(n.props.className || '').split(' ').includes(cls))
const byClass = (tree, cls) => nodes(tree).filter(n => String(n.props.className || '').split(' ').includes(cls))
const page = (M, props = {}) => draw({ type: M.page.ToolboxPage, props }, new Set(Object.values(M.page.TOOL_VIEWS)))

await t.test('the bundle under test carries the harness version', async () => {
  const { M } = await fresh(file)
  assert.strictEqual(M.VERSION, '0.2.2')
})

await t.test('landing: the sidebar row and the "open" keybind give the dashboard', async () => {
  const { M, contributions } = await registered()
  const nav = contributions.find(c => c.id === 'nav')
  assert.deepStrictEqual(Object.keys(nav.data).sort(), ['codicon', 'label', 'path'], 'the sidebar row only navigates')
  const route = contributions.find(c => c.id === 'page')
  assert.strictEqual(nav.data.path, route.data.path)
  const first = draw(route.render(), new Set(Object.values(M.page.TOOL_VIEWS)))
  assert.ok(has(first, 'dash'), 'the page does not open on the dashboard')
  assert.ok(!nodes(first).some(n => n.type === 'tool'), 'a tool is shown on the first visit')

  const open = contributions.find(c => c.id === 'open')
  assert.strictEqual(open.data.label, 'Eselsbrücke: open the dashboard')
  M.ui.$tool.set('regex') // a tool was open on the page
  open.data.run()
  assert.strictEqual(M.ui.$tool.get(), null, 'the keybind kept the tool')
  assert.deepStrictEqual(M.calls.filter(c => c[0] === 'navigate'), [['navigate', '/eselsbruecke']])
  const row = contributions.find(c => c.id === 'palette-dashboard')
  assert.strictEqual(row.data.label, 'Eselsbrücke: open the dashboard')
  M.ui.$tool.set('regex')
  row.data.run()
  assert.strictEqual(M.ui.$tool.get(), null)
})

await t.test('landing: a palette row and the pad keybind open their tool; leaving the page goes back to the dashboard', async () => {
  const { M, contributions } = await registered()
  const views = new Set(Object.values(M.page.TOOL_VIEWS))
  const route = contributions.find(c => c.id === 'page')
  contributions.find(c => c.id === 'open-formatter').data.run()
  assert.strictEqual(M.ui.$tool.get(), 'formatter')
  assert.deepStrictEqual(M.calls.filter(c => c[0] === 'navigate'), [['navigate', '/eselsbruecke']])
  let tree = draw(route.render(), views)
  assert.ok(!has(tree, 'dash'), 'the dashboard is drawn instead of the tool the palette asked for')
  assert.strictEqual(nodes(tree).find(n => n.type === 'tool').component, M.page.TOOL_VIEWS.formatter)

  const focus = M.ui.$focusPadAdd.get()
  contributions.find(c => c.id === 'pad-add').data.run()
  assert.strictEqual(M.ui.$tool.get(), 'pad')
  assert.strictEqual(M.ui.$focusPadAdd.get(), focus + 1, 'the pad keybind did not ask for the add field')

  // the user goes to a chat: the page unmounts, and the next sidebar click finds the dashboard
  M.ui.pageShown()
  M.ui.pageHidden()
  await tick(10)
  assert.strictEqual(M.ui.$tool.get(), null, 'the page kept its tool after it was left')
  tree = draw(route.render(), views)
  assert.ok(has(tree, 'dash'))

  // React's development mode unmounts and mounts again at once: that is not leaving
  M.ui.$tool.set('pad')
  M.ui.pageShown()
  M.ui.pageHidden()
  M.ui.pageShown()
  await tick(10)
  assert.strictEqual(M.ui.$tool.get(), 'pad', 'a remount was taken for leaving the page')
})

await t.test('landing: a tool that is switched off or unknown gives the dashboard; the beside pane keeps its own view', async () => {
  const { M, store } = await registered()
  const tools = M.page.pageTools(answer({ off: ['regex'] }))
  assert.strictEqual(M.page.currentTool('regex', tools), null)
  assert.strictEqual(M.page.currentTool('nope', tools), null)
  assert.strictEqual(M.page.currentTool(null, tools), null)
  assert.strictEqual(M.page.currentTool('dashboard', tools), null)
  assert.strictEqual(M.page.currentTool('pad', tools).id, 'pad')
  assert.ok(!tools.some(x => x.id === 'calc'), 'the calculator has no page')

  store.set('openBeside', 'true') // the user keeps Eselsbrücke beside the chat
  M.ui.openTool('diff')
  assert.strictEqual(M.ui.$besideTool.get(), 'diff')
  assert.strictEqual(M.ui.$tool.get(), null, 'the page changed with the pane')
  assert.ok(!M.calls.some(c => c[0] === 'navigate'), 'the main view was navigated')
  M.ui.pageShown()
  M.ui.pageHidden()
  await tick(10)
  assert.strictEqual(M.ui.$besideTool.get(), 'diff', 'leaving the page reset the pane')
  M.ui.openTool('dashboard', { beside: false })
  assert.deepStrictEqual(M.calls.filter(c => c[0] === 'navigate'), [['navigate', '/eselsbruecke']])
})

await t.test('page shell: rail from Dashboard through the four groups, the head without a profile chip, one row and a picker when narrow', async () => {
  const { M } = await registered()
  const wide = page(M, { onBeside: () => {}, onSettings: () => {} })
  const rail = nodes(wide).find(n => n.type === 'nav')
  const railText = nodes(rail).filter(n => n.type === 'button' || String(n.props.className) === 'grp').map(n => text(n).trim())
  assert.deepStrictEqual(railText.filter(x => ['Dashboard', 'Daily', 'Code', 'Convert', 'Design'].includes(x)), ['Dashboard', 'Daily', 'Code', 'Convert', 'Design'])
  assert.strictEqual(railText[0], 'Dashboard')
  assert.strictEqual(railText[railText.indexOf('Daily') + 4], 'World clock', 'the world clock is not the fourth daily tool')
  const icons = nodes(rail).filter(n => n.type === 'sdk' && n.props.name).map(n => n.props.name)
  assert.strictEqual(icons.length, 14, 'every rail row has an icon')
  const head = nodes(wide).find(n => n.type === 'header')
  assert.strictEqual(text(head).trim(), 'Eselsbrücke', 'on the dashboard the head holds the name and icon buttons only')
  assert.deepStrictEqual(nodes(head).filter(n => n.type === 'button').map(n => n.props['aria-label']), ['Open beside the chat', 'Settings'])

  M.$connection.set('offline')
  M.$outbox.set([{ kind: 'timer', op: { op: 'start', op_id: 'a' } }, { kind: 'timer', op: { op: 'pause', op_id: 'b' } }])
  M.ui.$tool.set('pad')
  const tool = page(M, { onBeside: () => {}, onSettings: () => {} })
  const toolHead = text(nodes(tool).find(n => n.type === 'header'))
  assert.match(toolHead, /not connected/)
  assert.match(toolHead, /2 not synced/)
  assert.match(toolHead, /Ask Hermes/)
  assert.doesNotMatch(toolHead, /\bp1\b/, 'the profile chip is back')

  M.ui.$besideTool.set(null)
  const narrow = page(M, { beside: true, onSettings: () => {} })
  assert.ok(!nodes(narrow).some(n => n.type === 'nav'), 'the rail is drawn beside the chat')
  const picker = nodes(narrow).find(n => n.type === 'select')
  assert.strictEqual(picker.props.value, 'dashboard')
  assert.deepStrictEqual(nodes(picker).filter(n => n.type === 'option').map(n => n.props.children).slice(0, 3), ['Dashboard', "Today's pad", 'Pomodoro'])
  assert.ok(nodes(narrow).find(n => String(n.props.className).split(' ').includes('narrow')), 'the pane is not marked narrow')
  assert.ok(!nodes(narrow).some(n => n.props['aria-label'] === 'Open beside the chat'), 'the pane offers to open itself')
})

await t.test('dashboard: pinned order, a switched-off tool skipped but kept, widgets apart from tiles', async () => {
  const { M } = await fresh(file)
  const D = M.dashboard
  const data = answer({ off: ['pad', 'diff'], dashboard: ['formatter', 'timezones', 'pad', 'diff', 'pomodoro', 'encode', 'calc', 'nope', 'pomodoro'] })
  const tools = M.ui.toolRows(data)
  const items = D.dashboardItems(tools, D.pinnedOf(data))
  assert.deepStrictEqual(items.widgets.map(x => x.id), ['timezones', 'pomodoro'])
  assert.deepStrictEqual(items.tiles.map(x => x.id), ['formatter', 'encode'])
  assert.ok(D.pinnedOf(data).includes('pad'), 'a switched-off tool left the list')
  assert.deepStrictEqual(D.addable(tools, D.pinnedOf(data)).map(x => x.id), ['timelog', 'regex', 'tokens', 'cron', 'generate', 'colour', 'qr'])
  // no toolbox yet (first paint, or Hermes never reached): the default dashboard, every tool on
  assert.deepStrictEqual(D.pinnedOf(undefined), DEFAULT)
  const first = D.dashboardItems(M.ui.toolRows(undefined), D.pinnedOf(undefined))
  assert.deepStrictEqual([...first.widgets, ...first.tiles].map(x => x.id), DEFAULT)

  const tree = draw({ type: D.Dashboard, props: { data, narrow: false, onOpen: () => {} } })
  assert.deepStrictEqual(nodes(tree).filter(n => n.props['data-w']).map(n => n.props['data-w']), ['timezones', 'pomodoro'])
  assert.deepStrictEqual(nodes(tree).filter(n => n.props['data-tile']).map(n => n.props['data-tile']), ['formatter', 'encode'])
  assert.ok(String(nodes(tree).find(n => n.props['data-w'] === 'timezones').props.className).includes('span2'), 'the clock does not span two columns')
  assert.ok(!has(tree, 'welcome'), 'the welcome card shows after the first run')
})

await t.test('dashboard: pin, unpin and move each make one save of the whole file', async () => {
  const { M, server } = await fresh(file)
  const D = M.dashboard
  const data = answer({ off: ['pomodoro'] })
  const tools = M.ui.toolRows(data)
  assert.deepStrictEqual(D.pin(DEFAULT, 'qr'), [...DEFAULT, 'qr'])
  assert.strictEqual(D.pin(DEFAULT, 'pad'), DEFAULT, 'pinning twice repeats the tool')
  assert.deepStrictEqual(D.unpin(DEFAULT, 'pad'), DEFAULT.filter(x => x !== 'pad'))
  // pad moves later past the switched-off pomodoro to the next widget drawn, the time log
  assert.deepStrictEqual(D.movePin(DEFAULT, 'pad', 1, tools), ['timezones', 'timelog', 'pomodoro', 'pad', 'generate', 'colour', 'formatter', 'diff', 'encode'])
  assert.deepStrictEqual(D.movePin(DEFAULT, 'pad', -1, tools), ['pad', 'timezones', 'pomodoro', 'timelog', 'generate', 'colour', 'formatter', 'diff', 'encode'])
  assert.strictEqual(D.movePin(DEFAULT, 'timezones', -1, tools), null, 'the first widget moved earlier')
  assert.strictEqual(D.movePin(DEFAULT, 'colour', 1, tools), null, 'the last widget moved into the tiles')
  assert.strictEqual(D.movePin(DEFAULT, 'formatter', -1, tools), null, 'the first tile moved into the widgets')
  assert.deepStrictEqual(D.movePin(DEFAULT, 'formatter', 1, tools).slice(-3), ['diff', 'formatter', 'encode'])
  assert.strictEqual(D.movePin(DEFAULT, 'pomodoro', 1, tools), null, 'a switched-off tool moved')

  const save = M.ui.useToolboxSave()
  const body = D.dashboardSave(data, D.pin(DEFAULT, 'qr'))
  assert.deepStrictEqual(body, { op: 'save', base_hash: 'h0', toolbox: { ...data.toolbox, dashboard: [...DEFAULT, 'qr'] } })
  await save(body)
  await save(D.dashboardSave(data, D.movePin(DEFAULT, 'pad', -1, tools)))
  assert.strictEqual(server.saves.length, 2)
  assert.deepStrictEqual(server.saves[0], body)
  assert.strictEqual(server.saves[1].toolbox.dashboard[0], 'pad')
  assert.strictEqual(server.saves[1].toolbox.clocks.length, 3, 'the save dropped the rest of the file')

  // the pin button in the page head on a tool view
  const on = M.page.pinToggle(data, tools.find(x => x.id === 'pad'))
  assert.strictEqual(on.label, 'On the dashboard')
  assert.deepStrictEqual(on.body.toolbox.dashboard, DEFAULT.filter(x => x !== 'pad'))
  const offTool = M.page.pinToggle(data, tools.find(x => x.id === 'qr'))
  assert.strictEqual(offTool.label, 'Pin to dashboard')
  assert.deepStrictEqual(offTool.body.toolbox.dashboard, [...DEFAULT, 'qr'])
  assert.strictEqual(M.page.pinToggle(undefined, tools[0]), null, 'a pin button without a loaded toolbox')
})

await t.test('a save that Hermes cannot take answers null with a toast, never a rejection', async () => {
  const { M, server, toasts } = await fresh(file)
  const save = M.ui.useToolboxSave()
  const body = M.dashboard.dashboardSave(answer(), [...DEFAULT, 'qr'])
  assert.ok(await save(body), 'a save that works answers the new view')
  server.down = true
  assert.strictEqual(await save(body), null)
  assert.strictEqual(toasts().length, 1)
  assert.strictEqual(server.saves.length, 1)
})

await t.test('chip: an icon when idle, ring and minutes for the pomodoro, dot and hours for the time log', async () => {
  const { M } = await fresh(file)
  const C = M.chip
  const now = Date.parse('2026-11-11T10:05:00Z')
  const timer = { id: 't1', kind: 'pomodoro', plan: M.pomodoroPlan(25, 5, 15, 4), started: '2026-11-11T10:00:00Z', paused: [] }
  const running = { id: 'e1', client: 'Bäckerei Lindner', project: 'Shop', start: '2026-11-11T09:00:00Z' }
  const layout = { chip: 'auto', chip_visible: true }

  const idle = C.chipState({ timer: null, running: null, now, layout })
  assert.deepStrictEqual([idle.kind, idle.label, idle.title], ['idle', '', 'Eselsbrücke'])

  const pomo = C.chipState({ timer, running, now, layout })
  assert.deepStrictEqual([pomo.kind, pomo.label, pomo.pct], ['pomodoro', '20m', 20])
  assert.strictEqual(pomo.title, 'Eselsbrücke: Work, 20 min left')
  const paused = C.chipState({ timer: { ...timer, paused: [['2026-11-11T10:05:00Z', null]] }, running: null, now: now + 600000, layout })
  assert.strictEqual(paused.title, 'Eselsbrücke: Work paused, 20 min left')

  const log = C.chipState({ timer: null, running, now, layout })
  assert.deepStrictEqual([log.kind, log.label], ['timelog', '1:05'])
  assert.strictEqual(log.title, 'Eselsbrücke: Bäckerei Lindner, Shop, running 1:05')

  // "While something runs, show"
  assert.strictEqual(C.chipState({ timer, running, now, layout: { ...layout, chip: 'timelog' } }).kind, 'timelog')
  assert.strictEqual(C.chipState({ timer, running: null, now, layout: { ...layout, chip: 'timelog' } }).kind, 'idle')
  assert.strictEqual(C.chipState({ timer: null, running, now, layout: { ...layout, chip: 'pomodoro' } }).kind, 'idle')
  assert.strictEqual(C.chipState({ timer, running, now, layout: { ...layout, chip: 'pomodoro' } }).kind, 'pomodoro')
  // a finished timer is not shown
  assert.strictEqual(C.chipState({ timer, running: null, now: now + 6 * 3600000, layout }).kind, 'idle')

  // never wide: three characters for the minutes, hours from 100 minutes on
  assert.deepStrictEqual([1, 25, 99, 100, 240, 1440].map(C.chipMinutes), ['1m', '25m', '99m', '2h', '4h', '24h'])
  const face = state => C.chipFace(state).filter(Boolean)
  assert.deepStrictEqual(face(idle).map(n => n.props.name || n.props.className), ['tools'], 'the idle chip is more than an icon')
  assert.deepStrictEqual(face(pomo).map(n => n.props.className || n.props.children), ['esbring', '20m'])
  assert.strictEqual(face(pomo)[0].props.style['--p'], '20%')
  assert.deepStrictEqual(face(log).map(n => n.props.className || n.props.children), ['esbdot', '1:05'])
  assert.deepStrictEqual(C.CHIP_SAMPLES.map(([label]) => label), ['Nothing runs', 'Pomodoro', 'Time log', 'A click waits to sync'])
})

await t.test('chip: waiting clicks are a dot and a count in the tooltip; chip_visible false hides it whatever waits', async () => {
  const { M, ctx } = await registered()
  const C = M.chip
  const layout = { chip: 'auto', chip_visible: true }
  const one = C.chipState({ layout, waiting: 1 })
  assert.strictEqual(one.title, 'Eselsbrücke, 1 click waits to sync')
  assert.deepStrictEqual(C.chipFace(one).filter(Boolean).map(n => n.props.name || n.props.className), ['tools', 'esbwait'])
  assert.strictEqual(C.chipState({ layout, waiting: 3 }).title, 'Eselsbrücke, 3 clicks wait to sync')

  assert.deepStrictEqual(C.chipState({ layout: { chip: 'auto', chip_visible: false }, waiting: 2 }), { hidden: true })
  assert.deepStrictEqual(C.chipState({ layout, connection: 'off' }), { hidden: true })
  // a file from before chip_visible says chip "off"; a missing layout (nothing loaded yet) shows the chip
  assert.deepStrictEqual(C.chipLayout({ rail: 'groups', dock: null, chip: 'off' }), { chip: 'auto', chip_visible: false })
  assert.deepStrictEqual(C.chipLayout(undefined), { chip: 'auto', chip_visible: true })
  assert.deepStrictEqual(C.chipLayout({ chip: 'timelog', chip_visible: true }), { chip: 'timelog', chip_visible: true })

  // the component: a button whose only text is its tooltip, and nothing at all once the user hid it
  M.$outbox.set([{ kind: 'timer', op: { op: 'start', op_id: 'a' } }])
  const shown = draw({ type: C.Chip, props: { onBeside: () => {} } })
  const button = nodes(shown).find(n => n.type === 'button' && String(n.props.className).includes('esbchip'))
  assert.strictEqual(button.props.title, 'Eselsbrücke, 1 click waits to sync')
  assert.strictEqual(text(button).trim(), '', 'the idle chip shows text')
  assert.ok(nodes(shown).some(n => text(n) === 'Open the dashboard'), 'the popover has no "Open the dashboard"')
  ctx.storage.set('chipLayout:p1', { chip: 'auto', chip_visible: false })
  assert.strictEqual(draw({ type: C.Chip, props: {} }), null, 'a hidden chip came back because a click waits')
})

// The status-bar item (visibility.js): registered as a data item Desktop's right-click menu lists while
// "Show in status bar" is on, disposed while it is off.
const barItems = contributions => contributions.filter(c => c.area === 'statusbar')

await t.test('status bar: shown by default as a data item with the stable id, the brand as toggleLabel and the chip inside its boundary', async () => {
  const { M, contributions } = await registered()
  const items = barItems(contributions)
  assert.strictEqual(items.length, 1, 'not exactly one status-bar item')
  const [item] = items
  assert.strictEqual(item.render, undefined, 'a top-level render: Desktop drops toggleLabel and never lists it')
  assert.strictEqual(item.data.id, 'eselsbruecke.chip')
  assert.strictEqual(item.data.toggleLabel, 'Eselsbrücke')
  const tree = item.data.render()
  assert.strictEqual(tree.type, M.chip.Boundary, 'the chip is not inside the plugin\'s own error boundary')
  assert.strictEqual(tree.props.children.type, M.chip.Chip)
  assert.strictEqual(typeof tree.props.children.props.onBeside, 'function')
  assert.strictEqual(M.visibility.chipShown(), true)
})

await t.test('status bar: the settings switch off disposes the item, on registers it once again', async () => {
  const { M, server, contributions, store } = await registered()
  const save = M.ui.useToolboxSave()
  const data = await M.rest('/toolbox')
  const bar = sw => nodes(draw({ type: M.settings.SettingsView, props: { data: sw, save } })).find(n => n.type === 'sdk' && n.props['aria-label'] === 'Show in status bar')
  await bar(data).props.onCheckedChange(false)
  assert.strictEqual(server.toolbox.layout.chip_visible, false, 'the switch did not save')
  assert.strictEqual(barItems(contributions).length, 0, 'switched off, but the item is still registered')
  assert.strictEqual(M.visibility.chipShown(), false)
  assert.deepStrictEqual(JSON.parse(store.get('chipLayout:p1')), { chip: 'auto', chip_visible: false }, 'the layout seen last was not stored')
  const off = await M.rest('/toolbox')
  assert.strictEqual(bar(off).props.checked, false)
  await bar(off).props.onCheckedChange(true)
  await M.visibility.readVisibility()
  await M.visibility.readVisibility()
  assert.strictEqual(barItems(contributions).length, 1, 'switched on, but not exactly one item')
  assert.strictEqual(barItems(contributions)[0].data.id, 'eselsbruecke.chip')
})

await t.test('status bar: a change made elsewhere lands on the next read; a failed read changes nothing; a file from before chip_visible hides it', async () => {
  const { M, server, contributions } = await registered()
  server.toolbox = { ...server.toolbox, layout: { chip: 'auto', chip_visible: false } } // the agent hid it
  assert.strictEqual(await M.visibility.readVisibility(), false)
  assert.strictEqual(barItems(contributions).length, 0)
  server.down = true
  assert.strictEqual(await M.visibility.readVisibility(), null)
  assert.strictEqual(barItems(contributions).length, 0, 'a failed read brought the chip back')
  server.down = false
  server.toolbox = { ...server.toolbox, layout: { chip: 'auto', chip_visible: true } }
  assert.strictEqual(await M.visibility.readVisibility(), true)
  server.down = true
  assert.strictEqual(await M.visibility.readVisibility(), null)
  assert.strictEqual(barItems(contributions).length, 1, 'a failed read removed the chip')
  server.down = false
  server.toolbox = { ...server.toolbox, layout: { rail: 'groups', chip: 'off' } }
  assert.strictEqual(await M.visibility.readVisibility(), false)
})

await t.test('status bar: the layout seen last decides at start, so a hidden chip does not flash; a profile switch uses that profile\'s', async () => {
  const env = await fresh(file)
  env.ctx.storage.set('chipLayout:p1', { chip: 'auto', chip_visible: false })
  env.server.down = true
  env.M.plugin.register(env.ctx)
  assert.strictEqual(barItems(env.contributions).length, 0, 'the hidden chip was registered at start')
  await tick(30)
  assert.strictEqual(barItems(env.contributions).length, 0, 'the hidden chip came back while Hermes is unreachable')
  env.server.down = false
  await env.M.visibility.readVisibility() // the toolbox says shown
  assert.strictEqual(barItems(env.contributions).length, 1)
  env.ctx.storage.set('chipLayout:p2', { chip: 'auto', chip_visible: false })
  env.server.down = true
  env.M.host.state.profile.set('p2')
  assert.strictEqual(barItems(env.contributions).length, 0, 'p2 hid the chip, but the switch kept p1\'s')
  // an answer for another profile than the one Desktop is on changes nothing
  env.M.queryClient.setQueryData(env.M.qk('p1', 'toolbox'), { toolbox: { layout: { chip: 'auto', chip_visible: true } } })
  assert.strictEqual(barItems(env.contributions).length, 0, 'p1\'s answer showed the chip in p2')
  env.M.host.state.profile.set('p1')
  await tick(30)
  assert.strictEqual(barItems(env.contributions).length, 1)
})

await t.test('status bar: disposing the plugin removes the item and stops following the toolbox', async () => {
  const { M, contributions, disposers } = await registered()
  disposers.forEach(fn => fn())
  assert.strictEqual(barItems(contributions).length, 0)
  M.queryClient.setQueryData(M.qk('p1', 'toolbox'), { toolbox: { layout: { chip: 'auto', chip_visible: true } } })
  assert.strictEqual(barItems(contributions).length, 0, 'a toolbox answer after dispose registered the chip again')
  assert.strictEqual(await M.visibility.readVisibility(), null)
})

await t.test('status bar: the chip\'s own boundary renders the chip, and nothing once it threw', async () => {
  const { M } = await fresh(file)
  const b = new M.chip.Boundary({ children: 'chip' })
  assert.strictEqual(b.render(), 'chip')
  b.state = M.chip.Boundary.getDerivedStateFromError(new Error('boom'))
  b.componentDidCatch(new Error('boom'))
  assert.strictEqual(b.render(), null, 'a chip that threw is still drawn')
})

await t.test('smart paste: the answer names the tool, the button fills its drafts and opens it', async () => {
  const { M } = await fresh(file)
  const D = M.dashboard
  const tools = M.ui.toolRows(answer())
  const opened = []
  const json = D.pasteFound('{"a": 1, "b": [2]}', tools)
  assert.deepStrictEqual([json.tool, json.title, json.action], ['formatter', 'JSON', 'Format it'])
  assert.strictEqual(D.openDetected(json, id => opened.push(id)), true)
  assert.deepStrictEqual(opened, ['formatter'])
  assert.strictEqual(M.drafts.getDraft(M.drafts.DRAFT.formatterText), '{"a": 1, "b": [2]}')

  const b64 = D.pasteFound('SGVsbG8gd29ybGQ=', tools)
  D.openDetected(b64, id => opened.push(id))
  assert.deepStrictEqual(opened, ['formatter', 'encode'])
  assert.deepStrictEqual([M.drafts.DRAFT.encodeText, M.drafts.DRAFT.encodeDir, M.drafts.DRAFT.encodeScheme].map(k => M.drafts.getDraft(k)), ['SGVsbG8gd29ybGQ=', 'decode', 'base64'])

  const col = D.pasteFound('#ff8800', tools)
  assert.deepStrictEqual([col.tool, col.swatch], ['colour', '#ff8800'])
  // a switched-off tool is not offered, and "nothing recognised" opens nothing
  const none = D.pasteFound('#ff8800', M.ui.toolRows(answer({ off: ['colour'] })))
  assert.strictEqual(none.tool, null)
  assert.strictEqual(D.openDetected(none, id => opened.push(id)), false)
  assert.strictEqual(D.pasteFound('   ', tools), null)
  assert.strictEqual(opened.length, 2)

  // drawn: the row shows title, detail, the swatch and the action button
  M.drafts.setDraft(M.drafts.DRAFT.smartPaste, '#ff8800')
  const tree = draw({ type: D.Dashboard, props: { data: answer(), narrow: false, onOpen: id => opened.push(id) } })
  const row = byClass(tree, 'sugg')[0]
  assert.match(text(row), /A colour\s+#ff8800\s+Open in Colour picker/)
  assert.strictEqual(byClass(row, 'sw16')[0].props.style.background, '#ff8800')
  nodes(row).find(n => n.type === 'button').props.onClick()
  assert.deepStrictEqual(opened.slice(-1), ['colour'])
  // Enter in the field does what the button does
  nodes(tree).find(n => n.props['aria-label'] === 'Smart paste').props.onKeyDown({ key: 'Enter', nativeEvent: {} })
  assert.strictEqual(opened.length, 4)
  assert.strictEqual(M.drafts.getDraft(M.drafts.DRAFT.colourText), '#ff8800')
})

await t.test('welcome: every tool with its blurb and a switch while first_run, "Done" saves first_run false', async () => {
  const { M, server } = await fresh(file)
  const D = M.dashboard
  const data = answer({ firstRun: true })
  const tree = draw({ type: D.Dashboard, props: { data, narrow: false, onOpen: () => {} } })
  const card = byClass(tree, 'welcome')[0]
  assert.ok(card, 'no welcome card on the first run')
  assert.strictEqual(byClass(card, 'trow').length, 14)
  assert.match(text(card), /Calculator\s+What Calculator does\./)
  assert.doesNotMatch(text(card), /preset/i)
  assert.strictEqual(nodes(tree).filter(n => n.props['data-w']).length, 6, 'the welcome card blocks the dashboard below it')
  const switches = nodes(card).filter(n => n.type === 'sdk' && 'checked' in n.props)
  assert.strictEqual(switches.length, 14)
  assert.ok(switches.every(s => s.props.checked === true), 'a tool starts switched off')

  assert.deepStrictEqual(D.welcomeDone(data), { op: 'save', base_hash: 'h0', toolbox: { ...data.toolbox, first_run: false } })
  // a switch on the card saves the file with the card still open (the backend's one-switch call would close it)
  const flip = D.welcomeSwitch(data, 'qr', false)
  assert.strictEqual(flip.op, 'save')
  assert.strictEqual(flip.toolbox.first_run, true)
  assert.deepStrictEqual(flip.toolbox.modules.qr, { on: false, order: 12, options: {} })
  assert.strictEqual(flip.toolbox.modules.pad.on, true)

  server.toolbox = data.toolbox
  nodes(card).find(n => n.type === 'button' && text(n) === 'Done').props.onClick()
  await tick(10)
  assert.strictEqual(server.saves.length, 1)
  assert.strictEqual(server.saves[0].toolbox.first_run, false)
  assert.strictEqual(server.toolbox.first_run, false)
})

await t.test('version mismatch: one sentence that names both versions and the side to update', async () => {
  const { M } = await fresh(file)
  assert.strictEqual(M.versionNote('0.2.2'), null, 'the same version is a mismatch')
  assert.strictEqual(M.versionNote('0.3.0'), 'Eselsbrücke is 0.2.2 on this computer and 0.3.0 on your Hermes server. Update Eselsbrücke on this computer.')
  assert.strictEqual(M.versionNote('0.1.1'), 'Eselsbrücke is 0.2.2 on this computer and 0.1.1 on your Hermes server. Update Eselsbrücke on your Hermes server.')
  assert.match(M.versionNote('0.10.0', '0.9.2'), /Update Eselsbrücke on this computer\.$/, '0.10 was read as older than 0.9')
  assert.strictEqual(M.versionNote('0.3.0', 'dev'), null, 'a development bundle complains')
  assert.strictEqual(M.versionNote(undefined), null, 'no answer from /health is a mismatch')
  // the settings page shows it
  const S = M.settings
  const tree = draw({ type: S.SettingsView, props: { data: answer(), health: { version: '0.1.1' }, save: async () => ({}) } })
  assert.match(text(tree), /0\.2\.2 on this computer and 0\.1\.1 on your Hermes server/)
  assert.doesNotMatch(text(draw({ type: S.SettingsView, props: { data: answer(), health: { version: '0.2.2' }, save: async () => ({}) } })), /on your Hermes server\./)
})

await t.test('settings: sections with the tools by group, the status bar switch and its saves, no presets, no tool id in sight', async () => {
  const { M } = await fresh(file)
  const S = M.settings
  const data = answer({ layout: { chip: 'pomodoro', chip_visible: true } })
  const groups = S.settingsGroups(M.ui.toolRows(data))
  assert.deepStrictEqual(groups.map(g => g.label), ['Daily tools', 'Code tools', 'Convert tools', 'Design tools', 'For the pad and the agent'])
  assert.deepStrictEqual(groups[4].tools.map(x => x.id), ['calc'])
  assert.deepStrictEqual(groups[0].tools.map(x => x.id), ['pad', 'pomodoro', 'timelog', 'timezones'])
  // an older Hermes still calls the group "focus"
  assert.strictEqual(S.settingsGroups(M.ui.toolRows({ tools: [{ id: 'pad', title: "Today's pad", group: 'focus', on: true }] }))[0].label, 'Daily tools')

  assert.deepStrictEqual(S.chipSave(data, { chip_visible: false }).toolbox.layout, { chip: 'pomodoro', chip_visible: false })
  assert.deepStrictEqual(S.chipSave(data, { chip: 'timelog' }), { op: 'save', base_hash: 'h0', toolbox: { ...data.toolbox, layout: { chip: 'timelog', chip_visible: true } } })
  assert.deepStrictEqual(S.rhythmSave(data, '50/10').toolbox.pomodoro, { rhythm: '50/10', work: 50, short: 10, long: 10, cycles: 4 })
  assert.deepStrictEqual(S.rhythmSave(data, 'custom').toolbox.pomodoro, { rhythm: 'custom', work: 25, short: 5, long: 15, cycles: 4 })

  const saved = []
  const tree = draw({ type: S.SettingsView, props: { data, health: { version: '0.2.2', time_zone: { zone: 'Europe/Berlin', offset: '+0100' } }, save: async b => { saved.push(b); return {} } } })
  assert.ok(String(tree.props.className).split(' ').includes('settings'), 'the page root is not the spaced grid')
  const titles = byClass(tree, 'sec').map(s => text(nodes(s).find(n => n.type === 'h3')))
  assert.deepStrictEqual(titles, ['Status bar', 'Daily tools', 'Code tools', 'Convert tools', 'Design tools', 'For the pad and the agent', 'Pomodoro', 'Alerts', 'Time zone', 'History'])
  assert.doesNotMatch(text(tree), /preset/i)
  assert.doesNotMatch(text(tree), /eselsbruecke_/, 'an agent tool id is printed on the page')
  const padRow = byClass(tree, 'srow').find(r => /Today's pad/.test(text(r)))
  assert.strictEqual(padRow.props.title, 'Hermes uses this as eselsbruecke_pad')
  assert.strictEqual(byClass(byClass(tree, 'states')[0], 'esbchip').length, 4, 'the four chip previews')

  const bar = byClass(tree, 'sec')[0]
  nodes(bar).find(n => n.type === 'sdk' && n.props['aria-label'] === 'Show in status bar').props.onCheckedChange(false)
  nodes(bar).find(n => n.type === 'button' && text(n) === 'Time log').props.onClick()
  nodes(padRow).find(n => n.type === 'sdk' && 'checked' in n.props).props.onCheckedChange(false)
  assert.deepStrictEqual(saved.map(b => b.op), ['save', 'save', 'switch'])
  assert.strictEqual(saved[0].toolbox.layout.chip_visible, false)
  assert.strictEqual(saved[1].toolbox.layout.chip, 'timelog')
  assert.deepStrictEqual(saved[2], { op: 'switch', module: 'pad', on: false })
  assert.strictEqual(nodes(bar).find(n => n.type === 'button' && text(n) === 'Pomodoro').props['aria-pressed'], true)

  const now = Date.parse('2026-11-11T20:00:00+01:00')
  assert.strictEqual(S.whenLabel('2026-11-11T19:33:00+01:00', now), 'today 19:33')
  assert.strictEqual(S.whenLabel('2026-11-10T16:02:00+01:00', now), 'yesterday 16:02')
  assert.strictEqual(S.whenLabel('2026-11-03T08:00:00+01:00', now), '2026-11-03 08:00')
  // "today" is the day in Hermes' zone: 23:30 UTC on the 11th is already the 12th at +01:00
  assert.strictEqual(S.whenLabel('2026-11-12T00:10:00+01:00', Date.parse('2026-11-11T23:30:00Z')), 'today 00:10')
})

await t.test('widgets: what the clock, pad, pomodoro, time log and colour widgets show', async () => {
  const { M } = await fresh(file)
  const D = M.dashboard
  const now = Date.parse('2026-11-11T16:52:00Z')
  const clocks = [{ zone: 'America/New_York', label: 'New York' }, { zone: 'Asia/Tokyo', label: 'Tokyo' }, { zone: 'America/Los_Angeles', label: 'San Francisco' },
    { zone: 'Not/AZone', label: 'Nowhere' }, { zone: 'UTC', label: 'UTC' }, { zone: 'Asia/Kolkata', label: 'Mumbai' }, { zone: 'Europe/London', label: 'London' }]
  const rows = D.clockRows(clocks, now, 'Europe/Berlin')
  assert.deepStrictEqual(rows.map(r => r.label), ['Berlin', 'New York', 'Tokyo', 'San Francisco', 'UTC'], 'home first, then four places a zone exists for')
  assert.deepStrictEqual(rows.map(r => r.time), ['17:52', '11:52', '01:52', '08:52', '16:52'])
  assert.deepStrictEqual([rows[0].you, rows[1].you, rows[2].day, rows[2].relative], [true, false, 'tomorrow', '+8 h'])
  assert.strictEqual(D.clockRows(undefined, now, 'Europe/Berlin').length, 1)
  assert.deepStrictEqual(D.clockRows(clocks, now, 'America/New_York').map(r => r.label), ['New York', 'Tokyo', 'San Francisco', 'UTC', 'Mumbai'], 'someone in New York sees New York once')

  const day = { date: '2026-11-11', lines: [{ id: 'a', kind: 'todo', text: 'one', done: false }, { id: 'b', kind: 'todo', text: 'two', done: true },
    { id: 'c', kind: 'note', text: 'three', done: false }, { id: 'd', kind: 'prompt', text: 'four', done: false }, { id: 'e', kind: 'reminder', text: 'five', done: false }] }
  assert.deepStrictEqual(D.padOpenLines(day).lines.map(l => l.id), ['a', 'c', 'e'])
  assert.deepStrictEqual(D.padOpenLines(day, 2), { lines: [day.lines[0], day.lines[2]], more: 1 })
  assert.deepStrictEqual(D.padOpenLines(undefined), { lines: [], more: 0 })

  const rhythm = { work: 50, short: 10, long: 10, cycles: 4 }
  assert.deepStrictEqual(D.pomodoroView(null, now, rhythm), { running: false, paused: false, time: '50:00', pct: 0, title: '', start: 'Start 50/10' })
  const timer = { id: 't', kind: 'pomodoro', plan: M.pomodoroPlan(25, 5, 15, 4), started: new Date(now - 61000).toISOString(), paused: [] }
  const view = D.pomodoroView(timer, now, rhythm)
  assert.deepStrictEqual([view.running, view.time, view.title, view.pct], [true, '23:59', 'Work', 4])
  assert.strictEqual(D.pomodoroView(timer, now + 5 * 3600000, rhythm).running, false, 'a finished pomodoro still counts')

  const entries = [{ start: '2026-11-11T09:00:00+01:00', hours: 1.5 }, { start: '2026-11-11T13:00:00+01:00', hours: 1.25 }, { start: '2026-11-10T09:00:00+01:00', hours: 4 },
    { start: '2026-11-11T17:00:00+01:00', hours: 0.9, running: true }]
  assert.strictEqual(D.hoursToday(entries, now), 2.75)
  assert.strictEqual(M.hoursLabel(D.hoursToday(entries, now)), '2:45')
  assert.strictEqual(D.hoursToday(undefined, now), 0)
  assert.deepStrictEqual(D.clientNames({ clients: [{ name: 'Lindner' }, { name: 'Studio' }], week: { totals: [{ client: 'Pressbrücke' }, { client: 'Lindner' }] } }), ['Lindner', 'Studio', 'Pressbrücke'])
  assert.deepStrictEqual(D.clientNames(undefined), [])

  assert.deepStrictEqual(D.lastColour('rgb(47 158 107)'), { text: 'rgb(47 158 107)', hex: '#2f9e6b' })
  assert.deepStrictEqual(D.lastColour('not a colour'), { text: 'not a colour', hex: null })
  assert.strictEqual(D.lastColour('').hex, '#2f9e6b')
})

await t.test('widgets drawn without the backend: every default widget and tile, the pad read-only while offline', async () => {
  const { M } = await fresh(file)
  const D = M.dashboard
  const opened = []
  const online = draw({ type: D.Dashboard, props: { data: undefined, narrow: true, onOpen: id => opened.push(id) } })
  assert.deepStrictEqual(nodes(online).filter(n => n.props['data-w']).map(n => n.props['data-w']), ['timezones', 'pad', 'pomodoro', 'timelog', 'generate', 'colour'])
  assert.deepStrictEqual(nodes(online).filter(n => n.props['data-tile']).map(n => text(n).trim()), ['Formatter', 'Text diff', 'Encode, decode'])
  const words = text(online)
  for (const expected of ['Add a line', 'Start 25/5', 'today', 'Copy a UUID', 'Copy a password', '#2f9e6b', 'Pick']) {
    assert.ok(words.includes(expected) || nodes(online).some(n => String(n.props.placeholder || '').includes(expected)), `the dashboard lacks "${expected}"`)
  }
  assert.strictEqual(nodes(online).find(n => n.props['aria-label'] === 'Smart paste').props.placeholder, 'Paste anything')
  assert.strictEqual(nodes(online).find(n => n.type === 'button' && text(n) === 'Edit').props.disabled, true, 'Edit without a loaded toolbox')
  nodes(online).find(n => n.props['data-tile'] === 'diff').props.onClick()
  nodes(online).find(n => n.type === 'button' && text(n) === 'Pick').props.onClick()
  assert.deepStrictEqual(opened, ['diff', 'colour'])

  M.$connection.set('offline')
  const offline = draw({ type: D.Dashboard, props: { data: answer(), narrow: false, onOpen: () => {} } })
  const padWidget = nodes(offline).find(n => n.props['data-w'] === 'pad')
  assert.ok(!nodes(padWidget).some(n => n.type === 'input'), 'the pad widget takes a line while offline')
  assert.match(text(padWidget), /Read-only/)
})

await t.test('style: a root with both classes is a grid, the settings sections have their gap, and the chip is no pill', async () => {
  const { M } = await fresh(file)
  const css = draw({ type: M.page.ToolboxPage, props: {} }, new Set(Object.values(M.page.TOOL_VIEWS)))
  const sheet = nodes(css).find(n => n.type === 'style').props.children
  assert.match(sheet, /\.esb\.col, \.esb \.col \{ display: grid; gap: 8px;/, 'a root with class "esb col" is no grid again')
  assert.match(sheet, /\.esb\.settings, \.esb \.settings \{ display: grid; gap: 22px; max-width: 700px;/)
  const chip = sheet.match(/\n\.esbchip \{[^}]*\}/)[0]
  assert.match(chip, /max-width: 60px/)
  assert.match(chip, /border: 0;/)
  assert.doesNotMatch(chip, /999px/)
  assert.match(sheet, /@container \(max-width: 700px\) \{ \.esb \.wgrid \{ grid-template-columns: repeat\(2,/)
  assert.match(sheet, /@container \(max-width: 430px\) \{ \.esb \.wgrid \{ grid-template-columns: minmax\(0, 1fr\); \}/)
  // nothing that floats may sit on the 4 % card tint
  for (const rule of sheet.split('\n').filter(l => /position:\s*(absolute|fixed)/.test(l))) assert.doesNotMatch(rule, /--esb-card|--ui-bg-card/, rule)
})

console.info = info
t.done()
