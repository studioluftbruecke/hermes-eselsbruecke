// Small UI helpers and the shared queries (toolbox, timer, time log) every surface reads.
import { atom, Codicon, host, useQuery, useQueryClient, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

import { $connection, alertBoth, getCtx, NOT_ON_TEXT, OFFLINE_TEXT, PATH, post, profileNow, qk, rest, storage } from './core.js'

/** h(tag, props, ...children): jsx without JSX syntax (the bundle is plain ESM). */
export const h = (tag, props, ...children) => {
  const kids = children.flat().filter(c => c !== null && c !== undefined && c !== false)
  return kids.length > 1 ? jsxs(tag, { ...(props || {}), children: kids }) : jsx(tag, { ...(props || {}), children: kids[0] })
}

export const Btn = ({ pri, children, ...rest }) => h('button', { type: 'button', className: pri ? 'btn pri' : 'btn', ...rest }, children)
export const Field = ({ label, children, className }) => h('label', { className: `field ${className || ''}` }, h('span', null, label), children)
export const Out = ({ err, children, ...rest }) => h('pre', { className: err ? 'out err' : 'out', ...rest }, children)
export const ToolHead = ({ title, blurb, children }) =>
  h('div', { className: 'toolhead' }, h('h2', null, title), blurb ? h('p', null, blurb) : null, h('span', { className: 'grow' }), children)

export function Input({ value, onChange, ...rest }) {
  return h('input', { className: 'inp', value: value ?? '', onChange: e => onChange(e.target.value), ...rest })
}
export function Area({ value, onChange, ...rest }) {
  return h('textarea', { className: 'inp', spellCheck: false, value: value ?? '', onChange: e => onChange(e.target.value), ...rest })
}
export function Choice({ value, onChange, options, ...rest }) {
  return h('select', { className: 'inp', value, onChange: e => onChange(e.target.value), ...rest },
    options.map(([v, label]) => jsx('option', { value: v, children: label }, v)))
}

/** One of several, as a row of buttons. `options` is [[value, label]]. */
export function Seg({ value, onChange, options, label }) {
  return h('div', { className: 'seg', role: 'group', 'aria-label': label },
    options.map(([v, text]) => jsx('button', { type: 'button', 'aria-pressed': value === v, onClick: () => onChange(v), children: text }, v)))
}

// What the page knows about each tool without asking Hermes: its Codicon, and the title, group and
// dashboard kind to show before the toolbox has loaded or while the Hermes side is an older version.
export const SHELF = {
  pad: ['checklist', "Today's pad", 'daily', 'widget'],
  pomodoro: ['watch', 'Pomodoro', 'daily', 'widget'],
  timelog: ['graph', 'Time log', 'daily', 'widget'],
  timezones: ['globe', 'World clock', 'daily', 'widget'],
  formatter: ['json', 'Formatter', 'code', 'tile'],
  diff: ['diff', 'Text diff', 'code', 'tile'],
  regex: ['regex', 'Regex tester', 'code', 'tile'],
  tokens: ['symbol-numeric', 'Token counter', 'code', 'tile'],
  cron: ['sync', 'Cron explainer', 'code', 'tile'],
  encode: ['code', 'Encode, decode', 'convert', 'tile'],
  generate: ['key', 'UUID, password', 'convert', 'widget'],
  colour: ['symbol-color', 'Colour picker', 'design', 'widget'],
  qr: ['screen-full', 'QR code', 'design', 'tile'],
  calc: ['symbol-operator', 'Calculator', 'engine', null],
}

/** The toolbox's tools as every surface reads them: the backend's rows, or every tool switched on
 *  while there is no answer yet. An older Hermes still says group `focus` and sends no dashboard kind. */
export function toolRows(data) {
  const rows = data && Array.isArray(data.tools) ? data.tools : Object.keys(SHELF).map(id => ({ id, on: true }))
  return rows.map(t => {
    const [, title, group, kind] = SHELF[t.id] || []
    return { ...t, title: t.title || title || t.id, group: t.group === 'focus' ? 'daily' : t.group || group || 'daily',
      dashboard: t.dashboard !== undefined ? t.dashboard : kind || null }
  })
}

/** The body that saves the toolbox file with some keys changed (dashboard, clocks, layout, first_run ...). */
export const docSave = (data, patch) => ({ op: 'save', base_hash: data.hash, toolbox: { ...data.toolbox, ...patch } })

export const Icon = ({ name, size = 16, ...rest }) => jsx(Codicon, { name, size, ...rest })
export const ToolIcon = ({ id }) => h('span', { className: 'mk' }, h(Icon, { name: (SHELF[id] || [])[0] || 'tools' }))
/** A button led by an icon; `label` is its tooltip and its accessible name. */
export const IconBtn = ({ icon, label, pri, children, ...rest }) =>
  h('button', { type: 'button', className: `btn ico${pri ? ' pri' : ''}`, title: label, 'aria-label': label, ...rest }, h(Icon, { name: icon, size: 14 }), children)

/** Put a text on the clipboard: Desktop's own door first, the browser's as the fallback. */
export async function copyText(text) {
  try {
    const ctx = getCtx()
    if (ctx && ctx.os && (await ctx.os.writeClipboard(text))) return true
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function Copy({ text, label = 'Copy' }) {
  const [done, setDone] = useState(false)
  return h(Btn, {
    disabled: !text,
    onClick: async () => {
      const ok = await copyText(text)
      if (!ok) alertBoth('Eselsbrücke', 'Could not copy to the clipboard.', 'warning')
      setDone(ok)
      setTimeout(() => setDone(false), 1200)
    },
  }, done ? 'Copied' : label)
}

/** The "not connected" line for a tool whose engine sits behind a route. */
export function ConnectionBanner({ needs = 'backend', what }) {
  const state = useValue($connection)
  if (state === 'off') return h('div', { className: 'banner' }, NOT_ON_TEXT)
  if (state !== 'offline') return null
  if (needs === 'none') return null
  return h('div', { className: 'banner' }, what || OFFLINE_TEXT)
}

export const useProfile = () => useValue(host.state.profile) || 'default'

/** Debounced value (the pad's "=" lines and the diff wait 300 ms after the last key). */
export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

// --- shared queries ----------------------------------------------------------------------------------

export function useToolbox() {
  const profile = useProfile()
  return useQuery({ queryKey: qk(profile, 'toolbox'), queryFn: () => rest('/toolbox'), staleTime: 30000, retry: false })
}

/** `save(body)` posts to /toolbox. It answers the new /toolbox view, or null after a refusal or a
 *  failed call, which it has already shown as a toast: callers are click handlers, and a rejection
 *  there would have nobody to catch it. A 409 brings the newest file, so the next click is not stale. */
export function useToolboxSave() {
  const client = useQueryClient()
  const profile = useProfile()
  return async body => {
    try {
      const out = await post('/toolbox', body)
      client.setQueryData(qk(profile, 'toolbox'), out)
      client.invalidateQueries({ queryKey: qk(profile, 'versions') })
      return out
    } catch (error) {
      if (error.status === 409 && error.body && error.body.current) client.setQueryData(qk(profile, 'toolbox'), error.body.current)
      alertBoth('Eselsbrücke', error.message, 'warning')
      return null
    }
  }
}

export const isOn = (toolbox, id) => {
  const t = toolbox && toolbox.tools && toolbox.tools.find(x => x.id === id)
  return t ? t.on : true
}

// --- what the page shows ------------------------------------------------------------------------------

export const DASHBOARD = 'dashboard'

// The tool each surface shows; null is the dashboard. The page and the beside-chat pane keep their own,
// so leaving the page (which puts it back on the dashboard) does not change what the pane shows.
export const $tool = atom(null)
export const $besideTool = atom(null)
export const viewAtom = beside => (beside ? $besideTool : $tool)
export const $focusPadAdd = atom(0)

/** Show a tool, or the dashboard with `DASHBOARD` (or nothing) as the id: in the beside-chat pane when
 *  that is where the user keeps Eselsbrücke (or `opts.beside` says so), else on the page. */
export function openTool(id, opts = {}) {
  const tool = id && id !== DASHBOARD ? id : null
  if (tool === 'pad' && opts.focusAdd) $focusPadAdd.set($focusPadAdd.get() + 1)
  const beside = !!(opts.beside ?? storage.get('openBeside', false)) && !!openBesideHook
  viewAtom(beside).set(tool)
  if (beside) openBesideHook()
  else host.navigate(PATH)
}

export const openDashboard = opts => openTool(DASHBOARD, opts)

let openBesideHook = null
export const setOpenBeside = fn => {
  openBesideHook = fn
}

// The sidebar row only navigates; it cannot say what to show. So the page goes back to the dashboard
// when it is left, and the next visit starts there unless openTool asked for a tool first. The reset
// waits one turn and checks again, because React's development mode mounts every page twice.
let pagesShown = 0
export function pageShown() {
  pagesShown += 1
}
export function pageHidden() {
  pagesShown = Math.max(0, pagesShown - 1)
  setTimeout(() => {
    if (!pagesShown) $tool.set(null)
  }, 0)
}

export const profileKey = () => profileNow()
