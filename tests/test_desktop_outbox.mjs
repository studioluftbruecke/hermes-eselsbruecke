// The Desktop outbox, timer clicks and alerts against a fake backend (tests/desktop_harness.mjs):
// replay order, a click queued during a replay, a 5xx kept and a 4xx dropped with a toast,
// "Try again" on an op older than a day, each kind replaying from its own oldest op and the
// toast for a click behind a stuck op, dedupe by op_id, timer errors shown, the wake burst
// and the hours label.
// Run by tests/test_desktop_build.py: node test_desktop_outbox.mjs <desktop/build/node_modules>
// Prints one JSON line { cases, failed, failures }; exit 1 on a failure.
import assert from 'assert'

import { bundle, fresh, suite, tick } from './desktop_harness.mjs'

globalThis.window = globalThis
const file = await bundle(process.argv[2])
const t = suite()
const ops = M => M.readOutbox().map(i => i.op.op)
const refused = toasts => toasts.filter(m => /refused|no timer|database/i.test(m))

await t.test('a click made after reconnecting waits behind the queued clicks', async () => {
  const { M, server, toasts } = await fresh(file)
  M.startLive(M.getCtx())
  await tick(20)
  server.down = true
  await M.timerAction({ op: 'start', kind: 'pomodoro' })
  assert.deepStrictEqual(ops(M), ['start'])
  server.down = false
  const sent = await M.timerAction({ op: 'pause' })
  await tick(50)
  assert.notStrictEqual(sent.ok, false, `the pause was refused: ${sent.error && sent.error.message}`)
  const posts = server.log.filter(l => l.startsWith('POST /timer'))
  assert.deepStrictEqual(posts, ['POST /timer start', 'POST /timer pause'], `server saw ${JSON.stringify(server.log)}`)
  assert.ok(server.timer && server.timer.paused.length === 1, 'the timer the user paused runs on the server')
  assert.deepStrictEqual(refused(toasts()), [])
  assert.deepStrictEqual(ops(M), [])
})

await t.test('a click queued while a replay runs survives the replay', async () => {
  const { M, server } = await fresh(file)
  server.down = true
  await M.timerAction({ op: 'start', kind: 'pomodoro' })
  server.down = false
  server.slowMs = 80
  const replay = M.replayOutbox()
  await tick(10)
  server.down = true // the connection drops again while the start's answer is on its way
  await M.timerAction({ op: 'pause' })
  assert.deepStrictEqual(ops(M), ['start', 'pause'])
  server.down = false
  await replay
  server.slowMs = 0
  await M.replayOutbox()
  assert.deepStrictEqual(ops(M), [])
  assert.ok(server.timer && server.timer.paused.length === 1, 'the pause reached the server')
})

await t.test('a 5xx keeps the op, counts the try, and the next replay sends it', async () => {
  const { M, server, toasts } = await fresh(file)
  server.down = true
  await M.timerAction({ op: 'start', kind: 'pomodoro' })
  server.down = false
  server.fail500 = true
  const first = await M.replayOutbox()
  assert.strictEqual(first.sent, 0)
  assert.deepStrictEqual(ops(M), ['start'], 'a 500 dropped the op')
  assert.strictEqual(M.readOutbox()[0].tries, 1)
  assert.match(M.readOutbox()[0].error || '', /database is locked/)
  assert.deepStrictEqual(refused(toasts()), [], 'a 500 must not say "refused"')
  server.fail500 = false
  await M.replayOutbox()
  assert.deepStrictEqual(ops(M), [])
  assert.ok(server.timer, 'the start reached the server on the next replay')
})

await t.test('a 409 drops the op with a toast that names the refusal', async () => {
  const { M, server, toasts } = await fresh(file)
  server.down = true
  await M.sendOrQueue('timer', { op: 'pause' })
  server.down = false
  await M.replayOutbox()
  assert.deepStrictEqual(ops(M), [])
  assert.ok(toasts().some(m => /refused/.test(m) && /no timer is running/.test(m)), `toasts ${JSON.stringify(toasts())}`)
})

