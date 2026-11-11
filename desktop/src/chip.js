// The status-bar chip: an icon while nothing runs, a ring and the minutes left for the pomodoro (not
// seconds; constraint 1), a dot and the hours for the running time-log timer, and a small amber dot
// while clicks wait in the outbox. The sentence is in the tooltip and in the popover, which has the
// quick actions. The toolbox's layout says whether it shows at all (chip_visible) and what it shows
// while something runs (chip: auto, pomodoro, timelog).
import { Codicon, Popover, PopoverContent, PopoverTrigger, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, storage } from './core.js'
import { $running, $tick, $timer, replayAndRefresh, timelogAction, timerAction } from './live.js'
import { $outbox, discardOutboxHead, outboxStatus, retryOutbox } from './outbox.js'
import { Style } from './style.js'
import { hoursLabel, phaseAt } from './timer.js'
import { Btn, DASHBOARD, h, isOn, openTool, useProfile, useToolbox } from './ui.js'

/** The chip's two settings out of the toolbox's layout. A file written before
 *  `chip_visible` existed says `chip: "off"` for hidden, and an older Hermes still serves that. */
export function chipLayout(layout) {
  const l = layout || {}
  return { chip: l.chip === 'pomodoro' || l.chip === 'timelog' ? l.chip : 'auto', chip_visible: l.chip_visible !== false && l.chip !== 'off' }
}

/** Minutes in at most three characters, so the chip stays narrow: "20m", and "2h" from 100 minutes on. */
export const chipMinutes = minutes => (minutes < 100 ? `${minutes}m` : `${Math.round(minutes / 60)}h`)

const runningHours = (running, now) => Math.max(0, now - new Date(running.start).getTime()) / 3600000

/** What the chip shows: { hidden } or { kind: 'idle' | 'pomodoro' | 'timelog', label, pct, waiting,
 *  sentence, title }. `layout` is the toolbox's layout, `waiting` the number of clicks in the outbox.
 *  A hidden chip stays hidden while clicks wait: the page head says "n not synced". */
export function chipState({ timer, running, now = Date.now(), layout, waiting = 0, connection }) {
  const { chip: mode, chip_visible: visible } = chipLayout(layout)
  if (connection === 'off' || !visible) return { hidden: true }
  const s = timer ? phaseAt(timer, now) : null
  const pomo = !!s && !s.done && mode !== 'timelog'
  const log = !!running && mode !== 'pomodoro' && !pomo
  const wait = waiting ? `, ${waiting} ${waiting === 1 ? 'click waits' : 'clicks wait'} to sync` : ''
  if (pomo) {
    const sentence = `${s.title}${s.paused ? ' paused' : ''}, ${s.remaining_min} min left`
    const pct = Math.round(((s.minutes * 60 - s.remaining_s) / (s.minutes * 60)) * 100)
    return { hidden: false, kind: 'pomodoro', label: chipMinutes(s.remaining_min), pct, waiting, sentence, title: `Eselsbrücke: ${sentence}${wait}` }
  }
  if (log) {
    const time = hoursLabel(runningHours(running, now))
    const sentence = `${running.client}${running.project ? `, ${running.project}` : ''}, running ${time}`
    return { hidden: false, kind: 'timelog', label: time, pct: 0, waiting, sentence, title: `Eselsbrücke: ${sentence}${wait}` }
  }
  return { hidden: false, kind: 'idle', label: '', pct: 0, waiting, sentence: '', title: `Eselsbrücke${wait}` }
}

/** The inside of the chip for a state, also drawn as the four previews on the settings page. */
export const chipFace = state => [
  state.kind === 'pomodoro' ? jsx('span', { className: 'esbring', style: { '--p': `${state.pct || 0}%` } }, 'ring')
    : state.kind === 'timelog' ? jsx('span', { className: 'esbdot' }, 'dot')
      : jsx(Codicon, { name: 'tools', size: 13 }, 'icon'),
  state.label ? jsx('span', { children: state.label }, 'label') : null,
  state.waiting ? jsx('span', { className: 'esbwait' }, 'wait') : null,
]

