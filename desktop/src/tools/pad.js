// Today's pad: lines with kinds (todo, note, reminder, prompt for tomorrow), "=" results from the
// calculator, line actions (done, delete with undo, make a card, ask Hermes, queue as a prompt), and
// "Queued for today" with "Start this chat". Without the backend: the last loaded day, read-only.
import { host, useQuery, useQueryClient, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, alertBoth, post, qk, rest } from '../core.js'
import { $focusPadAdd, Btn, Choice, ConnectionBanner, h, Input, ToolHead, useProfile } from '../ui.js'

const KINDS = [['todo', 'To-do'], ['note', 'Note'], ['reminder', 'Reminder'], ['prompt', 'Prompt for tomorrow']]

async function startChat(text) {
  try {
    if (typeof host.newChat === 'function') host.newChat(host.state.profile.get() || undefined)
    setTimeout(() => host.composer && host.composer.setDraft(null, text), 300)
  } catch (error) {
    alertBoth('Eselsbrücke', `Could not open a chat: ${error.message}`, 'warning')
  }
}

/** Enter adds the line, except while an input method (Japanese, Chinese, Korean) is still composing:
 *  there Enter confirms the composed characters (keyCode 229 in browsers that do not set isComposing). */
export const enterAdds = e => e.key === 'Enter' && !(e.nativeEvent && e.nativeEvent.isComposing) && e.keyCode !== 229

export function Line({ line, date, act, readOnly }) {
  const [menu, setMenu] = useState(false)
  const badges = []
  if (line.author === 'agent') badges.push(h('span', { key: 'a', className: 'badge agent', title: 'Added by Hermes; undo it in the chat or delete it here' }, 'agent'))
  if (line.rolled_days) badges.push(h('span', { key: 'r', className: 'badge roll' }, `from ${line.rolled_days} day${line.rolled_days > 1 ? 's' : ''} ago`))
  if (line.kind === 'reminder' && line.remind_at) badges.push(h('span', { key: 't', className: 'badge' }, `⏰ ${line.remind_at.slice(11, 16)}`))
  if (line.kind === 'prompt') badges.push(h('span', { key: 'p', className: 'badge' }, `prompt for ${line.queued_for || 'tomorrow'}`))
  if (line.card_id) badges.push(h('span', { key: 'c', className: 'badge' }, `card ${line.card_id}`))
  const checkable = line.kind === 'todo' || line.kind === 'reminder'
  return h('div', { className: `pline${line.done ? ' done' : ''}` },
    checkable
      ? h('input', { type: 'checkbox', checked: !!line.done, disabled: readOnly, 'aria-label': `Done: ${line.text}`, onChange: e => act({ op: 'update', id: line.id, changes: { done: e.target.checked } }) })
      : h('span', { className: 'muted', 'aria-hidden': true }, line.kind === 'note' ? '·' : '›'),
    h('div', { className: 'tx' }, line.text,
      line.result != null ? h('span', { className: 'res' }, ` ${line.result}`) : null,
      line.result_error ? h('span', { className: 'muted small' }, ` (${line.result_error})`) : null,
      badges.length ? h('div', { className: 'meta' }, badges) : null),
    readOnly ? null : h('div', { style: { position: 'relative' } },
      h(Btn, { 'aria-label': 'Line actions', 'aria-haspopup': 'menu', 'aria-expanded': menu, onClick: () => setMenu(!menu) }, '⋯'),
      menu ? h('div', { className: 'panel col', style: { position: 'absolute', right: 0, top: 26, zIndex: 5, minWidth: 210, padding: 4 } },
        h(Btn, { onClick: () => { setMenu(false); startChat(`@pad:${date} ${line.text}`) } }, 'Ask Hermes about this'),
        line.kind !== 'prompt' ? h(Btn, { onClick: () => { setMenu(false); act({ op: 'update', id: line.id, changes: { kind: 'prompt' } }) } }, 'Prompt for tomorrow') : null,
        line.card_id ? null : h(Btn, { onClick: () => { setMenu(false); act({ op: 'card', id: line.id }) } }, 'Make a kanban card'),
        h(Btn, { onClick: () => { setMenu(false); act({ op: 'delete', id: line.id }, line) } }, 'Delete')) : null))
}

