// The engines that run in the Desktop because they answer per keystroke or drag (constraint 8):
// colour, time zones and timestamps, encode/decode, counts, regex (JavaScript RegExp), generators.
// Each equals its Python twin on tests/fixtures/parity.json (tests/test_desktop_parity.mjs), with one
// stated difference: a zone's abbreviation comes from Intl and can read "GMT+9" where Python's zoneinfo
// says "JST", so the parity test leaves `abbr` out.
import WORDLIST from '../../data/eff_short_wordlist_1.txt'

import { uuid4, uuid7 } from './ids.js'

export class EngineError extends Error {}

/** Half away from zero (the Python engine's rnd). */
export function rnd(x, places = 0) {
  const f = 10 ** places
  const v = Math.floor(Math.abs(x) * f + 0.5) / f
  return x < 0 ? -v : v
}
const num = x => String(x)
const clamp = (x, lo = 0, hi = 1) => (x < lo ? lo : x > hi ? hi : x)

// --- colour ------------------------------------------------------------------------------------------

const lin = c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const gam = c => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055)

function srgbToOklab(r, g, b) {
  r = lin(r); g = lin(g); b = lin(b)
  let l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
  let m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
  let s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
  l = Math.cbrt(l); m = Math.cbrt(m); s = Math.cbrt(s)
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s]
}

function oklabToSrgb(L, a, b) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
  const bb = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s
  return [r > 0 ? gam(r) : r * 12.92, g > 0 ? gam(g) : g * 12.92, bb > 0 ? gam(bb) : bb * 12.92]
}

function hslToRgb(h, s, l) {
  h = (((h % 360) + 360) % 360) / 360
  if (s === 0) return [l, l, l]
  const hue = (p, q, t) => {
    t = ((t % 1) + 1) % 1
    if (t < 1 / 6) return p + (q - p) * 6 * t
    if (t < 1 / 2) return q
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
    return p
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  return [hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)]
}

function rgbToHsl(r, g, b) {
  const mx = Math.max(r, g, b)
  const mn = Math.min(r, g, b)
  const l = (mx + mn) / 2
  if (mx === mn) return [0, 0, l]
  const d = mx - mn
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn)
  let h
  if (mx === r) h = (g - b) / d + (g < b ? 6 : 0)
  else if (mx === g) h = (b - r) / d + 2
  else h = (r - g) / d + 4
  return [h * 60, s, l]
}

const NUM = '[-+]?(?:\\d+\\.?\\d*|\\.\\d+)'
const NAMED = { black: '#000000', white: '#ffffff', red: '#ff0000', green: '#008000', blue: '#0000ff', yellow: '#ffff00',
  orange: '#ffa500', purple: '#800080', gray: '#808080', grey: '#808080', transparent: '#00000000' }
const FN_RE = new RegExp(`^(rgba?|hsla?|oklch)\\(\\s*(${NUM})(%?)[\\s,]+(${NUM})(%?)[\\s,]+(${NUM})(%?)\\s*(?:[,/]\\s*(${NUM})(%?))?\\s*\\)$`)

export function parseColour(text) {
  let t = String(text).trim().toLowerCase()
  t = NAMED[t] || t
  let m = t.match(/^#?([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/)
  if (m) {
    let h = m[1]
    if (h.length <= 4) h = [...h].map(c => c + c).join('')
    const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1
    return [parseInt(h.slice(0, 2), 16) / 255, parseInt(h.slice(2, 4), 16) / 255, parseInt(h.slice(4, 6), 16) / 255, a, false]
  }
  m = t.match(FN_RE)
  if (!m) throw new EngineError(`cannot read the colour '${text}'; use #2f9e6b, rgb(47 158 107), hsl(153 54% 40%) or oklch(62% 0.13 160)`)
  const fn = m[1]
  const [v1, p1, v2, p2, v3, p3, va, pa] = [Number(m[2]), m[3], Number(m[4]), m[5], Number(m[6]), m[7], m[8], m[9]]
  const alpha = va == null ? 1 : clamp(Number(va) / (pa ? 100 : 1))
  if (fn.startsWith('rgb')) {
    const ch = [[v1, p1], [v2, p2], [v3, p3]].map(([v, p]) => (p ? v / 100 : v / 255))
    return [clamp(ch[0]), clamp(ch[1]), clamp(ch[2]), alpha, false]
  }
  if (fn.startsWith('hsl')) return [...hslToRgb(v1, clamp(v2 / 100), clamp(v3 / 100)), alpha, false]
  const L = p1 ? v1 / 100 : v1
  const C = p2 ? (v2 / 100) * 0.4 : v2
  const hr = (v3 * Math.PI) / 180
  const [r, g, b] = oklabToSrgb(L, C * Math.cos(hr), C * Math.sin(hr))
  const out = [r, g, b].some(c => c < -0.01 || c > 1.01)
  return [clamp(r), clamp(g), clamp(b), alpha, out]
}

const hex2 = c => Math.trunc(rnd(c * 255)).toString(16).padStart(2, '0')
const toHex = (r, g, b, a = 1) => `#${hex2(r)}${hex2(g)}${hex2(b)}${a < 1 ? hex2(a) : ''}`
const luminance = (r, g, b) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
export function contrastRatio(fg, bg) {
  const l1 = luminance(...fg)
  const l2 = luminance(...bg)
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)
}