await t.test('after the retry cap the op stops replaying and the chip can discard it', async () => {
  const { M, server } = await fresh(file)
  server.down = true
  await M.timerAction({ op: 'start', kind: 'pomodoro' })
  server.down = false
  server.fail500 = true
  for (let i = 0; i < M.MAX_TRIES; i++) await M.replayOutbox()
  const status = M.outboxStatus()
  assert.ok(status.stuck, 'no stuck op after the retry cap')
  assert.strictEqual(status.stuck.reason, 'tries')
  const before = server.log.length
  await M.replayOutbox()
  assert.strictEqual(server.log.filter(l => l.startsWith('POST')).length, server.log.slice(0, before).filter(l => l.startsWith('POST')).length, 'a stuck op was sent again')
  M.retryOutbox()
  assert.strictEqual(M.outboxStatus().stuck, null)
  M.discardOutboxHead()
  assert.deepStrictEqual(ops(M), [])
})

await t.test('an op older than the age limit stops replaying and is shown as stuck', async () => {
  const { M } = await fresh(file)
  const store = M.getCtx().storage
  store.set('outbox:p1', [{ kind: 'timer', op: { op: 'pause', op_id: 'x1', at: '2026-11-01T09:00:00+01:00' }, queuedAt: Date.now() - M.MAX_AGE_MS - 1000 }])
  M.refreshOutbox()
  const status = M.outboxStatus()
  assert.ok(status.stuck && status.stuck.reason === 'age', JSON.stringify(status))
})

// --- an op older than a day is sent once on "Try again"; the server decides -----------------

const old = (M, items) => {
  M.getCtx().storage.set('outbox:p1', items)
  M.refreshOutbox()
}
const dayAgo = M => Date.now() - M.MAX_AGE_MS - 3600 * 1000
const posts = server => server.log.filter(l => l.startsWith('POST'))
/** The buttons OutboxNote renders, by their text. */
function buttons(node, out = []) {
  if (!node || typeof node !== 'object') return out
  if (Array.isArray(node)) { node.forEach(n => buttons(n, out)); return out }
  const props = node.props || {}
  if (typeof node.type === 'function' && typeof props.children === 'string') out.push(props.children)
  buttons(props.children, out)
  return out
}

await t.test('the chip offers "Try again" for an op older than a day', async () => {
  const { M } = await fresh(file)
  old(M, [{ kind: 'timer', op: { op: 'stop', op_id: 's1', at: '2026-11-06T18:00:00+01:00' }, queuedAt: dayAgo(M) }])
  assert.strictEqual(typeof M.chip.OutboxNote, 'function', 'OutboxNote is not exported from chip.js')
  const labels = buttons(M.chip.OutboxNote({ count: 1 }))
  assert.deepStrictEqual(labels, ['Try again', 'Discard it'])
})

await t.test('"Try again" sends an op older than a day once, and the server applies it', async () => {
  const { M, server } = await fresh(file)
  server.timer = { id: 't1', kind: 'countdown', plan: [], started: '2026-11-06T17:00:00+01:00', paused: [] }
  old(M, [{ kind: 'timer', op: { op: 'stop', op_id: 's1', at: '2026-11-06T18:00:00+01:00' }, queuedAt: dayAgo(M) }])
  await M.replayOutbox()
  assert.deepStrictEqual(posts(server), [], 'the automatic replay sent an op older than a day')
  assert.strictEqual(M.outboxStatus().stuck.reason, 'age')
  M.retryOutbox()
  await M.replayOutbox()
  assert.deepStrictEqual(posts(server), ['POST /timer stop'])
  assert.strictEqual(server.timer, null, 'the server timer still runs')
  assert.deepStrictEqual(ops(M), [])
})

await t.test('a refused old op is dropped with a toast after "Try again"', async () => {
  const { M, toasts } = await fresh(file)
  old(M, [{ kind: 'timer', op: { op: 'stop', op_id: 's2', at: '2026-11-06T18:00:00+01:00' }, queuedAt: dayAgo(M) }])
  M.retryOutbox()
  await M.replayOutbox()
  assert.deepStrictEqual(ops(M), [])
  assert.ok(toasts().some(m => /refused/.test(m) && /no timer is running/.test(m)), `toasts ${JSON.stringify(toasts())}`)
})

