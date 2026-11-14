// The tool pages against a fake backend (tests/desktop_harness.mjs): what the world clock's saved list
// becomes on add, remove and rename and the body that saves it, its picker, rows and timestamp block,
// the pad's menu and in-place edit, the time log's edit op, currencies and amounts, and the drafts
// every tool's fields keep. React is a stand-in here (useState answers its first value, nothing
// renders), so the cases call the exported pure functions and read the element tree a tool returns.
// Run by tests/test_desktop_build.py: node test_desktop_tools.mjs <desktop/build/node_modules>
// Prints one JSON line { cases, failed, failures }; exit 1 on a failure.
import assert from 'assert'

import { bundle, fresh, suite } from './desktop_harness.mjs'

// the colour tool asks `window` whether Desktop has a screen picker
globalThis.window = globalThis

const file = await bundle(process.argv[2])
const t = suite()
// 2026-11-09 19:40:02 UTC, a Monday: 20:40 in Berlin (UTC+1), 04:40 on Tuesday in Tokyo.
const WINTER = 1794253202000
const BERLIN = 'Europe/Berlin'
const SAVED = [{ zone: 'America/New_York', label: 'New York' }, { zone: 'Asia/Tokyo', label: 'Tokyo' }]

// The element tree as a flat list and as text (the harness jsx makes { type, props }). `nodes` leaves
// components unrendered; `expand` renders them down to host elements first.
const nodes = n => (n && typeof n === 'object' && !Array.isArray(n) && n.props
  ? [n, ...[].concat(n.props.children || []).flatMap(nodes)] : Array.isArray(n) ? n.flatMap(nodes) : [])
const text = n => (n == null || n === false ? '' : typeof n !== 'object' ? String(n)
  : Array.isArray(n) ? n.map(text).join('') : text(n.props && n.props.children))
const expand = n => (n == null || typeof n !== 'object' ? n : Array.isArray(n) ? n.map(expand)
  : typeof n.type === 'function' ? expand(n.type(n.props)) : { ...n, props: { ...n.props, children: expand(n.props.children) } })

await t.test('the bundle under test carries the harness version', async () => {
  const { M } = await fresh(file)
  assert.strictEqual(M.VERSION, '0.2.2')
})

await t.test('world clock: adding a place appends it, and the save body is the whole document with the new list', async () => {
  const { M } = await fresh(file)
  const C = M.clockTool
  const out = C.nextClocks(SAVED, { type: 'add', zone: 'Asia/Kolkata', label: '  Mumbai ' }, 'Berlin')
  assert.deepStrictEqual(out, { ok: true, changed: true, clocks: [...SAVED, { zone: 'Asia/Kolkata', label: 'Mumbai' }] })
  assert.deepStrictEqual(SAVED.map(c => c.label), ['New York', 'Tokyo'], 'the list passed in was changed')
  const data = { hash: 'h7', toolbox: { schema: 2, first_run: false, dashboard: ['timezones', 'pad'], clocks: SAVED, layout: { chip: 'auto', chip_visible: true } } }
  assert.deepStrictEqual(C.clocksSave(data, out.clocks), { op: 'save', base_hash: 'h7',
    toolbox: { schema: 2, first_run: false, dashboard: ['timezones', 'pad'], clocks: out.clocks, layout: { chip: 'auto', chip_visible: true } } })
})

await t.test('world clock: removing and renaming keep the order and the zone', async () => {
  const { M } = await fresh(file)
  const C = M.clockTool
  assert.deepStrictEqual(C.nextClocks(SAVED, { type: 'remove', label: 'new york' }, 'Berlin'), { ok: true, changed: true, clocks: [{ zone: 'Asia/Tokyo', label: 'Tokyo' }] })
  assert.strictEqual(C.nextClocks(SAVED, { type: 'remove', label: 'Lima' }, 'Berlin').changed, false)
  assert.deepStrictEqual(C.nextClocks(SAVED, { type: 'rename', label: 'Tokyo', to: ' Tokyo   office ' }, 'Berlin'),
    { ok: true, changed: true, clocks: [{ zone: 'America/New_York', label: 'New York' }, { zone: 'Asia/Tokyo', label: 'Tokyo office' }] })
  // the same name again needs no save; another spelling of its own name is a change, not a clash
  assert.strictEqual(C.nextClocks(SAVED, { type: 'rename', label: 'Tokyo', to: 'Tokyo' }, 'Berlin').changed, false)
  assert.deepStrictEqual(C.nextClocks(SAVED, { type: 'rename', label: 'Tokyo', to: 'TOKYO' }, 'Berlin').clocks[1], { zone: 'Asia/Tokyo', label: 'TOKYO' })
})

