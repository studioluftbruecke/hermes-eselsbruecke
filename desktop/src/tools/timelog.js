// Time log: start and stop a billable timer per client and project, add time afterwards, the week
// with totals and amounts, undo, CSV. Start, stop and add go to the outbox without the backend (A16).
import { useQuery, useQueryClient, useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { alertBoth, post, qk, rest } from '../core.js'
import { $outbox } from '../outbox.js'
import { $running, $tick, timelogAction } from '../live.js'
import { hoursLabel as hours } from '../timer.js'
import { Btn, ConnectionBanner, Copy, Field, h, Input, ToolHead, useProfile } from '../ui.js'

const time = iso => (iso ? iso.slice(11, 16) : '')

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
  const [f, setF] = useState({ client: '', project: '', note: '', minutes: '' })
  const [rate, setRate] = useState({ name: '', rate: '' })
  const set = k => v => setF({ ...f, [k]: v })
  const week = q.data && q.data.week
  const clients = (q.data && q.data.clients) || []

  const refresh = () => client.invalidateQueries({ queryKey: qk(profile, 'timelog') })
  const run = async body => {
    await timelogAction(body) // a refusal is already a toast there
    refresh()
  }
  const click = async body => {
    try {
      const out = await post('/timelog', body)
      client.setQueryData(key, out)
    } catch (error) {
      alertBoth('Eselsbrücke', error.message, 'warning')
    }
  }
  const fields = () => ({ client: f.client.trim(), project: f.project.trim(), note: f.note.trim() })
  const runningHours = running ? Math.max(0, Date.now() - new Date(running.start).getTime()) / 3600000 : 0

  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Time log', blurb: 'Billable time per client and project. Every change is kept; undo reverts the newest.' },
      h('span', { className: 'row', style: { flexWrap: 'nowrap' } },
        h(Btn, { 'aria-label': 'Previous week', onClick: () => setDate(shiftWeek(week && week.from, -7)) }, '‹'),
        h('span', { className: 'small mono', style: { whiteSpace: 'nowrap' } }, week ? `${week.from} – ${week.to}` : '…'),
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
        h('tbody', null, week.entries.length ? week.entries.map(e => jsx('tr', { children: [
          jsx('td', { children: e.start.slice(5, 10) }, 'd'), jsx('td', { children: time(e.start) }, 's'), jsx('td', { children: e.end ? time(e.end) : '…' }, 'e'),
          jsx('td', { children: e.client }, 'c'), jsx('td', { children: e.project }, 'p'),
          jsx('td', { children: [e.note, e.by === 'agent' ? h('span', { className: 'badge agent', key: 'b' }, ' agent') : null] }, 'n'),
          jsx('td', { className: 'n', children: hours(e.hours) }, 'h'),
          jsx('td', { children: e.running ? null : h('button', { className: 'link', onClick: () => click({ op: 'delete', entry_id: e.id }) }, 'delete') }, 'x'),
        ] }, e.id)) : jsx('tr', { children: jsx('td', { colSpan: 8, className: 'muted', children: 'No time this week.' }) }))),
      week.skipped_lines ? h('p', { className: 'note' }, `${week.skipped_lines} damaged line(s) in the log were skipped.`) : null) : null,
    week && week.totals.length ? h('div', { className: 'panel col' },
      h('h3', null, `Totals: ${hours(week.hours)} h`),
      h('table', { className: 'tl' }, h('tbody', null, week.totals.map(t => jsx('tr', { children: [
        jsx('td', { children: t.client }, 'c'), jsx('td', { children: t.project }, 'p'),
        jsx('td', { className: 'n', children: hours(t.hours) }, 'h'),
        jsx('td', { className: 'n', children: t.amount ? `${t.amount} €` : '' }, 'a'),
      ] }, `${t.client}/${t.project}`)))),
      h('div', { className: 'row' },
        h(Btn, { onClick: shown(async () => { const r = await rest(`/timelog/export${week ? `?date=${week.from}` : ''}`); download(r.filename, r.csv) }) }, 'Download CSV'),
        h(CopyCsv, { from: week.from }))) : null,
    h('div', { className: 'panel row' },
      h('span', { className: 'muted small' }, 'Hourly rate'),
      h(Input, { value: rate.name, onChange: v => setRate({ ...rate, name: v }), list: 'esb-clients', placeholder: 'Client' }),
      h(Input, { type: 'number', value: rate.rate, onChange: v => setRate({ ...rate, rate: v }), placeholder: '€ per hour', style: { width: 110 } }),
      h(Btn, { disabled: !rate.name.trim(), onClick: () => click({ op: 'client', name: rate.name, rate: rate.rate === '' ? null : Number(rate.rate) }) }, 'Save rate')))
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
