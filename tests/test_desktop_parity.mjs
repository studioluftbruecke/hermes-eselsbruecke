// The Desktop's JavaScript engines against tests/fixtures/parity.json, the contract written from the
// Python engines (constraint 8). One stated difference: a zone's abbreviation (`abbr`) comes from
// Intl in the Desktop and from zoneinfo in Python ("GMT+9" against "JST"), so it is left out.
// Run by tests/test_desktop_build.py: node test_desktop_parity.mjs <desktop/build/node_modules>
// It bundles desktop/src/engines.js and timer.js with esbuild (the wordlist is a text import) into a
// temp module first, because node cannot import a .txt file. Prints one JSON line; exit 1 on a mismatch.
import assert from 'assert'
import fs from 'fs'
import { createRequire } from 'module'
import path from 'path'
import { fileURLToPath, pathToFileURL } from 'url'

const here = path.dirname(fileURLToPath(import.meta.url))
const src = path.resolve(here, '..', 'desktop', 'src')
if (!process.argv[2] || !fs.existsSync(path.join(path.resolve(process.argv[2]), 'esbuild'))) {
  console.error('usage: node test_desktop_parity.mjs <desktop/build/node_modules> (run npm ci in desktop/build first)')
  process.exit(2)
}
const nm = path.resolve(process.argv[2])
const esbuild = createRequire(path.join(nm, 'x.js'))('esbuild')
const dir = fs.mkdtempSync(path.join(process.env.TMPDIR || '/tmp', 'esb-parity-'))
const entry = path.join(dir, 'entry.js')
fs.writeFileSync(entry, `export * from ${JSON.stringify(path.join(src, 'engines.js'))}\nexport * as timer from ${JSON.stringify(path.join(src, 'timer.js'))}\n`)
const out = path.join(dir, 'engines.mjs')
await esbuild.build({ entryPoints: [entry], bundle: true, format: 'esm', platform: 'node', outfile: out, loader: { '.txt': 'text' }, logLevel: 'error' })
const E = await import(pathToFileURL(out).href)
fs.rmSync(dir, { recursive: true, force: true })

const fx = JSON.parse(fs.readFileSync(path.join(here, 'fixtures', 'parity.json'), 'utf8'))
const failures = []
const check = (name, fn) => {
  try {
    fn()
  } catch (error) {
    failures.push({ name, message: String(error.message).slice(0, 600) })
  }
}
const noAbbr = o => JSON.parse(JSON.stringify(o, (k, v) => (k === 'abbr' ? undefined : v)))
let n = 0

for (const c of fx.encode) {
  n++
  check(`encode ${c.scheme} ${JSON.stringify(c.text)}`, () => {
    assert.strictEqual(E.encode(c.text, c.scheme), c.encoded)
    assert.strictEqual(E.decode(c.encoded, c.scheme), c.text)
  })
}
for (const c of fx.colour) {
  n++
  check(`colour ${c.input}`, () => assert.deepStrictEqual(E.colour(c.input, c.background), c.out))
}
for (const c of fx.time) {
  n++
  check(`time ${c.time} ${c.from}`, () => assert.deepStrictEqual(noAbbr(E.convertTime(c.time, c.from, c.to)), noAbbr(c.out)))
}
for (const c of fx.timestamp) {
  n++
  check(`timestamp ${c.value}`, () => assert.deepStrictEqual(noAbbr(E.convertTimestamp(c.value, c.zones)), noAbbr(c.out)))
}
for (const c of fx.count) {
  n++
  check(`count ${JSON.stringify(c.text).slice(0, 30)}`, () => assert.deepStrictEqual(E.count(c.text), c.out))
}
for (const v of [4, 7]) {
  n++
  check(`uuid v${v}`, () => {
    const re = new RegExp(fx.uuid[`v${v}`])
    for (const id of E.uuids(v, 50)) assert.match(id, re)
  })
}
const iso = ms => (ms == null ? null : ms)
for (const c of fx.timer) {
  for (const want of c.states) {
    n++
    check(`timer ${c.timer.id} at ${want.at}`, () => {
      const got = E.timer.phaseAt(c.timer, Date.parse(want.at))
      const { at, ends_at, ...rest } = want
      for (const [k, v] of Object.entries(rest)) assert.deepStrictEqual(got[k], v, `${k}`)
      assert.strictEqual(iso(got.ends_at), ends_at == null ? null : Date.parse(ends_at), 'ends_at')
    })
  }
  n++
  check(`timer ${c.timer.id} due`, () => {
    const due = E.timer.dueEvents(c.timer, Date.parse(c.due.since), Date.parse(c.due.now))
    assert.deepStrictEqual(due.map(e => e.key), c.due.keys)
    assert.deepStrictEqual(due.map(e => e.at), c.due.at.map(Date.parse))
  })
}
// Shapes the Python side checks too: password sets and passphrase size.
n++
check('password has every chosen set', () => {
  for (let i = 0; i < 50; i++) {
    const p = E.password({ length: 8 }).password
    assert.match(p, /[a-z]/)
    assert.match(p, /[A-Z]/)
    assert.match(p, /[0-9]/)
    assert.match(p, /[!#$%&*+\-=?@^_~]/)
  }
})
n++
check('passphrase from the 1296-word list', () => assert.strictEqual(E.passphrase({ words: 4 }).wordlist_size, 1296))
n++
check('regex is JavaScript RegExp', () => {
  const r = E.regex('(\\d{4})-(\\d{2})', 'on 2026-11 and 2027-01')
  assert.deepStrictEqual(r.matches.map(m => m.text), ['2026-11', '2027-01'])
})

console.log(JSON.stringify({ cases: n, failed: failures.length, failures }))
process.exit(failures.length ? 1 : 0)