export function colour(text, background) {
  const [r0, g0, b0, a, outOfGamut] = parseColour(text)
  const [r8, g8, b8] = [r0, g0, b0].map(c => Math.trunc(rnd(c * 255)))
  const [r, g, b] = [r8 / 255, g8 / 255, b8 / 255]
  const [h, s, l] = rgbToHsl(r, g, b)
  const [L, A, B] = srgbToOklab(r, g, b)
  const C = Math.sqrt(A * A + B * B)
  const H = C > 0.0002 ? ((((Math.atan2(B, A) * 180) / Math.PI) % 360) + 360) % 360 : 0
  const alpha = a >= 1 ? '' : ` / ${num(rnd(a, 2))}`
  const res = {
    hex: toHex(r, g, b, a),
    rgb: `rgb(${r8} ${g8} ${b8}${alpha})`,
    hsl: `hsl(${num(rnd(h, 1))} ${num(rnd(s * 100, 1))}% ${num(rnd(l * 100, 1))}%${alpha})`,
    oklch: `oklch(${num(rnd(L * 100, 1))}% ${num(rnd(C, 3))} ${num(rnd(H, 1))}${alpha})`,
    alpha: rnd(a, 2),
    out_of_gamut: outOfGamut,
  }
  if (background) {
    const [br, bg, bb] = parseColour(background)
    const bg8 = [br, bg, bb].map(c => Math.trunc(rnd(c * 255)) / 255)
    const ratio = rnd(contrastRatio([r, g, b], bg8), 2)
    res.contrast = { background: toHex(...bg8), ratio, aa_normal: ratio >= 4.5, aa_large: ratio >= 3, aaa_normal: ratio >= 7, aaa_large: ratio >= 4.5 }
  }
  return res
}

// --- time zones and timestamps -----------------------------------------------------------------------

const pad = n => String(n).padStart(2, '0')
const fmtCache = new Map()
function fmt(zone) {
  if (!fmtCache.has(zone)) {
    try {
      fmtCache.set(zone, new Intl.DateTimeFormat('en-US', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short', timeZoneName: 'short' }))
    } catch {
      throw new EngineError(`unknown time zone '${zone}' (use IANA names like Europe/Berlin, America/New_York, UTC)`)
    }
  }
  return fmtCache.get(zone)
}

function parts(epochMs, zone) {
  const out = {}
  for (const p of fmt(zone).formatToParts(new Date(epochMs))) out[p.type] = p.value
  return out
}

/** Minutes east of UTC for a zone at an instant. */
function offsetMin(epochMs, zone) {
  const p = parts(epochMs, zone)
  const asUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second)
  return Math.round((asUtc - Math.floor(epochMs / 1000) * 1000) / 60000)
}

export function zoneRow(epochMs, zone) {
  const p = parts(epochMs, zone)
  const mins = offsetMin(epochMs, zone)
  const sign = mins >= 0 ? '+' : '-'
  return { zone, time: `${p.year}-${p.month}-${p.day} ${pad(+p.hour % 24)}:${p.minute}`, weekday: p.weekday,
    offset: `UTC${sign}${pad(Math.floor(Math.abs(mins) / 60))}:${pad(Math.abs(mins) % 60)}`, abbr: p.timeZoneName }
}

/** Wall time in a zone to epoch ms; a time skipped by a DST jump is read with the offset before it
 *  (as Python's zoneinfo does with fold=0). */
export function zonedToEpoch(y, mo, d, h, mi, zone) {
  const guess = Date.UTC(y, mo - 1, d, h, mi)
  const o1 = offsetMin(guess - 864e5 / 2, zone)
  const o2 = offsetMin(guess + 864e5 / 2, zone)
  const c1 = guess - o1 * 60000
  const c2 = guess - o2 * 60000
  const ok = c => { const r = zoneRow(c, zone); return r.time === `${y}-${pad(mo)}-${pad(d)} ${pad(h)}:${pad(mi)}` }
  if (ok(c1)) return c1
  if (ok(c2)) return c2
  return c1
}

export function convertTime(time, fromZone, toZones, nowMs = Date.now()) {
  fmt(fromZone)
  const text = String(time || 'now').trim()
  let epoch
  if (text.toLowerCase() === 'now') epoch = nowMs
  else {
    let m = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})(?::\d{2})?$/)
    if (m) epoch = zonedToEpoch(+m[1], +m[2], +m[3], +m[4], +m[5], fromZone)
    else if ((m = text.match(/^(\d{1,2}):(\d{2})$/))) {
      const t = zoneRow(nowMs, fromZone).time
      epoch = zonedToEpoch(+t.slice(0, 4), +t.slice(5, 7), +t.slice(8, 10), +m[1], +m[2], fromZone)
    } else throw new EngineError(`cannot read the time '${text}'; use 2026-11-09 14:30, 14:30 or now`)
  }
  const zones = (toZones || []).filter(z => String(z).trim())
  const list = zones.length ? zones : ['UTC']
  if (list.length > 12) throw new EngineError('at most 12 zones')
  return { from: zoneRow(epoch, fromZone), to: list.map(z => zoneRow(epoch, z)), unix: Math.floor(epoch / 1000) }
}

