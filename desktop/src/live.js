// What runs while Desktop is open, outside any page: the timer and time-log state the chip shows,
// the heartbeat (POST /presence every 60 s, so the alert tick stays silent while Desktop alerts), the
// Desktop's own alerts (phase ends and pad reminders, computed from the last record, so they keep
// coming while the backend is unreachable), and the outbox replay when /health answers again.
import { atom } from '@hermes/plugin-sdk'

import { $connection, alertBoth, getCtx, log, post, profileNow, rest, storage, uuid7 } from './core.js'
import { readOutbox, refreshOutbox, replayOutbox, sendOrQueue } from './outbox.js'
import { alertText, applyLocal, dueEvents, pomodoroPlan } from './timer.js'

export const $timer = atom(null) // the timer record (server's, or the local one while ops wait)
export const $tip = atom(null)
export const $running = atom(null) // the running time-log entry
export const $reminders = atom([]) // today's open reminder lines
export const $rhythm = atom({ work: 25, short: 5, long: 15, cycles: 4 })
export const $tick = atom(Date.now()) // one clock for every chip and dial, every 5 s

let lastProfile = null

export async function refreshTimer() {
  try {
    const out = await rest('/timer')
    if (!readOutbox().some(i => i.kind === 'timer')) $timer.set(out.timer || null)
    $tip.set(out.tip || null)
  } catch (error) {
    if (!error.network) $timer.set(null)
  }
}

export async function refreshRunning() {
  try {
    const out = await rest('/timelog')
    $running.set(out.week && out.week.running ? out.week.running : null)
  } catch (error) {
    if (!error.network) $running.set(null)
  }
}

/** Replay the outbox, then read the timer and the running entry back from the backend. */
export const replayAndRefresh = () => replayOutbox().then(() => Promise.all([refreshTimer(), refreshRunning()]))

async function refreshReminders() {
  try {
    const out = await rest('/pad')
    const lines = (out.day && out.day.lines) || []
    // remind_at is wall time in Hermes' zone; carry that zone's offset so the Mac reads the same instant
    const off = ((out.time_zone && out.time_zone.offset) || '+0000').replace(/^([+-]\d{2})(\d{2})$/, '$1:$2')
    $reminders.set(lines.filter(l => l.kind === 'reminder' && !l.done && l.remind_at).map(l => ({ ...l, at_ms: Date.parse(`${l.remind_at}:00${off}`) })))
  } catch (error) {
    if (!error.network) $reminders.set([])
  }
}

async function refreshRhythm() {
  try {
    const out = await rest('/toolbox')
    if (out.toolbox && out.toolbox.pomodoro) $rhythm.set(out.toolbox.pomodoro)
  } catch {
    // keep the last rhythm
  }
}

/** A timer click from any surface: sent at once, or kept in the outbox with its click time while the
 *  chip goes on counting from the local record. A refusal (409, 400) is shown as a toast and returned
 *  as { ok: false, error }; it never throws, so no button or palette row swallows it. */
export async function timerAction(body) {
  const r = $rhythm.get()
  const op = { ...body }
  if (op.op === 'start' && (op.kind || 'pomodoro') === 'pomodoro' && !op.plan) op.plan = pomodoroPlan(r.work, r.short, r.long, r.cycles)
  let sent
  try {
    sent = await sendOrQueue('timer', op)
  } catch (error) {
    alertBoth('Eselsbrücke', error.message, 'warning')
    return { ok: false, error }
  }
  if (sent.queued) {
    const stamped = readOutbox().filter(i => i.kind === 'timer').slice(-1)[0]
    $timer.set(applyLocal($timer.get(), stamped ? stamped.op : op, op.plan))
    if (!sent.behind) alertBoth('Eselsbrücke', 'Not connected to Hermes: the timer keeps counting here and syncs when the connection is back.', 'warning')
  } else if (sent.replayed) {
    await Promise.all([refreshTimer(), refreshRunning()])
  } else {
    $timer.set(sent.result.timer || null)
    $tip.set(sent.result.tip || null)
    if (sent.result.ended && sent.result.timelog) refreshRunning()
  }
  return sent
}

