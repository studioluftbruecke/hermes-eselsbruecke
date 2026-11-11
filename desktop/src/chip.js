// The status-bar chip: the pomodoro phase in minutes (not seconds; constraint 1), or the running
// time-log timer, plus "n not synced" while the outbox holds clicks. Its popover has the quick
// actions. What it shows follows the toolbox's layout.chip (auto, pomodoro, timelog, off).
import { Popover, PopoverContent, PopoverTrigger, useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection } from './core.js'
import { $running, $tick, $timer, replayAndRefresh, timelogAction, timerAction } from './live.js'
import { $outbox, discardOutboxHead, outboxStatus, retryOutbox } from './outbox.js'
import { Style } from './style.js'
import { phaseAt } from './timer.js'
import { Btn, h, openTool, useToolbox } from './ui.js'

const hm = hours => `${Math.floor(hours)}:${String(Math.floor((hours % 1) * 60)).padStart(2, '0')}`

/** The outbox in the popover: the count, and the oldest click that no longer syncs by itself
 *  (failed too often, or older than a day) with its error, "Try again" (sends it once more; the
 *  server decides) and "Discard". */
export function OutboxNote({ count }) {
  useValue($outbox)
  const { stuck } = outboxStatus()
  if (!stuck) return h('p', { className: 'note' }, `${count} click(s) wait for Hermes; they sync by themselves when it answers.`)
  const what = `${stuck.kind === 'timelog' ? 'time log' : 'timer'} ${stuck.op.op}`
  const when = stuck.op.at ? new Date(stuck.op.at).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : ''
  const why = stuck.reason === 'age' ? 'it is more than a day old' : `${stuck.tries} tries failed${stuck.error ? ` (${stuck.error})` : ''}`
  return h('div', { className: 'col', style: { gap: 4 } },
    h('p', { className: 'note' }, `${count} click(s) wait. The oldest (${what}, ${when}) no longer syncs by itself: ${why}.`),
    h('div', { className: 'row' },
      h(Btn, { onClick: () => { retryOutbox(); replayAndRefresh() } }, 'Try again'),
      h(Btn, { onClick: () => { discardOutboxHead(); replayAndRefresh() } }, 'Discard it')))
}

export function Chip({ onBeside }) {
  const t = useValue($timer)
  const running = useValue($running)
  const now = useValue($tick)
  const outbox = useValue($outbox)
  const conn = useValue($connection)
  const tb = useToolbox()
  const [open, setOpen] = useState(false)
  const mode = (tb.data && tb.data.toolbox && tb.data.toolbox.layout.chip) || 'auto'
  if (conn === 'off' || (mode === 'off' && !outbox.length)) return null
  const s = t ? phaseAt(t, now) : null
  const pomo = s && !s.done && mode !== 'timelog'
  const log = running && mode !== 'pomodoro' && !pomo
  const hours = running ? Math.max(0, Date.now() - new Date(running.start).getTime()) / 3600000 : 0
  const pct = pomo ? Math.round(((s.minutes * 60 - s.remaining_s) / (s.minutes * 60)) * 100) : 0
  let label = 'Toolbox'
  if (pomo) label = `${s.paused ? 'Paused' : s.title} ${s.remaining_min} min`
  else if (log) label = `${running.client} ${hm(hours)}`
  const act = fn => async () => {
    setOpen(false)
    await fn()
  }
  return jsx(Popover, { open, onOpenChange: setOpen, children: [
    jsx(Style, {}, 's'),
    jsx(PopoverTrigger, { asChild: true, children: h('button', { type: 'button', className: `esbchip${pomo || log ? ' live' : ''}`, title: 'Eselsbrücke', 'aria-label': `Eselsbrücke: ${label}` },
      pomo ? h('span', { className: 'ring', style: { '--p': `${pct}%` } }) : log ? h('span', null, '●') : null,
      h('span', null, label),
      outbox.length ? h('span', { className: 'warn' }, `· ${outbox.length} not synced`) : null) }, 't'),
    jsx(PopoverContent, { align: 'end', side: 'top', className: 'w-64', children: h('div', { className: 'esb col', style: { gap: 6 } },
      pomo ? h('div', { className: 'row' },
        h('span', { className: 'grow', style: { whiteSpace: 'nowrap' } }, `${s.title}, ends ${s.ends_at ? new Date(s.ends_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '(paused)'}`),
        s.paused ? h(Btn, { pri: true, onClick: act(() => timerAction({ op: 'resume' })) }, 'Resume') : h(Btn, { onClick: act(() => timerAction({ op: 'pause' })) }, 'Pause'),
        h(Btn, { onClick: act(() => timerAction({ op: 'stop' })) }, 'Stop'))
        : h(Btn, { pri: true, onClick: act(() => timerAction({ op: 'start', kind: 'pomodoro' })) }, 'Start a pomodoro'),
      running ? h('div', { className: 'row' }, h('span', { className: 'grow' }, `${running.client}${running.project ? ` · ${running.project}` : ''} ${hm(hours)}`),
        h(Btn, { onClick: act(() => timelogAction({ op: 'stop', entry_id: running.id, source: 'chip' })) }, 'Stop')) : null,
      outbox.length ? h(OutboxNote, { count: outbox.length }) : null,
      h('div', { className: 'row' },
        h(Btn, { onClick: act(() => openTool('pad', { beside: false })) }, 'Open toolbox'),
        onBeside ? h(Btn, { onClick: act(onBeside) }, 'Beside chat') : null)) }, 'c'),
  ] })
}
