// World clock: the time in the user's places in one overview (home first), a place picker that
// searches cities, a scrubber to look ahead or back, the times as one line of text, and Unix
// timestamps. The maths and the place list live in clockmath.js; this file decides what the saved
// list becomes and draws it. The clock runs without the backend; only changing the list needs it.
import { useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, alertBoth, storage } from '../core.js'
import { cityName, clockPlaces, clockRow, copyLine, homeZone, hourBar, places as allPlaces, relativeLabel, resolvePlace, searchPlaces, shiftLabel, utcLabel, validZone, zoneParts } from '../clockmath.js'
import { DRAFT, useDraft } from '../drafts.js'
import { convertTimestamp } from '../engines.js'
import { Btn, ConnectionBanner, Copy, h, Input, Out, ToolHead, useProfile, useToolbox, useToolboxSave } from '../ui.js'
import { enterAdds } from './pad.js'

export const MAX_CLOCKS = 12
export const MAX_LABEL = 40
export const LIMIT_TEXT = `${MAX_CLOCKS} saved places is the most. Remove one to add another.`
// What the backend starts every toolbox with; shown until a toolbox has been loaded once.
export const DEFAULT_CLOCKS = [{ zone: 'UTC', label: 'UTC' }, { zone: 'America/New_York', label: 'New York' }, { zone: 'Asia/Tokyo', label: 'Tokyo' }]

const sameLabel = (a, b) => String(a).trim().toLowerCase() === String(b).trim().toLowerCase()
const refuse = message => ({ ok: false, message })

/** The saved list after one change, or why not. `action` is { type: 'add', zone, label },
 *  { type: 'remove', label } or { type: 'rename', label, to }. The home row is never in the list, but
 *  its label counts as taken, so no second row carries the same name.
 *  Answers { ok: true, clocks, changed } or { ok: false, message }. */
export function nextClocks(list, action, homeLabel = '') {
  const clocks = (list || []).map(c => ({ ...c }))
  // the label already on the clock under this name (as it is written there), if any
  const taken = (label, except) => (sameLabel(label, homeLabel) ? homeLabel : (clocks.find(c => c !== except && sameLabel(c.label, label)) || {}).label)
  if (action.type === 'remove') {
    const rest = clocks.filter(c => !sameLabel(c.label, action.label))
    return { ok: true, clocks: rest, changed: rest.length !== clocks.length }
  }
  const label = String((action.type === 'rename' ? action.to : action.label) || '').replace(/\s+/g, ' ').trim()
  if (!label) return refuse('A place needs a name.')
  if (label.length > MAX_LABEL) return refuse(`A name is at most ${MAX_LABEL} characters.`)
  if (action.type === 'add') {
    if (clocks.length >= MAX_CLOCKS) return refuse(LIMIT_TEXT)
    if (!validZone(action.zone)) return refuse(`This Desktop does not know the time zone of ${label}.`)
    if (taken(label)) return refuse(`${taken(label)} is already on your clock.`)
    return { ok: true, clocks: [...clocks, { zone: action.zone, label }], changed: true }
  }
  if (action.type === 'rename') {
    const row = clocks.find(c => sameLabel(c.label, action.label))
    if (!row) return refuse(`${action.label} is not on your clock.`)
    if (row.label === label) return { ok: true, clocks, changed: false }
    if (taken(label, row)) return refuse(`${taken(label, row)} is already on your clock.`)
    row.label = label
    return { ok: true, clocks, changed: true }
  }
  return refuse('Unknown change.')
}

/** The body that saves a new list: the whole document, as POST /toolbox `save` takes it. */
export const clocksSave = (data, clocks) => ({ op: 'save', base_hash: data.hash, toolbox: { ...data.toolbox, clocks } })

export { clockPlaces }

/** What the picker shows for a typed text: results with their time now and the offset from home,
 *  or one line saying why there is none. `full` once the list holds the most it can. */
