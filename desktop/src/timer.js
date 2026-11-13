// Pomodoro and countdown phases in the Desktop: a pure function of the timer record (start, plan,
// pauses) and the clock, the same rule as timers.py, so the chip counts and alerts without the
// backend. tests/test_desktop_parity.mjs runs the fixtures' timer cases through it.

export const PHASE_TITLES = { work: 'Work', short: 'Break', long: 'Long break', countdown: 'Countdown' }

const ms = v => new Date(v).getTime()

export function pomodoroPlan(work = 25, short = 5, long = 15, cycles = 4) {
  const plan = []
  for (let i = 0; i < cycles; i++) {
    plan.push({ phase: 'work', minutes: work })
    const last = i === cycles - 1
    plan.push({ phase: last ? 'long' : 'short', minutes: last ? long : short })
  }
  return plan
}

const pauses = t => (t.paused || []).map(([a, b]) => [ms(a), b ? ms(b) : null])

/** Hours as h:mm, rounded to the minute first (1.995 h is 2:00, never 1:60). */
export function hoursLabel(hours) {
  const minutes = Math.round(hours * 60)
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`
}

export function elapsedS(t, now) {
  const start = ms(t.started)
  const end = t.ended ? ms(t.ended) : now
  let total = (end - start) / 1000
  for (let [a, b] of pauses(t)) {
    b = b == null ? end : b
    a = Math.max(a, start)
    b = Math.min(b, end)
    if (b > a) total -= (b - a) / 1000
  }
  return Math.max(0, total)
}

/** Wall-clock ms when the running clock reaches targetS, or null while an open pause holds it. */
export function wallAt(t, targetS) {
  let cur = ms(t.started)
  let e = 0
  for (let [a, b] of pauses(t).sort((x, y) => x[0] - y[0])) {
    if (a < cur) a = cur
    const eAtA = e + (a - cur) / 1000
    if (eAtA >= targetS) break
    if (b == null) return null
    e = eAtA
    cur = Math.max(b, cur)
  }
  return cur + (targetS - e) * 1000
}

export function phaseEnds(t) {
  let acc = 0
  return t.plan.map(step => (acc += step.minutes * 60))
}

export function phaseAt(t, now = Date.now()) {
  const e = elapsedS(t, now)
  const ends = phaseEnds(t)
  const p = t.paused || []
  const paused = p.length > 0 && !p[p.length - 1][1]
  for (let i = 0; i < ends.length; i++) {
    if (e < ends[i]) {
      const step = t.plan[i]
      const endsAt = paused ? null : wallAt(t, ends[i])
      const next = t.plan[i + 1] || null
      return { index: i, phase: step.phase, title: PHASE_TITLES[step.phase] || step.phase, minutes: step.minutes,
        remaining_s: Math.round(ends[i] - e), remaining_min: Math.ceil((ends[i] - e) / 60), ends_at: endsAt,
        paused, done: false, next: next && { phase: next.phase, minutes: next.minutes }, elapsed_s: Math.round(e),
        total_s: Math.round(ends[ends.length - 1]), phase_start_s: i ? ends[i - 1] : 0 }
    }
  }
  return { index: ends.length, phase: 'done', title: 'Done', remaining_s: 0, remaining_min: 0, ends_at: null, paused,
    done: true, next: null, elapsed_s: Math.round(e), total_s: ends.length ? Math.round(ends[ends.length - 1]) : 0 }
}

/** Phase ends with wall time in (since, now]. Keys equal the tick's: `<timer id>:<phase index>`. */
export function dueEvents(t, since, now) {
  const out = []
  phaseEnds(t).forEach((end, i) => {
    const at = wallAt(t, end)
    if (at == null || !(since < at && at <= now)) return
    if (t.ended && at > ms(t.ended)) return
    const step = t.plan[i]
    const next = t.plan[i + 1] || null
    out.push({ key: `${t.id}:${i}`, index: i, phase: step.phase, minutes: step.minutes, at,
      next: next && { phase: next.phase, minutes: next.minutes }, label: t.label || null, timer_kind: t.kind })
  })
  return out
}

export function alertText(ev) {
  if (ev.timer_kind === 'countdown') return { title: 'Countdown done', body: `${ev.label ? ev.label + ', ' : ''}${ev.minutes} min` }
  const title = `${PHASE_TITLES[ev.phase] || ev.phase} done`
  if (!ev.next) return { title, body: 'Pomodoro finished. What did you finish?' }
  return { title, body: `${PHASE_TITLES[ev.next.phase]} ${ev.next.minutes} min` }
}

/** The click applied to the last known record, so the chip keeps counting while an op waits in the
 *  outbox. The backend applies the same op (same op id and click time) when it is replayed. */
export function applyLocal(t, op, plan) {
  if (op.op === 'start') {
    const kind = op.kind || 'pomodoro'
    const p = kind === 'countdown' ? [{ phase: 'countdown', minutes: op.minutes }] : op.plan || plan
    return { id: `local-${op.op_id}`, kind, plan: p, started: op.at, paused: [], label: op.label, client: op.client, local: true }
  }
  if (!t) return t
  const paused = (t.paused || []).map(x => x.slice())
  if (op.op === 'pause') return { ...t, paused: [...paused, [op.at, null]] }
  if (op.op === 'resume' && paused.length) {
    paused[paused.length - 1][1] = op.at
    return { ...t, paused }
  }
  if (op.op === 'stop') return null
  return t
}