export function convertTimestamp(value, zones) {
  const list = (zones || []).filter(z => String(z).trim())
  const zs = list.length ? list : ['UTC']
  const text = String(value).trim()
  const isoUtc = e => new Date(Math.floor(e / 1000) * 1000).toISOString().replace('.000Z', 'Z')
  if (/^-?\d+(\.\d+)?$/.test(text)) {
    const n = Number(text)
    const unit = Math.abs(n) >= 1e11 ? 'ms' : 's'
    const secs = unit === 'ms' ? n / 1000 : n
    const e = secs * 1000
    return { input_unit: unit, unix: Math.floor(secs), unix_ms: Math.trunc(rnd(secs * 1000)), iso_utc: isoUtc(e), zones: zs.map(z => zoneRow(e, z)) }
  }
  const m = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?(Z|[+-]\d{2}:\d{2})?$/)
  if (!m) throw new EngineError(`cannot read '${text}': give Unix seconds, milliseconds or an ISO date`)
  let e
  if (m[7]) e = Date.parse(`${m[1]}-${m[2]}-${m[3]}T${m[4] || '00'}:${m[5] || '00'}:${m[6] || '00'}${m[7]}`)
  else e = zonedToEpoch(+m[1], +m[2], +m[3], +(m[4] || 0), +(m[5] || 0), zs[0]) + (+(m[6] || 0)) * 1000
  return { input_unit: 'iso', unix: Math.floor(e / 1000), unix_ms: Math.trunc(rnd(e)), iso_utc: isoUtc(e), zones: zs.map(z => zoneRow(e, z)) }
}

// --- encode and decode -------------------------------------------------------------------------------

const utf8 = new TextEncoder()
const utf8d = new TextDecoder('utf-8', { fatal: true })
const b64 = bytes => btoa(Array.from(bytes, b => String.fromCharCode(b)).join(''))