await t.test('world clock: a name that is taken, empty or too long is refused with a sentence', async () => {
  const { M } = await fresh(file)
  const C = M.clockTool
  const no = (action, home = 'Berlin') => { const out = C.nextClocks(SAVED, action, home); assert.strictEqual(out.ok, false, JSON.stringify(out)); return out.message }
  assert.strictEqual(no({ type: 'add', zone: 'Asia/Tokyo', label: 'tokyo' }), 'Tokyo is already on your clock.')
  // the home row is not in the saved list, but no second row may carry its name
  assert.strictEqual(no({ type: 'add', zone: 'Europe/Berlin', label: 'berlin' }), 'Berlin is already on your clock.')
  assert.strictEqual(no({ type: 'rename', label: 'Tokyo', to: 'New york' }), 'New York is already on your clock.')
  assert.strictEqual(no({ type: 'rename', label: 'Tokyo', to: '   ' }), 'A place needs a name.')
  assert.strictEqual(no({ type: 'add', zone: 'Asia/Tokyo', label: 'x'.repeat(41) }), 'A name is at most 40 characters.')
  assert.strictEqual(C.nextClocks(SAVED, { type: 'add', zone: 'Asia/Tokyo', label: 'x'.repeat(40) }, 'Berlin').ok, true)
  assert.match(no({ type: 'add', zone: 'Mars/Olympus', label: 'Olympus' }), /does not know the time zone of Olympus/)
  assert.strictEqual(no({ type: 'rename', label: 'Lima', to: 'Lima office' }), 'Lima is not on your clock.')
})

await t.test('world clock: 12 places is the limit, and the picker says so', async () => {
  const { M } = await fresh(file)
  const C = M.clockTool
  const eleven = Array.from({ length: 11 }, (_, i) => ({ zone: 'Asia/Tokyo', label: `Place ${i + 1}` }))
  const twelfth = C.nextClocks(eleven, { type: 'add', zone: 'Asia/Kolkata', label: 'Mumbai' }, 'Berlin')
  assert.strictEqual(twelfth.clocks.length, 12)
  assert.strictEqual(C.pickerState('lima', eleven, BERLIN, WINTER).full, false)
  const thirteenth = C.nextClocks(twelfth.clocks, { type: 'add', zone: 'America/Lima', label: 'Lima' }, 'Berlin')
  assert.deepStrictEqual(thirteenth, { ok: false, message: '12 saved places is the most. Remove one to add another.' })
  assert.deepStrictEqual(C.pickerState('lima', twelfth.clocks, BERLIN, WINTER), { full: true, results: [], note: '12 saved places is the most. Remove one to add another.' })
  // a full list can still lose a place and rename one
  assert.strictEqual(C.nextClocks(twelfth.clocks, { type: 'remove', label: 'Mumbai' }, 'Berlin').clocks.length, 11)
  assert.strictEqual(C.nextClocks(twelfth.clocks, { type: 'rename', label: 'Mumbai', to: 'Bombay' }, 'Berlin').ok, true)
})

await t.test('world clock: home is the first row and is never doubled; a zone Desktop does not know is left out', async () => {
  const { M } = await fresh(file)
  const C = M.clockTool
  const saved = [{ zone: 'UTC', label: 'UTC' }, { zone: 'America/New_York', label: 'New York' }, { zone: 'America/New_York', label: 'Boston' }, { zone: 'Mars/Olympus', label: 'Olympus' }]
  assert.deepStrictEqual(C.clockPlaces(saved, 'America/New_York'),
    [{ zone: 'America/New_York', label: 'New York', you: true }, { zone: 'UTC', label: 'UTC' }, { zone: 'America/New_York', label: 'Boston' }])
  assert.deepStrictEqual(C.clockPlaces(saved, BERLIN).map(p => p.label), ['Berlin', 'UTC', 'New York', 'Boston'])
  assert.deepStrictEqual(C.clockPlaces(null, 'UTC'), [{ zone: 'UTC', label: 'UTC', you: true }])
})