await t.test('"Try again" sends an old op once: a 5xx makes it stuck by age again', async () => {
  const { M, server } = await fresh(file)
  old(M, [{ kind: 'timer', op: { op: 'start', kind: 'pomodoro', op_id: 's3', at: '2026-11-06T18:00:00+01:00' }, queuedAt: dayAgo(M) }])
  server.fail500 = true
  M.retryOutbox()
  await M.replayOutbox()
  assert.strictEqual(M.readOutbox()[0].tries, 1)
  assert.strictEqual(M.outboxStatus().stuck && M.outboxStatus().stuck.reason, 'age')
  const before = posts(server).length
  server.fail500 = false
  await M.replayOutbox()
  assert.strictEqual(posts(server).length, before, 'the old op went out again without a click')
  assert.deepStrictEqual(ops(M), ['start'])
})

// --- each kind replays from its own oldest op -----------------------------------------------

const lockedTimelog = (M, server) => {
  const ctx = M.getCtx()
  const inner = ctx.rest
  ctx.rest = async (p, o = {}) => {
    if (p === '/timelog/ops') { server.log.push('POST /timelog/ops'); throw new Error(`Error invoking remote method 'hermes:api': Error: 500: {"ok":false,"error":"store","message":"database is locked"}`) }
    return inner(p, o)
  }
}

await t.test('a stuck time-log op does not hold back the timer clicks queued behind it', async () => {
  const { M, server } = await fresh(file)
  lockedTimelog(M, server)
  old(M, [
    { kind: 'timelog', op: { op: 'stop', op_id: 'l1', entry_id: 'e1', at: '2026-11-11T09:00:00+01:00' }, queuedAt: Date.now() - 60000, tries: 5, error: '500: database is locked' },
    { kind: 'timer', op: { op: 'start', kind: 'countdown', minutes: 25, op_id: 'k1', at: '2026-11-11T09:01:00+01:00' }, queuedAt: Date.now() - 50000 },
  ])
  const sent = await M.timerAction({ op: 'pause' })
  assert.deepStrictEqual(posts(server), ['POST /timer start', 'POST /timer pause'], `server saw ${JSON.stringify(server.log)}`)
  assert.ok(server.timer && server.timer.paused.length === 1, 'the pause did not reach the server')
  assert.notStrictEqual(sent.behind, true)
  assert.deepStrictEqual(M.readOutbox().map(i => `${i.kind}:${i.op.op}`), ['timelog:stop'])
  assert.strictEqual(M.outboxStatus().stuck.kind, 'timelog')
})

await t.test('a 5xx on one kind does not stop the other kind in the same replay', async () => {
  const { M, server } = await fresh(file)
  lockedTimelog(M, server)
  old(M, [
    { kind: 'timelog', op: { op: 'stop', op_id: 'l2', entry_id: 'e1', at: '2026-11-11T09:00:00+01:00' }, queuedAt: Date.now() - 60000 },
    { kind: 'timer', op: { op: 'start', kind: 'countdown', minutes: 25, op_id: 'k2', at: '2026-11-11T09:01:00+01:00' }, queuedAt: Date.now() - 50000 },
  ])
  await M.replayOutbox()
  assert.deepStrictEqual(posts(server), ['POST /timelog/ops', 'POST /timer start'])
  assert.deepStrictEqual(M.readOutbox().map(i => `${i.kind}:${i.op.op}:${i.tries || 0}`), ['timelog:stop:1'])
})

await t.test('a click waiting behind a stuck op of its kind gets a toast naming that op', async () => {
  const { M, server, toasts } = await fresh(file)
  server.fail500 = true
  old(M, [{ kind: 'timer', op: { op: 'start', kind: 'pomodoro', op_id: 'k3', at: '2026-11-11T09:01:00+01:00' }, queuedAt: Date.now() - 50000, tries: 5, error: '500: database is locked' }])
  const sent = await M.timerAction({ op: 'pause' })
  assert.strictEqual(sent.behind, true)
  assert.deepStrictEqual(posts(server), [], 'a stuck op or the click behind it was sent')
  const named = toasts().filter(m => /timer start/.test(m) && /Try again|Discard/.test(m))
  assert.strictEqual(named.length, 1, `toasts ${JSON.stringify(toasts())}`)
})

