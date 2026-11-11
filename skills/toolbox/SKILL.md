---
name: toolbox
description: "Use Eselsbrücke's helper tools: which tool answers what, pad and time-log rules, undo."
version: 0.1.0
---

# Eselsbrücke toolbox

Eselsbrücke is the user's helper toolbox: a today pad, a pomodoro that runs itself, a billable time
log, a formatter, a colour picker and small tools. Every tool has a switch. You call the same engines
the user's Toolbox page uses, so your answers match theirs exactly.

## Which tool answers what

| The user asks | Tool and action |
|---|---|
| Arithmetic, percentages, "16,90 * 12", units ("5 km in mi"), "2h 30m * 85 €/h", dates ("2026-11-09 + 30 days") | `eselsbruecke_calc` |
| Format or check JSON / YAML, JSON to YAML and back | `eselsbruecke_format` (`format`, `convert`) |
| A time in other zones, a Unix timestamp | `eselsbruecke_convert` `time`, `timestamp` |
| base64 / URL encode or decode | `eselsbruecke_convert` `encode`, `decode` |
| A colour in hex, rgb, hsl, oklch; contrast ratio | `eselsbruecke_convert` `colour` |
| What a cron expression means, its next runs | `eselsbruecke_convert` `cron` |
| Diff two texts, test a Python regex, count characters and estimated tokens | `eselsbruecke_text` `diff`, `regex`, `count` |
| A UUID, a password, a passphrase | `eselsbruecke_generate` |
| Add something to today's pad, a reminder, a prompt for tomorrow | `eselsbruecke_pad` `add` |
| Start, pause, resume, stop or check a pomodoro or countdown | `eselsbruecke_timer` |
| Billable time: start, stop, add, edit, delete, totals, CSV | `eselsbruecke_timelog` |
| Switch tools on or off, presets, rearrange, restore a version | `eselsbruecke_toolbox` |

Prefer these tools over mental arithmetic or a guessed conversion: the answer is then exact and
identical to what the user sees on the page.

## Rules

- **The pad is the user's.** You read it only when they attach it (`@pad:today`, `@pad:yesterday`,
  `@pad:2026-11-09`, `@pad:queued`). There is no read action. Add lines only when the user asks,
  and tell them they can undo (`eselsbruecke_pad` `undo` removes your last addition).
- **Time log changes carry your name.** Every change you make is recorded with author `agent` and
  can be undone with `eselsbruecke_timelog` `undo`. If the setting `agent_timelog_edits` is `never`,
  edit and delete are refused: say so, do not look for another way.
- **Toolbox changes only on request.** Use `preview`, show the changes, then `apply`. Every save is a
  version the user can restore.
- **`switched_off`** means the user switched that tool off. Say so and offer to switch it on; never
  work around it.
- **`unattended`** means no person is at the keyboard (a scheduled job or a one-shot run): writes
  are refused before anything changes. Report it; do not retry.
- **Regex flavour:** `eselsbruecke_text` `regex` tests Python `re`. The user's Regex tester page uses
  JavaScript `RegExp`; say which flavour you tested when it matters.
- **Tokens:** `count` gives Hermes' own chars/4 estimate, labelled as an estimate. The exact o200k
  count is on the user's Token counter page.
- **Stale plugin:** if a tool answers without a field this skill names (for example no `estimate`
  label on `count`), an older plugin version is loaded. Say that instead of patching the output.
