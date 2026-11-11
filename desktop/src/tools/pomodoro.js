// Pomodoro: the dial and phase bar computed from the timer record (works without the backend), work
// and break following each other without a click, a countdown, "What did you finish?" on stop, the
// 25/5 and 50/10 rhythms one click apart (D7), and a tip or an UnblockBrücke card in breaks.
import { useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $rhythm, $tick, $timer, $tip, timerAction } from '../live.js'
import { phaseAt } from '../timer.js'
import { Btn, ConnectionBanner, Field, h, Input, ToolHead, useToolbox, useToolboxSave } from '../ui.js'

const RHYTHMS = { '25/5': { work: 25, short: 5, long: 15 }, '50/10': { work: 50, short: 10, long: 10 } }

export const fmtMin = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

export function PomodoroTool() {
  const t = useValue($timer)
  const now = useValue($tick)
  const tip = useValue($tip)
  const rhythm = useValue($rhythm)
  const tb = useToolbox()
  const save = useToolboxSave()
  const [minutes, setMinutes] = useState('10')
  const [label, setLabel] = useState('')
  const [result, setResult] = useState('')
  const [client, setClient] = useState('')
  const s = t ? phaseAt(t, now) : null
  const running = s && !s.done
  const pct = s && !s.done ? Math.round(((s.minutes * 60 - s.remaining_s) / (s.minutes * 60)) * 100) : 0

  const setRhythm = async name => {
    const doc = tb.data && tb.data.toolbox
    if (!doc) return
    await save({ op: 'save', base_hash: tb.data.hash, toolbox: { ...doc, pomodoro: { ...doc.pomodoro, rhythm: name, ...RHYTHMS[name] } } })
    $rhythm.set({ ...rhythm, rhythm: name, ...RHYTHMS[name] })
  }

  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Pomodoro', blurb: 'Work and break follow each other without a click. The status bar shows the minutes left.' }),
    h(ConnectionBanner, { what: 'Not connected to Hermes. The timer keeps counting here; start, pause and stop are kept and sync later.' }),
    h('div', { className: 'pomo' },
      h('div', { className: 'dial', style: { '--p': `${pct}%` } },
        h('div', null, h('div', null,
          h('div', { className: 'big' }, running ? fmtMin(s.remaining_s) : `${rhythm.work}:00`),
          h('div', { className: 'muted small' }, running ? `${s.title}${s.paused ? ' (paused)' : ''}` : 'Ready')))),
      h('div', { className: 'col' },
        t && t.kind === 'pomodoro' ? h('div', { className: 'phases', 'aria-label': 'Phases' },
          t.plan.map((p, i) => jsx('i', { className: `${p.phase === 'work' ? 'w' : ''}${s && i === s.index ? ' now' : ''}${s && i < s.index ? ' past' : ''}`, style: { width: `${p.minutes * 2}px` }, title: `${p.phase} ${p.minutes} min` }, i))) : null,
        running
          ? h('div', { className: 'row' },
            s.paused ? h(Btn, { pri: true, onClick: () => timerAction({ op: 'resume' }) }, 'Resume') : h(Btn, { onClick: () => timerAction({ op: 'pause' }) }, 'Pause'),
            h(Input, { value: result, onChange: setResult, placeholder: 'What did you finish? (optional)', className: 'inp grow' }),
            h(Btn, { onClick: async () => { const r = await timerAction({ op: 'stop', result: result || undefined }); if (r.ok || r.queued) setResult('') } }, 'Stop'))
          : h('div', { className: 'col' },
            h('div', { className: 'row' },
              h(Btn, { pri: true, onClick: () => timerAction({ op: 'start', kind: 'pomodoro', client: client || undefined }) }, `Start ${rhythm.work}/${rhythm.short}`),
              Object.keys(RHYTHMS).map(name => jsx(Btn, { onClick: () => setRhythm(name), disabled: rhythm.work === RHYTHMS[name].work, children: name }, name)),
              h(Input, { value: client, onChange: setClient, placeholder: 'Client for the time log (optional)', className: 'inp grow' })),
            h('div', { className: 'row' },
              h(Field, { label: 'Countdown (minutes)' }, h(Input, { type: 'number', min: 1, max: 1440, value: minutes, onChange: setMinutes, style: { width: 90 } })),
              h(Field, { label: 'Label' }, h(Input, { value: label, onChange: setLabel, placeholder: 'tea' })),
              h(Btn, { style: { alignSelf: 'end' }, onClick: () => timerAction({ op: 'start', kind: 'countdown', minutes: Number(minutes), label: label || undefined }) }, 'Start countdown'))),
        running && (s.phase === 'short' || s.phase === 'long') && tip
          ? h('div', { className: 'tip' }, h('strong', null, tip.title), tip.text ? h('div', { className: 'muted' }, tip.text) : null,
            tip.source === 'unblockbruecke' ? h('div', { className: 'note' }, 'A card from UnblockBrücke') : null)
          : null,
        running && s.next ? h('p', { className: 'note' }, `Next: ${s.next.phase === 'work' ? 'Work' : 'Break'} ${s.next.minutes} min`) : null)))
}