await t.test('world clock: the picker lists places with their time and the offset from home, or says why not', async () => {
  const { M } = await fresh(file)
  const C = M.clockTool
  const mumbai = C.pickerState('mumb', SAVED, BERLIN, WINTER)
  assert.deepStrictEqual(mumbai, { full: false, note: '', results: [{ city: 'Mumbai', zone: 'Asia/Kolkata', country: 'India', time: '01:10', relative: '+4:30 h' }] })
  assert.deepStrictEqual(C.pickerState('   ', SAVED, BERLIN, WINTER), { full: false, results: [], note: '' })
  assert.deepStrictEqual(C.pickerState('zzzz', SAVED, BERLIN, WINTER), { full: false, results: [], note: 'No place found. Try a larger city nearby.' })
  // a saved place and the home place are not offered again
  assert.ok(!C.pickerState('tok', SAVED, BERLIN, WINTER).results.some(p => p.city === 'Tokyo'))
  assert.ok(C.pickerState('tok', SAVED, BERLIN, WINTER).results.length > 0)
  // typed in full, a place that is already here says so and offers no neighbour for Enter to add by mistake
  assert.deepStrictEqual(C.pickerState(' tokyo ', SAVED, BERLIN, WINTER), { full: false, results: [], note: 'Tokyo is already on your clock.' })
  assert.deepStrictEqual(C.pickerState('utc', [{ zone: 'UTC', label: 'UTC' }], BERLIN, WINTER), { full: false, results: [], note: 'UTC is already on your clock.' })
  assert.deepStrictEqual(C.pickerState('Berlin', [], BERLIN, WINTER), { full: false, results: [], note: 'Berlin is already on your clock.' })
  // a renamed row frees its city name
  assert.strictEqual(C.pickerState('tokyo', [{ zone: 'Asia/Tokyo', label: 'Tokyo office' }], BERLIN, WINTER).results[0].city, 'Tokyo')
  // a zone name typed out is a place too
  assert.deepStrictEqual(C.pickerState('America/Lima', SAVED, BERLIN, WINTER).results, [{ city: 'Lima', zone: 'America/Lima', country: 'Peru', time: '14:40', relative: `${M.clockmath.MINUS}6 h` }])
  assert.strictEqual(C.pickerState('Mars/Olympus', SAVED, BERLIN, WINTER).note, 'No place found. Try a larger city nearby.')
  assert.strictEqual(C.pickerState('san', SAVED, BERLIN, WINTER).results.length, 7)
})

await t.test('world clock: a saved list reaches the backend as one save and comes back', async () => {
  const { M, server } = await fresh(file)
  const C = M.clockTool
  const data = await M.rest('/toolbox')
  const next = C.nextClocks(data.toolbox.clocks, { type: 'add', zone: 'America/Los_Angeles', label: 'San Francisco' }, 'Berlin')
  const out = await M.post('/toolbox', C.clocksSave(data, next.clocks))
  assert.strictEqual(server.saves.length, 1)
  assert.strictEqual(server.saves[0].op, 'save')
  assert.strictEqual(server.saves[0].base_hash, 'h0')
  assert.deepStrictEqual(server.saves[0].toolbox, { ...data.toolbox, clocks: [{ zone: 'Asia/Tokyo', label: 'Tokyo' }, { zone: 'America/Los_Angeles', label: 'San Francisco' }] })
  assert.deepStrictEqual(out.toolbox.clocks.map(c => c.label), ['Tokyo', 'San Francisco'])
  assert.deepStrictEqual((await M.rest('/toolbox')).toolbox.dashboard, data.toolbox.dashboard, 'the save dropped another part of the document')
})

await t.test('world clock: a Unix time or a date becomes a row per place', async () => {
  const { M } = await fresh(file)
  const C = M.clockTool
  const places = [{ zone: BERLIN, label: 'Berlin' }, { zone: 'Asia/Tokyo', label: 'Tokyo office' }, { zone: 'Asia/Kolkata', label: 'Mumbai' }]
  const want = [{ label: 'Berlin', time: '2026-11-09 20:40', utc: 'UTC+1' }, { label: 'Tokyo office', time: '2026-11-10 04:40', utc: 'UTC+9' }, { label: 'Mumbai', time: '2026-11-10 01:10', utc: 'UTC+5:30' }]
  assert.deepStrictEqual(C.stampRows('1794253202', places), { ok: true, unit: 's', unix: 1794253202, iso: '2026-11-09T19:40:02Z', rows: want })
  assert.deepStrictEqual(C.stampRows(' 1794253202000 ', places).rows, want)
  assert.strictEqual(C.stampRows('1794253202000', places).unit, 'ms')
  // a date without an offset is read where the user is: 14:30 in Berlin is 13:30 UTC
  const date = C.stampRows('2026-11-09 14:30', places)
  assert.deepStrictEqual([date.unit, date.unix, date.rows[0].time, date.rows[1].time], ['iso', 1794231000, '2026-11-09 14:30', '2026-11-09 22:30'])
  assert.strictEqual(C.stampRows('   ', places), null)
  const bad = C.stampRows('next week', places)
  assert.strictEqual(bad.ok, false)
  assert.match(bad.error, /cannot read 'next week'/)
})

