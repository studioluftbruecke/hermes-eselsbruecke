// Convert and design tools, all in the Desktop (they answer per keystroke; constraint 8) and all
// working without the backend: encode/decode, UUIDs and passwords, colour (with WCAG contrast and,
// where Desktop allows it, a screen picker), QR codes. Time zones live in tools/clock.js.
import { useEffect, useMemo, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { alertBoth, storage } from '../core.js'
import { DRAFT, useDraft } from '../drafts.js'
import { colour, decode, encode, passphrase, password, uuids } from '../engines.js'
import { qrcode } from '../vendor.js'
import { Area, Btn, Choice, Copy, Field, h, Input, Out, ToolHead } from '../ui.js'

const attempt = fn => {
  try {
    return { ok: true, value: fn() }
  } catch (error) {
    return { ok: false, error: error.message }
  }
}

export function EncodeTool() {
  const [text, setText] = useDraft(DRAFT.encodeText, '')
  const [scheme, setScheme] = useDraft(DRAFT.encodeScheme, 'base64')
  const [dir, setDir] = useDraft(DRAFT.encodeDir, 'encode')
  const res = useMemo(() => (text ? attempt(() => (dir === 'encode' ? encode(text, scheme) : decode(text, scheme))) : null), [text, scheme, dir])
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Encode, decode', blurb: 'Base64, Base64URL and URL encoding, UTF-8 throughout.' }),
    h('div', { className: 'row' },
      h(Choice, { value: dir, onChange: setDir, options: [['encode', 'Encode'], ['decode', 'Decode']], 'aria-label': 'Direction' }),
      h(Choice, { value: scheme, onChange: setScheme, options: [['base64', 'Base64'], ['base64url', 'Base64URL'], ['url', 'URL']], 'aria-label': 'Scheme' })),
    h(Area, { value: text, onChange: setText, rows: 6, placeholder: dir === 'encode' ? 'Text' : 'Encoded text' }),
    res ? (res.ok ? h('div', { className: 'col' }, h(Out, null, res.value), h('div', { className: 'row' }, h(Copy, { text: res.value }), h(Btn, { onClick: () => { setText(res.value); setDir(dir === 'encode' ? 'decode' : 'encode') } }, 'Swap'))) : h(Out, { err: true }, res.error)) : null)
}

export function GenerateTool() {
  const [version, setVersion] = useState('4')
  const [n, setN] = useState('1')
  const [ids, setIds] = useState([])
  const [opt, setOpt] = useState({ length: 20, lower: true, upper: true, digits: true, symbols: true, avoidAmbiguous: false })
  const [pw, setPw] = useState(null)
  const [words, setWords] = useState(5)
  const [phrase, setPhrase] = useState(null)
  const box = (k, label) => h('label', { className: 'row small' }, h('input', { type: 'checkbox', checked: opt[k], onChange: e => setOpt({ ...opt, [k]: e.target.checked }) }), label)
  const gen = (fn, set) => {
    const r = attempt(fn)
    if (r.ok) set(r.value)
    else alertBoth('Eselsbrücke', r.error, 'warning')
  }
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'UUID, password', blurb: "Made on this Mac with the system's secure random numbers; nothing is sent anywhere." }),
    h('div', { className: 'panel col' }, h('h3', null, 'UUID'),
      h('div', { className: 'row' },
        h(Choice, { value: version, onChange: setVersion, options: [['4', 'v4 (random)'], ['7', 'v7 (time-ordered)']], 'aria-label': 'Version' }),
        h(Input, { type: 'number', min: 1, max: 100, value: n, onChange: setN, style: { width: 70 }, 'aria-label': 'How many' }),
        h(Btn, { pri: true, onClick: () => setIds(uuids(Number(version), Number(n) || 1)) }, 'Generate')),
      ids.length ? h('div', { className: 'col' }, h(Out, null, ids.join('\n')), h(Copy, { text: ids.join('\n') })) : null),
    h('div', { className: 'panel col' }, h('h3', null, 'Password'),
      h('div', { className: 'row' },
        h(Field, { label: 'Length' }, h(Input, { type: 'number', min: 4, max: 256, value: opt.length, onChange: v => setOpt({ ...opt, length: Number(v) }), style: { width: 80 } })),
        box('lower', 'a-z'), box('upper', 'A-Z'), box('digits', '0-9'), box('symbols', '!#$…'), box('avoidAmbiguous', 'no Il1O0o'),
        h(Btn, { pri: true, onClick: () => gen(() => password(opt), setPw) }, 'Generate')),
      pw ? h('div', { className: 'row' }, h('code', { className: 'out grow' }, pw.password), h(Copy, { text: pw.password }), h('span', { className: 'note' }, `${pw.entropy_bits} bits`)) : null),
    h('div', { className: 'panel col' }, h('h3', null, 'Passphrase'),
      h('div', { className: 'row' },
        h(Field, { label: 'Words' }, h(Input, { type: 'number', min: 3, max: 20, value: words, onChange: v => setWords(Number(v)), style: { width: 70 } })),
        h(Btn, { pri: true, onClick: () => gen(() => passphrase({ words }), setPhrase) }, 'Generate')),
      phrase ? h('div', { className: 'row' }, h('code', { className: 'out grow' }, phrase.passphrase), h(Copy, { text: phrase.passphrase }), h('span', { className: 'note' }, `${phrase.entropy_bits} bits, ${phrase.wordlist}`)) : null))
}

