/**
 * Eselsbrücke, the Desktop half: the Toolbox page and its sidebar row, the plugin's settings page,
 * the status-bar chip, palette rows per switched-on tool, two rebindable shortcuts, "open beside
 * chat", Desktop alerts, and the outbox. Source of desktop/plugin.js, built by desktop/build/build.mjs.
 *
 * Nothing heavy runs when this module is evaluated (Desktop evaluates every plugin.js at start, even
 * switched off; constraint 9): the vendored packages load on first use (vendor.js).
 */
import { host, KEYBINDS_AREA, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

import { Chip } from './chip.js'
import { getCtx, ID, log, PATH, rest, setCtx, storage, uuid4 } from './core.js'
import { startLive, timerAction } from './live.js'
import { refreshOutbox } from './outbox.js'
import { openSettings, ToolboxPage } from './page.js'
import { PresetChooser, reconcileOnOpen, SettingsPage } from './settings.js'
import { Style } from './style.js'
import { h, openTool, setOpenBeside, useToolbox } from './ui.js'

let closeBeside = null
let disposing = false
const BESIDE = `${ID}-beside`

async function copyUuid() {
  const id = uuid4()
  const ok = await getCtx().os.writeClipboard(id)
  host.notify({ kind: ok ? 'success' : 'warning', title: 'Eselsbrücke', message: ok ? `Copied ${id}` : `Could not copy; the UUID is ${id}` })
}

/** Open the toolbox beside the chat, or bring the open pane to the front as it is (typed text stays).
 *  The setting `openBeside` is cleared only when the user closes the pane, not when the plugin is
 *  disabled or reloaded (that closes the pane through ctx.onDispose). */
function openBeside() {
  storage.set('openBeside', true)
  if (typeof host.openWorkspace !== 'function') {
    host.navigate(PATH)
    return
  }
  if (closeBeside && typeof host.revealPane === 'function') {
    host.revealPane(`plugin-workspace:${BESIDE}`)
    return
  }
  // Re-opening the same id replaces the tab's registration in place and fronts it (sdk openWorkspace);
  // the old disposer is dropped, not run, so its onClose does not clear the setting.
  closeBeside = host.openWorkspace(BESIDE, {
    title: 'Toolbox',
    dock: { pane: 'workspace', pos: 'right' },
    minWidth: '22rem',
    onClose: () => {
      closeBeside = null
      if (!disposing) storage.set('openBeside', false)
    },
    render: () => jsx(ToolboxPage, { beside: true, onSettings: openSettings }),
  })
}

function closeBesideOnDispose() {
  if (!closeBeside) return
  disposing = true
  try {
    closeBeside()
  } finally {
    disposing = false
    closeBeside = null
  }
}

function Page() {
  const tb = useToolbox()
  if (tb.data && tb.data.toolbox && tb.data.toolbox.first_run) {
    return h('div', { className: 'esb', style: { padding: 24, maxWidth: 860 } }, jsx(Style, {}), h('h1', { style: { marginBottom: 12 } }, 'Toolbox'), jsx(PresetChooser, {}))
  }
  return jsx(ToolboxPage, { onBeside: openBeside, onSettings: openSettings })
}

// Palette rows cannot read the query (constraint 13): one row per switched-on tool, plus fixed actions.
let paletteDisposers = []
async function registerPalette(ctx) {
  let all = []
  try {
    all = (await rest('/toolbox')).tools || []
  } catch {
    return
  }
  const tools = all.filter(t => t.on && t.surfaces && t.surfaces.includes('palette'))
  const on = id => all.some(t => t.id === id && t.on)
  paletteDisposers.forEach(d => d())
  paletteDisposers = tools.map(t => ctx.register({ id: `open-${t.id}`, area: PALETTE_AREA, data: { id: `${ID}.open.${t.id}`, label: `Eselsbrücke: ${t.title}`, run: () => openTool(t.id) } }))
  if (tools.some(t => t.id === 'pad')) paletteDisposers.push(ctx.register({ id: 'palette-pad-add', area: PALETTE_AREA, data: { id: `${ID}.pad.add`, label: "Eselsbrücke: add a line to today's pad", run: () => openTool('pad', { focusAdd: true }) } }))
  if (tools.some(t => t.id === 'generate')) paletteDisposers.push(ctx.register({ id: 'uuid-copy', area: PALETTE_AREA, data: { id: `${ID}.uuid.copy`, label: 'Eselsbrücke: copy a new UUID', run: copyUuid } }))
  if (on('pomodoro')) paletteDisposers.push(ctx.register({ id: 'pomodoro-start', area: PALETTE_AREA, data: { id: `${ID}.pomodoro.start`, label: 'Eselsbrücke: start a pomodoro', run: () => timerAction({ op: 'start', kind: 'pomodoro' }) } }))
  paletteDisposers.push(ctx.register({ id: 'beside', area: PALETTE_AREA, data: { id: `${ID}.beside`, label: 'Eselsbrücke: open the toolbox beside the chat', run: openBeside } }))
}

export default {
  id: ID,
  name: 'Eselsbrücke',
  description: "The helper toolbox: today's pad, pomodoro, time log, formatter, colour, diff, regex, tokens, time zones, encode, generators, cron, QR.",
  register(ctx) {
    setCtx(ctx)
    setOpenBeside(openBeside)
    if (typeof ctx.onDispose === 'function') ctx.onDispose(closeBesideOnDispose)
    refreshOutbox()
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: PATH }, render: () => jsx(Page, {}) })
    ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Toolbox', codicon: 'tools' } })
    ctx.register({ id: 'chip', area: STATUSBAR_AREAS.right, render: () => jsx(Chip, { onBeside: openBeside }) })
    ctx.register({ id: 'open', area: KEYBINDS_AREA, data: { id: `${ID}.open`, label: 'Eselsbrücke: open the toolbox', defaults: ['mod+shift+e'], run: () => openTool(storage.get('lastTool', 'pad')) } })
    ctx.register({ id: 'pad-add', area: KEYBINDS_AREA, data: { id: `${ID}.pad.add`, label: "Eselsbrücke: add to today's pad", defaults: ['mod+alt+p'], run: () => openTool('pad', { focusAdd: true }) } })
    if (typeof ctx.registerSettingsPage === 'function') {
      ctx.registerSettingsPage({ id: 'toolbox', title: 'Toolbox', icon: 'tools', render: () => jsx(SettingsPage, {}) })
    }
    registerPalette(ctx)
    if (typeof ctx.setInterval === 'function') ctx.setInterval(() => registerPalette(ctx), 300000)
    startLive(ctx)
    reconcileOnOpen()
    log('registered page, sidebar row, settings page, chip, palette, keybinds mod+shift+e and mod+alt+p')
  },
}