await t.test('world clock: without Hermes the rows come from the list kept on this computer, and nothing can be changed', async () => {
  const { M, store } = await fresh(file)
  store.set('clocks:p1', JSON.stringify([{ zone: 'Asia/Tokyo', label: 'Tokyo office' }, { zone: 'Asia/Kolkata', label: 'Mumbai' }]))
  M.$connection.set('offline')
  M.drafts.setDraft(M.drafts.DRAFT.clockStamp, '1794253202')
  const tree = expand(M.clockTool.ClockTool())
  const all = nodes(tree)
  const rows = all.filter(n => n.props.className === 'cr' && nodes(n).some(x => x.props.className === 'bar24'))
  const home = M.clockmath.cityName(M.clockmath.homeZone())
  assert.deepStrictEqual(rows.map(r => text(nodes(r).find(x => x.type === 'b'))), [`${home}you`, 'Tokyo office', 'Mumbai'])
  for (const row of rows) {
    const cells = nodes(nodes(row).find(x => x.props.className === 'bar24')).filter(x => x.type === 'i')
    assert.strictEqual(cells.length, 24)
    assert.strictEqual(cells.filter(c => / now$/.test(c.props.className)).length, 1, 'one outlined hour per bar')
  }
  assert.match(text(all.find(n => n.props.className === 'banner')), /^Not connected to Hermes\. The clock keeps running/)
  assert.strictEqual(all.find(n => n.props['aria-label'] === 'Add a place').props.disabled, true)
  assert.ok(!all.some(n => /^Remove /.test(n.props['aria-label'] || '')), 'a remove button while nothing can be saved')
  assert.ok(!all.some(n => n.props.className === 'lbl'), 'a label that can be renamed while nothing can be saved')
  // the timestamp block reads its draft (smart paste fills it) and works without the backend
  assert.strictEqual(all.find(n => n.props['aria-label'] === 'Unix seconds, milliseconds or a date').props.value, '1794253202')
  assert.match(text(all.find(n => / cstamp$/.test(n.props.className || ''))), /Tokyo office2026-11-10 04:40UTC\+9/)
  // nothing kept yet: the places every toolbox starts with
  const first = await fresh(file)
  const start = nodes(expand(first.M.clockTool.ClockTool())).filter(n => n.type === 'b').map(text)
  assert.ok(start.includes('Tokyo') && (start.includes('New York') || home === 'New York'), JSON.stringify(start))
})

const ENTRY = { id: 'e1', client: 'Acme', project: 'Site', note: 'export bugs', start: '2026-11-09T09:00:12+01:00', end: '2026-11-09T11:30:00+01:00', hours: 2.5, running: false }

await t.test('time log: the edit row becomes an edit op with only what changed, on the entry\'s own day and offset', async () => {
  const { M } = await fresh(file)
  const T = M.timelogTool
  const f = T.editFields(ENTRY)
  assert.deepStrictEqual(f, { client: 'Acme', project: 'Site', note: 'export bugs', from: '09:00', to: '11:30' })
  assert.deepStrictEqual(T.editOp(ENTRY, f), { ok: true, body: null }, 'an untouched row asks for a save')
  assert.deepStrictEqual(T.editOp(ENTRY, { ...f, to: '12:15', note: ' export bugs,  both ' }),
    { ok: true, body: { op: 'edit', entry_id: 'e1', fields: { note: 'export bugs, both', end: '2026-11-09T12:15:00+01:00' } } })
  assert.deepStrictEqual(T.editOp(ENTRY, { ...f, from: '8:45', client: 'Acme GmbH', project: '' }).body.fields, { client: 'Acme GmbH', project: '', start: '2026-11-09T08:45:00+01:00' })
  // an entry written through the outbox carries the Mac's offset; the edited time stays on that clock
  const outbox = { ...ENTRY, start: '2026-11-09T11:00:05-05:00', end: '2026-11-09T12:00:00-05:00' }
  assert.deepStrictEqual(T.editOp(outbox, { ...T.editFields(outbox), to: '18:40' }).body.fields, { end: '2026-11-09T18:40:00-05:00' })
  const utc = { ...ENTRY, start: '2026-11-09T08:00:00Z', end: '2026-11-09T09:00:00Z' }
  assert.deepStrictEqual(T.editOp(utc, { ...T.editFields(utc), to: '09:30' }).body.fields, { end: '2026-11-09T09:30:00Z' })
})

