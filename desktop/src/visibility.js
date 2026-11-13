// The status-bar chip's place in Desktop's frame. "Show in status bar" on the settings page is the
// toolbox's layout.chip_visible: while it is on, the chip is registered as a status-bar *data* item
// with a stable id and toggleLabel 'Eselsbrücke', so Desktop's right-click menu on the bar lists it
// too; while it is off, the item is disposed and nothing is registered.
//
// Desktop keeps its right-click choice by `data.id`, which the plugin context does not prefix, so the
// id carries the plugin's name itself. A data item gets no Desktop ContribBoundary, so the chip is
// wrapped in its own (chip.js Boundary).
//
// The layout seen last for the profile (ctx.storage `chipLayout:<profile>`) decides at start and on a
// profile switch until the toolbox answers, so a chip the user hid does not flash at every start or
// while Hermes is unreachable. After that every toolbox answer in React Query's cache applies (a save
// on the settings page lands at once), and the toolbox is read again when the window gains focus and
// every 60 s, so a change made by the agent shows without opening the page. A failed read changes
// nothing.
import { host, queryClient, STATUSBAR_AREAS } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

import { Boundary, Chip, chipLayout, chipLayoutKey } from './chip.js'
import { ID, log, profileNow, qk, rest, storage } from './core.js'

export const POLL_MS = 60000
export const CHIP_ITEM_ID = `${ID}.chip`
export const BRAND = 'Eselsbrücke'

let ctxRef = null
let onBesideRef = null
let disposeChip = null
let stops = []

export const chipShown = () => !!disposeChip

function applyChip(show) {
  if (show && !disposeChip) {
    const onBeside = onBesideRef
    disposeChip = ctxRef.register({ id: 'chip', area: STATUSBAR_AREAS.right,
      data: { id: CHIP_ITEM_ID, toggleLabel: BRAND, render: () => jsx(Boundary, { children: jsx(Chip, { onBeside }) }) } })
  } else if (!show && disposeChip) {
    disposeChip()
    disposeChip = null
  }
}

const isToolboxKey = key => Array.isArray(key) && key.length === 3 && key[0] === ID && key[2] === 'toolbox'

/** A /toolbox answer for `profile`: keep its layout as the one seen last, and show or remove the chip
 *  when it is the profile Desktop is on. */
export function applyToolbox(profile, data) {
  if (!ctxRef || !data || !data.toolbox) return
  const layout = chipLayout(data.toolbox.layout)
  storage.set(chipLayoutKey(profile), layout)
  if (profile === profileNow()) applyChip(layout.chip_visible)
}

/** Read the toolbox once through React Query (an answer up to 30 s old is reused) and apply it.
 *  Returns whether the chip is registered, or null after a failed read (nothing changed). */
export async function readVisibility() {
  if (!ctxRef) return null
  const profile = profileNow()
  try {
    const data = await queryClient.fetchQuery({ queryKey: qk(profile, 'toolbox'), queryFn: () => rest('/toolbox'), staleTime: 30000 })
    applyToolbox(profile, data)
    return chipShown()
  } catch (error) {
    log('toolbox read failed; status-bar chip unchanged', error.message)
    return null
  }
}

/** Show the chip as the layout seen last says, then follow the toolbox. `onBeside` opens the pane. */
export function startVisibility(ctx, onBeside) {
  ctxRef = ctx
  onBesideRef = onBeside
  applyChip(chipLayout(storage.get(chipLayoutKey(profileNow()), null)).chip_visible)
  stops.push(queryClient.getQueryCache().subscribe(event => {
    if (event.type !== 'updated' || !event.action || event.action.type !== 'success') return
    const key = event.query.queryKey
    if (isToolboxKey(key)) applyToolbox(key[1], event.query.state.data)
  }))
  stops.push(host.state.profile.listen(() => {
    applyChip(chipLayout(storage.get(chipLayoutKey(profileNow()), null)).chip_visible)
    readVisibility()
  }))
  readVisibility()
  if (typeof ctx.setInterval === 'function') ctx.setInterval(readVisibility, POLL_MS)
  if (typeof ctx.addEventListener === 'function' && typeof window !== 'undefined') ctx.addEventListener(window, 'focus', () => readVisibility())
}

export function stopVisibility() {
  stops.forEach(stop => stop())
  stops = []
  if (disposeChip) disposeChip()
  disposeChip = null
  onBesideRef = null
  ctxRef = null
}
