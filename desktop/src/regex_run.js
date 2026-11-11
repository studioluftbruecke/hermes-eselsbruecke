// The Regex tester's runner (X13): the user's pattern runs in a Web Worker started from a Blob URL,
// never on the renderer thread, because a pattern with catastrophic backtracking ((a+)+$ on 28
// characters takes seconds in V8) would freeze all of Desktop. A run that has not answered after
// `timeoutMs` is terminated; a newer run supersedes (and terminates) the one before it. The worker's
// code is engines.js `regex`, so the page and the parity fixtures test one function.
import { regex } from './engines.js'

export const TIMEOUT_MS = 300

let workerUrl = null
/** The worker's source, built on first use (nothing runs at module evaluation, constraint 9). */
function makeWorker() {
  if (!workerUrl) {
    const src = `const regex = ${regex.toString()};
self.onmessage = e => {
  const { pattern, text, flags } = e.data
  let out
  try { out = regex(pattern, text, flags) } catch (err) { out = { ok: false, error: String((err && err.message) || err) } }
  self.postMessage(out)
}`
    workerUrl = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }))
  }
  return new Worker(workerUrl)
}

let current = null

/** Run `regex(pattern, text, flags)` off the renderer thread. Resolves with the engine's answer, or
 *  { ok: false, timeout: true, error } after `timeoutMs`, or { ok: false, cancelled: true } when a
 *  newer run started first. Never rejects. */
export function runRegex(pattern, text, flags = '', { timeoutMs = TIMEOUT_MS } = {}) {
  if (current) current.cancel()
  return new Promise(resolve => {
    let worker
    let timer = null
    let done = false
    const job = {}
    const finish = out => {
      if (done) return
      done = true
      clearTimeout(timer)
      if (worker) worker.terminate()
      if (current === job) current = null
      resolve(out)
    }
    job.cancel = () => finish({ ok: false, cancelled: true })
    current = job
    try {
      worker = makeWorker()
    } catch (error) {
      finish({ ok: false, error: `The regex tester could not start its worker: ${error.message}` })
      return
    }
    worker.onmessage = e => finish(e.data)
    worker.onerror = e => finish({ ok: false, error: (e && e.message) || 'The regex worker failed.' })
    timer = setTimeout(() => finish({ ok: false, timeout: true,
      error: `Stopped after ${timeoutMs} ms: this pattern takes too long on this text. Nested quantifiers such as (a+)+ backtrack exponentially; make the inner part unambiguous.` }), timeoutMs)
    worker.postMessage({ pattern, text: String(text), flags })
  })
}

/** Stop a run in flight (the tester unmounts). */
export function cancelRegex() {
  if (current) current.cancel()
}