await t.test('time log: an edit that cannot be right is refused before it is sent', async () => {
  const { M } = await fresh(file)
  const T = M.timelogTool
  const f = T.editFields(ENTRY)
  assert.deepStrictEqual(T.editOp(ENTRY, { ...f, client: '   ' }), { ok: false, error: 'An entry needs a client.' })
  assert.deepStrictEqual(T.editOp(ENTRY, { ...f, to: '25:00' }), { ok: false, error: 'Write a time like 09:30.' })
  assert.deepStrictEqual(T.editOp(ENTRY, { ...f, from: 'nine' }), { ok: false, error: 'Write a time like 09:30.' })
  assert.deepStrictEqual(T.editOp(ENTRY, { ...f, to: '' }), { ok: false, error: 'Write a time like 09:30.' })
  assert.deepStrictEqual(T.editOp(ENTRY, { ...f, to: '08:00' }), { ok: false, error: 'The end lies before the start.' })
  assert.deepStrictEqual(T.editOp(ENTRY, { ...f, from: '11:45' }), { ok: false, error: 'The end lies before the start.' })
  assert.strictEqual(T.editOp(ENTRY, { ...f, from: '11:30' }).ok, true)
})

await t.test('time log: an amount shows its currency, euros as before, and a total without one counts as euros', async () => {
  const { M } = await fresh(file)
  const T = M.timelogTool
  assert.strictEqual(T.amountLabel({ amount: '202.80', currency: 'EUR' }), '202.80 €')
  assert.strictEqual(T.amountLabel({ amount: '202.80' }), '202.80 €')
  assert.strictEqual(T.amountLabel({ amount: '202.80', currency: 'USD' }), '202.80 USD')
  assert.strictEqual(T.amountLabel({ amount: '0.00', currency: 'CHF' }), '0.00 CHF')
  assert.strictEqual(T.amountLabel({ amount: null, currency: 'USD' }), '')
  assert.strictEqual(T.amountLabel({ client: 'Internal' }), '')
})

await t.test('time log: the rate row sends a three-letter currency, EUR when the field is empty', async () => {
  const { M } = await fresh(file)
  const T = M.timelogTool
  assert.deepStrictEqual(T.CURRENCIES, ['EUR', 'USD', 'GBP', 'CHF'])
  assert.deepStrictEqual([T.currencyCode(''), T.currencyCode(' usd '), T.currencyCode('Sek'), T.currencyCode('euro'), T.currencyCode('$'), T.currencyCode('e1r')], ['EUR', 'USD', 'SEK', null, null, null])
  assert.deepStrictEqual(T.rateOp({ name: ' Acme ', rate: '95', currency: 'chf' }), { op: 'client', name: 'Acme', rate: 95, currency: 'CHF' })
  assert.deepStrictEqual(T.rateOp({ name: 'Acme', rate: '80.5', currency: '' }), { op: 'client', name: 'Acme', rate: 80.5, currency: 'EUR' })
  assert.deepStrictEqual(T.rateOp({ name: 'Acme', rate: '', currency: 'USD' }), { op: 'client', name: 'Acme', rate: null, currency: 'USD' })
  assert.strictEqual(T.rateOp({ name: '  ', rate: '80', currency: 'EUR' }), null)
  assert.strictEqual(T.rateOp({ name: 'Acme', rate: '80', currency: 'euros' }), null)
})

const LINE = { id: 'l1', kind: 'todo', text: 'Call the bank', done: false }

