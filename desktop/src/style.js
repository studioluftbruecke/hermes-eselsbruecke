// One scoped <style> for the whole plugin (only Tailwind classes Desktop itself compiled exist, so the
// plugin brings its own few rules), every colour from Desktop's theme variables. Radius rule from the
// mockup: panels 10, controls 7, chips and switches full.
// --esb-card is a 4 % tint over transparent: right for a panel in the page, see-through for anything
// that floats. A floating surface (menu, popover, search results) uses var(--ui-bg-elevated).
import { jsx } from 'react/jsx-runtime'

import { TOOLS_CSS } from './style_tools.js'

const CSS = `
.esb { --esb-fg: var(--ui-text-primary, currentColor); --esb-muted: var(--ui-text-tertiary, var(--ui-text-secondary));
  --esb-line: var(--ui-stroke-secondary); --esb-acc: var(--ui-accent); --esb-sunk: var(--ui-bg-tertiary, transparent);
  --esb-card: var(--ui-bg-card, transparent); --esb-acc-soft: color-mix(in srgb, var(--ui-accent) 14%, transparent);
  --esb-acc-line: color-mix(in srgb, var(--ui-accent) 45%, var(--ui-stroke-secondary)); --esb-red: var(--ui-red);
  --esb-mono: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  color: var(--esb-fg); font-size: 13px; line-height: 1.45; min-width: 0; }
.esb, .esb *, .esb *::before, .esb *::after { box-sizing: border-box; }
.esb :focus-visible { outline: 2px solid var(--esb-acc); outline-offset: 1px; }
.esb h1 { font-size: 16px; margin: 0; font-weight: 650; letter-spacing: -.01em; }
.esb h2 { font-size: 15px; margin: 0; font-weight: 640; letter-spacing: -.01em; }
.esb h3 { font-size: 12.5px; margin: 0 0 6px; font-weight: 600; }
.esb p { margin: 0; }
.esb .muted { color: var(--esb-muted); }
.esb .mono { font-family: var(--esb-mono); }
.esb .small { font-size: 12px; }
.esb .one { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.esb .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.esb.col, .esb .col { display: grid; gap: 8px; min-width: 0; }
.esb .grow { flex: 1; min-width: 0; }
.esb .page { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.esb .head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 9px 14px; border-bottom: 1px solid var(--esb-line); flex: none; }
.esb.narrow .head { flex-wrap: nowrap; }
.esb.narrow .head h1, .esb.narrow .head .lbl { display: none; }
.esb.narrow .head select { min-width: 0; flex: 0 1 auto; }
.esb .strip { padding: 6px 14px; border-bottom: 1px solid var(--esb-line); background: var(--esb-sunk); font-size: 12px; color: var(--esb-muted); flex: none; }
.esb .body { display: grid; grid-template-columns: 188px minmax(0, 1fr); flex: 1; min-height: 0; }
.esb.narrow .body { grid-template-columns: minmax(0, 1fr); }
.esb .rail { border-right: 1px solid var(--esb-line); padding: 8px 8px 16px; display: flex; flex-direction: column; gap: 1px; overflow: auto; min-width: 0; }
.esb .grp { font-size: 11px; color: var(--esb-muted); padding: 9px 8px 3px; }
.esb .ri { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-radius: 7px; border: 0; background: transparent; color: inherit;
  font: inherit; text-align: left; cursor: pointer; width: 100%; }
.esb .ri:hover { background: var(--ui-row-hover-background, var(--esb-sunk)); }
.esb .ri.on { background: var(--esb-acc-soft); }
.esb .ri.home { margin-bottom: 2px; font-weight: 600; }
.esb .mk { width: 18px; display: inline-grid; place-items: center; color: var(--esb-muted); flex: none; }
.esb .ri.on .mk { color: var(--esb-fg); }
.esb .ri .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.esb .canvas { padding: 14px 16px 22px; overflow: auto; min-width: 0; }
.esb .toolhead { display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; margin-bottom: 12px; }
.esb .toolhead p { color: var(--esb-muted); font-size: 12.5px; max-width: 70ch; }
.esb .panel { border: 1px solid var(--esb-line); border-radius: 10px; padding: 12px; min-width: 0; background: var(--esb-card); }
.esb .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.esb .field { display: grid; gap: 3px; min-width: 0; }
.esb .field > span { font-size: 11.5px; color: var(--esb-muted); }
.esb .inp { font: inherit; font-size: 12.5px; color: inherit; background: transparent; border: 1px solid var(--esb-line); border-radius: 7px; padding: 4px 7px; min-width: 0; }
.esb input.inp, .esb select.inp { text-overflow: ellipsis; }
.esb textarea.inp { font-family: var(--esb-mono); font-size: 12px; line-height: 1.5; resize: vertical; width: 100%; min-height: 120px; }
.esb .btn { font: inherit; font-size: 12.5px; border: 1px solid var(--esb-line); background: transparent; color: inherit; border-radius: 7px; padding: 3px 10px; cursor: pointer; white-space: nowrap; }
.esb .btn:hover { background: var(--ui-control-hover-background, var(--esb-sunk)); }
.esb .btn.pri { background: var(--esb-acc-soft); border-color: var(--esb-acc-line); }
.esb .btn:disabled { opacity: .5; cursor: default; }
.esb .btn.ico { padding: 3px 6px; display: inline-flex; align-items: center; gap: 5px; min-height: 26px; }
.esb .link { font: inherit; font-size: 12px; background: none; border: 0; color: var(--esb-acc); padding: 0; cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.esb .out { font: 12px/1.5 var(--esb-mono); white-space: pre-wrap; word-break: break-word; background: var(--esb-sunk);
  border: 1px solid var(--esb-line); border-radius: 7px; padding: 8px 10px; min-height: 34px; margin: 0; }
.esb .out.err { border-color: color-mix(in srgb, var(--esb-red) 55%, var(--esb-line)); }
.esb .kv { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 4px 10px; align-items: center; font-size: 12.5px; }
.esb .kv .k { color: var(--esb-muted); }
.esb .kv .v { font-family: var(--esb-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.esb .note { font-size: 12px; color: var(--esb-muted); }
.esb .banner { border: 1px dashed var(--esb-line); border-radius: 10px; padding: 8px 10px; font-size: 12.5px; color: var(--esb-muted); margin-bottom: 10px; }
.esb .chip { display: inline-flex; align-items: center; gap: 6px; font: inherit; font-size: 12px; border: 1px solid var(--esb-line); border-radius: 999px; padding: 1px 9px;
  color: var(--esb-muted); background: transparent; white-space: nowrap; }
.esb button.chip { cursor: pointer; }
.esb .chip.live { color: var(--esb-fg); border-color: var(--esb-acc-line); background: var(--esb-acc-soft); }
.esb .badge { font-size: 11px; border-radius: 999px; padding: 0 7px; border: 1px solid var(--esb-line); color: var(--esb-muted); white-space: nowrap; }
.esb .badge.agent { border-color: var(--esb-acc-line); color: var(--esb-fg); background: var(--esb-acc-soft); }
.esb .badge.roll { border-style: dashed; }
.esb .pline { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 8px; align-items: start; padding: 5px 6px; border-radius: 7px; }
.esb .pline:hover { background: var(--ui-row-hover-background, var(--esb-sunk)); }
.esb .pline input[type=checkbox] { margin: 3px 0 0; accent-color: var(--esb-acc); }
.esb .pline .tx { min-width: 0; overflow-wrap: anywhere; }
.esb .pline.done .tx { color: var(--esb-muted); text-decoration: line-through; }
.esb .pline .meta { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 2px; }
.esb .pline .res, .esb .pl .res { font-family: var(--esb-mono); color: var(--esb-acc); }
.esb .queued { border: 1px dashed var(--esb-acc-line); border-radius: 10px; padding: 8px 10px; margin-bottom: 10px; display: grid; gap: 6px; }
.esb .pomo { display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 16px; align-items: center; }
.esb.narrow .pomo { grid-template-columns: minmax(0, 1fr); justify-items: start; }
.esb .dial { width: 160px; height: 160px; border-radius: 50%; display: grid; place-items: center;
  background: conic-gradient(var(--esb-acc) var(--p, 0%), color-mix(in srgb, var(--esb-fg) 9%, transparent) 0); }
.esb .dial > div { width: 132px; height: 132px; border-radius: 50%; background: var(--ui-bg-editor, var(--esb-card)); display: grid; place-items: center; text-align: center; }
.esb .dial .big { font-size: 30px; font-weight: 650; letter-spacing: -.02em; }
.esb .phases { display: flex; gap: 3px; margin: 8px 0; flex-wrap: wrap; }
.esb .phases i { height: 6px; border-radius: 3px; background: color-mix(in srgb, var(--esb-fg) 12%, transparent); }
.esb .phases i.w { background: color-mix(in srgb, var(--esb-acc) 40%, transparent); }
.esb .phases i.now { outline: 2px solid var(--esb-acc); outline-offset: 1px; }
.esb .phases i.past { background: var(--esb-acc); }
.esb .tip { border-left: 3px solid var(--esb-acc); padding: 6px 10px; background: var(--esb-sunk); border-radius: 0 7px 7px 0; font-size: 12.5px; }
.esb table.tl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.esb .tl th { text-align: left; font-weight: 500; color: var(--esb-muted); padding: 4px 6px; border-bottom: 1px solid var(--esb-line); }
.esb .tl td { padding: 4px 6px; vertical-align: top; }
.esb .tl tr + tr td { border-top: 1px solid color-mix(in srgb, var(--esb-line) 60%, transparent); }
.esb .tl td.n { font-family: var(--esb-mono); text-align: right; white-space: nowrap; }
.esb .swatch { height: 64px; border-radius: 10px; border: 1px solid var(--esb-line); display: grid; place-items: center; font-weight: 600; }
.esb .verdict { font: 600 11px var(--esb-mono); border-radius: 4px; padding: 0 5px; }
.esb .verdict.pass { background: var(--esb-acc-soft); }
.esb .verdict.fail { background: color-mix(in srgb, var(--esb-red) 16%, transparent); }
.esb mark.m { background: color-mix(in srgb, var(--esb-acc) 30%, transparent); color: inherit; border-radius: 3px; }
.esb .dl { font: 12px/1.5 var(--esb-mono); white-space: pre-wrap; word-break: break-word; }
.esb .dl .add { background: var(--ui-diff-add-background, color-mix(in srgb, var(--esb-acc) 16%, transparent)); }
.esb .dl .del { background: var(--ui-diff-remove-background, color-mix(in srgb, var(--esb-red) 14%, transparent)); }
.esb .dl .ln { color: var(--esb-muted); display: inline-block; min-width: 3.5ch; text-align: right; margin-right: 1ch; user-select: none; }
.esb .qr svg { width: 200px; height: 200px; }
/* The QR code keeps its own black on white: a scanner needs that contrast whatever the theme. */

/* Dashboard. The widget grid follows the width of the dashboard itself, so it is right in the page,
   beside the chat and in a narrow window alike. */
.esb .dash { display: grid; gap: 12px; align-content: start; container-type: inline-size; }
.esb .vh { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.esb .paste { display: grid; gap: 6px; }
.esb .paste input { width: 100%; padding: 7px 10px; }
.esb .sugg { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; border: 1px solid var(--esb-acc-line); background: var(--esb-acc-soft); border-radius: 9px; padding: 6px 10px; }
.esb .sugg code { font: 12px var(--esb-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 46ch; min-width: 0; }
.esb .sw16 { width: 16px; height: 16px; border-radius: 4px; border: 1px solid var(--esb-line); flex: none; }
.esb .wgrid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.esb .w { position: relative; border: 1px solid var(--esb-line); border-radius: 10px; padding: 10px 12px 12px; background: var(--esb-card); display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; align-content: start; min-width: 0; }
.esb .w.span2 { grid-column: span 2; }
.esb .w > header { display: flex; align-items: center; gap: 6px; color: var(--esb-muted); min-height: 20px; min-width: 0; }
.esb .w > header button.t { font: inherit; font-size: 12px; font-weight: 600; border: 0; background: none; color: inherit; padding: 0; cursor: pointer; text-align: left; }
.esb .w > header button.t:hover { color: var(--esb-fg); }
.esb .w .inp { width: 100%; }
.esb .w .row > .inp { width: auto; }
@container (max-width: 700px) { .esb .wgrid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@container (max-width: 430px) { .esb .wgrid { grid-template-columns: minmax(0, 1fr); } .esb .w.span2 { grid-column: auto; } }
.esb .wedit { display: flex; gap: 4px; margin-left: auto; }
.esb .wedit button { font: inherit; font-size: 11px; line-height: 18px; min-width: 20px; border: 1px solid var(--esb-line); background: transparent; color: var(--esb-fg); border-radius: 5px; padding: 0 6px;
  cursor: pointer; display: inline-grid; place-items: center; }
.esb .wedit button:disabled { opacity: .4; cursor: default; }
/* three buttons do not fit beside the title of a one-column widget: they take their own line there */
.esb .editing .w > header { flex-wrap: wrap; }
.esb .editing .w, .esb .editing .tile { border-style: dashed; border-color: var(--esb-acc-line); }
.esb .tiles { display: flex; flex-wrap: wrap; gap: 8px; }
.esb .tile { display: inline-flex; align-items: center; gap: 7px; border: 1px solid var(--esb-line); background: var(--esb-card); color: var(--esb-fg); border-radius: 9px; padding: 6px 11px; font: inherit; }
.esb button.tile { cursor: pointer; }
.esb button.tile:hover { border-color: var(--esb-acc-line); }
.esb .tile .x { margin-left: 4px; font-size: 11px; color: var(--esb-muted); }
.esb .addrow { border: 1px dashed var(--esb-line); border-radius: 10px; padding: 10px 12px; display: grid; gap: 8px; }
.esb .addrow h3 { font-size: 12px; margin: 0; color: var(--esb-muted); }
.esb .wbig { font: 650 26px/1.1 var(--esb-mono); letter-spacing: -.03em; font-variant-numeric: tabular-nums; }
.esb .pl { display: grid; grid-template-columns: 16px minmax(0, 1fr); gap: 8px; align-items: start; padding: 4px; border-radius: 7px; }
.esb .pl:hover { background: var(--ui-row-hover-background, var(--esb-sunk)); }
.esb .pl input[type=checkbox] { margin: 3px 0 0; accent-color: var(--esb-acc); }
.esb .pl .tx { overflow-wrap: anywhere; min-width: 0; }
.esb .pl .dot { text-align: center; color: var(--esb-muted); }
.esb .cr { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto auto; gap: 10px; align-items: center; padding: 5px 2px; }
.esb .cr + .cr { border-top: 1px solid color-mix(in srgb, var(--esb-line) 65%, transparent); }
.esb .cr .nm { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.esb .cr .nm .badge { margin-left: 6px; }
.esb .cr .tm { font: 600 14px var(--esb-mono); font-variant-numeric: tabular-nums; }
.esb .cr .rl { font-size: 11.5px; color: var(--esb-muted); min-width: 52px; text-align: right; white-space: nowrap; }
/* day and night there, drawn: the icon font has no sun and no moon */
.esb .sun, .esb .moon { border-radius: 50%; justify-self: center; color: var(--esb-muted); }
.esb .sun { width: 6px; height: 6px; background: currentColor; outline: 1.5px dotted currentColor; outline-offset: 2px; }
.esb .moon { width: 11px; height: 11px; box-shadow: inset -3.5px -1px 0 0 currentColor; }

/* Welcome card and settings */
.esb .welcome { border: 1px solid var(--esb-acc-line); border-radius: 12px; padding: 14px; background: var(--esb-acc-soft); display: grid; gap: 10px; }
.esb .wtools { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 2px 32px; }
.esb .trow { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 9px; align-items: start; padding: 5px 0; }
.esb .trow .mk { margin-top: 1px; }
.esb .trow b { font-weight: 600; display: block; }
.esb .trow .d { font-size: 11.5px; color: var(--esb-muted); display: block; }
.esb.settings, .esb .settings { display: grid; gap: 22px; max-width: 700px; align-content: start; }
.esb.settings > .banner { margin-bottom: 0; }
.esb.settings > section:not(.sec) { margin: 0 !important; } /* the shared sidebar-row block */
.esb .sec { display: grid; gap: 8px; min-width: 0; }
.esb .sec > h3 { font-size: 12.5px; margin: 0; }
.esb .box { border: 1px solid var(--esb-line); border-radius: 10px; background: var(--esb-card); min-width: 0; }
.esb .srow { display: flex; gap: 12px; align-items: center; padding: 8px 12px; min-width: 0; }
.esb .srow + .srow, .esb .srow + .states { border-top: 1px solid color-mix(in srgb, var(--esb-line) 65%, transparent); }
.esb .srow b { font-weight: 600; }
.esb .srow .d, .esb .srow.d, .esb .states .d { font-size: 11.5px; color: var(--esb-muted); }
.esb .seg { display: inline-flex; border: 1px solid var(--esb-line); border-radius: 7px; overflow: hidden; flex: none; }
.esb .seg button { font: inherit; font-size: 12px; border: 0; background: transparent; color: var(--esb-muted); padding: 3px 9px; cursor: pointer; white-space: nowrap; }
.esb .seg button[aria-pressed="true"] { background: var(--esb-acc-soft); color: var(--esb-fg); }
.esb .states { display: flex; flex-wrap: wrap; gap: 10px 18px; padding: 10px 12px; }
.esb .states .st { display: grid; gap: 4px; justify-items: start; }
.esb .states .fake { height: 22px; display: inline-flex; align-items: center; background: var(--esb-sunk); border: 1px solid var(--esb-line); border-radius: 5px; padding: 0 3px; }
.esb .states .esbchip { cursor: default; }

/* The status-bar chip sits outside .esb, so it reads Desktop's variables itself. No border, no pill,
   and never wider than 60 px: the sentence is its tooltip. */
.esbchip { height: 18px; max-width: 60px; display: inline-flex; align-items: center; align-self: center; gap: 4px; padding: 0 4px; border: 0; border-radius: 4px;
  background: transparent; color: var(--ui-text-tertiary); font: inherit; font-size: 11px; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; cursor: pointer; }
.esbchip:hover { background: color-mix(in srgb, var(--ui-text-primary) 9%, transparent); color: var(--ui-text-primary); }
.esbchip.live { color: var(--ui-text-primary); }
.esbchip .codicon { font-size: 13px; }
.esbring { width: 11px; height: 11px; border-radius: 50%; flex: none;
  background: conic-gradient(var(--ui-accent) var(--p, 0%), color-mix(in srgb, var(--ui-text-primary) 22%, transparent) 0);
  -webkit-mask: radial-gradient(circle, transparent 36%, #000 40%); mask: radial-gradient(circle, transparent 36%, #000 40%); }
.esbdot { width: 7px; height: 7px; border-radius: 50%; background: var(--ui-accent); flex: none; }
.esbwait { width: 6px; height: 6px; border-radius: 50%; background: var(--ui-orange, #d9912a); flex: none; }
@media (prefers-reduced-motion: reduce) { .esb * { transition: none !important; } }
`

export const Style = () => jsx('style', { children: CSS + TOOLS_CSS })
