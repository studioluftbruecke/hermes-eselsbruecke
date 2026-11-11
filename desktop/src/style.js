// One scoped <style> for the whole plugin (only Tailwind classes Desktop itself compiled exist, so the
// plugin brings its own few rules), every colour from Desktop's theme variables. Radius rule from the
// mockup: panels 10, controls 7, chips and switches full.
import { jsx } from 'react/jsx-runtime'

const CSS = `
.esb { --esb-fg: var(--ui-text-primary, currentColor); --esb-muted: var(--ui-text-tertiary, var(--ui-text-secondary));
  --esb-line: var(--ui-stroke-secondary); --esb-acc: var(--ui-accent); --esb-sunk: var(--ui-bg-tertiary, transparent);
  --esb-card: var(--ui-bg-card, transparent); --esb-acc-soft: color-mix(in srgb, var(--ui-accent) 14%, transparent);
  --esb-acc-line: color-mix(in srgb, var(--ui-accent) 45%, var(--ui-stroke-secondary)); --esb-red: var(--ui-red);
  color: var(--esb-fg); font-size: 13px; min-width: 0; }
.esb *, .esb *::before, .esb *::after { box-sizing: border-box; }
.esb h1 { font-size: 17px; margin: 0; font-weight: 650; letter-spacing: -.01em; }
.esb h2 { font-size: 14px; margin: 0; font-weight: 620; }
.esb h3 { font-size: 12.5px; margin: 0 0 6px; font-weight: 600; }
.esb p { margin: 0; }
.esb .muted { color: var(--esb-muted); }
.esb .mono { font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace); }
.esb .small { font-size: 12px; }
.esb .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.esb .col { display: grid; gap: 8px; min-width: 0; }
.esb .grow { flex: 1; min-width: 0; }
.esb .page { display: grid; grid-template-rows: auto minmax(0, 1fr); height: 100%; min-height: 0; }
.esb .head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 12px 16px; border-bottom: 1px solid var(--esb-line); }
.esb .body { display: grid; grid-template-columns: 206px minmax(0, 1fr); min-height: 0; }
.esb.narrow .body { grid-template-columns: minmax(0, 1fr); }
.esb.narrow .rail { display: none; }
.esb .rail { border-right: 1px solid var(--esb-line); padding: 10px 8px; display: flex; flex-direction: column; gap: 1px; overflow: auto; min-width: 0; }
.esb .grp { font-size: 11px; color: var(--esb-muted); padding: 8px 8px 3px; }
.esb .ri { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-radius: 7px; border: 0; background: transparent; color: inherit;
  font: inherit; text-align: left; cursor: pointer; width: 100%; }
.esb .ri:hover { background: var(--ui-row-hover-background, var(--esb-sunk)); }
.esb .ri.on { background: var(--esb-acc-soft); }
.esb .ri .mk { width: 20px; height: 20px; border-radius: 6px; display: grid; place-items: center; font: 600 10.5px var(--font-mono, monospace);
  background: var(--esb-sunk); color: var(--esb-muted); flex: none; }
.esb .ri.on .mk { background: var(--esb-acc); color: var(--ui-bg-editor); }
.esb .ri .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.esb .canvas { padding: 14px 16px 24px; overflow: auto; min-width: 0; }
.esb .toolhead { display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; margin-bottom: 12px; }
.esb .toolhead p { color: var(--esb-muted); font-size: 12.5px; max-width: 70ch; }
.esb .panel { border: 1px solid var(--esb-line); border-radius: 10px; padding: 12px; min-width: 0; background: var(--esb-card); }
.esb .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.esb .field { display: grid; gap: 3px; min-width: 0; }
.esb .field > span { font-size: 11.5px; color: var(--esb-muted); }
.esb .inp { font: inherit; font-size: 12.5px; color: inherit; background: transparent; border: 1px solid var(--esb-line); border-radius: 7px; padding: 4px 7px; min-width: 0; }
.esb textarea.inp { font-family: var(--font-mono, ui-monospace, monospace); font-size: 12px; line-height: 1.5; resize: vertical; width: 100%; min-height: 120px; }
.esb .btn { font: inherit; font-size: 12.5px; border: 1px solid var(--esb-line); background: transparent; color: inherit; border-radius: 7px; padding: 3px 10px; cursor: pointer; white-space: nowrap; }
.esb .btn:hover { background: var(--ui-control-hover-background, var(--esb-sunk)); }
.esb .btn.pri { background: var(--esb-acc-soft); border-color: var(--esb-acc-line); }
.esb .btn:disabled { opacity: .5; cursor: default; }
.esb .link { font: inherit; font-size: 12px; background: none; border: 0; color: var(--esb-acc); padding: 0; cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.esb .out { font: 12px/1.5 var(--font-mono, ui-monospace, monospace); white-space: pre-wrap; word-break: break-word; background: var(--esb-sunk);
  border: 1px solid var(--esb-line); border-radius: 7px; padding: 8px 10px; min-height: 34px; margin: 0; }
.esb .out.err { border-color: color-mix(in srgb, var(--esb-red) 55%, var(--esb-line)); }
.esb .kv { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 4px 10px; align-items: center; font-size: 12.5px; }
.esb .kv .k { color: var(--esb-muted); }
.esb .kv .v { font-family: var(--font-mono, monospace); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.esb .note { font-size: 12px; color: var(--esb-muted); }
.esb .banner { border: 1px dashed var(--esb-line); border-radius: 10px; padding: 8px 10px; font-size: 12.5px; color: var(--esb-muted); margin-bottom: 10px; }
.esb .chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; border: 1px solid var(--esb-line); border-radius: 999px; padding: 1px 9px; color: var(--esb-muted); white-space: nowrap; }
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
.esb .pline .res { font-family: var(--font-mono, monospace); color: var(--esb-acc); }
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
.esb .tl td.n { font-family: var(--font-mono, monospace); text-align: right; white-space: nowrap; }
.esb .swatch { height: 64px; border-radius: 10px; border: 1px solid var(--esb-line); display: grid; place-items: center; font-weight: 600; }
.esb .verdict { font: 600 11px var(--font-mono, monospace); border-radius: 4px; padding: 0 5px; }
.esb .verdict.pass { background: var(--esb-acc-soft); }
.esb .verdict.fail { background: color-mix(in srgb, var(--esb-red) 16%, transparent); }
.esb mark.m { background: color-mix(in srgb, var(--esb-acc) 30%, transparent); color: inherit; border-radius: 3px; }
.esb .dl { font: 12px/1.5 var(--font-mono, monospace); white-space: pre-wrap; word-break: break-word; }
.esb .dl .add { background: var(--ui-diff-add-background, color-mix(in srgb, var(--esb-acc) 16%, transparent)); }
.esb .dl .del { background: var(--ui-diff-remove-background, color-mix(in srgb, var(--esb-red) 14%, transparent)); }
.esb .dl .ln { color: var(--esb-muted); display: inline-block; min-width: 3.5ch; text-align: right; margin-right: 1ch; user-select: none; }
.esb .qr svg { width: 200px; height: 200px; }
/* The QR code keeps its own black on white: a scanner needs that contrast whatever the theme. */
.esbchip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; border: 1px solid var(--ui-stroke-secondary); border-radius: 999px;
  padding: 0 8px; height: 20px; background: transparent; color: var(--ui-text-secondary); cursor: pointer; font-family: inherit; white-space: nowrap; }
.esbchip.live { color: var(--ui-text-primary); border-color: color-mix(in srgb, var(--ui-accent) 45%, var(--ui-stroke-secondary));
  background: color-mix(in srgb, var(--ui-accent) 14%, transparent); }
.esbchip .ring { width: 11px; height: 11px; border-radius: 50%; flex: none;
  background: conic-gradient(var(--ui-accent) var(--p, 0%), color-mix(in srgb, var(--ui-text-primary) 14%, transparent) 0); }
.esbchip .warn { color: var(--ui-orange, var(--ui-text-primary)); }
@media (prefers-reduced-motion: reduce) { .esb * { transition: none !important; } }
`

export const Style = () => jsx('style', { children: CSS })
