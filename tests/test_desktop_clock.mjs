// The world clock's maths, the place list, smart paste and drafts (desktop/src/clockmath.js, detect.js,
// drafts.js): pure modules, tested in node. Place names are checked against tests/fixtures/places.json,
// the same fixture the Python half answers (tests/test_places.py), so both halves resolve a city alike.
// Run by tests/test_desktop_build.py: node test_desktop_clock.mjs <desktop/build/node_modules>
// Prints one JSON line { cases, failed, failures }; exit 1 on a failure.
import assert from 'assert'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

import { bundle, fresh, suite } from './desktop_harness.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const FIXTURE = JSON.parse(fs.readFileSync(path.join(here, 'fixtures', 'places.json'), 'utf8'))
const file = await bundle(process.argv[2])
const { M } = await fresh(file)
const { clockmath: C, detect: D, drafts } = M
const t = suite()
// 2026-11-09 19:40:02 UTC, a Monday: Berlin is on winter time (UTC+1), New York on EST (UTC-5).
const WINTER = 1794253202000
// 2026-07-01 12:00 UTC: Berlin UTC+2, New York UTC-4.
const SUMMER = Date.UTC(2026, 6, 1, 12, 0)

await t.test('a place name resolves like the fixture says', () => {
  for (const [query, zone, label] of FIXTURE.resolve) {
    const got = C.resolvePlace(query)
    assert.deepStrictEqual(got, zone === null ? null : { zone, label }, `resolvePlace(${JSON.stringify(query)})`)
  }
})

await t.test('every zone and city in places.json is known to Intl here', () => {
  const unknown = [...new Set(C.places().map(p => p.zone))].filter(z => !C.validZone(z))
  assert.deepStrictEqual(unknown, [])
  assert.ok(C.places().length > 500, String(C.places().length))
})

await t.test('search: prefix first, a city that is no zone, accents, country, taken labels left out', () => {
  assert.strictEqual(C.searchPlaces('tok')[0].zone, 'Asia/Tokyo')
  assert.deepStrictEqual(C.searchPlaces('mumb')[0], { city: 'Mumbai', zone: 'Asia/Kolkata', country: 'India' })
  assert.strictEqual(C.searchPlaces('sao pa')[0].city, 'São Paulo')
  assert.strictEqual(C.searchPlaces('dussel')[0].city, 'Düsseldorf')
  assert.ok(C.searchPlaces('japan').some(p => p.zone === 'Asia/Tokyo'))
  assert.ok(C.searchPlaces('new york').some(p => p.city === 'New York'))
  assert.ok(!C.searchPlaces('new york', { taken: ['New York'] }).some(p => p.city === 'New York'))
  assert.strictEqual(C.searchPlaces('san', { limit: 3 }).length, 3)
  assert.deepStrictEqual(C.searchPlaces('   '), [])
  assert.deepStrictEqual(C.searchPlaces('zzzz'), [])
})

await t.test('offsets, relative labels and the day word follow daylight saving', () => {
  assert.strictEqual(C.offsetMinutes('Europe/Berlin', WINTER), 60)
  assert.strictEqual(C.offsetMinutes('Europe/Berlin', SUMMER), 120)
  assert.strictEqual(C.utcLabel('Asia/Kolkata', WINTER), 'UTC+5:30')
  assert.strictEqual(C.utcLabel('America/New_York', WINTER), `UTC${C.MINUS}5`)
  assert.strictEqual(C.utcLabel('UTC', WINTER), 'UTC+0')
  assert.strictEqual(C.relativeLabel('Asia/Tokyo', 'Europe/Berlin', WINTER), '+8 h')
  assert.strictEqual(C.relativeLabel('Asia/Tokyo', 'Europe/Berlin', SUMMER), '+7 h')
  assert.strictEqual(C.relativeLabel('America/New_York', 'Europe/Berlin', WINTER), `${C.MINUS}6 h`)
  assert.strictEqual(C.relativeLabel('Asia/Kolkata', 'Europe/Berlin', WINTER), '+4:30 h')
  assert.strictEqual(C.relativeLabel('Europe/Paris', 'Europe/Berlin', WINTER), 'same time')
  assert.strictEqual(C.dayWord('Asia/Tokyo', 'Europe/Berlin', WINTER), 'tomorrow')
  assert.strictEqual(C.dayWord('America/New_York', 'Europe/Berlin', WINTER), '')
  assert.strictEqual(C.dayWord('America/Los_Angeles', 'Asia/Tokyo', WINTER), 'yesterday')
})

