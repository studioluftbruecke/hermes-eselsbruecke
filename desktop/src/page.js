// The Eselsbrücke page (a page with a sidebar row; it also opens beside the chat): a head, the
// rail with the dashboard and the switched-on tools by group, and the canvas. It lands on the
// dashboard; a palette row, the pad keybind or a dashboard tile shows a tool. The same component
// renders in the beside-chat pane and in a narrow window (`narrow`: no rail, a picker in the head).
import { host, pluginSettingsHref, Popover, PopoverContent, PopoverTrigger, useQuery, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { OutboxNote } from './chip.js'
import { $connection, NOT_ON_TEXT, qk, rest, versionNote } from './core.js'
import { Dashboard, dashboardSave, pin, pinnedOf, unpin } from './dashboard.js'
import { $outbox } from './outbox.js'
import { Style } from './style.js'
import { PadTool } from './tools/pad.js'
import { PomodoroTool } from './tools/pomodoro.js'
import { TimelogTool } from './tools/timelog.js'
import { CronTool, DiffTool, FormatterTool, RegexTool, TokensTool } from './tools/code.js'
import { ClockTool } from './tools/clock.js'
import { ColourTool, EncodeTool, GenerateTool, QrTool } from './tools/convert.js'
import { Btn, Choice, DASHBOARD, h, Icon, IconBtn, pageHidden, pageShown, ToolIcon, toolRows, useProfile, useToolbox, useToolboxSave, viewAtom } from './ui.js'

export const TOOL_VIEWS = {
  pad: PadTool, pomodoro: PomodoroTool, timelog: TimelogTool, formatter: FormatterTool, diff: DiffTool, regex: RegexTool,
  tokens: TokensTool, cron: CronTool, encode: EncodeTool, timezones: ClockTool, generate: GenerateTool, colour: ColourTool, qr: QrTool,
}
// What "Ask Hermes" drafts for each tool. The pad attaches itself; the others name the agent
// tool that does the same job, so the chat answers with exact output instead of a guess.
export const ASK = {
  pad: '@pad:today ', pomodoro: 'With eselsbruecke_timer: ', timelog: 'With eselsbruecke_timelog: ',
  formatter: 'Format this with eselsbruecke_format:\n', diff: 'Compare these two texts with eselsbruecke_text (diff):\n',
  regex: 'With eselsbruecke_text (regex, Python flavour): ', tokens: 'Count the tokens of this with eselsbruecke_text:\n',
  cron: 'Explain this cron line with eselsbruecke_convert: ', encode: 'With eselsbruecke_convert (encode or decode): ',
  timezones: 'With eselsbruecke_convert (the time in my places): ', generate: 'With eselsbruecke_generate: ', colour: 'With eselsbruecke_convert (colour): ',
  qr: 'Make a QR code for: ',
}

export function askHermes(id) {
  try {
    if (typeof host.newChat === 'function') host.newChat(host.state.profile.get() || undefined)
    setTimeout(() => host.composer && host.composer.setDraft(null, ASK[id] || ''), 300)
  } catch (error) {
    host.notify({ kind: 'warning', title: 'Eselsbrücke', message: `Could not open a chat: ${error.message}` })
  }
}

const GROUPS = [['daily', 'Daily'], ['code', 'Code'], ['convert', 'Convert'], ['design', 'Design']]

/** The tools the page can show: switched on, and with a page in this Desktop. */
export const pageTools = data => toolRows(data).filter(t => t.on && TOOL_VIEWS[t.id])

/** The tool to show for what was asked, or null for the dashboard: nothing asked, the dashboard asked,
 *  or a tool that is switched off. */
export const currentTool = (chosen, tools) => (chosen && chosen !== DASHBOARD && tools.find(t => t.id === chosen)) || null

/** The rail below "Dashboard": [{ id, label, tools }] for each group that has a tool. */
export const railGroups = tools => GROUPS.map(([id, label]) => ({ id, label, tools: tools.filter(t => t.group === id) })).filter(g => g.tools.length)

/** The narrow head's picker: the dashboard, then the tools in rail order. */
export const pickerOptions = tools => [[DASHBOARD, 'Dashboard'], ...railGroups(tools).flatMap(g => g.tools.map(t => [t.id, t.title]))]

/** The head's pin button on a tool view: { pinned, label, body } with the save that toggles it, or
 *  null while the toolbox is not loaded or for a tool the dashboard cannot hold. */
export function pinToggle(data, tool) {
  if (!data || !data.toolbox || !tool || !tool.dashboard) return null
  const list = pinnedOf(data)
  const pinned = list.includes(tool.id)
  return { pinned, label: pinned ? 'On the dashboard' : 'Pin to dashboard', body: dashboardSave(data, pinned ? unpin(list, tool.id) : pin(list, tool.id)) }
}

/** Watch the element's width: below 640 px the page drops the rail (beside-chat and narrow windows). */
function useNarrow(ref) {
  const [narrow, setNarrow] = useState(false)
  useEffect(() => {
    if (!ref.current || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setNarrow(e.contentRect.width < 640))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return narrow
}

/** "n not synced" in the head. It opens the outbox note with "Try again" and "Discard", so a stuck
 *  click can be dealt with while the status-bar chip is hidden. */
function NotSynced({ count }) {
  return jsx(Popover, { children: [
    jsx(PopoverTrigger, { asChild: true, children: h('button', { type: 'button', className: 'chip', title: 'Clicks that wait for Hermes' }, `${count} not synced`) }, 't'),
    jsx(PopoverContent, { align: 'start', className: 'w-64', children: h('div', { className: 'esb col' }, h(OutboxNote, { count })) }, 'c'),
  ] })
}

export function ToolboxPage({ beside = false, onBeside, onSettings }) {
  const tb = useToolbox()
  const save = useToolboxSave()
  const profile = useProfile()
  const conn = useValue($connection)
  const outbox = useValue($outbox)
  const $view = viewAtom(beside)
  const chosen = useValue($view)
  const health = useQuery({ queryKey: qk(profile, 'health'), queryFn: () => rest('/health'), staleTime: 300000, retry: false })
  const ref = useRef(null)
  const narrow = useNarrow(ref) || beside
  useEffect(() => {
    if (beside) return undefined
    pageShown()
    return pageHidden
  }, [beside])
  if (conn === 'off') {
    return h('div', { className: 'esb', style: { padding: 24 } }, jsx(Style, {}), h('h1', null, 'Eselsbrücke'),
      h('p', { className: 'muted', style: { marginTop: 8 } }, NOT_ON_TEXT, ' Turn it on in Capabilities → Plugins for the profile ', h('strong', null, profile), ', or switch to a profile that has it.'))
  }
  const tools = pageTools(tb.data)
  const current = currentTool(chosen, tools)
  const View = current ? TOOL_VIEWS[current.id] : null
  const pick = id => $view.set(id && id !== DASHBOARD ? id : null)
  const pinned = pinToggle(tb.data, current)
  const note = versionNote(health.data && health.data.version)
  return h('div', { ref, className: `esb${narrow ? ' narrow' : ''}`, style: { height: '100%' } }, jsx(Style, {}),
    h('div', { className: 'page' },
      h('header', { className: 'head' },
        h('h1', null, 'Eselsbrücke'),
        narrow ? h(Choice, { value: current ? current.id : DASHBOARD, onChange: pick, options: pickerOptions(tools), 'aria-label': 'View' }) : null,
        conn === 'offline' ? h('span', { className: 'chip' }, 'not connected') : null,
        outbox.length ? h(NotSynced, { count: outbox.length }) : null,
        h('span', { className: 'grow' }),
        current ? h(Btn, { onClick: () => askHermes(current.id), title: 'Open a new chat with this tool drafted; you press send' }, 'Ask Hermes') : null,
        pinned ? h(IconBtn, { icon: pinned.pinned ? 'pinned' : 'pin', label: pinned.label, pri: pinned.pinned, 'aria-pressed': pinned.pinned, onClick: () => save(pinned.body) },
          h('span', { className: 'lbl' }, pinned.label)) : null,
        !beside && onBeside ? h(IconBtn, { icon: 'split-horizontal', label: 'Open beside the chat', onClick: onBeside }) : null,
        onSettings ? h(IconBtn, { icon: 'settings-gear', label: 'Settings', onClick: onSettings }) : null),
      note ? h('p', { className: 'strip', role: 'status' }, note) : null,
      h('div', { className: 'body' },
        narrow ? null : h('nav', { className: 'rail', 'aria-label': 'Tools' },
          jsx('button', { type: 'button', className: `ri home${current ? '' : ' on'}`, onClick: () => pick(null), 'aria-current': current ? undefined : 'page',
            children: [jsx('span', { className: 'mk', children: h(Icon, { name: 'dashboard' }) }, 'm'), jsx('span', { className: 'nm', children: 'Dashboard' }, 'n')] }, DASHBOARD),
          railGroups(tools).map(g => [jsx('div', { className: 'grp', children: g.label }, `g-${g.id}`), ...g.tools.map(t => jsx('button', {
            type: 'button', className: `ri${current && t.id === current.id ? ' on' : ''}`, onClick: () => pick(t.id), 'aria-current': current && t.id === current.id ? 'page' : undefined,
            children: [jsx(ToolIcon, { id: t.id }, 'm'), jsx('span', { className: 'nm', children: t.title }, 'n')],
          }, t.id))])),
        h('main', { className: 'canvas' }, View ? jsx(View, {}, current.id) : jsx(Dashboard, { data: tb.data, narrow, onOpen: pick }, DASHBOARD)))))
}

export const openSettings = () => host.navigate(pluginSettingsHref('eselsbruecke', 'toolbox'))