/** A time-log click (start, stop, add): like timerAction, a refusal is a toast, never a throw. */
export async function timelogAction(input) {
  // a start carries its own entry id, so a stop made offline after it names the same entry on replay
  const body = input.op === 'start' && !input.entry_id ? { ...input, entry_id: `e${uuid7().replace(/-/g, '').slice(-12)}` } : input
  let sent
  try {
    sent = await sendOrQueue('timelog', body)
  } catch (error) {
    alertBoth('Eselsbrücke', error.message, 'warning')
    return { ok: false, error }
  }
  if (sent.queued) {
    if (body.op === 'start') $running.set({ id: body.entry_id, client: body.fields.client, project: body.fields.project || '', start: new Date().toISOString(), running: true, local: true })
    if (body.op === 'stop') $running.set(null)
    if (!sent.behind) alertBoth('Eselsbrücke', 'Not connected to Hermes: the time-log change is kept and syncs when the connection is back.', 'warning')
  } else if (sent.replayed) {
    await refreshRunning()
  } else {
    $running.set(sent.result.week && sent.result.week.running ? sent.result.week.running : null)
  }
  return sent
}

// --- Desktop alerts ---------------------------------------------------------------------------------

const alertedKey = () => `alerted:${profileNow()}`
function alreadyAlerted(key) {
  const list = storage.get(alertedKey(), [])
  if (list.includes(key)) return true
  storage.set(alertedKey(), [...list, key].slice(-200))
  return false
}

// The alert loop ticks every 5 s. A phase end older than this window was missed (the Mac slept, or
// App Nap held the loop): those collapse into one "while you were away" alert for the newest of them,
// instead of one toast per phase end in the gap.
export const ALERT_WINDOW_MS = 15000

let since = Date.now()
export function checkAlerts(now = Date.now(), from = since) {
  since = now
  const t = $timer.get()
  if (t) {
    const fresh = []
    const missed = []
    for (const ev of dueEvents(t, from, now)) {
      if (alreadyAlerted(ev.key)) continue
      if (ev.at < now - ALERT_WINDOW_MS) missed.push(ev)
      else fresh.push(ev)
    }
    if (missed.length && !fresh.length) {
      const last = missed[missed.length - 1]
      const { title, body } = alertText(last)
      const at = new Date(last.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      const more = missed.length > 1 ? `, the last of ${missed.length} phase ends` : ''
      alertBoth(`Eselsbrücke: ${title}`, `While you were away (at ${at}${more}): ${body}`)
    }
    for (const ev of fresh) {
      const { title, body } = alertText(ev)
      alertBoth(`Eselsbrücke: ${title}`, body)
    }
  }
  for (const line of $reminders.get()) {
    const at = line.at_ms
    if (!(from < at && at <= now)) continue
    if (alreadyAlerted(`${line.id}:${line.remind_at}`)) continue
    alertBoth('Eselsbrücke reminder', line.text)
  }
}

export function startLive(ctx) {
  const every = (fn, ms) => (typeof ctx.setInterval === 'function' ? ctx.setInterval(fn, ms) : null)
  const beat = async () => {
    try {
      await post('/presence', {})
    } catch {
      // offline: the tick takes over after 90 s
    }
  }
  const sync = async () => {
    const profile = profileNow()
    if (profile !== lastProfile) {
      lastProfile = profile
      refreshOutbox()
      $timer.set(null)
    }
    if (readOutbox().length) {
      const r = await replayOutbox()
      if (r.sent) log('outbox replayed', r)
    }
    await Promise.all([refreshTimer(), refreshRunning(), refreshReminders(), refreshRhythm()])
  }
  sync()
  beat()
  every(sync, 30000)
  every(beat, 60000)
  every(() => {
    $tick.set(Date.now())
    checkAlerts()
  }, 5000)
  if (typeof ctx.addEventListener === 'function') ctx.addEventListener(window, 'online', () => sync())
  $connection.listen(state => {
    if (state === 'ok' && readOutbox().length) replayAndRefresh()
  })
  log('live loop started')
  return getCtx()
}