await t.test('pad: an edited text becomes one update, and an empty or unchanged text is not saved', async () => {
  const { M } = await fresh(file)
  const P = M.pad
  assert.deepStrictEqual(P.editBody(LINE, '  Call the  bank at ten '), { op: 'update', id: 'l1', changes: { text: 'Call the bank at ten' } })
  assert.strictEqual(P.editBody(LINE, '   '), null)
  assert.strictEqual(P.editBody(LINE, ''), null)
  assert.strictEqual(P.editBody(LINE, ' Call the bank '), null)
  assert.strictEqual(P.editKey({ key: 'Enter', nativeEvent: {} }), 'save')
  assert.strictEqual(P.editKey({ key: 'Escape', nativeEvent: {} }), 'cancel')
  assert.strictEqual(P.editKey({ key: 'a', nativeEvent: {} }), null)
  // Enter that confirms composed characters (Japanese, Chinese, Korean) does not save
  assert.strictEqual(P.editKey({ key: 'Enter', nativeEvent: { isComposing: true } }), null)
  assert.strictEqual(P.editKey({ key: 'Enter', keyCode: 229, nativeEvent: {} }), null)
})

await t.test('pad: the line menu is Desktop\'s menu, Edit first and Delete last after a separator, never a see-through panel', async () => {
  const { M } = await fresh(file)
  const sent = []
  const tree = M.pad.Line({ line: LINE, date: '2026-11-11', act: (...a) => { sent.push(a) }, readOnly: false })
  const all = nodes(tree)
  assert.ok(!all.some(n => /\bpanel\b/.test(n.props.className || '')), 'the menu is drawn as a .panel again (4 % tint over transparent)')
  const items = all.filter(n => typeof n.props.onSelect === 'function')
  assert.deepStrictEqual(items.map(text), ['Edit', 'Ask Hermes about this', 'Prompt for tomorrow', 'Make a kanban card', 'Delete'])
  assert.strictEqual(items[4].props.variant, 'destructive')
  // the menu's own children in order: the last two are a separator (no text, no action) and Delete
  const content = all.find(n => [].concat(n.props.children || []).includes(items[0]))
  const kids = [].concat(content.props.children)
  assert.strictEqual(kids[kids.length - 1], items[4])
  const separator = kids[kids.length - 2]
  assert.ok(separator && text(separator) === '' && !separator.props.onSelect, 'no separator before Delete')
  assert.strictEqual(typeof content.type, 'function', 'the menu is a host element, not the SDK component')
  // the trigger is a real button inside the SDK trigger, and it is the menu that owns open and close
  const root = all.find(n => typeof n.props.onOpenChange === 'function')
  assert.strictEqual(root.props.open, false)
  const trigger = all.find(n => n.props['aria-label'] === 'Line actions')
  assert.strictEqual(trigger.type, 'button')
  assert.ok(all.some(n => n.props.asChild === true && [].concat(n.props.children).includes(trigger)))
  items[2].props.onSelect()
  items[3].props.onSelect()
  items[4].props.onSelect()
  assert.deepStrictEqual(sent, [[{ op: 'update', id: 'l1', changes: { kind: 'prompt' } }], [{ op: 'card', id: 'l1' }], [{ op: 'delete', id: 'l1' }, LINE]])
})

await t.test('pad: the menu leaves out what does not apply, the text is clickable to edit, and a read-only pad has neither', async () => {
  const { M } = await fresh(file)
  const labels = line => nodes(M.pad.Line({ line, date: '2026-11-11', act: () => {}, readOnly: false })).filter(n => typeof n.props.onSelect === 'function').map(text)
  assert.deepStrictEqual(labels({ ...LINE, kind: 'prompt', queued_for: '2026-11-12' }), ['Edit', 'Ask Hermes about this', 'Make a kanban card', 'Delete'])
  assert.deepStrictEqual(labels({ ...LINE, card_id: 't_12' }), ['Edit', 'Ask Hermes about this', 'Prompt for tomorrow', 'Delete'])
  const live = nodes(M.pad.Line({ line: LINE, date: '2026-11-11', act: () => {}, readOnly: false }))
  const clickable = live.find(n => n.props.title === 'Click to edit')
  assert.strictEqual(text(clickable), 'Call the bank')
  assert.strictEqual(typeof clickable.props.onClick, 'function')
  const frozen = nodes(M.pad.Line({ line: LINE, date: '2026-11-11', act: () => {}, readOnly: true }))
  assert.ok(!frozen.some(n => typeof n.props.onSelect === 'function' || n.props['aria-label'] === 'Line actions' || n.props.title === 'Click to edit'))
  assert.match(text(frozen), /Call the bank/)
})

