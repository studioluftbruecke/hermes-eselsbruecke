// The outbox (A16): a time-log or timer click that fails with a network error is kept in
// ctx.storage under `outbox:<profile>` (the profile at the click; ctx.storage is one store for the
// whole app) with a UUID v7 op id and the click time, shown as "n not synced" on the chip, and
// replayed in order through /timelog/ops and /timer when /health answers again while that profile
// is active.
//
// Order is the rule, per kind: while the outbox holds ops of a kind, a new click of that kind is
// queued behind them and the replay starts at once, so it cannot overtake them. Each kind replays from
// its own oldest op, so a stuck time-log op never holds back a timer click (N3). Storage is the one
// list: the replay reads it again before each op and removes what it sent by op_id, so a click queued
// during a replay stays. The backend's answer decides an op's fate:
//   - network error, or 404 (the plugin is not on): kept, the whole replay stops, nothing is counted
//   - 5xx, 408, 429: kept, the try is counted with the error, that kind stops for this replay
//   - any other 4xx (400, 409, ...): a refusal; dropped with a toast that names it
//   - 2xx (applied or duplicate): dropped
// An op that failed MAX_TRIES times or has waited longer than MAX_AGE_MS is stuck: the replay no
// longer sends it or anything of its kind behind it, and the chip's popover shows it with "Try again"
// and "Discard". "Try again" lets it go out once more whatever its age (N1): the server dedupes by
// op_id and checks the click time, so a refusal drops it with a toast as usual.
import { atom } from '@hermes/plugin-sdk'

import { alertBoth, isoLocal, log, post, profileNow, rest, storage, uuid7 } from './core.js'

export const MAX_TRIES = 5
export const MAX_AGE_MS = 24 * 3600 * 1000

const key = profile => `outbox:${profile}`
export const $outbox = atom([])

export const readOutbox = (profile = profileNow()) => storage.get(key(profile), [])

function write(profile, ops) {
  storage.set(key(profile), ops)
  if (profile === profileNow()) $outbox.set(ops)
}

/** One synchronous read-modify-write of the stored list (no await in between). */
const update = (profile, fn) => write(profile, fn(readOutbox(profile)))
const append = (profile, item) => update(profile, ops => (ops.some(i => i.op.op_id === item.op.op_id) ? ops : [...ops, item]))
const removeOp = (profile, opId) => update(profile, ops => ops.filter(i => i.op.op_id !== opId))
const patchOp = (profile, opId, fn) => update(profile, ops => ops.map(i => (i.op.op_id === opId ? fn(i) : i)))

export const refreshOutbox = () => $outbox.set(readOutbox())

/** Stamp a click: the op id and the click time travel with it, online or not. */
export const stamp = body => ({ ...body, op_id: body.op_id || uuid7(), at: body.at || isoLocal() })

/** Why an op no longer replays by itself ('tries' or 'age'), or null. A "Try again" (`retry`) lifts
 *  the age for one send. */
export function stuckReason(item, now = Date.now()) {
  if ((item.tries || 0) >= MAX_TRIES) return 'tries'
  if (!item.retry && now - (item.queuedAt || now) > MAX_AGE_MS) return 'age'
  return null
}

/** The oldest op of each kind, in outbox order: each is where its kind's replay starts. */
const heads = ops => ops.filter((i, n) => ops.findIndex(j => j.kind === i.kind) === n)

/** The oldest kind head that no longer syncs by itself, or null. */
const stuckHead = (ops, now = Date.now()) => heads(ops).find(i => stuckReason(i, now)) || null

const kindName = item => (item.kind === 'timelog' ? 'time-log' : 'timer')
const what = item => `${kindName(item)} ${item.op.op}`

/** What the chip shows: how many ops wait, and the oldest stuck one (any kind) when there is one. */
export function outboxStatus(now = Date.now(), profile = profileNow()) {
  const ops = readOutbox(profile)
  const head = stuckHead(ops, now)
  const reason = head ? stuckReason(head, now) : null
  return { count: ops.length, stuck: reason ? { reason, kind: head.kind, op: head.op, tries: head.tries || 0, error: head.error || null, queuedAt: head.queuedAt } : null }
}

/** "Try again" in the chip: the stuck op starts over and goes out once more, whatever its age. */
export function retryOutbox(profile = profileNow()) {
  const ops = readOutbox(profile)
  const head = stuckHead(ops) || ops[0]
  if (head) patchOp(profile, head.op.op_id, i => ({ ...i, tries: 0, error: null, retry: true }))
}

