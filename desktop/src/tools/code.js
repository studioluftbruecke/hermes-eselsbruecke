// Code tools. Formatter: JSON and YAML through the Python engine (the agent's output, byte for byte),
// the other languages through Prettier in the Desktop; without the backend Prettier formats JSON and
// YAML too, labelled "formatted in Desktop". Diff and cron need the backend.
// Regex is JavaScript's RegExp; the agent's tool is Python's re, and the page says so.
import { useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { post, rest, storage } from '../core.js'
import { DRAFT, useDraft } from '../drafts.js'
import { estimateTokens } from '../engines.js'
import { cancelRegex, runRegex, TIMEOUT_MS as REGEX_TIMEOUT_MS } from '../regex_run.js'
import { prettier, tiktokenLite } from '../vendor.js'
import { Area, Btn, Choice, ConnectionBanner, Copy, Field, h, Input, Out, ToolHead, useDebounced } from '../ui.js'

const LANGS = [['json', 'JSON'], ['yaml', 'YAML'], ['markdown', 'Markdown'], ['typescript', 'TypeScript'], ['babel', 'JavaScript'], ['css', 'CSS'], ['html', 'HTML']]

async function formatText(text, lang) {
  if (lang === 'json' || lang === 'yaml') {
    try {
      const out = await post('/run/format', { action: 'format', text, lang })
      if (!out.ok) return { error: out.message || out.error }
      return { text: out.text, how: 'Formatted by the Python engine (same as the agent).' }
    } catch (error) {
      if (!error.network && !error.notOn) return { error: error.message }
      const text2 = await prettier().format(text, lang)
      return { text: text2, how: 'Formatted in Desktop (Hermes is not reachable): Prettier, which may differ from the agent.' }
    }
  }
  return { text: await prettier().format(text, lang), how: 'Formatted in Desktop with Prettier 3.9.' }
}

export function FormatterTool() {
  const [lang, setLang] = useState(storage.get('fmtLang', 'json'))
  const [text, setText] = useDraft(DRAFT.formatterText, '')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async (input = text) => {
    setBusy(true)
    try {
      setRes(await formatText(input, lang))
    } catch (error) {
      setRes({ error: `${error.name || 'Error'}: ${error.message}`.slice(0, 600) })
    } finally {
      setBusy(false)
    }
  }
  const convert = async to => {
    try {
      const out = await post('/run/format', { action: 'convert', text, from: lang, to })
      setRes(out.ok ? { text: out.text, how: `Converted ${lang.toUpperCase()} to ${to.toUpperCase()} by the Python engine.` } : { error: out.message || out.error })
    } catch (error) {
      setRes({ error: error.message })
    }
  }
  // "Format clipboard" reads the clipboard once (if Desktop refuses, it says so and asks for a paste)
  const fromClipboard = async () => {
    try {
      const clip = await navigator.clipboard.readText()
      setText(clip)
      run(clip)
    } catch (error) {
      setRes({ error: `Desktop did not allow reading the clipboard (${error.name}). Paste into the box and press Format.` })
    }
  }
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Formatter', blurb: 'JSON and YAML go through the same engine as the agent; Markdown, TypeScript, JavaScript, CSS and HTML through Prettier in Desktop.' }),
    h('div', { className: 'row' },
      h(Choice, { value: lang, onChange: v => { setLang(v); storage.set('fmtLang', v) }, options: LANGS, 'aria-label': 'Language' }),
      h(Btn, { pri: true, disabled: busy || !text, onClick: () => run() }, busy ? 'Formatting…' : 'Format'),
      h(Btn, { onClick: fromClipboard }, 'Format clipboard'),
      lang === 'json' ? h(Btn, { disabled: !text, onClick: () => convert('yaml') }, 'To YAML') : null,
      lang === 'yaml' ? h(Btn, { disabled: !text, onClick: () => convert('json') }, 'To JSON') : null),
    h('div', { className: 'grid2' },
      h(Area, { value: text, onChange: setText, placeholder: 'Paste code here', 'aria-label': 'Input', rows: 14 }),
      h('div', { className: 'col' },
        res && res.error ? h(Out, { err: true }, res.error) : h(Out, { style: { minHeight: 240 } }, res ? res.text : ''),
        res && res.how ? h('p', { className: 'note' }, res.how) : null,
        res && res.text ? h('div', { className: 'row' }, h(Copy, { text: res.text }), h(Btn, { onClick: () => setText(res.text) }, 'Use as input')) : null)))
}

