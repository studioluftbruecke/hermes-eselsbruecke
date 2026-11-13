// The world clock's maths and its place list, pure and shared by the World clock tool, the dashboard
// widget and smart paste. Places come from data/places.json (the tz database's zone.tab plus a city
// list), the same file the Python half resolves city names with (engines/places.py), so "Mumbai"
// means the same zone for the page and the agent (tests/fixtures/places.json).
// Nothing runs at import: the list is built and a zone's formatter is made on first use.
import DATA from '../../data/places.json'

export const MINUS = '\u2212'
const pad2 = n => String(n).padStart(2, '0')

/** The zone this computer is in. */
export const homeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

/** One spelling for matching: lower case, no accents, no dots or apostrophes, hyphens as spaces. */
export const fold = text => String(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  .replace(/[.'\u2019]/g, '').replace(/-/g, ' ').replace(/\s+/g, ' ').trim()

export const cityName = zone => (zone === 'UTC' ? 'UTC' : DATA.names[zone] || zone.split('/').pop().replace(/_/g, ' '))

const formatters = new Map()
function formatter(zone) {
  if (!formatters.has(zone)) {
    let f = null
    try {
      f = new Intl.DateTimeFormat('en-GB', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', weekday: 'short' })
    } catch {
      f = null
    }
    formatters.set(zone, f)
  }
  return formatters.get(zone)
}

/** Whether this Desktop's Intl knows the zone (an older Chromium may lack a newer name). */
export const validZone = zone => typeof zone === 'string' && !!zone && !!formatter(zone)

/** { year, month, day, hour, minute, weekday } of an instant in a zone, as two-digit strings. */
export function zoneParts(zone, ms) {
  const out = {}
  for (const p of formatter(zone).formatToParts(new Date(ms))) out[p.type] = p.value
  return out
}

export function offsetMinutes(zone, ms) {
  const p = zoneParts(zone, ms)
  return Math.round((Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute) - Math.floor(ms / 60000) * 60000) / 60000)
}

const hoursText = minutes => `${Math.trunc(minutes / 60)}${minutes % 60 ? `:${pad2(minutes % 60)}` : ''}`

/** "UTC+9", "UTC−5", "UTC+5:30". */
export function utcLabel(zone, ms) {
  const o = offsetMinutes(zone, ms)
  return `UTC${o < 0 ? MINUS : '+'}${hoursText(Math.abs(o))}`
}

/** How far a zone is from home at that instant: "+8 h", "−6 h", "+5:30 h" or "same time". */
export function relativeLabel(zone, home, ms) {
  const d = offsetMinutes(zone, ms) - offsetMinutes(home, ms)
  return d ? `${d > 0 ? '+' : MINUS}${hoursText(Math.abs(d))} h` : 'same time'
}

/** "tomorrow" or "yesterday" when the zone's calendar day differs from home's, else "". */
export function dayWord(zone, home, ms) {
  const a = zoneParts(zone, ms)
  const b = zoneParts(home, ms)
  const da = Date.UTC(+a.year, +a.month - 1, +a.day)
  const db = Date.UTC(+b.year, +b.month - 1, +b.day)
  return da > db ? 'tomorrow' : da < db ? 'yesterday' : ''
}

/** Home's day, hour by hour, as that zone lives it: 24 cells of 'work' (9 to 17 there), 'awake'
 *  (7 to 22) or 'night', and `now`, the cell of the instant shown. */
export function hourBar(zone, home, ms) {
  const h = zoneParts(home, ms)
  const dayStart = ms - (+h.hour * 60 + +h.minute) * 60000
  const cells = []
  for (let i = 0; i < 24; i++) {
    const hour = +zoneParts(zone, dayStart + i * 3600000).hour
    cells.push(hour >= 9 && hour < 17 ? 'work' : hour >= 7 && hour < 22 ? 'awake' : 'night')
  }
  return { cells, now: +h.hour }
}

/** Everything one clock row shows. `place` is { zone, label }. */
export function clockRow(place, home, ms) {
  const p = zoneParts(place.zone, ms)
  return { zone: place.zone, label: place.label, time: `${p.hour}:${p.minute}`, date: `${p.year}-${p.month}-${p.day}`, weekday: p.weekday,
    utc: utcLabel(place.zone, ms), relative: relativeLabel(place.zone, home, ms), day: dayWord(place.zone, home, ms), daylight: +p.hour >= 7 && +p.hour < 19 }
}

/** The rows a clock shows: home first (`you: true`), then the saved places. A saved place that is the
 *  home row again (the default list holds New York, and some people live there) and a zone this
 *  Desktop does not know are left out of the view; they stay in the saved list. */
export function clockPlaces(saved, home) {
  const you = { zone: home, label: cityName(home), you: true }
  const same = label => String(label).trim().toLowerCase() === you.label.toLowerCase()
  return [you, ...(Array.isArray(saved) ? saved : []).filter(c => c && validZone(c.zone) && !(c.zone === home && same(c.label)))]
}

/** "15:00 Berlin · 09:00 New York · 23:00 Tokyo" */
export const copyLine = rows => rows.map(r => `${r.time} ${r.label}`).join(' · ')

/** The scrubber's caption: "Now", "In 3 h", "In 1 h 30 min", "2 h ago". */
export function shiftLabel(minutes) {
  if (!minutes) return 'Now'
  const a = Math.abs(minutes)
  const text = [Math.trunc(a / 60) ? `${Math.trunc(a / 60)} h` : '', a % 60 ? `${a % 60} min` : ''].filter(Boolean).join(' ')
  return minutes > 0 ? `In ${text}` : `${text} ago`
}

let list = null
/** Every place: UTC, the city list, then every zone under its city name. { city, zone, country, key }. */
export function places() {
  if (!list) {
    list = [{ city: 'UTC', zone: 'UTC', country: 'Coordinated Universal Time' },
      ...DATA.cities.map(([city, zone, country]) => ({ city, zone, country })),
      ...Object.entries(DATA.zones).map(([zone, country]) => ({ city: cityName(zone), zone, country }))]
    for (const p of list) p.key = fold(p.city)
  }
  return list
}

/** Up to `limit` places for what was typed, best first: a city that starts with it, a city that
 *  contains it, then a zone name or a country that contains it. Places whose label is already taken
 *  and zones this Desktop does not know are left out. */
export function searchPlaces(query, { taken = [], limit = 7 } = {}) {
  const q = fold(query)
  if (!q) return []
  const have = new Set(taken.map(fold))
  const scored = []
  for (const p of places()) {
    if (have.has(p.key)) continue
    const s = p.key.startsWith(q) ? 0 : p.key.includes(q) ? 1 : fold(p.zone.replace(/[_/]/g, ' ')).includes(q) ? 2 : fold(p.country).includes(q) ? 3 : 9
    if (s < 9) scored.push([s, p])
  }
  scored.sort((a, b) => a[0] - b[0] || a[1].city.localeCompare(b[1].city))
  const out = []
  for (const [, p] of scored) {
    if (validZone(p.zone)) out.push({ city: p.city, zone: p.zone, country: p.country })
    if (out.length >= limit) break
  }
  return out
}

let byLower = null
// Intl ignores the case of a zone name and Python's zoneinfo does not, so a typed zone name is looked
// up in the list and answered in the list's own spelling by both halves.
const zoneByLower = () => byLower || (byLower = new Map(Object.keys(DATA.zones).map(z => [z.toLowerCase(), z])))

/** A typed name as a place, the same answer as the Python half's engines/places.py `resolve`:
 *  "UTC", a zone name from the list (typed in any case), or a city by its exact folded name.
 *  { zone, label } or null. */
export function resolvePlace(name) {
  const text = String(name || '').trim()
  if (!text) return null
  if (text.toLowerCase() === 'utc') return { zone: 'UTC', label: 'UTC' }
  if (text.includes('/')) {
    const zone = zoneByLower().get(text.toLowerCase())
    return zone && validZone(zone) ? { zone, label: cityName(zone) } : null
  }
  const key = fold(text)
  const hit = places().find(p => p.key === key)
  return hit ? { zone: hit.zone, label: hit.city } : null
}
