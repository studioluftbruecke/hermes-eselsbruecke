// What a tool's fields hold, kept for as long as Desktop runs: switching tools, visiting the dashboard
// or leaving the Eselsbrücke page and coming back does not empty them. Memory only, never ctx.storage
// or the backend, because people paste secrets into a formatter. One atom per key, so the page and
// the beside-chat pane show the same text, and smart paste can fill a tool before it opens.
import { atom, useValue } from '@hermes/plugin-sdk'

export const DRAFT = {
  formatterText: 'formatter.text', diffLeft: 'diff.left', diffRight: 'diff.right',
  regexPattern: 'regex.pattern', regexFlags: 'regex.flags', regexText: 'regex.text',
  tokensText: 'tokens.text', cronExpr: 'cron.expr',
  encodeText: 'encode.text', encodeDir: 'encode.dir', encodeScheme: 'encode.scheme',
  qrText: 'qr.text', colourText: 'colour.text', clockStamp: 'clock.stamp',
  padAdd: 'pad.add', pomodoroResult: 'pomodoro.result', timelogForm: 'timelog.form', smartPaste: 'dashboard.paste',
}

const atoms = new Map()
const draftAtom = (key, initial) => {
  if (!atoms.has(key)) atoms.set(key, atom(initial))
  return atoms.get(key)
}

export const getDraft = (key, fallback = '') => (atoms.has(key) ? atoms.get(key).get() : fallback)
export const setDraft = (key, value) => draftAtom(key, value).set(value)

/** useState for a field that should survive: [value, set]. `initial` applies only the first time. */
export function useDraft(key, initial = '') {
  const a = draftAtom(key, initial)
  return [useValue(a), a.set]
}