export function encode(text, scheme) {
  if (scheme === 'base64') return b64(utf8.encode(String(text)))
  if (scheme === 'base64url') return b64(utf8.encode(String(text))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  if (scheme === 'url') return encodeURIComponent(String(text))
  throw new EngineError('scheme must be one of base64, base64url, url')
}

export function decode(text, scheme) {
  const raw = String(text).trim()
  if (scheme === 'base64' || scheme === 'base64url') {
    let c = raw.replace(/\s+/g, '')
    if (scheme === 'base64url') c = c.replace(/-/g, '+').replace(/_/g, '/')
    if (/[^A-Za-z0-9+/=]/.test(c)) throw new EngineError('not base64: only A-Z, a-z, 0-9, + / (or - _ for base64url) and = are allowed')
    c += '='.repeat((4 - (c.length % 4)) % 4)
    let bin
    try {
      bin = atob(c)
    } catch (e) {
      throw new EngineError(`cannot decode: ${e.message}`)
    }
    try {
      return utf8d.decode(Uint8Array.from(bin, ch => ch.charCodeAt(0)))
    } catch {
      throw new EngineError('decoded bytes are not UTF-8 text')
    }
  }
  if (scheme === 'url') {
    if (/%(?![0-9A-Fa-f]{2})/.test(raw)) throw new EngineError('not URL-encoded: a % must be followed by two hex digits')
    try {
      return decodeURIComponent(raw)
    } catch (e) {
      throw new EngineError(`cannot decode: ${e.message}`)
    }
  }
  throw new EngineError('scheme must be one of base64, base64url, url')
}

// --- counts ------------------------------------------------------------------------------------------

const CJK = /[\u1100-\u11ff\u2e80-\u9fff\ua960-\ua97f\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]/g

/** Hermes' own estimate: ceil(UTF-8 bytes / 4), a dense CJK character counted as one token. */
export function estimateTokens(text) {
  if (!text) return 0
  if (/^[\x00-\x7f]*$/.test(text)) return Math.floor((text.length + 3) / 4)
  const stripped = text.replace(CJK, '')
  const dense = [...text].length - [...stripped].length
  return dense + Math.floor((utf8.encode(stripped).length + 3) / 4)
}

export function count(text) {
  const t = String(text ?? '')
  return { characters: [...t].length, characters_no_spaces: [...t.replace(/\s/g, '')].length, words: (t.match(/\S+/g) || []).length,
    lines: t ? t.split('\n').length : 0, bytes_utf8: utf8.encode(t).length, tokens_estimate: estimateTokens(t) }
}

// --- regex (JavaScript flavour) ----------------------------------------------------------------------

export function regex(pattern, text, flags = '') {
  let re
  try {
    re = new RegExp(pattern, flags.includes('g') ? flags : flags + 'g')
  } catch (e) {
    return { ok: false, error: e.message }
  }
  const matches = []
  for (const m of String(text).matchAll(re)) {
    matches.push({ start: m.index, end: m.index + m[0].length, text: m[0], groups: m.slice(1), named: m.groups || null })
    if (matches.length >= 200) break
    if (m[0] === '' && re.lastIndex === m.index) re.lastIndex++
  }
  return { ok: true, flavour: 'JavaScript RegExp', matches }
}

// --- generators --------------------------------------------------------------------------------------

const WORDS = WORDLIST.split('\n').map(l => l.trim().split(/\s+/)).filter(p => p.length === 2).map(p => p[1])
const LOWER = 'abcdefghijklmnopqrstuvwxyz'
const UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
const DIGITS = '0123456789'
const SYMBOLS = '!#$%&*+-=?@^_~'
const AMBIGUOUS = new Set('Il1O0o')

/** Uniform integer below n from crypto.getRandomValues (rejection sampling). */
export function randBelow(n) {
  const limit = Math.floor(0x100000000 / n) * n
  const buf = new Uint32Array(1)
  for (;;) {
    crypto.getRandomValues(buf)
    if (buf[0] < limit) return buf[0] % n
  }
}

export const uuids = (version = 4, n = 1) => Array.from({ length: Math.max(1, Math.min(n, 100)) }, () => (version === 7 ? uuid7() : uuid4()))

export function password({ length = 20, lower = true, upper = true, digits = true, symbols = true, avoidAmbiguous = false } = {}) {
  if (!(length >= 4 && length <= 256)) throw new EngineError('length must be between 4 and 256')
  let sets = [[LOWER, lower], [UPPER, upper], [DIGITS, digits], [SYMBOLS, symbols]].filter(([, on]) => on).map(([s]) => s)
  if (avoidAmbiguous) sets = sets.map(s => [...s].filter(c => !AMBIGUOUS.has(c)).join(''))
  if (!sets.length) throw new EngineError('switch on at least one character set')
  const pool = sets.join('')
  let chars
  do chars = Array.from({ length }, () => pool[randBelow(pool.length)])
  while (!(length < sets.length || sets.every(s => chars.some(c => s.includes(c)))))
  return { password: chars.join(''), entropy_bits: rnd(length * Math.log2(pool.length), 1), pool_size: pool.length }
}

export function passphrase({ words = 6, separator = '-', capitalize = false, number = false } = {}) {
  if (!(words >= 3 && words <= 20)) throw new EngineError('words must be between 3 and 20')
  let picked = Array.from({ length: words }, () => WORDS[randBelow(WORDS.length)])
  if (capitalize) picked = picked.map(w => w[0].toUpperCase() + w.slice(1))
  let bits = words * Math.log2(WORDS.length)
  if (number) {
    picked[randBelow(words)] += String(randBelow(10))
    bits += Math.log2(10) + Math.log2(words)
  }
  return { passphrase: picked.join(separator), entropy_bits: rnd(bits, 1), wordlist: 'EFF short 1', wordlist_size: WORDS.length }
}
