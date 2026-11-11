// The plugin's own settings page (constraint 10), one section per subject with a gap between them:
// the status-bar chip (whether it shows, what it shows while something runs, its four faces), the tool
// switches by group, the pomodoro rhythm, "Alerts while Desktop is closed" with its home-channel
// warning and the newest tick error, Hermes' time zone, and the history of the toolbox file with restore.
import { atom, host, Switch, useQuery, useValue } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

import { CHIP_SAMPLES, chipFace, chipLayout } from './chip.js'
import { alertBoth, dayAt, ID, post, qk, rest, versionNote } from './core.js'
import { $rhythm } from './live.js'
import { SidebarBlock } from './sidebar.js'
import { Style } from './style.js'
import { ConnectionBanner, docSave, Field, h, Seg, ToolIcon, toolRows, useProfile, useToolbox, useToolboxSave } from './ui.js'

const GROUPS = [['daily', 'Daily tools'], ['code', 'Code tools'], ['convert', 'Convert tools'], ['design', 'Design tools'], ['engine', 'For the pad and the agent']]
const RHYTHMS = { '25/5': { work: 25, short: 5, long: 15 }, '50/10': { work: 50, short: 10, long: 10 } }
const CUSTOM_FIELDS = [['work', 'Work, minutes'], ['short', 'Short break, minutes'], ['long', 'Long break, minutes'], ['cycles', 'Work phases before the long break']]

/** The tool sections: [{ id, label, tools }] in the page's order; a group this Desktop does not know
 *  (a newer Hermes) comes last as "Other tools". */
export function settingsGroups(tools) {
  const known = new Set(GROUPS.map(([id]) => id))
  const other = tools.filter(t => !known.has(t.group))
  return [...GROUPS.map(([id, label]) => ({ id, label, tools: tools.filter(t => t.group === id) })), { id: 'other', label: 'Other tools', tools: other }]
    .filter(g => g.tools.length)
}

/** The save for a click on the rhythm control: a named rhythm brings its minutes, "custom" keeps them. */
export const rhythmSave = (data, name) => docSave(data, { pomodoro: { ...data.toolbox.pomodoro, rhythm: name, ...(RHYTHMS[name] || {}) } })

/** The saves of the status bar section. */
export const chipSave = (data, patch) => docSave(data, { layout: { ...data.toolbox.layout, ...patch } })

/** "today 19:33", "yesterday 16:02" or "2026-11-03 16:02" for a time the backend wrote. */
export function whenLabel(iso, now = Date.now()) {
  if (!iso) return ''
  const day = iso.slice(0, 10)
  const time = iso.slice(11, 16)
  return `${day === dayAt(iso, now) ? 'today' : day === dayAt(iso, now - 86400000) ? 'yesterday' : day} ${time}`
}

const Section = ({ title, children }) => h('section', { className: 'sec' }, h('h3', null, title), h('div', { className: 'box' }, children))
const Row = ({ title, hint, lead, children, tip }) => h('div', { className: 'srow', title: tip },
  lead, h('div', { className: 'grow' }, h('b', null, title), hint ? h('div', { className: 'd' }, hint) : null), children)

function StatusBar({ data, save }) {
  const layout = chipLayout(data.toolbox.layout)
  return h(Section, { title: 'Status bar' },
    h(Row, { title: 'Show in status bar', hint: 'A small icon. While a timer runs it shows a ring and the minutes left.' },
      jsx(Switch, { checked: layout.chip_visible, 'aria-label': 'Show in status bar', onCheckedChange: v => save(chipSave(data, { chip_visible: v })) })),
    h(Row, { title: 'While something runs, show' },
      h(Seg, { value: layout.chip, label: 'While something runs, show', onChange: v => save(chipSave(data, { chip: v })),
        options: [['auto', 'What is running'], ['pomodoro', 'Pomodoro'], ['timelog', 'Time log']] })),
    h('div', { className: 'states' }, CHIP_SAMPLES.map(([label, state]) => jsx('div', { className: 'st', children: [
      jsx('span', { className: 'fake', children: h('span', { className: `esbchip${state.kind === 'idle' ? '' : ' live'}`, 'data-state': state.kind }, chipFace(state)) }, 'f'),
      jsx('span', { className: 'd', children: label }, 'l'),
    ] }, label))))
}

function Pomodoro({ data, save }) {
  const p = data.toolbox.pomodoro
  const set = async body => {
    const out = await save(body)
    if (out && out.toolbox && out.toolbox.pomodoro) $rhythm.set(out.toolbox.pomodoro)
  }
  const setField = (k, v) => Number(v) > 0 && Number(v) !== p[k] && set(docSave(data, { pomodoro: { ...p, rhythm: 'custom', [k]: Number(v) } }))
  return h(Section, { title: 'Pomodoro' },
    h(Row, { title: 'Rhythm', hint: 'Work and break, in minutes.' },
      h(Seg, { value: p.rhythm, label: 'Rhythm', onChange: v => set(rhythmSave(data, v)), options: [['25/5', '25/5'], ['50/10', '50/10'], ['custom', 'Custom']] })),
    p.rhythm === 'custom' ? h('div', { className: 'srow', style: { flexWrap: 'wrap', alignItems: 'end' } },
      CUSTOM_FIELDS.map(([k, label]) => jsx(Field, { label, children: h('input', { className: 'inp', type: 'number', min: 1, defaultValue: p[k], style: { width: 84 },
        onBlur: e => setField(k, e.target.value) }) }, `${k}-${data.hash}`))) : null)
}