export function DiffTool() {
  const [left, setLeft] = useDraft(DRAFT.diffLeft, '')
  const [right, setRight] = useDraft(DRAFT.diffRight, '')
  const [res, setRes] = useState(null)
  const l = useDebounced(left, 400)
  const r = useDebounced(right, 400)
  useEffect(() => {
    if (!l && !r) return setRes(null)
    let live = true
    post('/run/text', { action: 'diff', left: l, right: r }).then(out => live && setRes(out), error => live && setRes({ ok: false, message: error.message }))
    return () => {
      live = false
    }
  }, [l, r])
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Text diff', blurb: 'Two texts, the lines and words that changed.' }),
    h(ConnectionBanner, { what: 'Not connected to Hermes: the diff runs on the backend and is not available now.' }),
    h('div', { className: 'grid2' },
      h(Field, { label: 'Before' }, h(Area, { value: left, onChange: setLeft, rows: 10 })),
      h(Field, { label: 'After' }, h(Area, { value: right, onChange: setRight, rows: 10 }))),
    res && res.ok === false ? h(Out, { err: true }, res.message || res.error) : null,
    res && res.rows ? h('div', { className: 'panel col' },
      h('p', { className: 'note' }, res.identical ? 'The texts are identical.' : `${res.changed} changed, ${res.added} added, ${res.removed} removed`),
      h('div', { className: 'dl' }, res.rows.map((row, i) => jsx(DiffRow, { row }, i))),
      res.unified ? h('div', { className: 'row' }, h(Copy, { text: res.unified, label: 'Copy unified diff' })) : null) : null)
}

function DiffRow({ row }) {
  const num = (a, b) => h('span', { className: 'ln' }, a ?? b ?? '')
  if (row.op === 'same') return h('div', null, num(row.left_no), row.text || ' ')
  if (row.op === 'add') return h('div', { className: 'add' }, num(null, row.right_no), '+ ', row.text)
  if (row.op === 'del') return h('div', { className: 'del' }, num(row.left_no), '- ', row.text)
  return h('div', null, num(row.left_no), (row.words || []).map((w, i) => jsx('span', { className: w.op === 'same' ? undefined : w.op, children: w.text }, i)))
}

export function RegexTool() {
  const [pattern, setPattern] = useDraft(DRAFT.regexPattern, '')
  const [flags, setFlags] = useDraft(DRAFT.regexFlags, 'gi')
  const [text, setText] = useDraft(DRAFT.regexText, '')
  // The pattern runs in a worker with a time limit, 150 ms after the last key. The result keeps
  // the text it was computed on, so the marks never point into a newer text.
  const input = useDebounced(JSON.stringify([pattern, flags, text]), 150)
  const [run, setRun] = useState({ res: null, text: '' })
  useEffect(() => {
    const [p, f, t] = JSON.parse(input)
    if (!p) {
      setRun({ res: null, text: t })
      return undefined
    }
    let live = true
    runRegex(p, t, f.replace(/[^dgimsuvy]/g, '')).then(res => {
      if (live && !res.cancelled) setRun({ res, text: t })
    })
    return () => {
      live = false
    }
  }, [input])
  useEffect(() => cancelRegex, [])
  const { res } = run
  const marked = []
  if (res && res.ok) {
    let at = 0
    res.matches.forEach((m, i) => {
      if (m.start > at) marked.push(run.text.slice(at, m.start))
      marked.push(jsx('mark', { className: 'm', children: m.text || '\u200b' }, i))
      at = m.end
    })
    marked.push(run.text.slice(at))
  }
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Regex tester', blurb: `JavaScript RegExp, as you type, stopped after ${REGEX_TIMEOUT_MS} ms so a runaway pattern cannot freeze Desktop. The agent tests the Python flavour (re), which differs in a few places (named groups, lookbehind, flags).` }),
    h('div', { className: 'row' },
      h(Input, { value: pattern, onChange: setPattern, placeholder: 'Pattern, e.g. (\\d{4})-(\\d{2})', className: 'inp grow mono' }),
      h(Input, { value: flags, onChange: setFlags, 'aria-label': 'Flags', style: { width: 70 }, className: 'inp mono' })),
    h(Area, { value: text, onChange: setText, placeholder: 'Text to search', rows: 8 }),
    res && !res.ok ? h(Out, { err: true }, res.error) : null,
    res && res.ok ? h('div', { className: 'panel col' },
      h('p', { className: 'note' }, `${res.matches.length} match${res.matches.length === 1 ? '' : 'es'}${res.matches.length >= 200 ? ' (first 200)' : ''}`),
      h('div', { className: 'dl' }, marked),
      res.matches.some(m => m.groups.length) ? h('div', { className: 'out' }, res.matches.slice(0, 20).map((m, i) => `${i + 1}: ${JSON.stringify(m.named || m.groups)}`).join('\n')) : null) : null)
}

