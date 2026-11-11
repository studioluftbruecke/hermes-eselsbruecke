// Evaluate desktop/plugin.js the way Desktop's loader does (its three allowed specifiers mapped to
// modules), with stand-ins: every SDK and React export is a callable proxy, so module evaluation and
// register() run without a renderer. Prints one JSON line: CPU ms of the import (process.cpuUsage,
// user + system), whether register() ran, and the contributions it made. Run by build.mjs in a fresh
// node process with --disallow-code-generation-from-strings (the renderer forbids eval as well).
import fs from 'fs'
import path from 'path'
import { pathToFileURL } from 'url'

const file = process.argv[2]
const dir = fs.mkdtempSync(path.join(process.env.TMPDIR || '/tmp', 'esb-eval-'))
const STUB = `
const any = new Proxy(function () {}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => '' : k === 'then' ? undefined : any),
  apply: () => any, construct: () => any,
});
`
let src = fs.readFileSync(file, 'utf8')
const specs = { '@hermes/plugin-sdk': 'sdk', react: 'react', 'react/jsx-runtime': 'jsx' }
for (const [spec, name] of Object.entries(specs)) {
  const names = new Set()
  const re = new RegExp(`import\\s*\\{([^}]*)\\}\\s*from\\s*["']${spec.replace('/', '\\/')}["']`, 'g')
  for (const m of src.matchAll(re)) for (const part of m[1].split(',')) if (part.trim()) names.add(part.trim().split(/\s+as\s+/)[0])
  const body = STUB + [...names].map(n => `export const ${n} = any;`).join('\n') + '\nexport default any;\n'
  const stub = path.join(dir, `${name}.mjs`)
  fs.writeFileSync(stub, body)
  src = src.split(`"${spec}"`).join(`"${pathToFileURL(stub).href}"`).split(`'${spec}'`).join(`'${pathToFileURL(stub).href}'`)
}
const target = path.join(dir, 'plugin.mjs')
fs.writeFileSync(target, src)
globalThis.window = globalThis
// Warm the ESM loader and the stand-ins first, so the measurement is the bundle's own evaluation.
const empty = path.join(dir, 'empty.mjs')
fs.writeFileSync(empty, 'export default 1\n')
await import(pathToFileURL(empty).href)
for (const name of Object.values(specs)) await import(pathToFileURL(path.join(dir, `${name}.mjs`)).href)

const c0 = process.cpuUsage()
const t0 = performance.now()
const mod = await import(pathToFileURL(target).href)
const c1 = process.cpuUsage(c0)
const wallMs = performance.now() - t0

const contributions = []
const ctx = {
  register: c => { contributions.push(`${c.area}:${c.id}`); return () => {} },
  registerSettingsPage: p => { contributions.push(`settings:${p.id}`); return () => {} },
  rest: () => Promise.reject(new Error('fetch failed')),
  storage: { get: (k, f) => f, set: () => {}, remove: () => {} },
  os: { notify: () => {}, writeClipboard: async () => false },
  setInterval: () => () => {}, setTimeout: () => () => {}, addEventListener: () => () => {}, onDispose: () => {},
}
let registered = false
try {
  mod.default.register(ctx)
  registered = true
} catch (error) {
  console.error(String(error && error.stack))
}
fs.rmSync(dir, { recursive: true, force: true })
console.log(JSON.stringify({ cpuMs: +((c1.user + c1.system) / 1000).toFixed(1), wallMs: +wallMs.toFixed(1), registered, contributions }))
process.exit(0)
