// Smart paste: what a pasted text is and which tool takes it. Pure, so the dashboard can call it per
// keystroke. `isOn(id)` says whether a tool is switched on; a kind whose tool is off is not offered.
// The answer names the drafts to fill before the tool opens (drafts.js), so the tool shows the text.
import { cityName, homeZone, zoneParts } from './clockmath.js'
import { DRAFT } from './drafts.js'

const HINT = 'JSON, a timestamp, a colour, Base64, a cron line or a link.'

/** null for an empty text, else { kind, tool, title, detail, action, drafts, swatch? }.
 *  tool is null when nothing was recognised or the matching tool is off. */
export function detect(text, isOn = () => true, home = homeZone()) {
  const v = String(text || '').trim()
  if (!v) return null
  if (isOn('colour') && (/^#([0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(v) || /^(rgb|hsl|oklch)a?\([^)]+\)$/i.test(v))) {
    return { kind: 'colour', tool: 'colour', title: 'A colour', detail: v, swatch: v, action: 'Open in Colour picker', drafts: { [DRAFT.colourText]: v } }
  }
  if (isOn('timezones') && /^\d{10}(\d{3})?$/.test(v)) {
    const p = zoneParts(home, v.length === 13 ? +v : +v * 1000)
    return { kind: 'timestamp', tool: 'timezones', title: 'A Unix timestamp', detail: `${p.weekday} ${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} in ${cityName(home)}`,
      action: 'Open in World clock', drafts: { [DRAFT.clockStamp]: v } }
  }
  if (isOn('formatter') && /^[[{]/.test(v)) {
    try {
      const j = JSON.parse(v)
      return { kind: 'json', tool: 'formatter', title: 'JSON', detail: `valid, ${Array.isArray(j) ? `${j.length} items` : `${Object.keys(j).length} keys`}`, action: 'Format it', drafts: { [DRAFT.formatterText]: v } }
    } catch (error) {
      return { kind: 'json-error', tool: 'formatter', title: 'JSON with an error', detail: String(error.message).slice(0, 80), action: 'Open in Formatter', drafts: { [DRAFT.formatterText]: v } }
    }
  }
  if (isOn('qr') && /^https?:\/\/\S+$/i.test(v)) return { kind: 'link', tool: 'qr', title: 'A link', detail: v, action: 'Make a QR code', drafts: { [DRAFT.qrText]: v } }
  if (isOn('cron') && /^(@(hourly|daily|weekly|monthly|yearly|annually)|([\d*/,\-]+\s+){4}[\d*/,\-a-z]+)$/i.test(v)) {
    return { kind: 'cron', tool: 'cron', title: 'A cron line', detail: v, action: 'Explain it', drafts: { [DRAFT.cronExpr]: v } }
  }
  if (isOn('encode') && v.length >= 8 && v.length % 4 === 0 && /^[A-Za-z0-9+/]+={0,2}$/.test(v)) {
    let decoded = null
    try {
      decoded = new TextDecoder('utf-8', { fatal: true }).decode(Uint8Array.from(atob(v), c => c.charCodeAt(0)))
    } catch {
      decoded = null
    }
    // only bytes that are readable UTF-8 text are called Base64: "deadbeef" is also a run of its alphabet
    if (decoded && decoded.length >= 3 && /^[\P{Cc}\n\r\t]+$/u.test(decoded)) {
      return { kind: 'base64', tool: 'encode', title: 'Base64', detail: decoded.slice(0, 80), action: 'Open in Encode, decode',
        drafts: { [DRAFT.encodeText]: v, [DRAFT.encodeDir]: 'decode', [DRAFT.encodeScheme]: 'base64' } }
    }
  }
  if (isOn('tokens') && v.length > 40) {
    return { kind: 'text', tool: 'tokens', title: 'Text', detail: `${v.length} characters, ${v.split(/\s+/).length} words`, action: 'Count tokens', drafts: { [DRAFT.tokensText]: v } }
  }
  return { kind: 'none', tool: null, title: 'Nothing recognised', detail: HINT, action: null, drafts: {} }
}
