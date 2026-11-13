// Vendored packages as lazy factories. Desktop evaluates every discovered
// plugin.js at start under a 10 s deadline, before it checks whether the plugin is on, so nothing
// heavy runs at module top level: each package is its CommonJS build, `require`d on first use (esbuild
// wraps it in a function that runs once). The o200k ranks are not in the bundle; the page loads them
// from the plugin's own route GET /data/o200k on first use.

let prettierCache = null
/** Prettier with the plugins the formatter needs (Markdown, TypeScript, JavaScript, CSS, HTML, and
 *  JSON and YAML for the "formatted in Desktop" fallback). */
export function prettier() {
  if (!prettierCache) {
    const core = require('prettier/standalone')
    const plugins = [require('prettier/plugins/babel'), require('prettier/plugins/estree'), require('prettier/plugins/typescript'),
      require('prettier/plugins/postcss'), require('prettier/plugins/html'), require('prettier/plugins/markdown'), require('prettier/plugins/yaml')]
    prettierCache = { format: (text, parser) => core.format(text, { parser, plugins }) }
  }
  return prettierCache
}

let qrCache = null
export function qrcode() {
  if (!qrCache) qrCache = require('qrcode-generator')
  return qrCache.default || qrCache
}

let tiktokenCache = null
export function tiktokenLite() {
  if (!tiktokenCache) tiktokenCache = require('js-tiktoken/lite')
  return tiktokenCache
}