await t.test('the chip shows, retries and discards the stuck op even when another kind is older', async () => {
  const { M } = await fresh(file)
  old(M, [
    { kind: 'timer', op: { op: 'start', kind: 'countdown', minutes: 5, op_id: 'k4', at: '2026-11-11T09:00:00+01:00' }, queuedAt: Date.now() - 60000 },
    { kind: 'timelog', op: { op: 'stop', op_id: 'l4', entry_id: 'e1', at: '2026-11-11T09:01:00+01:00' }, queuedAt: Date.now() - 50000, tries: 5 },
  ])
  const status = M.outboxStatus()
  assert.ok(status.stuck && status.stuck.kind === 'timelog', JSON.stringify(status))
  M.retryOutbox()
  assert.strictEqual(M.readOutbox().find(i => i.op.op_id === 'l4').tries, 0, 'Try again reset the wrong op')
  M.getCtx().storage.set('outbox:p1', M.readOutbox().map(i => (i.op.op_id === 'l4' ? { ...i, tries: 5 } : i)))
  M.discardOutboxHead()
  assert.deepStrictEqual(M.readOutbox().map(i => i.op.op_id), ['k4'], 'Discard removed the wrong op')
})

await t.test('dedupe: one op_id is kept once in the outbox', async () => {
  const { M, server } = await fresh(file)
  server.down = true
  await M.sendOrQueue('timer', { op: 'start', kind: 'countdown', minutes: 5, op_id: 'same-id' })
  await M.sendOrQueue('timer', { op: 'start', kind: 'countdown', minutes: 5, op_id: 'same-id' })
  assert.strictEqual(M.readOutbox().length, 1)
})

await t.test('a refused timer click shows the server message and does not throw', async () => {
  const { M, toasts } = await fresh(file)
  let result
  try {
    result = await M.timerAction({ op: 'pause' })
  } catch (error) {
    assert.fail(`timerAction threw: ${error.message}`)
  }
  assert.strictEqual(result.ok, false)
  assert.ok(toasts().some(m => /no timer is running/.test(m)), `toasts ${JSON.stringify(toasts())}`)
})

await t.test('after a 2 h sleep the missed phase ends make one "while you were away" alert', async () => {
  const { M, toasts } = await fresh(file)
  const now = Date.now()
  const started = new Date(now - 2 * 3600000).toISOString()
  M.$timer.set({ id: 'w1', kind: 'pomodoro', plan: M.pomodoroPlan(25, 5, 15, 4), started, paused: [] })
  assert.strictEqual(typeof M.checkAlerts, 'function', 'checkAlerts is not exported')
  M.checkAlerts(now, now - 2 * 3600000)
  const fired = toasts()
  assert.strictEqual(fired.length, 1, `fired ${fired.length}: ${JSON.stringify(fired)}`)
  assert.match(fired[0], /while you were away/i)
  M.checkAlerts(now, now - 2 * 3600000)
  assert.strictEqual(toasts().length, 1, 'the summary fired twice')
})

await t.test('a phase end inside the tick window still alerts at once', async () => {
  const { M, toasts } = await fresh(file)
  const now = Date.now()
  M.$timer.set({ id: 'w2', kind: 'countdown', plan: [{ phase: 'countdown', minutes: 1 }], started: new Date(now - 62000).toISOString(), paused: [], label: 'tea' })
  M.checkAlerts(now, now - 5000)
  assert.deepStrictEqual(toasts().length, 1)
  assert.doesNotMatch(toasts()[0], /while you were away/i)
})

await t.test('the hours label rounds the total minutes', async () => {
  const { M } = await fresh(file)
  assert.strictEqual(typeof M.hoursLabel, 'function', 'hoursLabel is not exported from timer.js')
  assert.strictEqual(M.hoursLabel(1.995), '2:00')
  assert.strictEqual(M.hoursLabel(1.5), '1:30')
  assert.strictEqual(M.hoursLabel(0), '0:00')
  assert.strictEqual(M.hoursLabel(0.9999), '1:00')
  assert.strictEqual(M.hoursLabel(12.25), '12:15')
})

t.done()
