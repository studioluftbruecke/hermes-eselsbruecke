// The dashboard, the page's landing: the welcome card on the first run, smart paste, then what the
// user pinned in the order of `toolbox.dashboard`: widgets for the tools with live state (world clock,
// pad, pomodoro, time log) or one-click actions (UUID and password, colour), tiles for the rest. Edit
// mode moves, removes and adds; each change is one save of the toolbox file.
// What is shown is decided in the small pure functions below, which tests/test_desktop_dashboard.mjs
// runs without a renderer; the components only draw their answers.
import { host, Switch, useQuery, useQueryClient, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { clockPlaces, clockRow, homeZone } from './clockmath.js'
import { $connection, alertBoth, dayAt, post, qk, rest, storage } from './core.js'
import { detect } from './detect.js'
import { DRAFT, setDraft, useDraft } from './drafts.js'
import { colour, password, uuids } from './engines.js'
import { $rhythm, $running, $tick, $timer, timelogAction, timerAction } from './live.js'
import { hoursLabel, phaseAt } from './timer.js'
import { enterAdds } from './tools/pad.js'
import { Btn, Choice, copyText, docSave, h, Icon, Input, SHELF, ToolIcon, toolRows, useProfile, useToolboxSave } from './ui.js'

export const DEFAULT_DASHBOARD = ['timezones', 'pad', 'pomodoro', 'timelog', 'generate', 'colour', 'formatter', 'diff', 'encode']
// The tools this Desktop draws a widget for; any other pinned tool is a tile that opens it.
const WIDGET_IDS = new Set(['timezones', 'pad', 'pomodoro', 'timelog', 'generate', 'colour'])
const TWO_COLUMNS = new Set(['timezones', 'pad'])

/** 'widgets' or 'tiles' for a tool that can be on the dashboard and is switched on, else null. */
const zoneOf = t => (!t || !t.on || !t.dashboard || !SHELF[t.id] ? null : t.dashboard === 'widget' && WIDGET_IDS.has(t.id) ? 'widgets' : 'tiles')

export const pinnedOf = data => (data && data.toolbox && Array.isArray(data.toolbox.dashboard) ? data.toolbox.dashboard : DEFAULT_DASHBOARD)

/** What the dashboard draws: { widgets, tiles }, each the tool rows in pinned order. A switched-off
 *  tool stays in the list and is skipped here, so it is back in its place when switched on again. */
export function dashboardItems(tools, pinned) {
  const byId = new Map(tools.map(t => [t.id, t]))
  const out = { widgets: [], tiles: [] }
  for (const id of new Set(pinned)) {
    const zone = zoneOf(byId.get(id))
    if (zone) out[zone].push(byId.get(id))
  }
  return out
}

/** The switched-on tools that can be pinned and are not. */
export const addable = (tools, pinned) => tools.filter(t => zoneOf(t) && !pinned.includes(t.id))

export const pin = (pinned, id) => (pinned.includes(id) ? pinned : [...pinned, id])
export const unpin = (pinned, id) => pinned.filter(x => x !== id)

/** The list with `id` moved one place earlier (dir -1) or later (dir 1) among what is drawn beside it:
 *  it changes places with the nearest switched-on tool of its own kind (widget or tile). null at the end. */
export function movePin(pinned, id, dir, tools) {
  const zone = x => zoneOf(tools.find(t => t.id === x))
  const i = pinned.indexOf(id)
  if (i < 0 || !zone(id)) return null
  let j = i + dir
  while (j >= 0 && j < pinned.length && zone(pinned[j]) !== zone(id)) j += dir
  if (j < 0 || j >= pinned.length) return null
  const next = pinned.slice()
  ;[next[i], next[j]] = [next[j], next[i]]
  return next
}

export const dashboardSave = (data, pinned) => docSave(data, { dashboard: pinned })

/** "Done" on the welcome card. */
export const welcomeDone = data => docSave(data, { first_run: false })

/** A switch on the welcome card. It saves the whole file, because the backend's one-switch call also
 *  ends the first run, and the card stays until "Done". */
export function welcomeSwitch(data, id, on) {
  const modules = data.toolbox.modules || {}
  return docSave(data, { modules: { ...modules, [id]: { ...(modules[id] || {}), on } } })
}

/** What smart paste found in a text: detect.js's answer for the switched-on tools, or null. */
export const pasteFound = (text, tools) => detect(text, id => tools.some(t => t.id === id && t.on && SHELF[id]))

/** The answer row's button: the text goes into the tool's fields, then the tool opens. */
export function openDetected(found, open) {
  if (!found || !found.tool) return false
  for (const [key, value] of Object.entries(found.drafts || {})) setDraft(key, value)
  open(found.tool)
  return true
}

/** The world clock widget's rows: this computer's zone first (`you`), then up to `limit` saved places. */
export function clockRows(clocks, now, home = homeZone(), limit = 4) {
  return clockPlaces(clocks, home).slice(0, limit + 1).map((p, i) => ({ ...clockRow(p, home, now), you: i === 0 }))
}

/** The pad widget's lines: today's lines that are not done (queued prompts have their own list in the
 *  tool), at most `limit`, and how many more there are. */
export function padOpenLines(day, limit = 6) {
  const open = ((day && day.lines) || []).filter(l => !l.done && l.kind !== 'prompt')
  return { lines: open.slice(0, limit), more: Math.max(0, open.length - limit) }
}

const clockText = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`

/** The pomodoro widget: the time left and how far the ring is, or the rhythm a start would use. */
export function pomodoroView(timer, now, rhythm) {
  const s = timer ? phaseAt(timer, now) : null
  if (!s || s.done) return { running: false, paused: false, time: `${rhythm.work}:00`, pct: 0, title: '', start: `Start ${rhythm.work}/${rhythm.short}` }
  return { running: true, paused: s.paused, time: clockText(s.remaining_s), title: s.title,
    pct: Math.round(((s.minutes * 60 - s.remaining_s) / (s.minutes * 60)) * 100), start: '' }
}

/** Hours of the finished entries that started today, in the zone the entries are written in. */
export function hoursToday(entries, now = Date.now()) {
  let total = 0
  for (const e of entries || []) if (!e.running && e.start && e.start.slice(0, 10) === dayAt(e.start, now)) total += e.hours || 0
  return total
}

/** The names the client picker offers: the saved clients, then whoever has time this week. */
export function clientNames(data) {
  const names = [...((data && data.clients) || []).map(c => c.name), ...((data && data.week && data.week.totals) || []).map(t => t.client)]
  return [...new Set(names.filter(Boolean))]
}

/** The colour last used in the Colour picker, with a hex to draw when it reads as a colour. */
export function lastColour(text) {
  const value = String(text || '').trim() || '#2f9e6b'
  try {
    return { text: value, hex: colour(value).hex }
  } catch {
    return { text: value, hex: null }
  }
}

// --- widgets ------------------------------------------------------------------------------------------

function ClockWidget({ clocks }) {
  const now = useValue($tick)
  return h('div', null, clockRows(clocks, now).map((r, i) => jsx('div', { className: 'cr', children: [
    jsx('span', { className: r.daylight ? 'sun' : 'moon', title: r.daylight ? 'Day there' : 'Night there' }, 'i'),
    jsx('span', { className: 'nm', children: [r.label, r.day ? jsx('span', { className: 'badge', children: r.day }, 'd') : null] }, 'n'),
    jsx('span', { className: 'tm', children: r.time }, 't'),
    jsx('span', { className: 'rl', children: r.you ? '' : r.relative }, 'r'),
  ] }, i)))
}

function PadWidget({ onOpen }) {
  const profile = useProfile()
  const client = useQueryClient()
  const conn = useValue($connection)
  const key = qk(profile, 'pad', 'today')
  const q = useQuery({ queryKey: key, queryFn: () => rest('/pad'), refetchInterval: 60000, retry: false })
  const [text, setText] = useDraft(DRAFT.padAdd)
  const day = q.data && q.data.day
  const readOnly = conn === 'offline' || conn === 'off'
  const { lines, more } = padOpenLines(day)
  const act = async body => {
    try {
      client.setQueryData(key, await post('/pad/lines', { ...body, date: day && day.date }))
      return true
    } catch (error) {
      alertBoth('Eselsbrücke', error.message, 'warning')
      return false
    }
  }
  const add = async () => {
    if (text.trim() && (await act({ op: 'add', text, kind: 'todo' }))) setText('')
  }
  return [
    jsx('div', { children: lines.length ? lines.map(l => jsx('div', { className: 'pl', children: [
      l.kind === 'todo' || l.kind === 'reminder'
        ? jsx('input', { type: 'checkbox', checked: false, disabled: readOnly, 'aria-label': `Done: ${l.text}`, onChange: () => act({ op: 'update', id: l.id, changes: { done: true } }) }, 'c')
        : jsx('span', { className: 'dot', 'aria-hidden': true, children: '•' }, 'c'),
      jsx('span', { className: 'tx', children: [l.text, l.result != null ? jsx('span', { className: 'res', children: ` ${l.result}` }, 'r') : null] }, 't'),
    ] }, l.id)) : h('p', { className: 'muted' }, q.error && !q.data ? q.error.message : q.isLoading ? 'Loading…' : 'Nothing open today.') }, 'lines'),
    more ? jsx('button', { type: 'button', className: 'link', style: { justifySelf: 'start' }, onClick: () => onOpen('pad'), children: `${more} more` }, 'more') : null,
    readOnly ? jsx('p', { className: 'note', children: 'Not connected to Hermes. Read-only.' }, 'ro')
      : jsx(Input, { value: text, onChange: setText, placeholder: 'Add a line (Enter)', 'aria-label': "Add a line to today's pad", onKeyDown: e => enterAdds(e) && add() }, 'add'),
  ]
}

/** The shared 5 s clock, or one that ticks every second while `active` (the pomodoro shows seconds). */
function useNow(active) {
  const shared = useValue($tick)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return undefined
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [active])
  return active ? Math.max(now, shared) : shared
}

function PomodoroWidget() {
  const t = useValue($timer)
  const rhythm = useValue($rhythm)
  const tick = useValue($tick)
  const now = useNow(pomodoroView(t, tick, rhythm).running)
  const v = pomodoroView(t, now, rhythm)
  return [
    jsx('div', { className: 'row', children: [
      jsx('span', { className: 'esbring', style: { width: 30, height: 30, '--p': `${v.pct}%` } }, 'r'),
      jsx('span', { className: 'wbig', children: v.time }, 't')] }, 'time'),
    jsx('div', { className: 'row', children: v.running ? [
      v.paused ? jsx(Btn, { pri: true, onClick: () => timerAction({ op: 'resume' }), children: 'Resume' }, 'p') : jsx(Btn, { onClick: () => timerAction({ op: 'pause' }), children: 'Pause' }, 'p'),
      jsx(Btn, { onClick: () => timerAction({ op: 'stop' }), children: 'Stop' }, 's'),
      jsx('span', { className: 'muted small', children: `${v.title}${v.paused ? ', paused' : ''}` }, 'l'),
    ] : jsx(Btn, { pri: true, onClick: () => timerAction({ op: 'start', kind: 'pomodoro' }), children: v.start }) }, 'actions'),
  ]
}

function TimelogWidget() {
  const profile = useProfile()
  const client = useQueryClient()
  const q = useQuery({ queryKey: qk(profile, 'timelog', 'this-week'), queryFn: () => rest('/timelog'), refetchInterval: 60000, retry: false })
  const running = useValue($running)
  const now = useValue($tick)
  const [picked, setPicked] = useState('')
  const names = clientNames(q.data)
  const last = storage.get('timelogClient', '')
  const who = picked || (names.includes(last) ? last : names[0] || '')
  const run = async body => {
    await timelogAction(body) // a refusal is already a toast there
    client.invalidateQueries({ queryKey: qk(profile, 'timelog') })
  }
  if (running) {
    return [
      jsx('div', { className: 'row', children: [jsx('span', { className: 'esbdot' }, 'd'),
        jsx('span', { className: 'wbig', children: hoursLabel(Math.max(0, now - new Date(running.start).getTime()) / 3600000) }, 't')] }, 'time'),
      jsx('div', { className: 'row', children: [
        jsx(Btn, { onClick: () => run({ op: 'stop', entry_id: running.id, source: 'page' }), children: 'Stop' }, 's'),
        jsx('span', { className: 'muted small', children: `${running.client}${running.project ? `, ${running.project}` : ''}` }, 'c')] }, 'actions'),
    ]
  }
  const start = () => {
    storage.set('timelogClient', who.trim())
    return run({ op: 'start', fields: { client: who.trim(), project: '', note: '' }, source: 'page' })
  }
  return [
    jsx('div', { className: 'row', children: [
      jsx('span', { className: 'wbig', children: hoursLabel(hoursToday(q.data && q.data.week && q.data.week.entries, now)) }, 't'),
      jsx('span', { className: 'muted small', children: 'today' }, 'l')] }, 'time'),
    jsx('div', { className: 'row', style: { flexWrap: 'nowrap' }, children: [
      names.length
        ? jsx(Choice, { value: who, onChange: setPicked, options: names.map(n => [n, n]), 'aria-label': 'Client', className: 'inp grow' }, 'c')
        : jsx(Input, { value: picked, onChange: setPicked, placeholder: 'Client', 'aria-label': 'Client', className: 'inp grow' }, 'c'),
      jsx(Btn, { pri: true, disabled: !who.trim(), onClick: start, children: 'Start' }, 's')] }, 'actions'),
  ]
}

function GenerateWidget() {
  const [made, setMade] = useState('')
  const make = async (value, what) => {
    setMade(value)
    const ok = await copyText(value)
    host.notify({ kind: ok ? 'success' : 'warning', title: 'Eselsbrücke', message: ok ? `Copied ${what}` : 'Could not copy to the clipboard.' })
  }
  return [
    jsx('div', { className: 'row', children: [
      jsx(Btn, { onClick: () => make(uuids(4, 1)[0], 'a new UUID'), children: 'Copy a UUID' }, 'u'),
      jsx(Btn, { onClick: () => make(password().password, 'a password'), children: 'Copy a password' }, 'p')] }, 'actions'),
    made ? jsx('p', { className: 'mono small muted one', title: made, children: made }, 'made') : null,
  ]
}

function ColourWidget({ onOpen }) {
  const c = lastColour(storage.get('colour', ''))
  const copy = async () => {
    const ok = await copyText(c.text)
    host.notify({ kind: ok ? 'success' : 'warning', title: 'Eselsbrücke', message: ok ? `Copied ${c.text}` : 'Could not copy to the clipboard.' })
  }
  return [
    jsx('div', { className: 'row', style: { flexWrap: 'nowrap' }, children: [
      c.hex ? jsx('span', { className: 'sw16', style: { width: 30, height: 30, borderRadius: 8, background: c.hex } }, 's') : null,
      jsx('span', { className: 'mono one', title: c.text, children: c.text }, 't')] }, 'colour'),
    jsx('div', { className: 'row', children: [
      jsx(Btn, { onClick: copy, children: 'Copy' }, 'c'),
      jsx(Btn, { onClick: () => onOpen('colour'), children: 'Pick' }, 'p')] }, 'actions'),
  ]
}

const WIDGETS = { timezones: ClockWidget, pad: PadWidget, pomodoro: PomodoroWidget, timelog: TimelogWidget, generate: GenerateWidget, colour: ColourWidget }

// --- the page -----------------------------------------------------------------------------------------

function EditButtons({ tool, pinned, tools, change }) {
  const earlier = movePin(pinned, tool.id, -1, tools)
  const later = movePin(pinned, tool.id, 1, tools)
  return h('span', { className: 'wedit' },
    h('button', { type: 'button', disabled: !earlier, 'aria-label': `Move ${tool.title} earlier`, title: 'Earlier', onClick: () => change(earlier) }, h(Icon, { name: 'arrow-left', size: 11 })),
    h('button', { type: 'button', disabled: !later, 'aria-label': `Move ${tool.title} later`, title: 'Later', onClick: () => change(later) }, h(Icon, { name: 'arrow-right', size: 11 })),
    h('button', { type: 'button', 'aria-label': `Remove ${tool.title} from the dashboard`, onClick: () => change(unpin(pinned, tool.id)) }, 'Remove'))
}

function Welcome({ data, tools, save }) {
  return h('section', { className: 'welcome' },
    h('div', { className: 'row' }, h('h2', null, 'Welcome to Eselsbrücke'), h('span', { className: 'grow' }),
      h(Btn, { pri: true, onClick: () => save(welcomeDone(data)) }, 'Done')),
    h('p', null, 'Every tool is on. Switch off what you do not need. You can change this any time in Settings, and Hermes can do it for you when you ask.'),
    h('div', { className: 'wtools' }, tools.map(t => jsx('div', { className: 'trow', children: [
      jsx(ToolIcon, { id: t.id }, 'i'),
      jsx('div', { children: [jsx('b', { children: t.title }, 't'), jsx('span', { className: 'd', children: t.blurb }, 'b')] }, 'd'),
      jsx(Switch, { checked: !!t.on, 'aria-label': t.title, onCheckedChange: v => save(welcomeSwitch(data, t.id, v)) }, 's'),
    ] }, t.id))))
}

/** `data` is the /toolbox answer (absent before the first load and while Hermes was never reached),
 *  `onOpen(id)` shows a tool on the surface this dashboard is drawn on. */
export function Dashboard({ data, narrow, onOpen }) {
  const save = useToolboxSave()
  const [edit, setEdit] = useState(false)
  const [text, setText] = useDraft(DRAFT.smartPaste)
  const tools = toolRows(data)
  const pinned = pinnedOf(data)
  const { widgets, tiles } = dashboardItems(tools, pinned)
  const found = pasteFound(text, tools)
  const more = addable(tools, pinned)
  const change = next => next && data && save(dashboardSave(data, next))
  const buttons = t => (edit ? jsx(EditButtons, { tool: t, pinned, tools, change }, 'edit') : null)
  return h('div', { className: 'dash' },
    data && data.toolbox && data.toolbox.first_run ? h(Welcome, { data, tools, save }) : null,
    h('div', { className: 'vh' }, h('h2', null, 'Dashboard'), h('span', { className: 'grow' }),
      h(Btn, { pri: edit, disabled: !data, onClick: () => setEdit(!edit) }, edit ? 'Done' : 'Edit')),
    h('div', { className: 'paste' },
      h(Input, { value: text, onChange: setText, 'aria-label': 'Smart paste', onKeyDown: e => enterAdds(e) && openDetected(found, onOpen),
        placeholder: narrow ? 'Paste anything' : 'Paste anything: JSON, a timestamp, a colour, Base64, a cron line, a link' }),
      found ? h('div', { className: 'sugg' }, h('strong', null, found.title),
        found.swatch ? h('span', { className: 'sw16', style: { background: found.swatch } }) : null,
        found.tool ? h('code', null, found.detail) : h('span', { className: 'muted small' }, found.detail),
        h('span', { className: 'grow' }),
        found.tool ? h(Btn, { pri: true, onClick: () => openDetected(found, onOpen) }, found.action) : null) : null),
    h('div', { className: `col${edit ? ' editing' : ''}`, style: { gap: 12 } },
      widgets.length ? h('div', { className: 'wgrid' }, widgets.map(t => jsx('section', { className: `w${TWO_COLUMNS.has(t.id) ? ' span2' : ''}`, 'data-w': t.id, children: [
        jsx('header', { children: [jsx(ToolIcon, { id: t.id }, 'i'),
          jsx('button', { type: 'button', className: 't', onClick: () => onOpen(t.id), children: t.title }, 't'), buttons(t)] }, 'h'),
        jsx(WIDGETS[t.id], { onOpen, clocks: data && data.toolbox && data.toolbox.clocks }, 'w'),
      ] }, t.id))) : null,
      tiles.length ? h('div', { className: 'tiles' }, tiles.map(t => (edit
        ? jsx('span', { className: 'tile', 'data-tile': t.id, children: [jsx(ToolIcon, { id: t.id }, 'i'), t.title, buttons(t)] }, t.id)
        : jsx('button', { type: 'button', className: 'tile', 'data-tile': t.id, title: t.blurb, onClick: () => onOpen(t.id), children: [jsx(ToolIcon, { id: t.id }, 'i'), t.title] }, t.id)))) : null,
      !widgets.length && !tiles.length ? h('p', { className: 'muted' }, tools.some(t => zoneOf(t))
        ? 'Nothing is pinned. Edit adds tools to the dashboard.' : 'Every tool is switched off. Switch some on in Settings.') : null),
    edit ? h('div', { className: 'addrow' }, h('h3', null, 'Add to the dashboard'),
      h('div', { className: 'tiles' }, more.length
        ? more.map(t => jsx('button', { type: 'button', className: 'tile', onClick: () => change(pin(pinned, t.id)), children: [jsx(ToolIcon, { id: t.id }, 'i'), t.title, jsx('span', { className: 'x', children: '+' }, 'x')] }, t.id))
        : h('span', { className: 'muted small' }, 'Every tool that is switched on is already here.'))) : null)
}
