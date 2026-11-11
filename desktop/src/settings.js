// The plugin's own settings page (constraint 10): tool switches, presets, the pomodoro rhythm, what
// the status-bar chip shows, "Alerts while Desktop is closed" with its home-channel warning and the
// newest tick error, Hermes' time zone, and the toolbox versions with restore. Also the first-run
// chooser (D6), shown on the Toolbox page until a preset is picked.
import { atom, host, Switch, useQuery, useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { alertBoth, ID, post, qk, rest } from './core.js'
import { Style } from './style.js'
import { Btn, Choice, ConnectionBanner, Field, h, useProfile, useToolbox, useToolboxSave } from './ui.js'

const GROUP_TITLES = { focus: 'Focus', code: 'Code', convert: 'Convert', design: 'Design', engine: 'Engine' }

export function PresetChooser({ onDone }) {
  const tb = useToolbox()
  const save = useToolboxSave()
  const [pick, setPick] = useState('everything')
  const presets = (tb.data && tb.data.presets) || []
  return h('div', { className: 'panel col' },
    h('h2', null, 'Start with a set of tools'),
    h('p', { className: 'muted' }, 'Every tool is a switch; you can change them any time under Switches and presets. Hermes can change them too when you ask, and every change is a version you can restore.'),
    h('div', { className: 'grid2' }, presets.map(p => jsx('label', { className: 'panel row', style: { cursor: 'pointer', borderColor: pick === p.name ? 'var(--esb-acc-line)' : undefined },
      children: [jsx('input', { type: 'radio', name: 'esb-preset', checked: pick === p.name, onChange: () => setPick(p.name) }, 'r'),
        jsx('div', { className: 'col grow', children: [jsx('strong', { children: p.title }, 't'), jsx('span', { className: 'note', children: p.blurb }, 'b')] }, 'd')] }, p.name))),
    h('div', { className: 'row' }, h(Btn, { pri: true, onClick: async () => { await save({ op: 'preset', preset: pick }); onDone && onDone() } }, 'Use this set')))
}

function AlertsBlock({ doc, hash }) {
  const profile = useProfile()
  const save = useToolboxSave()
  const q = useQuery({ queryKey: qk(profile, 'alerts'), queryFn: () => rest('/alerts'), retry: false })
  const a = q.data && q.data.alerts
  const on = !!(doc.alerts && doc.alerts.while_closed)
  const toggle = async v => {
    await save({ op: 'save', base_hash: hash, toolbox: { ...doc, alerts: { ...doc.alerts, while_closed: v } } })
    q.refetch()
  }
  return h('div', { className: 'panel col' },
    h('div', { className: 'row' },
      h('div', { className: 'col grow' }, h('strong', null, 'Alerts while Desktop is closed'),
        h('span', { className: 'note' }, 'A small Hermes job checks once a minute and sends due pomodoro, countdown and reminder alerts to your home channels (Telegram, Signal, …). It stays silent while Desktop is open.')),
      jsx(Switch, { checked: on, onCheckedChange: toggle, 'aria-label': 'Alerts while Desktop is closed' })),
    a && a.warning ? h('p', { className: 'banner' }, a.warning) : null,
    a && a.newest_error ? h('p', { className: 'note' }, `Newest tick error (${a.newest_error.at}): ${a.newest_error.error}`) : null,
    a && on && a.jobs ? h('p', { className: 'note' }, a.jobs.length ? `Job ${a.jobs[0].job_id}: ${a.jobs[0].schedule || 'every 1m'}, last ${a.jobs[0].last_status || 'not run yet'}.` : 'The job is missing; it is created on the next save, timer start or page open.') : null)
}

function Versions() {
  const profile = useProfile()
  const save = useToolboxSave()
  const q = useQuery({ queryKey: qk(profile, 'versions'), queryFn: () => rest('/toolbox/versions'), retry: false })
  const list = (q.data && q.data.versions) || []
  return h('div', { className: 'panel col' }, h('strong', null, 'Versions'),
    list.length ? h('table', { className: 'tl' }, h('tbody', null, list.map(v => jsx('tr', { children: [
      jsx('td', { className: 'n', children: `#${v.n}` }, 'n'), jsx('td', { children: v.time ? v.time.slice(0, 16).replace('T', ' ') : '' }, 'a'),
      jsx('td', { children: v.author === 'agent' ? h('span', { className: 'badge agent' }, 'Hermes') : 'you' }, 'w'),
      jsx('td', { children: v.summary }, 's'),
      jsx('td', { children: v.current ? h('span', { className: 'note' }, 'current') : h('button', { className: 'link', onClick: async () => { await save({ op: 'restore', version: v.n }); q.refetch() } }, 'restore') }, 'r'),
    ] }, v.n)))) : h('p', { className: 'note' }, 'No versions yet.'))
}

export function SettingsPage() {
  const tb = useToolbox()
  const save = useToolboxSave()
  const health = useQuery({ queryKey: qk(useProfile(), 'health'), queryFn: () => rest('/health'), retry: false })
  if (!tb.data) return h('div', { className: 'esb', style: { padding: 16 } }, jsx(Style, {}), h(ConnectionBanner, null), h('p', { className: 'muted' }, tb.error ? tb.error.message : 'Loading…'))
  const { toolbox: doc, tools, presets, hash } = tb.data
  const groups = {}
  for (const t of tools) (groups[t.group] = groups[t.group] || []).push(t)
  const setPomo = (k, v) => save({ op: 'save', base_hash: hash, toolbox: { ...doc, pomodoro: { ...doc.pomodoro, rhythm: 'custom', [k]: Number(v) } } })
  const tz = health.data && health.data.time_zone
  return h('div', { className: 'esb col', style: { padding: 4, gap: 12 } }, jsx(Style, {}),
    h(ConnectionBanner, null),
    h('div', { className: 'panel col' }, h('strong', null, 'Presets'),
      h('div', { className: 'row' }, presets.map(p => jsx(Btn, { pri: doc.preset === p.name, title: p.blurb, onClick: () => save({ op: 'preset', preset: p.name }), children: p.title }, p.name)))),
    h('div', { className: 'panel col' }, h('strong', null, 'Tools'),
      Object.entries(groups).map(([g, list]) => jsx('div', { className: 'col', children: [
        jsx('div', { className: 'grp', children: GROUP_TITLES[g] || g }, 'g'),
        ...list.map(t => jsx('div', { className: 'row', children: [
          jsx('div', { className: 'col grow', style: { gap: 0 }, children: [jsx('span', { children: t.title }, 't'), jsx('span', { className: 'note', children: t.blurb }, 'b')] }, 'd'),
          t.agent_tool ? jsx('span', { className: 'badge', title: 'The agent tool this switch shows or hides', children: t.agent_tool }, 'a') : null,
          jsx(Switch, { checked: t.on, 'aria-label': t.title, onCheckedChange: v => save({ op: 'switch', module: t.id, on: v }) }, 's'),
        ] }, t.id)),
      ] }, g))),
    h('div', { className: 'panel col' }, h('strong', null, 'Pomodoro'),
      h('div', { className: 'row', style: { alignItems: 'end' } },
        h(Btn, { pri: doc.pomodoro.rhythm === '25/5', onClick: () => save({ op: 'save', base_hash: hash, toolbox: { ...doc, pomodoro: { ...doc.pomodoro, rhythm: '25/5', work: 25, short: 5, long: 15 } } }) }, '25/5'),
        h(Btn, { pri: doc.pomodoro.rhythm === '50/10', onClick: () => save({ op: 'save', base_hash: hash, toolbox: { ...doc, pomodoro: { ...doc.pomodoro, rhythm: '50/10', work: 50, short: 10, long: 10 } } }) }, '50/10'),
        ['work', 'short', 'long', 'cycles'].map(k => jsx(Field, { label: k, children: h('input', { className: 'inp', type: 'number', defaultValue: doc.pomodoro[k], onBlur: e => Number(e.target.value) !== doc.pomodoro[k] && setPomo(k, e.target.value), style: { width: 70 } }) }, `${k}-${hash}`)))),
    h('div', { className: 'panel row' }, h('strong', { className: 'grow' }, 'Status-bar chip shows'),
      h(Choice, { value: doc.layout.chip, onChange: v => save({ op: 'save', base_hash: hash, toolbox: { ...doc, layout: { ...doc.layout, chip: v } } }),
        options: [['auto', 'What is running'], ['pomodoro', 'Pomodoro'], ['timelog', 'Time log'], ['off', 'Nothing']], 'aria-label': 'Chip' })),
    jsx(AlertsBlock, { doc, hash }),
    tz ? h('div', { className: 'panel col' }, h('strong', null, 'Time zone'),
      h('p', { className: 'note' }, tz.zone ? `"Today", reminders and weekly totals follow Hermes' zone ${tz.zone} (UTC${String(tz.offset).replace(/^([+-]\d{2})(\d{2})$/, '$1:$2')}).` : tz.note),
      !tz.zone ? h('p', { className: 'note' }, `This Mac is in ${Intl.DateTimeFormat().resolvedOptions().timeZone}.`) : null) : null,
    jsx(Versions, {}),
    h('p', { className: 'note' }, 'Agent settings (time-log edits, pad additions from automations, the first day of the week) are in this plugin\'s Settings form under Capabilities → Plugins.'),
    h(TwoPlaceNote, null))
}

// Desktop loads this file from the computer it runs on, never from a remote Hermes, so an update on the
// server leaves this half behind (README "Install and update"). host.state.connectionId is 'local' for
// this computer's own Hermes; any other value, null or a Desktop without the field shows the line,
// because a missed update costs more than one line.
const NO_CONNECTION = atom(null)
const TWO_PLACE_TIP = 'No Hermes on this computer: Capabilities → Plugins → Install from Git with this plugin\'s repository, Force reinstall.'

export function TwoPlaceNote() {
  const id = useValue((host.state && host.state.connectionId) || NO_CONNECTION)
  if (id === 'local') return null
  return h('p', { className: 'note', title: TWO_PLACE_TIP, 'data-esb': 'two-place' },
    'Hermes on another computer? Update this plugin on both. Here: ', h('code', null, `hermes plugins update ${ID}`), ', then Rescan.')
}

export async function reconcileOnOpen() {
  try {
    await post('/alerts/reconcile', {})
  } catch (error) {
    if (!error.network && !error.notOn) alertBoth('Eselsbrücke', `Alert job: ${error.message}`, 'warning')
  }
}
