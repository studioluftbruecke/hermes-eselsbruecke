// Time log: start and stop a billable timer per client and project, add time afterwards, edit a
// finished entry, the week with totals and amounts in each client's currency, undo, CSV. Start, stop
// and add go to the outbox without the backend.
import { useQuery, useQueryClient, useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { alertBoth, post, qk, rest } from '../core.js'
import { DRAFT, useDraft } from '../drafts.js'
import { $outbox } from '../outbox.js'
import { $running, $tick, timelogAction } from '../live.js'
import { hoursLabel as hours } from '../timer.js'
import { Btn, ConnectionBanner, Copy, Field, h, Input, ToolHead, useProfile } from '../ui.js'
import { enterAdds } from './pad.js'

const time = iso => (iso ? iso.slice(11, 16) : '')
const tidy = text => String(text ?? '').replace(/\s+/g, ' ').trim()

export const CURRENCIES = ['EUR', 'USD', 'GBP', 'CHF']

/** A typed currency as its three-letter code: 'EUR' for an empty field, null for anything else that
 *  is not three letters. */
export function currencyCode(text) {
  const code = tidy(text).toUpperCase()
  return !code ? 'EUR' : /^[A-Z]{3}$/.test(code) ? code : null
}

/** A total's amount as the page shows it: "202.80 €" for euros (and for a total without a currency,
 *  as older backends send it), "202.80 USD" for any other currency, "" without a rate. */
export function amountLabel(total) {
  if (!total || total.amount == null || total.amount === '') return ''
  const currency = total.currency || 'EUR'
  return currency === 'EUR' ? `${total.amount} €` : `${total.amount} ${currency}`
}

/** The rate row as the `client` op, or null while it cannot be saved (no client, or a currency that
 *  is not three letters). An empty rate clears the client's rate. */
export function rateOp(row) {
  const name = tidy(row.name)
  const currency = currencyCode(row.currency)
  if (!name || !currency) return null
  return { op: 'client', name, rate: row.rate === '' || row.rate == null ? null : Number(row.rate), currency }
}

/** What the edit row starts with: the entry's texts and its times as the row shows them. */
export const editFields = entry => ({ client: entry.client || '', project: entry.project || '', note: entry.note || '', from: time(entry.start), to: time(entry.end) })

// An entry's time keeps its day and its UTC offset when the clock time is edited: the row shows the
// wall time of the stored offset (Hermes' zone, or the Mac's for a click that came through the outbox),
// and the edited time is meant on that same clock.
function withTime(iso, hhmm) {
  const at = String(iso || '').match(/^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$/)
  const t = String(hhmm || '').trim().match(/^(\d{1,2}):(\d{2})$/)
  if (!at || !t || +t[1] > 23 || +t[2] > 59) return null
  return `${at[1]}T${t[1].padStart(2, '0')}:${t[2]}:00${at[2] || ''}`
}

/** The edit row as an `edit` op holding only what changed.
 *  { ok: true, body } (body null when nothing changed) or { ok: false, error }. */
export function editOp(entry, f) {
  const fields = {}
  for (const k of ['client', 'project', 'note']) if (tidy(f[k]) !== (entry[k] || '')) fields[k] = tidy(f[k])
  if ('client' in fields && !fields.client) return { ok: false, error: 'An entry needs a client.' }
  for (const [from, field] of [['from', 'start'], ['to', 'end']]) {
    if (tidy(f[from]) === time(entry[field])) continue
    const iso = withTime(entry[field], f[from])
    if (!iso) return { ok: false, error: 'Write a time like 09:30.' }
    fields[field] = iso
  }
  const start = fields.start || entry.start
  const end = fields.end || entry.end
  if (end && Date.parse(end) < Date.parse(start)) return { ok: false, error: 'The end lies before the start.' }
  return { ok: true, body: Object.keys(fields).length ? { op: 'edit', entry_id: entry.id, fields } : null }
}

/** A button handler whose failure becomes a toast instead of an unhandled rejection. */
const shown = fn => async () => {
  try {
    await fn()
  } catch (error) {
    alertBoth('Eselsbrücke', error.message, 'warning')
  }
}

function download(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export function TimelogTool() {
  const profile = useProfile()
  const client = useQueryClient()
  const [date, setDate] = useState(null)
  const key = qk(profile, 'timelog', date || 'this-week')
  const q = useQuery({ queryKey: key, queryFn: () => rest(date ? `/timelog?date=${date}` : '/timelog'), refetchInterval: 60000, retry: false })
  const running = useValue($running)
  const outbox = useValue($outbox)
  useValue($tick)
  const [f, setF] = useDraft(DRAFT.timelogForm, { client: '', project: '', note: '', minutes: '' })
  const [rate, setRate] = useState({ name: '', rate: '', currency: '' })
  const [edit, setEdit] = useState(null) // the entry being edited: { id, client, project, note, from, to }
  const set = k => v => setF({ ...f, [k]: v })
  const week = q.data && q.data.week
  const clients = (q.data && q.data.clients) || []

  const refresh = () => client.invalidateQueries({ queryKey: qk(profile, 'timelog') })
  const run = async body => {
    await timelogAction(body) // a refusal is already a toast there
    refresh()
  }
  /** One click the backend answers at once. False when it refused (the reason is a toast). */
  const click = async body => {
    try {
      // the answer is the week of `date`: without it a click in an earlier week would show this week
      const out = await post('/timelog', date ? { ...body, date } : body)
      client.setQueryData(key, out)
      return true
    } catch (error) {
      alertBoth('Eselsbrücke', error.message, 'warning')
      return false
    }
  }
  const saveEdit = async entry => {
    const out = editOp(entry, edit)
    if (!out.ok) return alertBoth('Eselsbrücke', out.error, 'warning')
    // a refused edit keeps the fields open
    if (!out.body || (await click(out.body))) setEdit(null)
    return undefined
  }
  const editCell = (entry, k, label, props) => h(Input, { value: edit[k], onChange: v => setEdit({ ...edit, [k]: v }), 'aria-label': label,
    onKeyDown: e => (enterAdds(e) ? saveEdit(entry) : e.key === 'Escape' ? setEdit(null) : null), ...props })
  // a text field, not a time picker: the picker follows the computer's 12 or 24 hour setting, the rows are always 24 hour
  const clockCell = (entry, k, label) => editCell(entry, k, label, { className: 'inp mono hm', placeholder: '09:30', maxLength: 5, inputMode: 'numeric' })
  const rateBody = rateOp(rate)
  const fields = () => ({ client: f.client.trim(), project: f.project.trim(), note: f.note.trim() })
  const runningHours = running ? Math.max(0, Date.now() - new Date(running.start).getTime()) / 3600000 : 0

  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Time log', blurb: 'Billable time per client and project. Every change is kept; undo reverts the newest.' },
      h('span', { className: 'row', style: { flexWrap: 'nowrap' } },
        h(Btn, { 'aria-label': 'Previous week', onClick: () => setDate(shiftWeek(week && week.from, -7)) }, '‹'),
        h('span', { className: 'small mono', style: { whiteSpace: 'nowrap' } }, week ? `${week.from} to ${week.to}` : '…'),
        h(Btn, { 'aria-label': 'Next week', onClick: () => setDate(shiftWeek(week && week.from, 7)) }, '›'),
        date ? h(Btn, { onClick: () => setDate(null) }, 'This week') : null)),
    h(ConnectionBanner, { what: 'Not connected to Hermes. Start, stop and add are kept and sync later; totals are from the last load.' }),
    outbox.filter(i => i.kind === 'timelog').length ? h('div', { className: 'banner' }, `${outbox.filter(i => i.kind === 'timelog').length} change(s) not synced yet.`) : null,
    running
      ? h('div', { className: 'panel row' },
        h('span', { className: 'chip live' }, '● running'),
        h('strong', null, running.client), running.project ? h('span', { className: 'muted' }, running.project) : null,
        h('span', { className: 'mono' }, hours(runningHours)),
        running.long_running ? h('span', { className: 'badge' }, 'over 10 h: still working?') : null,
        h('span', { className: 'grow' }),
        h(Btn, { pri: true, onClick: () => run({ op: 'stop', entry_id: running.id }) }, 'Stop'))
      : null,
    h('div', { className: 'panel col' },
      h('div', { className: 'row' },
        h(Field, { label: 'Client', className: 'grow' }, h(Input, { value: f.client, onChange: set('client'), list: 'esb-clients', placeholder: 'Acme' })),
        h(Field, { label: 'Project', className: 'grow' }, h(Input, { value: f.project, onChange: set('project') })),
        h(Field, { label: 'Note', className: 'grow' }, h(Input, { value: f.note, onChange: set('note') }))),
      h('datalist', { id: 'esb-clients' }, clients.map(c => jsx('option', { value: c.name }, c.name))),
      h('div', { className: 'row' },
        h(Btn, { pri: true, disabled: !f.client.trim(), onClick: () => run({ op: 'start', fields: fields(), source: 'page' }) }, 'Start timer'),
        h('span', { className: 'muted small' }, 'or add'),
        h(Input, { type: 'number', min: 1, value: f.minutes, onChange: set('minutes'), placeholder: 'min', style: { width: 80 } }),
        h(Btn, { disabled: !f.client.trim() || !Number(f.minutes), onClick: () => run({ op: 'add', fields: { ...fields(), minutes: Number(f.minutes) }, source: 'page' }) }, 'Add minutes'),
        h('span', { className: 'grow' }),
        h(Btn, { onClick: () => click({ op: 'undo' }) }, 'Undo last change'))),
    week ? h('div', { className: 'panel' },
      h('table', { className: 'tl' },
        h('thead', null, h('tr', null, ['Day', 'From', 'To', 'Client', 'Project', 'Note', 'Hours', ''].map(x => jsx('th', { children: x }, x)))),
        h('tbody', null, week.entries.length ? week.entries.map(e => (edit && edit.id === e.id && !e.running
          ? jsx('tr', { children: [
            jsx('td', { className: 'day', children: e.start.slice(5, 10) }, 'd'),
            jsx('td', { children: clockCell(e, 'from', 'From') }, 's'),
            jsx('td', { children: clockCell(e, 'to', 'To') }, 'e'),
            jsx('td', { children: editCell(e, 'client', 'Client', { maxLength: 200, list: 'esb-clients', autoFocus: true }) }, 'c'),
            jsx('td', { children: editCell(e, 'project', 'Project', { maxLength: 200 }) }, 'p'),
            jsx('td', { children: editCell(e, 'note', 'Note', { maxLength: 200 }) }, 'n'),
            jsx('td', { className: 'n', children: hours(e.hours) }, 'h'),
            jsx('td', { children: h('span', { className: 'acts' },
              h('button', { type: 'button', className: 'link', onClick: () => saveEdit(e) }, 'save'),
              h('button', { type: 'button', className: 'link', onClick: () => setEdit(null) }, 'cancel')) }, 'x'),
          ] }, e.id)
          : jsx('tr', { children: [
            jsx('td', { className: 'day', children: e.start.slice(5, 10) }, 'd'), jsx('td', { children: time(e.start) }, 's'), jsx('td', { children: e.end ? time(e.end) : '…' }, 'e'),
            jsx('td', { children: e.client }, 'c'), jsx('td', { children: e.project }, 'p'),
            jsx('td', { children: [e.note, e.by === 'agent' ? ' ' : null, e.by === 'agent' ? jsx('span', { className: 'badge agent', children: 'agent' }, 'b') : null] }, 'n'),
            jsx('td', { className: 'n', children: hours(e.hours) }, 'h'),
            jsx('td', { children: e.running ? null : h('span', { className: 'acts' },
              h('button', { type: 'button', className: 'link', onClick: () => setEdit({ id: e.id, ...editFields(e) }) }, 'edit'),
              h('button', { type: 'button', className: 'link', onClick: () => click({ op: 'delete', entry_id: e.id }) }, 'delete')) }, 'x'),
          ] }, e.id))) : jsx('tr', { children: jsx('td', { colSpan: 8, className: 'muted', children: 'No time this week.' }) }))),
      week.skipped_lines ? h('p', { className: 'note' }, `${week.skipped_lines} damaged line(s) in the log were skipped.`) : null) : null,
    week && week.totals.length ? h('div', { className: 'panel col' },
      h('h3', null, `Totals: ${hours(week.hours)} h`),
      h('table', { className: 'tl' }, h('tbody', null, week.totals.map(t => jsx('tr', { children: [
        jsx('td', { children: t.client }, 'c'), jsx('td', { children: t.project }, 'p'),
        jsx('td', { className: 'n', children: hours(t.hours) }, 'h'),
        jsx('td', { className: 'n', children: amountLabel(t) }, 'a'),
      ] }, `${t.client}/${t.project}`)))),
      h('div', { className: 'row' },
        h(Btn, { onClick: shown(async () => { const r = await rest(`/timelog/export${week ? `?date=${week.from}` : ''}`); download(r.filename, r.csv) }) }, 'Download CSV'),
        h(CopyCsv, { from: week.from }))) : null,
    h('div', { className: 'panel row' },
      h('span', { className: 'muted small' }, 'Hourly rate'),
      h(Input, { value: rate.name, onChange: v => setRate({ ...rate, name: v }), list: 'esb-clients', placeholder: 'Client' }),
      h(Input, { type: 'number', value: rate.rate, onChange: v => setRate({ ...rate, rate: v }), placeholder: 'per hour', 'aria-label': 'Rate per hour', style: { width: 110 } }),
      h(Input, { value: rate.currency, onChange: v => setRate({ ...rate, currency: v }), list: 'esb-currencies', placeholder: 'EUR', maxLength: 3, 'aria-label': 'Currency', style: { width: 70 } }),
      h('datalist', { id: 'esb-currencies' }, CURRENCIES.map(c => jsx('option', { value: c }, c))),
      h(Btn, { disabled: !rateBody, onClick: () => click(rateBody) }, 'Save rate'),
      currencyCode(rate.currency) ? null : h('span', { className: 'note' }, 'A currency is three letters, like EUR.')))
}

function CopyCsv({ from }) {
  const [csv, setCsv] = useState('')
  if (!csv) return h(Btn, { onClick: shown(async () => setCsv((await rest(`/timelog/export?date=${from}`)).csv)) }, 'Copy CSV…')
  return h(Copy, { text: csv, label: 'Copy CSV' })
}

function shiftWeek(from, days) {
  if (!from) return null
  const d = new Date(`${from}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}