/** "Discard" in the chip: the stuck op leaves the outbox, so the ones of its kind behind it can replay. */
export function discardOutboxHead(profile = profileNow()) {
  const ops = readOutbox(profile)
  const head = stuckHead(ops) || ops[0]
  if (!head) return
  removeOp(profile, head.op.op_id)
  log('discarded from the outbox', head.kind, head.op.op, head.op.op_id)
}

const send = (kind, op) => (kind === 'timer' ? post('/timer', op) : post('/timelog', { ...op, source: op.source || 'page' }))

/**
 * Send a timer or time-log op; on a network error keep it. `kind` is 'timer' or 'timelog'.
 * While the outbox holds ops of that kind, the op goes behind them and the replay runs at once:
 * `replayed` when it went out with them, `queued` when it still waits; when it waits behind a stuck
 * op of its kind, a toast names that op. A refusal is thrown.
 * Returns { ok, queued, replayed, result }.
 */
export async function sendOrQueue(kind, body) {
  const profile = profileNow()
  const op = stamp(body)
  if (readOutbox(profile).some(i => i.kind === kind)) {
    append(profile, { kind, op, queuedAt: Date.now() })
    log('queued behind the outbox', kind, op.op, op.op_id)
    await replayOutbox()
    const left = readOutbox(profile)
    if (!left.some(i => i.op.op_id === op.op_id)) return { ok: true, queued: false, replayed: true, result: null }
    const head = left.find(i => i.kind === kind)
    if (head && head.op.op_id !== op.op_id && stuckReason(head)) {
      const when = head.op.at ? new Date(head.op.at).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : ''
      alertBoth('Eselsbrücke', `This click waits behind an older ${what(head)}${when ? ` (${when})` : ''} that no longer syncs by itself. Open the status-bar chip to Try again or Discard it.`, 'warning')
    }
    return { ok: false, queued: true, behind: true }
  }
  try {
    return { ok: true, queued: false, result: await send(kind, op) }
  } catch (error) {
    if (error.network) {
      append(profile, { kind, op, queuedAt: Date.now() })
      log('queued in the outbox', kind, op.op, op.op_id)
      return { ok: false, queued: true, error }
    }
    throw error
  }
}

let replaying = false

const waitsForBackend = error => error.network || error.status === 404
const retryable = error => error.status >= 500 || error.status === 408 || error.status === 429

/** Replay the active profile's outbox, each kind in its own order. A kind stops at its first op that
 *  has to wait; a backend that does not answer stops them all. */
export async function replayOutbox() {
  const profile = profileNow()
  if (!readOutbox(profile).length || replaying) return { sent: 0, left: readOutbox(profile).length }
  replaying = true
  let sent = 0
  const halted = new Set() // kinds that wait until the next replay
  try {
    await rest('/health')
    for (;;) {
      if (profileNow() !== profile) break
      // only whole kinds halt, so the first op of a kind still running is that kind's oldest
      const item = readOutbox(profile).find(i => !halted.has(i.kind))
      if (!item) break
      if (stuckReason(item)) {
        halted.add(item.kind)
        continue
      }
      try {
        if (item.kind === 'timelog') {
          const out = await post('/timelog/ops', { ops: [item.op] })
          const r = (out.results || [])[0] || {}
          if (r.error) alertBoth('Eselsbrücke', `A time-log change made offline was refused: ${r.message || r.error}`, 'warning')
        } else {
          await post('/timer', item.op)
        }
      } catch (error) {
        if (waitsForBackend(error)) break
        if (retryable(error)) {
          // a "Try again" was this op's one send: an old op is stuck by age again
          patchOp(profile, item.op.op_id, i => ({ ...i, tries: (i.tries || 0) + 1, error: `${error.status}: ${error.message}`, retry: false }))
          log('outbox op kept after', error.status, item.kind, item.op.op, item.op.op_id)
          halted.add(item.kind)
          continue
        }
        alertBoth('Eselsbrücke', `A ${kindName(item)} change made offline was refused: ${error.message}`, 'warning')
      }
      removeOp(profile, item.op.op_id)
      sent += 1
    }
    return { sent, left: readOutbox(profile).length }
  } catch {
    return { sent, left: readOutbox(profile).length }
  } finally {
    replaying = false
  }
}