export function PadTool() {
  const profile = useProfile()
  const client = useQueryClient()
  const conn = useValue($connection)
  const [date, setDate] = useState(null)
  const key = qk(profile, 'pad', date || 'today')
  const q = useQuery({ queryKey: key, queryFn: () => rest(date ? `/pad?date=${date}` : '/pad'), refetchInterval: 60000, retry: false })
  const [text, setText] = useState('')
  const [kind, setKind] = useState('todo')
  const [when, setWhen] = useState('')
  const input = useRef(null)
  const focus = useValue($focusPadAdd)
  useEffect(() => {
    if (focus && input.current) input.current.focus()
  }, [focus])

  const day = q.data && q.data.day
  const readOnly = conn === 'offline' || conn === 'off'
  const act = async (body, deleted) => {
    try {
      const out = await post('/pad/lines', { ...body, date: day && day.date })
      client.setQueryData(key, out)
      if (body.op === 'card' && out.card) host.notify({ kind: 'success', title: 'Eselsbrücke', message: `Kanban card ${out.card.task_id} created in triage for ${out.card.assignee}.` })
      if (body.op === 'card' && !out.card && out.fallback_draft) {
        host.notify({ kind: 'warning', title: 'Eselsbrücke', message: out.message || 'No card was created; the line is in a chat draft instead.' })
        startChat(out.fallback_draft)
      }
      if (deleted) {
        const position = day.lines.findIndex(l => l.id === deleted.id)
        host.notify({ kind: 'info', title: 'Eselsbrücke', message: 'Line deleted.', action: { label: 'Undo', onClick: () => act({ op: 'restore', line: deleted, position }) } })
      }
    } catch (error) {
      alertBoth('Eselsbrücke', error.message, 'warning')
    }
  }
  const add = async () => {
    if (!text.trim()) return
    await act({ op: 'add', text, kind, remind_at: kind === 'reminder' ? when : undefined })
    setText('')
  }

  return h('div', { className: 'col' },
    h(ToolHead, { title: "Today's pad", blurb: 'Notes, to-dos, reminders and prompts for tomorrow. Hermes sees it only when you attach @pad:today in a chat.' },
      h('span', { className: 'row', style: { flexWrap: 'nowrap' } },
        h(Btn, { 'aria-label': 'Previous day', onClick: () => setDate(day && shiftDate(day.date, -1)) }, '‹'),
        h('span', { className: 'small mono' }, day ? day.date : '…'),
        h(Btn, { 'aria-label': 'Next day', onClick: () => setDate(day && shiftDate(day.date, 1)) }, '›'),
        date ? h(Btn, { onClick: () => setDate(null) }, 'Today') : null)),
    h(ConnectionBanner, { what: 'Not connected to Hermes. The pad shows the day loaded last, read-only.' }),
    q.error && !q.data ? h('div', { className: 'banner' }, q.error.message) : null,
    q.data && q.data.time_zone && q.data.time_zone.note ? h('div', { className: 'note' }, q.data.time_zone.note) : null,
    q.data && q.data.queued && q.data.queued.length
      ? h('div', { className: 'queued' }, h('h3', null, 'Queued for today'),
        q.data.queued.map(l => h('div', { key: l.id, className: 'row' }, h('span', { className: 'grow' }, l.text), h(Btn, { pri: true, onClick: () => startChat(l.text) }, 'Start this chat'))))
      : null,
    h('div', { className: 'panel' },
      day && day.lines.length ? day.lines.map(l => jsx(Line, { line: l, date: day.date, act, readOnly }, l.id))
        : h('p', { className: 'muted' }, q.isLoading ? 'Loading…' : 'Nothing on the pad yet. Lines ending in "=" get a result, like 16,90 * 12 ='),
      readOnly ? null : h('div', { className: 'row', style: { marginTop: 10 } },
        h(Input, { ref: input, className: 'inp grow', value: text, onChange: setText, placeholder: 'Add a line (Enter)', onKeyDown: e => enterAdds(e) && add() }),
        h(Choice, { value: kind, onChange: setKind, options: KINDS, 'aria-label': 'Kind' }),
        kind === 'reminder' ? h(Input, { type: 'time', value: when, onChange: setWhen, 'aria-label': 'Remind at' }) : null,
        h(Btn, { pri: true, onClick: add }, 'Add'))),
    q.data && !q.data.calc_on ? h('p', { className: 'note' }, 'The calculator is switched off, so "=" lines show no result.') : null)
}

function shiftDate(iso, days) {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}
