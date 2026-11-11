// Eselsbrücke Desktop half: the backend door, connection state and small shared helpers.
// Every call goes to this plugin's own routes (`ctx.rest`, `/api/plugins/eselsbruecke/...`) on the
// user's Hermes backend; nothing here reaches any other host (PLAN constraint 5).
import { atom, host } from '@hermes/plugin-sdk'

export const ID = 'eselsbruecke'
// This Desktop half's version, written in by the build (desktop/build/build.mjs); 'dev' in a bundle made without it.
export const VERSION = typeof __ESB_VERSION__ === 'string' ? __ESB_VERSION__ : 'dev'
export const PATH = '/eselsbruecke'

/** -1, 0 or 1: two dotted versions by their numbers, so 0.10.0 is newer than 0.9.2. */
export function compareVersions(a, b) {
  const parts = v => String(v).split(/[.+-]/).map(n => parseInt(n, 10) || 0)
  const [x, y] = [parts(a), parts(b)]
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) < (y[i] || 0) ? -1 : 1
  }
  return 0
}

/** One line when the two halves are different versions, naming the side to update; else null.
 *  Desktop loads its half from this computer and Hermes its half from the server, so an update of
 *  one leaves the other behind. `server` is /health's version. */
export function versionNote(server, desktop = VERSION) {
  if (!server || !desktop || desktop === 'dev') return null
  const order = compareVersions(desktop, server)
  if (!order) return null
  return `Eselsbrücke is ${desktop} on this computer and ${server} on your Hermes server. Update Eselsbrücke ${order < 0 ? 'on this computer' : 'on your Hermes server'}.`
}

/** The calendar day it is at `now` at the UTC offset an ISO time carries. The backend writes its times
 *  in Hermes' zone, which this computer may not share, so "today" is read there. */
export function dayAt(iso, now = Date.now()) {
  const m = /([+-])(\d{2}):?(\d{2})$/.exec(String(iso || ''))
  const minutes = m ? (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) : 0
  return new Date(now + minutes * 60000).toISOString().slice(0, 10)
}

let pluginCtx = null
export const setCtx = ctx => {
  pluginCtx = ctx
}
export const getCtx = () => pluginCtx

export const log = (...args) => console.info(`[${ID}]`, ...args)

// 'unknown' until the first call, 'ok' after a 2xx, 'offline' after a network error (Desktop cannot
// reach the backend), 'off' after 404 "Plugin not found" (the plugin is not on in this profile).
export const $connection = atom('unknown')

export const NOT_ON_TEXT = 'Eselsbrücke is not on in this profile.'
export const OFFLINE_TEXT = 'Not connected to Hermes. Showing what was loaded last.'

// ctx.rest rejects on HTTP >= 400 with "<status>: <body>" somewhere in the message (Electron adds a
// prefix). Recover the status and the JSON body; anything without a status is a network error.
export function restError(error) {
  const message = error && error.message ? String(error.message) : String(error)
  const found = message.match(/\b([1-5]\d\d): ([\s\S]*)$/)
  const status = found ? Number(found[1]) : error && error.statusCode ? Number(error.statusCode) : 0
  let body = null
  const raw = found ? found[2] : message
  const start = raw.indexOf('{')
  if (start >= 0) {
    try {
      body = JSON.parse(raw.slice(start))
    } catch {
      body = null
    }
  }
  if (body && body.detail && !body.message) body.message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
  const notOn = status === 404 && /plugin not found/i.test((body && body.message) || raw)
  const out = new Error(notOn ? NOT_ON_TEXT : (body && body.message) || raw || 'Request failed')
  out.status = status
  out.body = body
  out.network = !status
  out.notOn = notOn
  return out
}

export async function rest(path, opts) {
  if (!pluginCtx || typeof pluginCtx.rest !== 'function') throw new Error('ctx.rest is not available in this Desktop build')
  try {
    const out = await pluginCtx.rest(path, { timeoutMs: 30000, ...(opts || {}) })
    if ($connection.get() !== 'ok') $connection.set('ok')
    return out
  } catch (error) {
    const out = restError(error)
    if (out.network) $connection.set('offline')
    else if (out.notOn) $connection.set('off')
    else if ($connection.get() !== 'ok') $connection.set('ok')
    log('rest', (opts && opts.method) || 'GET', path, 'failed', { status: out.status, message: out.message })
    throw out
  }
}

export const post = (path, body, opts) => rest(path, { method: 'POST', body, ...(opts || {}) })

/** The profile the gateway socket is bound to: the one whose backend `ctx.rest` reaches. */
export const profileNow = () => host.state.profile.get() || 'default'

export const qk = (profile, ...rest) => [ID, profile, ...rest]

export const storage = {
  get: (key, fallback) => (pluginCtx && pluginCtx.storage ? pluginCtx.storage.get(key, fallback) : fallback),
  set: (key, value) => pluginCtx && pluginCtx.storage && pluginCtx.storage.set(key, value),
}

/** Every Desktop alert goes out twice (constraint 17): the in-app toast, always shown, and the OS
 *  notification, which Desktop shows only while Hermes is in the background. */
export function alertBoth(title, body, kind = 'info') {
  try {
    host.notify({ kind, title, message: body || title })
  } catch (error) {
    log('notify failed', String(error))
  }
  try {
    if (pluginCtx && pluginCtx.os && typeof pluginCtx.os.notify === 'function') pluginCtx.os.notify({ title, body: body || undefined, activate: PATH })
  } catch (error) {
    log('os.notify failed', String(error))
  }
}

export const pad2 = n => String(n).padStart(2, '0')
export const isoLocal = (d = new Date()) => {
  const off = -d.getTimezoneOffset()
  const sign = off >= 0 ? '+' : '-'
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}${sign}${pad2(Math.floor(Math.abs(off) / 60))}:${pad2(Math.abs(off) % 60)}`
}

export { uuid4, uuid7 } from './ids.js'
