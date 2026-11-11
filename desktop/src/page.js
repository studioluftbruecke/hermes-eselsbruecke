// The Toolbox page (D5: a page with a sidebar row; any tool also opens beside the chat): a head with
// the profile and connection, the rail of switched-on tools by group, the tool canvas. The same
// component renders in the beside-chat pane (`narrow`, rail hidden, a tool picker in the head).
import { host, pluginSettingsHref, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, NOT_ON_TEXT, storage } from './core.js'
import { $outbox } from './outbox.js'
import { Style } from './style.js'
import { PadTool } from './tools/pad.js'
import { PomodoroTool } from './tools/pomodoro.js'
import { TimelogTool } from './tools/timelog.js'
import { CronTool, DiffTool, FormatterTool, RegexTool, TokensTool } from './tools/code.js'
import { ColourTool, EncodeTool, GenerateTool, QrTool, TimezonesTool } from './tools/convert.js'
import { $tool, Btn, Choice, h, useProfile, useToolbox } from './ui.js'

export const TOOL_VIEWS = {
  pad: PadTool, pomodoro: PomodoroTool, timelog: TimelogTool, formatter: FormatterTool, diff: DiffTool, regex: RegexTool,
  tokens: TokensTool, cron: CronTool, encode: EncodeTool, timezones: TimezonesTool, generate: GenerateTool, colour: ColourTool, qr: QrTool,
}
export const MARKS = { pad: 'P', pomodoro: 'T', timelog: 'H', formatter: '{}', diff: '±', regex: '.*', tokens: '#', cron: '*', encode: '%',
  timezones: 'Z', generate: 'ID', colour: 'C', qr: 'QR' }
// F20: what "Ask Hermes" drafts for each tool. The pad attaches itself; the others name the agent
// tool that does the same job, so the chat answers with exact output instead of a guess.
export const ASK = {
  pad: '@pad:today ', pomodoro: 'With eselsbruecke_timer: ', timelog: 'With eselsbruecke_timelog: ',
  formatter: 'Format this with eselsbruecke_format:\n', diff: 'Compare these two texts with eselsbruecke_text (diff):\n',
  regex: 'With eselsbruecke_text (regex, Python flavour): ', tokens: 'Count the tokens of this with eselsbruecke_text:\n',
  cron: 'Explain this cron line with eselsbruecke_convert: ', encode: 'With eselsbruecke_convert (encode or decode): ',
  timezones: 'With eselsbruecke_convert (time zones): ', generate: 'With eselsbruecke_generate: ', colour: 'With eselsbruecke_convert (colour): ',
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

const GROUPS = [['focus', 'Focus'], ['code', 'Code'], ['convert', 'Convert'], ['design', 'Design']]

// Used when the toolbox cannot be loaded yet (first paint, or Hermes unreachable before any load).
const FALLBACK = Object.keys(TOOL_VIEWS).map(id => ({ id, title: id, group: 'focus', on: true }))

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

export function ToolboxPage({ beside = false, onBeside, onSettings }) {
  const tb = useToolbox()
  const profile = useProfile()
  const conn = useValue($connection)
  const outbox = useValue($outbox)
  const chosen = useValue($tool)
  const ref = useRef(null)
  const narrow = useNarrow(ref) || beside
  const tools = ((tb.data && tb.data.tools) || FALLBACK).filter(t => t.on && TOOL_VIEWS[t.id])
  const current = tools.find(t => t.id === (chosen || storage.get('lastTool', 'pad'))) || tools[0]
  const View = current ? TOOL_VIEWS[current.id] : null
  const pick = id => {
    $tool.set(id)
    storage.set('lastTool', id)
  }
  if (conn === 'off') {
    return h('div', { className: 'esb', style: { padding: 24 } }, jsx(Style, {}), h('h1', null, 'Toolbox'),
      h('p', { className: 'muted', style: { marginTop: 8 } }, NOT_ON_TEXT, ' Turn it on in Capabilities → Plugins for the profile ', h('strong', null, profile), ', or switch to a profile that has it.'))
  }
  return h('div', { ref, className: `esb${narrow ? ' narrow' : ''}`, style: { height: '100%' } }, jsx(Style, {}),
    h('div', { className: 'page' },
      h('div', { className: 'head' },
        h('h1', null, 'Toolbox'),
        h('span', { className: `chip${conn === 'ok' ? ' live' : ''}` }, conn === 'offline' ? 'not connected' : profile),
        outbox.length ? h('span', { className: 'chip' }, `${outbox.length} not synced`) : null,
        narrow ? h(Choice, { value: current ? current.id : '', onChange: pick, options: tools.map(t => [t.id, t.title]), 'aria-label': 'Tool' }) : null,
        h('span', { className: 'grow' }),
        current ? h(Btn, { onClick: () => askHermes(current.id), title: 'Open a new chat with this tool drafted; you press send' }, 'Ask Hermes') : null,
        !beside && onBeside ? h(Btn, { onClick: onBeside, title: 'Open the toolbox in a pane beside the chat' }, 'Open beside chat') : null,
        onSettings ? h(Btn, { onClick: onSettings }, 'Switches and presets') : null),
      h('div', { className: 'body' },
        h('nav', { className: 'rail', 'aria-label': 'Tools' }, GROUPS.map(([g, label]) => {
          const inGroup = tools.filter(t => t.group === g)
          if (!inGroup.length) return null
          return [jsx('div', { className: 'grp', children: label }, `g-${g}`), ...inGroup.map(t => jsx('button', {
            type: 'button', className: `ri${current && t.id === current.id ? ' on' : ''}`, onClick: () => pick(t.id), 'aria-current': current && t.id === current.id ? 'page' : undefined,
            children: [jsx('span', { className: 'mk', children: MARKS[t.id] || '·' }, 'm'), jsx('span', { className: 'nm', children: t.title }, 'n')],
          }, t.id))]
        })),
        h('main', { className: 'canvas' }, View ? jsx(View, {}, current.id) : h('p', { className: 'muted' }, 'Every tool is switched off. Turn some on in Switches and presets.')))))
}

export const openSettings = () => host.navigate(pluginSettingsHref('eselsbruecke', 'toolbox'))
