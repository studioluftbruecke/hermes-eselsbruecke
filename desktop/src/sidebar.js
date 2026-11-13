/**
 * The Eselsbrücke sidebar row: started in register(), its "Sidebar" block drawn on the settings page.
 * The row itself is the shared module (sidebar-row.js, a byte-identical copy of the template; never
 * edit it here). Position 51, the first plugin row below Kanban (the studio's plugins share one order).
 */
import { atom, Input, SIDEBAR_NAV_AREA, Switch, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

import { PATH } from './core.js'
import { SidebarSection, startSidebarRow } from './sidebar-row.js'

const SDK = { SIDEBAR_NAV_AREA, Switch, Input, jsx, jsxs, atom, useValue }
let row = null

export function startRow(ctx) {
  row = startSidebarRow(ctx, { brand: 'Eselsbrücke', path: PATH, codicon: 'tools', defaultPosition: 51, sdk: SDK })
  return row
}

/** The settings block; nothing until register() has started the row. */
export function SidebarBlock() {
  return row ? jsx(SidebarSection, { row, sdk: SDK }) : null
}