export function ColourTool() {
  const [text, set] = useDraft(DRAFT.colourText, storage.get('colour', '#2f9e6b'))
  const [bg, setBg] = useState('#ffffff')
  const res = useMemo(() => attempt(() => colour(text, bg)), [text, bg])
  // The last colour that reads as one is remembered across restarts (the dashboard shows it too),
  // whether it was typed, picked or filled in by smart paste.
  useEffect(() => {
    if (res.ok && storage.get('colour') !== text) storage.set('colour', text)
  }, [text, res.ok])
  const pick = async () => {
    try {
      const r = await new window.EyeDropper().open()
      set(r.sRGBHex)
    } catch (error) {
      if (error.name !== 'AbortError') alertBoth('Eselsbrücke', `The screen picker did not work: ${error.message}`, 'warning')
    }
  }
  const v = res.ok ? res.value : null
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'Colour picker', blurb: 'Hex, RGB, HSL and OKLCH, and WCAG contrast against a background.' }),
    h('div', { className: 'row' },
      h('input', { type: 'color', value: v ? v.hex.slice(0, 7) : '#000000', onChange: e => set(e.target.value), 'aria-label': 'Pick a colour' }),
      h(Input, { value: text, onChange: set, className: 'inp mono grow', 'aria-label': 'Colour' }),
      'EyeDropper' in window ? h(Btn, { onClick: pick }, 'Pick from screen') : null,
      h(Field, { label: 'Background' }, h(Input, { value: bg, onChange: setBg, className: 'inp mono', style: { width: 120 } }))),
    v ? h('div', { className: 'grid2' },
      h('div', { className: 'swatch', style: { background: v.hex, color: bg } }, 'Aa'),
      h('div', { className: 'kv' }, ['hex', 'rgb', 'hsl', 'oklch'].map(k => [
        jsx('span', { className: 'k', children: k }, `${k}k`), jsx('span', { className: 'v', children: v[k] }, `${k}v`), jsx(Copy, { text: v[k] }, `${k}c`)]).flat()))
      : h(Out, { err: true }, res.error),
    v && v.out_of_gamut ? h('p', { className: 'note' }, 'That OKLCH colour is outside sRGB; it was clamped to the nearest colour a screen shows.') : null,
    v && v.contrast ? h('div', { className: 'panel row' },
      h('strong', null, `${v.contrast.ratio}:1`),
      [['aa_normal', 'AA'], ['aa_large', 'AA large'], ['aaa_normal', 'AAA'], ['aaa_large', 'AAA large']].map(([k, label]) =>
        jsx('span', { className: `verdict ${v.contrast[k] ? 'pass' : 'fail'}`, children: `${label} ${v.contrast[k] ? 'pass' : 'fail'}` }, k))) : null)
}

function save(name, blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

/** The SVG drawn onto a canvas at 8 px per module, saved as PNG (all in the renderer). */
function savePng(svgText) {
  const img = new Image()
  img.onload = () => {
    const size = Math.max(img.naturalWidth, 200) * 4
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const g = canvas.getContext('2d')
    g.imageSmoothingEnabled = false
    g.drawImage(img, 0, 0, size, size)
    canvas.toBlob(b => (b ? save('qr-code.png', b) : alertBoth('Eselsbrücke', 'Could not draw the PNG.', 'warning')), 'image/png')
  }
  img.onerror = () => alertBoth('Eselsbrücke', 'Could not draw the PNG.', 'warning')
  img.src = `data:image/svg+xml;utf8,${encodeURIComponent(svgText)}`
}

export function QrTool() {
  const [text, setText] = useDraft(DRAFT.qrText, '')
  const svg = useMemo(() => {
    if (!text) return null
    return attempt(() => {
      const q = qrcode()(0, 'M')
      q.addData(text, 'Byte')
      q.make()
      return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true })
    })
  }, [text])
  return h('div', { className: 'col' },
    h(ToolHead, { title: 'QR code', blurb: 'Made on this Mac; nothing is sent anywhere.' }),
    h(Area, { value: text, onChange: setText, rows: 3, placeholder: 'Text or a link' }),
    svg && svg.ok ? h('div', { className: 'row' },
      h('img', { className: 'qr', alt: 'QR code', width: 200, height: 200, src: `data:image/svg+xml;utf8,${encodeURIComponent(svg.value)}` }),
      h('div', { className: 'col' }, h(Copy, { text: svg.value, label: 'Copy SVG' }),
        h(Btn, { onClick: () => save('qr-code.svg', new Blob([svg.value], { type: 'image/svg+xml' })) }, 'Download SVG'),
        h(Btn, { onClick: () => savePng(svg.value) }, 'Download PNG'))) : null,
    svg && !svg.ok ? h(Out, { err: true }, `${svg.error} (a QR code holds about 2,300 characters at most)`) : null)
}