export function pickerState(query, saved, home, ms = Date.now()) {
  if ((saved || []).length >= MAX_CLOCKS) return { full: true, results: [], note: LIMIT_TEXT }
  const q = String(query || '').trim()
  if (!q) return { full: false, results: [], note: '' }
  const labels = [cityName(home), ...(saved || []).map(c => c.label)]
  // A place typed in full that is already here gets that answer and no list: the search would offer
  // its neighbours in the same zone, and Enter would add one of them in its place.
  const exact = resolvePlace(q)
  const held = exact && labels.find(l => sameLabel(l, exact.label))
  if (held) return { full: false, results: [], note: `${held} is already on your clock.` }
  let found = searchPlaces(q, { taken: labels })
  // a zone name typed out (Europe/Paris) is a place too, though the search matches cities and countries
  if (!found.length && exact) found = [{ city: exact.label, zone: exact.zone, country: (allPlaces().find(p => p.zone === exact.zone) || {}).country || '' }]
  const results = found.map(p => {
    const t = zoneParts(p.zone, ms)
    return { ...p, time: `${t.hour}:${t.minute}`, relative: relativeLabel(p.zone, home, ms) }
  })
  return { full: false, results, note: results.length ? '' : 'No place found. Try a larger city nearby.' }
}

/** A typed Unix time (seconds or milliseconds) or ISO date as a row per place. A date without an
 *  offset is read in the first place's zone, which is home.
 *  { ok: true, unit, unix, iso, rows: [{ label, time, utc }] }, { ok: false, error }, or null for no text. */
export function stampRows(text, places) {
  if (!String(text || '').trim()) return null
  try {
    const r = convertTimestamp(text, places.map(p => p.zone))
    return { ok: true, unit: r.input_unit, unix: r.unix, iso: r.iso_utc,
      rows: places.map((p, i) => ({ label: p.label, time: r.zones[i].time, utc: utcLabel(p.zone, r.unix_ms) })) }
  } catch (error) {
    return { ok: false, error: error.message }
  }
}

const UNITS = { s: 'Read as seconds.', ms: 'Read as milliseconds.', iso: 'Read as a date in your time zone, unless it has an offset.' }

/** The time now, renewed at each full minute: the rows show hours and minutes, so they change on
 *  the minute like the system clock, and the tool draws once a minute while nothing else happens. */
function useNow() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    let timer = null
    const arm = () => {
      timer = setTimeout(() => {
        setNow(Date.now())
        arm()
      }, 60000 - (Date.now() % 60000) + 40)
    }
    arm()
    return () => clearTimeout(timer)
  }, [])
  return now
}

const SUN = [jsx('circle', { cx: 8, cy: 8, r: 2.8 }, 'c'), jsx('path', { d: 'M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1' }, 'p')]
const MOON = [jsx('path', { d: 'M12.5 9.6A5 5 0 1 1 6.4 3.5a4 4 0 0 0 6.1 6.1z' }, 'p')]
// Desktop's icon font has no sun or moon, so the two are drawn here.
const DayIcon = ({ daylight }) => h('svg', { className: 'ic', viewBox: '0 0 16 16', 'aria-hidden': true }, daylight ? SUN : MOON)

const BAR_CLASS = { work: 'bw', awake: 'be', night: '' }
const BAR_TITLE = 'Your day, hour by hour: bright where it is 9 to 17 there'

function HourBar({ zone, home, ms }) {
  const bar = hourBar(zone, home, ms)
  return h('div', { className: 'bar24', title: BAR_TITLE },
    bar.cells.map((cell, i) => jsx('i', { className: `${BAR_CLASS[cell]}${i === bar.now ? ' now' : ''}` }, i)))
}