// Tokens: the estimate at once; the exact o200k count needs the ranks (2.3 MB, GET /data/o200k) and
// building the encoder blocks Desktop for about a second or more once per run. Until this Mac
// has measured a first count under 1 s, the exact count waits for a click.
let encoder = null
let encoderMs = null
async function loadEncoder() {
  if (encoder) return encoder
  const ranks = await rest('/data/o200k', { timeoutMs: 60000 })
  const t0 = performance.now()
  const { Tiktoken } = tiktokenLite()
  encoder = new Tiktoken(ranks)
  encoderMs = Math.round(performance.now() - t0)
  storage.set('tokenFirstMs', encoderMs)
  return encoder
}

export function TokensTool() {
  const [text, setText] = useDraft(DRAFT.tokensText, '')
  const [exact, setExact] = useState(encoder ? 'ready' : 'idle')
  const firstMs = storage.get('tokenFirstMs', null)
  const auto = firstMs != null && firstMs <= 1000
  useEffect(() => {
    if (auto && exact === 'idle') start()
  }, [])
  const start = async () => {
    setExact('loading')
    try {
      await loadEncoder()
      setExact('ready')
    } catch (error) {
      setExact(`error: ${error.network ? 'Hermes is not reachable, so the ranks cannot load. The estimate stays.' : error.message}`)
    }
  }
  const est = estimateTokens(text)
  const count = exact === 'ready' && encoder ? encoder.encode(text).length : null
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Token counter', blurb: "Hermes' own estimate at once; the exact count uses OpenAI's o200k tokenizer (GPT-4o and later). Other models count differently." }),
    h(Area, { value: text, onChange: setText, rows: 10, placeholder: 'Paste a prompt' }),
    h('div', { className: 'kv' },
      h('span', { className: 'k' }, 'Estimate'), h('span', { className: 'v' }, String(est)), h('span', { className: 'note' }, 'UTF-8 bytes / 4'),
      h('span', { className: 'k' }, 'o200k exact'), h('span', { className: 'v' }, count != null ? String(count) : 'not counted'),
      exact === 'ready' ? h('span', { className: 'note' }, encoderMs != null ? `encoder built in ${encoderMs} ms` : '')
        : exact === 'loading' ? h('span', { className: 'note' }, 'loading…')
          : h(Btn, { onClick: start }, 'Count exactly'),
      h('span', { className: 'k' }, 'Characters'), h('span', { className: 'v' }, String([...text].length)), h('span', null)),
    exact === 'idle' && !auto ? h('p', { className: 'note' }, `The first exact count downloads 2.3 MB from your Hermes and pauses Desktop for ${firstMs ? `about ${(firstMs / 1000).toFixed(1)} s` : 'a second or more'}, once per run.`) : null,
    exact.startsWith && exact.startsWith('error') ? h(Out, { err: true }, exact.slice(7)) : null)
}

export function CronTool() {
  const [expr, setExpr] = useDraft(DRAFT.cronExpr, '*/15 9-17 * * 1-5')
  const [zone, setZone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
  const [res, setRes] = useState(null)
  const e = useDebounced(expr, 300)
  const z = useDebounced(zone, 300)
  useEffect(() => {
    if (!e.trim()) return setRes(null)
    let live = true
    post('/run/convert', { action: 'cron', expression: e, zone: z, count: 5 }).then(o => live && setRes(o), err => live && setRes({ ok: false, message: err.message }))
    return () => {
      live = false
    }
  }, [e, z])
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Cron explainer', blurb: 'A cron line in words, and its next runs.' }),
    h(ConnectionBanner, { what: 'Not connected to Hermes: the cron explainer runs on the backend and is not available now.' }),
    h('div', { className: 'row' },
      h(Input, { value: expr, onChange: setExpr, className: 'inp grow mono', 'aria-label': 'Cron expression' }),
      h(Input, { value: zone, onChange: setZone, 'aria-label': 'Time zone', style: { width: 180 } })),
    res && res.ok === false ? h(Out, { err: true }, res.message || res.error) : null,
    res && res.words ? h('div', { className: 'panel col' }, h('strong', null, res.words), h(Out, null, (res.next || []).join('\n'))) : null)
}