export const CHIP_SAMPLES = [
  ['Nothing runs', { kind: 'idle' }],
  ['Pomodoro', { kind: 'pomodoro', label: '20m', pct: 20 }],
  ['Time log', { kind: 'timelog', label: '1:05' }],
  ['A click waits to sync', { kind: 'idle', waiting: 1 }],
]

/** The outbox in the popover: the count, and the oldest click that no longer syncs by itself
 *  (failed too often, or older than a day) with its error, "Try again" (sends it once more; the
 *  server decides) and "Discard". */
export function OutboxNote({ count }) {
  useValue($outbox)
  const { stuck } = outboxStatus()
  const clicks = `${count} ${count === 1 ? 'click waits' : 'clicks wait'}`
  if (!stuck) return h('p', { className: 'note' }, `${clicks} for Hermes and will sync when it answers.`)
  const what = `${stuck.kind === 'timelog' ? 'time log' : 'timer'} ${stuck.op.op}`
  const when = stuck.op.at ? new Date(stuck.op.at).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : ''
  const why = stuck.reason === 'age' ? 'it is more than a day old' : `${stuck.tries} tries failed${stuck.error ? ` (${stuck.error})` : ''}`
  return h('div', { className: 'col', style: { gap: 4 } },
    h('p', { className: 'note' }, `${clicks}. The oldest (${what}, ${when}) no longer syncs by itself: ${why}.`),
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
  const profile = useProfile()
  const [open, setOpen] = useState(false)
  const loaded = tb.data && tb.data.toolbox ? tb.data.toolbox.layout : null
  // The status bar paints before the toolbox answers. The layout seen last decides until then, so a
  // chip the user has hidden does not show up at every start or while Hermes is unreachable.
  const key = `chipLayout:${profile}`
  useEffect(() => {
    if (loaded) storage.set(key, chipLayout(loaded))
  }, [key, loaded && loaded.chip, loaded && loaded.chip_visible])
  const state = chipState({ timer: t, running, now, layout: loaded || storage.get(key, null), waiting: outbox.length, connection: conn })
  if (state.hidden) return null
  const s = t ? phaseAt(t, now) : null
  const pomo = s && !s.done
  const act = fn => async () => {
    setOpen(false)
    await fn()
  }
  return jsx(Popover, { open, onOpenChange: setOpen, children: [
    jsx(Style, {}, 's'),
    jsx(PopoverTrigger, { asChild: true, children: h('button', { type: 'button', className: `esbchip${state.kind === 'idle' ? '' : ' live'}`, title: state.title, 'aria-label': state.title, 'data-state': state.kind },
      chipFace(state)) }, 't'),
    jsx(PopoverContent, { align: 'end', side: 'top', className: 'w-64', children: h('div', { className: 'esb col', style: { gap: 6 } },
      pomo ? h('div', { className: 'row' },
        h('span', { className: 'grow' }, `${s.title}${s.paused ? ' paused' : ''}, ${s.remaining_min} min left`),
        s.paused ? h(Btn, { pri: true, onClick: act(() => timerAction({ op: 'resume' })) }, 'Resume') : h(Btn, { onClick: act(() => timerAction({ op: 'pause' })) }, 'Pause'),
        h(Btn, { onClick: act(() => timerAction({ op: 'stop' })) }, 'Stop'))
        : isOn(tb.data, 'pomodoro') ? h(Btn, { pri: true, onClick: act(() => timerAction({ op: 'start', kind: 'pomodoro' })) }, 'Start a pomodoro') : null,
      running ? h('div', { className: 'row' },
        h('span', { className: 'grow' }, `${running.client}${running.project ? `, ${running.project}` : ''}, running ${hoursLabel(runningHours(running, now))}`),
        h(Btn, { onClick: act(() => timelogAction({ op: 'stop', entry_id: running.id, source: 'chip' })) }, 'Stop')) : null,
      outbox.length ? h(OutboxNote, { count: outbox.length }) : null,
      h('div', { className: 'row' },
        h(Btn, { onClick: act(() => openTool(DASHBOARD, { beside: false })) }, 'Open the dashboard'),
        onBeside ? h(Btn, { onClick: act(onBeside) }, 'Beside chat') : null)) }, 'c'),
  ] })
}
