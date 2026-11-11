// Small UI helpers and the shared queries (toolbox, timer, time log) every surface reads.
import { atom, host, useQuery, useQueryClient, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

import { $connection, alertBoth, getCtx, NOT_ON_TEXT, OFFLINE_TEXT, post, profileNow, qk, rest, storage } from './core.js'

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

export function Copy({ text, label = 'Copy' }) {
  const [done, setDone] = useState(false)
  return h(Btn, {
    disabled: !text,
    onClick: async () => {
      let ok = false
      try {
        const ctx = getCtx()
        ok = ctx && ctx.os ? await ctx.os.writeClipboard(text) : false
        if (!ok) {
          await navigator.clipboard.writeText(text)
          ok = true
        }
      } catch {
        ok = false
      }
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

export function useToolboxSave() {
  const client = useQueryClient()
  const profile = useProfile()
  return async body => {
    try {
      const out = await post('/toolbox', body)
      client.setQueryData(qk(profile, 'toolbox'), out)
      return out
    } catch (error) {
      if (error.status === 409 && error.body && error.body.current) client.setQueryData(qk(profile, 'toolbox'), error.body.current)
      alertBoth('Eselsbrücke', error.message, 'warning')
      throw error
    }
  }
}

export const isOn = (toolbox, id) => {
  const t = toolbox && toolbox.tools && toolbox.tools.find(x => x.id === id)
  return t ? t.on : true
}

// The tool the page shows; the palette, the keybinds and the chip set it before they navigate.
export const $tool = atom(null)
export const $focusPadAdd = atom(0)

export function openTool(id, opts = {}) {
  $tool.set(id)
  storage.set('lastTool', id)
  if (id === 'pad' && opts.focusAdd) $focusPadAdd.set($focusPadAdd.get() + 1)
  const beside = opts.beside ?? storage.get('openBeside', false)
  if (beside && openBesideHook) openBesideHook()
  else host.navigate('/eselsbruecke')
}

let openBesideHook = null
export const setOpenBeside = fn => {
  openBesideHook = fn
}

export const profileKey = () => profileNow()