await t.test('drafts: every tool shows what its fields held, so the text survives leaving the tool', async () => {
  const { M, store } = await fresh(file)
  const { DRAFT, setDraft } = M.drafts
  const views = M.page.TOOL_VIEWS
  assert.ok(views && views.encode, 'page.js no longer exports TOOL_VIEWS: reach the tool components another way in this case')
  // the value a field shows, found by one of its props
  const shown = (id, prop, want) => {
    const hit = nodes(views[id]()).find(n => n.props[prop] === want && 'value' in n.props)
    assert.ok(hit, `${id}: no field with ${prop} = ${JSON.stringify(want)}`)
    return hit.props.value
  }
  const cases = [
    ['formatter', DRAFT.formatterText, '{"a":1}', 'aria-label', 'Input'],
    ['diff', DRAFT.diffLeft, 'before text', 'rows', 10],
    ['regex', DRAFT.regexPattern, '(\\d+)', 'placeholder', 'Pattern, e.g. (\\d{4})-(\\d{2})'],
    ['regex', DRAFT.regexFlags, 'gm', 'aria-label', 'Flags'],
    ['regex', DRAFT.regexText, 'a 12 b', 'placeholder', 'Text to search'],
    ['tokens', DRAFT.tokensText, 'count me', 'placeholder', 'Paste a prompt'],
    ['cron', DRAFT.cronExpr, '0 9 * * 1', 'aria-label', 'Cron expression'],
    ['encode', DRAFT.encodeText, 'aGVsbG8=', 'rows', 6],
    ['encode', DRAFT.encodeDir, 'decode', 'aria-label', 'Direction'],
    ['encode', DRAFT.encodeScheme, 'base64url', 'aria-label', 'Scheme'],
    ['qr', DRAFT.qrText, 'https://luftbruecke.studio', 'placeholder', 'Text or a link'],
    ['colour', DRAFT.colourText, 'oklch(62% 0.13 160)', 'aria-label', 'Colour'],
    ['timezones', DRAFT.clockStamp, '1794253202000', 'aria-label', 'Unix seconds, milliseconds or a date'],
  ]
  for (const [id, key, value, prop, want] of cases) {
    setDraft(key, value)
    assert.strictEqual(shown(id, prop, want), value, `${id} does not show its draft ${key}`)
  }
  setDraft(DRAFT.diffRight, 'after text')
  assert.deepStrictEqual(nodes(views.diff()).filter(n => n.props.rows === 10).map(n => n.props.value), ['before text', 'after text'])
  // the pad's add field: the pad is writable once Hermes answers
  M.$connection.set('ok')
  setDraft(DRAFT.padAdd, 'half a line')
  assert.strictEqual(shown('pad', 'placeholder', 'Add a line (Enter)'), 'half a line')
  setDraft(DRAFT.timelogForm, { client: 'Acme', project: 'Site', note: 'call', minutes: '30' })
  assert.strictEqual(shown('timelog', 'placeholder', 'Acme'), 'Acme')
  assert.strictEqual(shown('timelog', 'placeholder', 'min'), '30')
  // first use: each field starts with its own default, the colour with the one kept on this computer
  const first = await fresh(file)
  first.store.set('colour', JSON.stringify('#123456'))
  const start = (id, prop, want) => nodes(first.M.page.TOOL_VIEWS[id]()).find(n => n.props[prop] === want && 'value' in n.props).props.value
  assert.strictEqual(start('colour', 'aria-label', 'Colour'), '#123456')
  assert.strictEqual(start('cron', 'aria-label', 'Cron expression'), '*/15 9-17 * * 1-5')
  assert.strictEqual(start('regex', 'aria-label', 'Flags'), 'gi')
  assert.strictEqual(start('encode', 'aria-label', 'Direction'), 'encode')
  assert.strictEqual(store.has('formatter.text'), false, 'a draft was written to storage (drafts are memory only)')
})

await t.test('the old Time zones tool is gone, and its id opens the world clock', async () => {
  const { M } = await fresh(file)
  assert.strictEqual(M.page.TOOL_VIEWS.timezones, M.clockTool.ClockTool)
  const head = nodes(M.clockTool.ClockTool()).find(n => n.props.title === 'World clock')
  assert.strictEqual(head.props.blurb, 'The time in your places, and Unix timestamps.')
})

t.done()