export function ClockTool() {
  const tb = useToolbox()
  const save = useToolboxSave()
  const profile = useProfile()
  const conn = useValue($connection)
  const now = useNow()
  const [shift, setShift] = useState(0)
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)
  const [active, setActive] = useState(0)
  const [rename, setRename] = useState(null) // { label, text } while a label is being renamed
  const [busy, setBusy] = useState(false)
  const [stamp, setStamp] = useDraft(DRAFT.clockStamp, String(Math.floor(Date.now() / 1000)))
  const field = useRef(null)

  const home = homeZone()
  const doc = tb.data && tb.data.toolbox
  const loaded = doc && Array.isArray(doc.clocks) ? doc.clocks : null
  const cacheKey = `clocks:${profile}`
  // The last loaded list is kept on this computer, so the places are here after a restart without Hermes.
  useEffect(() => {
    if (loaded) storage.set(cacheKey, loaded)
  }, [cacheKey, JSON.stringify(loaded)])
  const saved = loaded || storage.get(cacheKey, DEFAULT_CLOCKS)
  const readOnly = !loaded || conn === 'offline' || conn === 'off'

  const ms = now + shift * 60000
  const places = clockPlaces(saved, home)
  const rows = places.map(p => clockRow(p, home, ms))
  const line = copyLine(rows)
  const pick = readOnly ? { full: false, results: [], note: '' } : pickerState(query, saved, home, now)
  const at = Math.min(active, Math.max(0, pick.results.length - 1))
  const listOpen = focused && !pick.full && (pick.results.length > 0 || !!pick.note)
  const ts = stampRows(stamp, places)

  /** One change to the saved list: refused with a toast, or saved. True when the list is as asked. */
  const change = async action => {
    const out = nextClocks(saved, action, cityName(home))
    if (!out.ok) {
      alertBoth('Eselsbrücke', out.message, 'warning')
      return false
    }
    if (!out.changed) return true
    setBusy(true)
    try {
      return !!(await save(clocksSave(tb.data, out.clocks))) // a refusal is already a toast
    } finally {
      setBusy(false)
    }
  }
  const add = async place => {
    if (busy || !place) return
    if (await change({ type: 'add', zone: place.zone, label: place.city })) setQuery('')
    setActive(0)
    if (field.current) field.current.focus()
  }
  const finishRename = async () => {
    if (!rename.text.trim() || (await change({ type: 'rename', label: rename.label, to: rename.text }))) setRename(null)
  }
  const pickerKey = e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      setActive(Math.max(0, Math.min(pick.results.length - 1, at + (e.key === 'ArrowDown' ? 1 : -1))))
    } else if (enterAdds(e)) add(pick.results[at])
    else if (e.key === 'Escape') setQuery('')
  }

  const row = (place, r) => {
    const renaming = !!rename && rename.label === place.label && !place.you && !readOnly
    return jsx('div', { className: 'cr', children: [
      jsx(DayIcon, { daylight: r.daylight }, 'i'),
      jsx('div', { className: 'nm', children: [
        renaming
          ? jsx(Input, { value: rename.text, onChange: text => setRename({ ...rename, text }), autoFocus: true, onFocus: e => e.target.select(), maxLength: MAX_LABEL,
            'aria-label': `Name for ${place.label}`, title: 'Enter saves, Escape cancels', disabled: busy,
            onKeyDown: e => (enterAdds(e) ? finishRename() : e.key === 'Escape' ? setRename(null) : null) }, 'e')
          : jsx('b', { children: [
            place.you || readOnly ? place.label
              : jsx('button', { type: 'button', className: 'lbl', title: 'Click to rename', onClick: () => setRename({ label: place.label, text: place.label }), children: place.label }, 'l'),
            place.you ? jsx('span', { className: 'badge acc', children: 'you' }, 'y') : null] }, 'b'),
        jsx('span', { children: `${r.utc} · ${r.weekday}${r.day ? ` · ${r.day}` : ''}` }, 's')] }, 'n'),
      jsx(HourBar, { zone: place.zone, home, ms }, 'h'),
      jsx('span', { className: 'tm', children: r.time }, 't'),
      jsx('span', { className: 'rl', children: place.you ? '' : r.relative }, 'r'),
      place.you || readOnly ? jsx('span', {}, 'x')
        : jsx('button', { type: 'button', className: 'rm', 'aria-label': `Remove ${place.label}`, title: `Remove ${place.label}`, disabled: busy,
          onClick: () => change({ type: 'remove', label: place.label }), children: '×' }, 'x'),
    ] }, place.you ? 'you' : `p-${place.label}`)
  }

  return h('div', { className: `col clock${shift ? ' shifted' : ''}` },
    h(ToolHead, { title: 'World clock', blurb: 'The time in your places, and Unix timestamps.' }),
    h(ConnectionBanner, { what: 'Not connected to Hermes. The clock keeps running; places can be changed when the connection is back.' }),
    h('div', { className: 'picker' },
      h(Input, { ref: field, value: query, disabled: readOnly || pick.full, autoComplete: 'off', role: 'combobox', 'aria-label': 'Add a place', 'aria-expanded': listOpen,
        'aria-controls': 'esb-places', 'aria-autocomplete': 'list', 'aria-activedescendant': listOpen && pick.results.length ? `esb-place-${at}` : undefined,
        placeholder: 'Add a place: type a city, like Tokyo or San Francisco',
        onChange: text => { setQuery(text); setActive(0) }, onFocus: () => setFocused(true), onBlur: () => setFocused(false), onKeyDown: pickerKey }),
      pick.full ? h('p', { className: 'note' }, pick.note) : null,
      listOpen ? h('div', { className: 'results', id: 'esb-places', role: 'listbox', 'aria-label': 'Places',
        // a press on a result must not take the focus from the field, or the list would close under the click
        onMouseDown: e => e.preventDefault() },
      pick.results.length
        ? pick.results.map((p, i) => jsx('button', { type: 'button', id: `esb-place-${i}`, role: 'option', 'aria-selected': i === at, tabIndex: -1, className: i === at ? 'first' : undefined,
          onMouseEnter: () => setActive(i), onClick: () => add(p), children: [
            jsx('span', { children: [jsx('b', { children: p.city }, 'c'), ' ', jsx('span', { className: 'z', children: p.country }, 'z')] }, 'n'),
            jsx('span', { className: 'mono', children: p.time }, 't'),
            jsx('span', { className: 'z', children: p.relative }, 'r')] }, `${p.zone}/${p.city}`))
        : h('span', { className: 'none' }, pick.note)) : null),
    h('div', { className: 'panel cfull' }, places.map((p, i) => row(p, rows[i]))),
    h('div', { className: 'scrub' },
      h('strong', null, shiftLabel(shift)),
      h('input', { type: 'range', min: -720, max: 720, step: 15, value: shift, 'aria-label': 'Move the time', 'aria-valuetext': shiftLabel(shift), onChange: e => setShift(Number(e.target.value)) }),
      h(Btn, { disabled: !shift, onClick: () => setShift(0) }, 'Now')),
    h('div', { className: 'row' }, h(Copy, { text: line, label: 'Copy as text' }), h('span', { className: 'copyline' }, line)),
    h('div', { className: 'panel col cstamp' },
      h('div', { className: 'row' }, h('h3', null, 'Unix timestamp'), h('span', { className: 'grow' }),
        h(Input, { value: stamp, onChange: setStamp, className: 'inp mono', 'aria-label': 'Unix seconds, milliseconds or a date', style: { width: 170 } }),
        h(Btn, { onClick: () => setStamp(String(Math.floor(Date.now() / 1000))) }, 'Now')),
      !ts ? h('p', { className: 'note' }, 'Type Unix seconds, milliseconds or a date like 2026-11-09 14:30.') : null,
      ts && !ts.ok ? h(Out, { err: true }, ts.error) : null,
      ts && ts.ok ? h('div', null, ts.rows.map((r, i) => jsx('div', { className: 'cr', children: [
        jsx('span', {}, 'i'), jsx('span', { className: 'nm', children: r.label }, 'n'), jsx('span', { className: 'tm', children: r.time }, 't'), jsx('span', { className: 'rl', children: r.utc }, 'u')] }, i))) : null,
      ts && ts.ok ? h('div', { className: 'row small also' },
        h('span', { className: 'note grow' }, UNITS[ts.unit]),
        h('span', { className: 'pair' }, h('span', { className: 'muted' }, 'Unix'), h('span', { className: 'mono' }, String(ts.unix)), h(Copy, { text: String(ts.unix) })),
        h('span', { className: 'pair' }, h('span', { className: 'muted' }, 'ISO'), h('span', { className: 'mono' }, ts.iso), h(Copy, { text: ts.iso }))) : null))
}
