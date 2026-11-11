// sidebar-row v1 begin
// The plugin's sidebar row: its brand as the label (plus an optional count), a show switch and a
// position, kept per Desktop in ctx.storage under 'sidebar' as { show, position }. One source:
// templates/plugin-skeleton/desktop/sidebar-row.js. Every copy (desktop/src/sidebar-row.js in a
// built plugin, the marked block in a single-file desktop/plugin.js) must equal it between these
// markers; tests/test_sidebar_row.py fails one that differs. Change the template, then copy it.
// Import-free: the plugin passes the SDK names in `sdk`:
//   { SIDEBAR_NAV_AREA, Switch, Input, jsx, jsxs, atom, useValue }
const SIDEBAR_ROW_KEY = 'sidebar'
const SIDEBAR_ROW_MIN = 1
const SIDEBAR_ROW_MAX = 99

/** An integer from 1 to 99, or `fallback` when `value` is not a number. */
function sidebarRowPosition(value, fallback) {
  if (value === null || value === undefined || value === '') return fallback
  const n = Math.round(Number(value))
  if (!Number.isFinite(n)) return fallback
  return Math.min(SIDEBAR_ROW_MAX, Math.max(SIDEBAR_ROW_MIN, n))
}

/** The row's label: the brand, plus " · N" while N is above 0 ("99+" from 100). */
function sidebarRowLabel(brand, count) {
  const n = Math.floor(Number(count) || 0)
  return n > 0 ? `${brand} · ${n < 100 ? n : '99+'}` : brand
}

/** Register the row from this Desktop's stored choice (nothing stored: shown, at defaultPosition).
 *  No backend read, so the row paints in its place with the first frame. Every change disposes the
 *  held contribution before it registers again: Desktop's registry replaces an entry by id, and an
 *  older disposer would then remove the new entry. */
function startSidebarRow(ctx, { brand, path, codicon, defaultPosition, sdk }) {
  const store = ctx.storage || { get: (key, fallback) => fallback, set: () => {} }
  const fallback = sidebarRowPosition(defaultPosition, 50)
  const stored = store.get(SIDEBAR_ROW_KEY, null)
  const saved = stored && typeof stored === 'object' ? stored : {}
  const $prefs = sdk.atom({ show: saved.show !== false, position: sidebarRowPosition(saved.position, fallback) })
  let count = 0
  let disposeRow = null
  let stopped = false

  const drop = () => {
    const dispose = disposeRow
    disposeRow = null
    if (dispose) dispose()
  }
  const apply = () => {
    drop()
    const { show, position } = $prefs.get()
    if (stopped || !show) return
    disposeRow = ctx.register({ id: 'nav', area: sdk.SIDEBAR_NAV_AREA, order: position, data: { codicon, label: sidebarRowLabel(brand, count), path } })
  }
  apply()

  return {
    brand,
    $prefs,
    prefs: () => $prefs.get(),
    /** A new count relabels a shown row; a hidden row stays hidden and shows the count when shown. */
    setCount(n) {
      const next = Math.max(0, Math.floor(Number(n) || 0))
      const relabel = sidebarRowLabel(brand, next) !== sidebarRowLabel(brand, count)
      count = next
      if (relabel && $prefs.get().show) apply()
    },
    /** Store { show, position } (either may be left out), then show, hide or move the row at once. */
    setPrefs(patch) {
      const now = $prefs.get()
      const p = patch && typeof patch === 'object' ? patch : {}
      const next = {
        show: 'show' in p ? p.show !== false : now.show,
        position: sidebarRowPosition(p.position, now.position),
      }
      if (next.show === now.show && next.position === now.position) return now
      store.set(SIDEBAR_ROW_KEY, next)
      $prefs.set(next)
      apply()
      return next
    },
    /** Remove the row for good (the plugin's own unload runs Desktop's disposers anyway). */
    dispose() {
      stopped = true
      drop()
    },
  }
}

/** The "Sidebar" block of the plugin's settings page: SDK Switch and Input, nothing else. */
function SidebarSection({ row, sdk }) {
  const { jsx, Switch, Input } = sdk
  const jsxs = sdk.jsxs || sdk.jsx
  const prefs = sdk.useValue(row.$prefs)
  const line = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, minHeight: 32 }
  const note = { margin: 0, fontSize: '0.75rem', color: 'var(--ui-text-secondary)' }
  const commit = event => {
    const next = row.setPrefs({ position: event.target.value })
    event.target.value = String(next.position)
  }
  return jsxs('section', {
    'data-sidebar-section': row.brand,
    style: { display: 'grid', gap: 6, margin: '12px 0', padding: '10px 12px', border: '1px solid var(--ui-stroke-tertiary)', borderRadius: 8 },
    children: [
      jsx('h3', { style: { margin: 0, fontSize: '0.8125rem', fontWeight: 600 }, children: 'Sidebar' }, 'title'),
      jsxs('div', { style: line, children: [
        jsx('span', { children: 'Show in the sidebar' }),
        jsx(Switch, { checked: prefs.show, 'aria-label': 'Show in the sidebar', onCheckedChange: on => row.setPrefs({ show: on }) }),
      ] }, 'show'),
      jsxs('div', { style: line, children: [
        jsx('span', { children: 'Position' }),
        jsx(Input, {
          type: 'number', min: SIDEBAR_ROW_MIN, max: SIDEBAR_ROW_MAX, step: 1, inputMode: 'numeric',
          'aria-label': 'Position', defaultValue: String(prefs.position), style: { width: 72 },
          onBlur: commit,
          onKeyDown: event => { if (event.key === 'Enter') commit(event) },
        }, String(prefs.position)),
      ] }, 'position'),
      jsx('p', { style: note, children: 'Lower numbers sit higher. Kanban is 50.' }, 'hint'),
      prefs.show ? null : jsx('p', { style: note, children: `Open it from the command palette: Open ${row.brand}.` }, 'hidden'),
    ],
  })
}
// sidebar-row v1 end

export { SidebarSection, sidebarRowLabel, sidebarRowPosition, startSidebarRow }