await t.test('a clock row, the copy line and the scrubber caption', () => {
  const row = C.clockRow({ zone: 'Asia/Tokyo', label: 'Tokyo office' }, 'Europe/Berlin', WINTER)
  assert.deepStrictEqual(row, { zone: 'Asia/Tokyo', label: 'Tokyo office', time: '04:40', date: '2026-11-10', weekday: 'Tue', utc: 'UTC+9', relative: '+8 h', day: 'tomorrow', daylight: false })
  const home = C.clockRow({ zone: 'Europe/Berlin', label: 'Berlin' }, 'Europe/Berlin', WINTER)
  assert.strictEqual(C.copyLine([home, row]), '20:40 Berlin · 04:40 Tokyo office')
  assert.strictEqual(C.shiftLabel(0), 'Now')
  assert.strictEqual(C.shiftLabel(180), 'In 3 h')
  assert.strictEqual(C.shiftLabel(90), 'In 1 h 30 min')
  assert.strictEqual(C.shiftLabel(-120), '2 h ago')
  assert.strictEqual(C.shiftLabel(-15), '15 min ago')
})

await t.test("the hour bar is home's day as the place lives it", () => {
  const same = C.hourBar('Europe/Berlin', 'Europe/Berlin', WINTER)
  assert.strictEqual(same.cells.length, 24)
  assert.strictEqual(same.now, 20)
  assert.deepStrictEqual(same.cells.map((c, i) => (c === 'work' ? i : null)).filter(i => i !== null), [9, 10, 11, 12, 13, 14, 15, 16])
  assert.strictEqual(same.cells[7], 'awake')
  assert.strictEqual(same.cells[3], 'night')
  // 9 to 17 in New York is 15 to 23 in Berlin
  const ny = C.hourBar('America/New_York', 'Europe/Berlin', WINTER)
  assert.deepStrictEqual(ny.cells.map((c, i) => (c === 'work' ? i : null)).filter(i => i !== null), [15, 16, 17, 18, 19, 20, 21, 22])
  assert.strictEqual(ny.now, 20)
})

await t.test('smart paste names the kind, the tool and the drafts to fill', () => {
  const on = () => true
  const kind = text => { const d = D.detect(text, on, 'Europe/Berlin'); return d && [d.kind, d.tool] }
  assert.deepStrictEqual(kind('{"a":1,"b":[2,3]}'), ['json', 'formatter'])
  assert.deepStrictEqual(kind('{"a":1,'), ['json-error', 'formatter'])
  assert.deepStrictEqual(kind('1794253202'), ['timestamp', 'timezones'])
  assert.deepStrictEqual(kind('1794253202000'), ['timestamp', 'timezones'])
  assert.deepStrictEqual(kind('#2f9e6b'), ['colour', 'colour'])
  assert.deepStrictEqual(kind('oklch(62% 0.13 160)'), ['colour', 'colour'])
  assert.deepStrictEqual(kind('aGVsbG8gd29ybGQ='), ['base64', 'encode'])
  assert.deepStrictEqual(kind('aGVsbG8='), ['base64', 'encode'])
  assert.deepStrictEqual(kind('*/15 9-17 * * 1-5'), ['cron', 'cron'])
  assert.deepStrictEqual(kind('@daily'), ['cron', 'cron'])
  assert.deepStrictEqual(kind('https://luftbruecke.studio/x?y=1'), ['link', 'qr'])
  assert.deepStrictEqual(kind('hello'), ['none', null])
  assert.deepStrictEqual(kind('password'), ['none', null])
  assert.deepStrictEqual(kind('deadbeef'), ['none', null])
  assert.strictEqual(D.detect('   ', on), null)
  assert.strictEqual(D.detect('1794253202', on, 'Europe/Berlin').detail, 'Mon 2026-11-09 20:40 in Berlin')
  assert.deepStrictEqual(D.detect('aGVsbG8gd29ybGQ=', on).drafts, { 'encode.text': 'aGVsbG8gd29ybGQ=', 'encode.dir': 'decode', 'encode.scheme': 'base64' })
  assert.strictEqual(D.detect('aGVsbG8gd29ybGQ=', on).detail, 'hello world')
})

await t.test('smart paste does not offer a tool that is switched off', () => {
  const d = D.detect('#2f9e6b', id => id !== 'colour')
  assert.deepStrictEqual([d.kind, d.tool], ['none', null])
  assert.deepStrictEqual(D.detect('1794253202', id => id !== 'timezones').tool, null)
})

await t.test('a draft is kept under its key and shared by every reader', () => {
  assert.strictEqual(drafts.getDraft(drafts.DRAFT.formatterText, 'fallback'), 'fallback')
  drafts.setDraft(drafts.DRAFT.formatterText, '{"a":1}')
  assert.strictEqual(drafts.getDraft(drafts.DRAFT.formatterText), '{"a":1}')
  const [value, set] = drafts.useDraft(drafts.DRAFT.formatterText, 'ignored')
  assert.strictEqual(value, '{"a":1}')
  set('next')
  assert.strictEqual(drafts.useDraft(drafts.DRAFT.formatterText)[0], 'next')
  assert.strictEqual(drafts.useDraft(drafts.DRAFT.qrText, 'first')[0], 'first')
  assert.strictEqual(new Set(Object.values(drafts.DRAFT)).size, Object.keys(drafts.DRAFT).length)
})

t.done()