function Alerts({ data, save }) {
  const profile = useProfile()
  const q = useQuery({ queryKey: qk(profile, 'alerts'), queryFn: () => rest('/alerts'), retry: false })
  const a = q.data && q.data.alerts
  const doc = data.toolbox
  const on = !!(doc.alerts && doc.alerts.while_closed)
  const toggle = async v => {
    await save(docSave(data, { alerts: { ...doc.alerts, while_closed: v } }))
    q.refetch()
  }
  const job = a && on && a.jobs ? a.jobs[0] : null
  return h(Section, { title: 'Alerts' },
    h(Row, { title: 'Alerts while Desktop is closed', hint: 'Hermes sends due timer and reminder alerts to your home channel.' },
      jsx(Switch, { checked: on, onCheckedChange: toggle, 'aria-label': 'Alerts while Desktop is closed' })),
    a && a.warning ? h('div', { className: 'srow d' }, a.warning) : null,
    a && a.newest_error ? h('div', { className: 'srow d' }, `The newest check failed (${whenLabel(a.newest_error.at)}): ${a.newest_error.error}`) : null,
    a && on && a.jobs ? h('div', { className: 'srow d' }, job
      ? `The check runs ${job.schedule || 'every 1m'}. Last run: ${job.last_status || 'not yet'}.`
      : 'The check is missing. It is set up again on the next save, timer start or page open.') : null)
}

function History({ save }) {
  const profile = useProfile()
  const q = useQuery({ queryKey: qk(profile, 'versions'), queryFn: () => rest('/toolbox/versions'), retry: false })
  const list = (q.data && q.data.versions) || []
  const restore = n => save({ op: 'restore', version: n })
  return h(Section, { title: 'History' },
    list.length ? list.map(v => jsx('div', { className: 'srow', children: [
      jsx('div', { className: 'grow', children: [
        jsx('b', { style: { fontWeight: 500 }, children: v.summary || 'Saved' }, 's'),
        jsx('div', { className: 'd', children: [v.author === 'agent' ? jsx('span', { className: 'badge agent', children: 'Hermes' }, 'a') : 'you', ` · ${whenLabel(v.time)}`] }, 'w')] }, 'd'),
      v.current ? jsx('span', { className: 'muted small', children: 'current' }, 'r')
        : jsx('button', { type: 'button', className: 'link', onClick: () => restore(v.n), children: 'Restore' }, 'r'),
    ] }, v.n)) : h('div', { className: 'srow d' }, 'No changes yet. Every change to these settings is kept here and can be restored.'))
}

export function SettingsPage() {
  const tb = useToolbox()
  const save = useToolboxSave()
  const health = useQuery({ queryKey: qk(useProfile(), 'health'), queryFn: () => rest('/health'), retry: false })
  if (!tb.data) return h('div', { className: 'esb', style: { padding: 16 } }, jsx(Style, {}), h(ConnectionBanner, null), h('p', { className: 'muted' }, tb.error ? tb.error.message : 'Loading…'))
  return h(SettingsView, { data: tb.data, health: health.data, save })
}

/** The page for a loaded toolbox: `data` is the /toolbox answer, `health` the /health answer when
 *  there is one, `save(body)` posts to /toolbox. */
export function SettingsView({ data, health, save }) {
  const tz = health && health.time_zone
  const note = versionNote(health && health.version)
  return h('div', { className: 'esb settings', style: { padding: 4 } }, jsx(Style, {}),
    h(ConnectionBanner, null),
    note ? h('p', { className: 'banner', role: 'status' }, note) : null,
    data.file_error ? h('p', { className: 'banner' }, `The settings file could not be read, so the last good version is shown. ${data.file_error}`) : null,
    h(StatusBar, { data, save }),
    h(SidebarBlock, null),
    settingsGroups(toolRows(data)).map(g => jsx(Section, { title: g.label, children: g.tools.map(t => jsx(Row, {
      title: t.title, hint: t.blurb, lead: h(ToolIcon, { id: t.id }), tip: t.agent_tool ? `Hermes uses this as ${t.agent_tool}` : undefined,
      children: jsx(Switch, { checked: !!t.on, 'aria-label': t.title, onCheckedChange: v => save({ op: 'switch', module: t.id, on: v }) }),
    }, t.id)) }, g.id)),
    h(Pomodoro, { data, save }),
    h(Alerts, { data, save }),
    tz ? h(Section, { title: 'Time zone' }, h('div', { className: 'srow d', style: { display: 'block' } },
      tz.zone ? `"Today", reminders and weekly totals follow the zone of Hermes, ${tz.zone} (UTC${String(tz.offset).replace(/^([+-]\d{2})(\d{2})$/, '$1:$2')}).` : tz.note,
      !tz.zone ? ` This computer is in ${Intl.DateTimeFormat().resolvedOptions().timeZone}.` : null)) : null,
    h(History, { save }),
    h('p', { className: 'note' }, 'The settings for the agent (time-log edits, pad lines from automations, the first day of the week) are in this plugin\'s Settings form under Capabilities → Plugins.'),
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
