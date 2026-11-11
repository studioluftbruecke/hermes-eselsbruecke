// CSS of the tool pages (world clock, pad, time log), added to the plugin's one <style> by style.js.
// Every selector starts with `.esb `, every colour is one of the --esb-* variables style.js defines.
// The world clock's rules all sit under its own roots (.clock, .cfull, .cstamp), so a dashboard rule
// for a class of the same name does not change the tool page, and these do not reach the dashboard.
export const TOOLS_CSS = `
.esb .badge.acc { border-color: var(--esb-acc-line); color: var(--esb-fg); background: var(--esb-acc-soft); }
.esb .clock { container: esbclock / inline-size; gap: 12px; }
.esb .clock .picker { position: relative; }
.esb .clock .picker input { width: 100%; padding: 7px 10px; text-overflow: ellipsis; }
.esb .clock .picker .note { margin-top: 6px; }
.esb .clock .results { position: absolute; left: 0; right: 0; top: 36px; border-radius: 9px; padding: 4px; display: grid; background: var(--ui-bg-elevated);
  border: 1px solid var(--esb-line); box-shadow: var(--shadow-md); z-index: 5; }
.esb .clock .results button { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 12px; align-items: baseline; text-align: left; border: 0;
  background: transparent; padding: 6px 8px; border-radius: 6px; font: inherit; color: inherit; cursor: pointer; }
.esb .clock .results button.first { background: var(--esb-sunk); }
.esb .clock .results .z { color: var(--esb-muted); font-size: 11.5px; }
.esb .clock .results .none { color: var(--esb-muted); font-size: 12px; padding: 6px 8px; }
.esb .cfull .cr, .esb .cstamp .cr { display: grid; gap: 10px; align-items: center; }
.esb .cfull .cr { grid-template-columns: 16px minmax(110px, 1.1fr) minmax(120px, 1.4fr) auto 64px 22px; padding: 9px 4px; }
.esb .cstamp .cr { grid-template-columns: 16px minmax(0, 1fr) auto auto; padding: 5px 2px; }
.esb .cfull .cr + .cr, .esb .cstamp .cr + .cr { border-top: 1px solid color-mix(in srgb, var(--esb-line) 65%, transparent); }
.esb .cfull svg.ic { width: 14px; height: 14px; color: var(--esb-muted); fill: none; stroke: currentColor; stroke-width: 1.4; stroke-linecap: round; stroke-linejoin: round; flex: none; }
.esb .cfull .nm, .esb .cstamp .nm { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.esb .cfull .nm b { display: flex; align-items: center; gap: 6px; font-weight: 600; min-width: 0; }
.esb .cfull .nm > span { font-size: 11.5px; color: var(--esb-muted); }
.esb .cfull .nm .lbl { font: inherit; color: inherit; background: none; border: 0; padding: 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; cursor: text; border-radius: 4px; }
.esb .cfull .nm .lbl:hover { background: var(--esb-sunk); }
.esb .cfull .nm .inp { width: 100%; }
.esb .cfull .tm, .esb .cstamp .tm { font: 600 14px var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace); font-variant-numeric: tabular-nums; }
.esb .cfull .tm { font-size: 21px; letter-spacing: -.02em; }
.esb .cfull .rl, .esb .cstamp .rl { font-size: 11.5px; color: var(--esb-muted); min-width: 52px; text-align: right; white-space: nowrap; }
.esb .cfull .bar24 { display: grid; grid-template-columns: repeat(24, minmax(0, 1fr)); gap: 1px; height: 10px; }
.esb .cfull .bar24 i { background: color-mix(in srgb, var(--esb-fg) 11%, transparent); border-radius: 1px; }
.esb .cfull .bar24 i.be { background: color-mix(in srgb, var(--esb-acc) 26%, transparent); }
.esb .cfull .bar24 i.bw { background: color-mix(in srgb, var(--esb-acc) 70%, transparent); }
.esb .cfull .bar24 i.now { outline: 1.5px solid var(--esb-fg); outline-offset: 0; }
.esb .cfull .rm { border: 0; background: none; color: var(--esb-muted); cursor: pointer; font: inherit; padding: 0 4px; border-radius: 4px; }
.esb .cfull .rm:hover { color: var(--esb-red); }
.esb .cfull .rm:disabled { opacity: .5; cursor: default; }
.esb .clock.shifted .cfull .tm, .esb .clock.shifted .copyline { color: var(--esb-acc); }
.esb .clock .scrub { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; align-items: center; }
.esb .clock .scrub strong { min-width: 104px; }
.esb .clock .scrub input { width: 100%; accent-color: var(--esb-acc); }
.esb .clock .copyline { font: 12px var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace); color: var(--esb-muted); overflow-wrap: anywhere; flex: 1; min-width: 0; }
.esb .cstamp h3 { margin: 0; color: var(--esb-muted); }
.esb .cstamp .rl { min-width: 68px; }
.esb .cstamp .also { gap: 6px 18px; padding-top: 8px; border-top: 1px solid color-mix(in srgb, var(--esb-line) 65%, transparent); }
.esb .cstamp .pair { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
@container esbclock (max-width: 430px) {
  .esb .cfull .bar24 { display: none; }
  .esb .cfull .cr { grid-template-columns: 16px minmax(0, 1fr) auto 52px 22px; }
  .esb .cfull .rl { min-width: 0; }
  .esb .cstamp .cr { grid-template-columns: minmax(0, 1fr) auto auto; }
  .esb .cstamp .cr > span:first-child { display: none; }
  .esb .cstamp .rl { min-width: 56px; }
}
.esb .pline .tx .t { cursor: text; }
.esb .pline > .inp { width: 100%; }
.esb .pline .hint { font-size: 12px; color: var(--esb-muted); white-space: nowrap; align-self: center; }
.esb .tl td.day { white-space: nowrap; }
.esb .tl td .inp { width: 100%; min-width: 64px; }
.esb .tl td .inp.hm { width: 62px; min-width: 0; }
.esb .tl td .acts { display: flex; gap: 10px; white-space: nowrap; }
`
