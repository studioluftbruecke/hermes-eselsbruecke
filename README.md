# Eselsbrücke

A helper toolbox for Hermes. Every tool in the box has an on/off switch, so the box holds only what
you use. A today pad for short notes, a pomodoro that moves on by itself, a billable time log, a
formatter, a colour picker and a row of small tools. Your Hermes agent can call the same tools, so
its arithmetic, conversions and formatting come out exact instead of guessed.

"Eselsbrücke" is the German word for a memory aid: a little bridge that gets you across.

Version 0.1.0. Needs Hermes 0.23 or later, and Hermes Desktop 0.23 or later for the Desktop half
(older Desktop builds read at most 512 KiB of a plugin file).

## Where it shows up in Hermes Desktop

- A **Toolbox** page (sidebar row): the tools you switched on in a rail on the left, one tool at a
  time on the right. The first visit asks which set to start with (Everything, Focus, Developer,
  Designer).
- **Beside the chat:** "Open beside chat" puts the toolbox in a pane next to the conversation.
- A **status-bar chip**: the running pomodoro phase or time-log timer, in minutes, and "n not synced"
  while clicks wait for Hermes. Its menu pauses, stops and opens the toolbox.
- **Command palette** rows: open any switched-on tool, add a line to today's pad, start a
  pomodoro, copy a new UUID, open the toolbox beside the chat.
- **Shortcuts** (rebindable): `Cmd+Shift+E` opens the toolbox, `Cmd+Alt+P` adds a line to today's
  pad.
- **Alerts:** a phase end, a countdown or a reminder shows as a toast in Desktop and as a macOS
  notification while Hermes is in the background.
- **Plugin settings** (Capabilities → Plugins → Eselsbrücke → Toolbox): presets, a switch per tool,
  the pomodoro rhythm, what the chip shows, "Alerts while Desktop is closed", Hermes' time zone, and
  the saved versions of your toolbox with restore.
- Every tool has an **Ask Hermes** button: a new chat opens with the tool drafted, and you press send.

## Tools

| Tool | What you get | Your agent |
| --- | --- | --- |
| Today pad | Short notes for today. Unchecked lines roll to tomorrow. A line can be a to-do, a note, a reminder at a time, or a prompt for tomorrow (it waits under "Queued for today" with "Start this chat"). A line can become a kanban card. A line ending in `=` shows its result | Sees the pad only when you attach it (`@pad:today`, `@pad:yesterday`, `@pad:2026-11-09`, `@pad:queued`); adds lines only when you ask, each with an undo |
| Pomodoro | Work and break follow each other without a click (25/5 with a long break after four, 50/10, or your own); a countdown; a tip at each break; "what did you finish?" goes onto the pad as a done line | `eselsbruecke_timer` |
| Time log | Billable timers per client and project, time added afterwards, weekly totals and amounts with an hourly rate, CSV; every entry change is kept and can be undone (a client's rate is a setting and has no undo); a click made while Desktop cannot reach Hermes is synced later with its real time | `eselsbruecke_timelog` |
| Formatter | JSON and YAML through the same engine as the agent; Markdown, TypeScript, JavaScript, CSS and HTML through Prettier in Desktop; JSON to YAML and back | `eselsbruecke_format` (JSON, YAML) |
| Colour picker | hex, rgb, hsl and oklch; WCAG contrast against a background; pick from the screen where Desktop allows it | `eselsbruecke_convert` |
| Text diff | Two texts, line and word changes, a unified diff to copy | `eselsbruecke_text` |
| Regex tester | Matches and groups as you type (JavaScript RegExp) | `eselsbruecke_text` (Python `re`; the page says which flavour) |
| Token counter | Hermes' own estimate at once; the exact o200k count (GPT-4o and later) on request | `eselsbruecke_text` (the estimate) |
| Time zones | A time in one zone shown in others; Unix timestamps both ways | `eselsbruecke_convert` |
| Encode and decode | Base64, Base64URL and URL encoding, UTF-8 | `eselsbruecke_convert` |
| UUID, password | UUID v4 and v7, passwords, passphrases (EFF short word list) | `eselsbruecke_generate` |
| Cron explainer | A cron line in words, with the next runs in your zone | `eselsbruecke_convert` |
| QR code | A QR code for any text or link; copy or download as SVG or PNG | none (Desktop only) |
| Calculator | No page of its own: the engine behind the pad's `=` lines and your agent's exact arithmetic (percentages, units, durations times rates, dates), with its own switch | `eselsbruecke_calc` |

`eselsbruecke_toolbox` lets the agent list the tools, switch one on or off, preview and apply a
change, or restore a version, when you ask it to; every save keeps a version. A switched-off tool
is refused in a running chat at once and leaves the agent's tool list in the next chat. Every pad
line and time-log entry the agent changes carries its name and can be undone in one step. Client
names and rates have no undo.

When something goes wrong:

- **A hand-edited `toolbox.json` that is not valid** does not take the plugin down. Eselsbrücke
  uses the newest valid saved version (or the defaults when there is none) and says so on the
  page and in the agent's `list` (`file_error`). Your next save or restore first copies the broken
  file aside as `toolbox.broken-<time>.json`.
- **Clicks while Desktop cannot reach Hermes** wait in an outbox and sync in the order you made
  them, timer clicks and time-log clicks each in their own order, so one stuck click never holds
  back the other kind. A refusal from Hermes drops that click with a message. After 5 failed
  tries, or when a click is more than a day old, it stops and the status-bar chip offers "Try
  again" (sends it once more; Hermes accepts or refuses it) or "Discard it". A new click behind a
  stopped one of its kind says so.
- **The YAML formatter** stops a file whose aliases would expand past 100,000 values and
  characters, so a tiny file cannot become megabytes of JSON.

In scheduled jobs and one-shot runs (`hermes chat -q`), where nobody is at the keyboard, the agent's
writes to the pad, the timer and the time log are refused; read-only actions work.

## Settings

In Capabilities → Plugins → Eselsbrücke → Settings (they are also in `config.yaml`):

| Setting | Default | What it does |
| --- | --- | --- |
| Agent edits to time-log entries | allow | `never`: the agent may start, stop and add, but not edit or delete |
| Your automations may add pad lines | off | On: your scheduled jobs may add pad lines (marked as added by Hermes, with undo) |
| First day of the week | monday | For the weekly totals; the files stay in ISO weeks |

"Today" follows Hermes' own time zone (`timezone` in Hermes' settings). When it is empty, Hermes
uses the server's clock (often UTC), and the settings page says so.

## Disclosures

- **Network calls:** none beyond your own Hermes backend. The Desktop half talks only to this
  plugin's routes there (`/api/plugins/eselsbruecke/...`), including one download of the token
  counter's vocabulary (2.3 MB) when you first ask for an exact count in a Desktop session. The
  formatter (Prettier languages), colour, regex, time zones, encoding, generators, QR code and the
  running pomodoro also work while Desktop cannot reach the backend.
- **Files:** everything lives in the plugin's data folder
  (`<profile>/plugin-data/agent-plugin-eselsbruecke-…`): `toolbox.json` and its last 20 versions
  (plus any `toolbox.broken-*.json` set aside), one pad file per day and `pad/agent_log.jsonl` (the
  agent's pad additions, for undo), `timers.json`, the time log (one JSONL file per ISO week, only
  ever appended), `clients.json` (clients and rates), `presence.json` (Desktop's heartbeat),
  `alerts_state.json` (the alert job's last setup), `tick_state.json` (the alert ledger),
  `tick_errors.jsonl` (the newest 20 alert-job errors), and `exports/` (CSV files the agent writes).
  Desktop keeps a few view choices and the outbox (clicks waiting for Hermes) in its own plugin storage on your Mac.
- **Scheduled jobs:** when "Alerts while Desktop is closed" is on (off by default), the plugin
  creates one Hermes job, `eselsbruecke-alerts`, every minute and without a model, and writes one
  small script, `<profile>/scripts/eselsbruecke_alerts.py`. The script prints only an alert that is
  due and stays silent while Desktop is open (Desktop sends a heartbeat); Hermes delivers what it
  prints to every home channel the profile has. Without a home channel the alert stays in the job's
  run output, and the settings page says so. Turning the switch off removes the job and the script.
  One limit: if you quit Desktop less than 90 s before an alert is due, that alert is not sent
  (the job takes the last heartbeat to mean Desktop showed it).
  If you uninstall the plugin with the switch on, the job stays and prints nothing: remove it with
  `hermes cron list` and `hermes cron remove <id>`.
- **Child processes:** the regex tester's agent tool runs Python's `re` in a short-lived child
  process of the same Python (`-I -S`, an empty working folder, a 2 s limit), so a pattern that never
  finishes cannot hang Hermes. Nothing else starts a process.
- **Hermes tools the plugin calls:** `cronjob_manage` (the alert job) and `kanban_create` (a pad line
  made into a card), through Hermes' own tool registry.
- **Context references:** any `@pad:...` you type in a message attaches that pad to the turn,
  including a message you paste from elsewhere. Profiles that do not enable the plugin get nothing.
- **Bundled code and data:** `desktop/plugin.js` (2.3 MB) carries Prettier 3.9.10, qrcode-generator
  2.0.4, js-tiktoken 1.0.21 (lite) and its dependency base64-js 1.5.1, all MIT, each loaded only on
  first use. `data/o200k_base.json` (2.3 MB) is the o200k vocabulary OpenAI publishes with tiktoken
  (MIT), as js-tiktoken packages it. `data/eff_short_wordlist_1.txt` is the EFF's Short Wordlist #1
  for passphrases, unmodified, under CC BY 3.0 US (attribution to the Electronic Frontier Foundation).
  `THIRD_PARTY_NOTICES.md` carries each licence text and copyright line, and the licences of the
  projects Prettier bundles. `desktop/build/` rebuilds `plugin.js`, the vocabulary and the notices byte
  for byte (`npm ci`, then `HERMES_SOURCE=<Hermes source tree> node build.mjs`); the SHA-256 of each
  is in the release notes. Hermes' install scan says `safe`; its medium and low findings are inside
  the vendored code and the build scripts (character codes, encoded strings, files over 1 MB).
  `.gitleaks.toml` exempts the vocabulary file from the generic API-key rule, because some of its
  base64 tokens look like keys.
- **Credentials:** none.
- **Telemetry:** none.

## Install and update

Hermes Desktop loads the Desktop half (`desktop/plugin.js`) from the computer it runs on, never
from a Hermes on a server. With Hermes on a server, install and update the plugin in both places, on
the same version. With Hermes and Desktop on one computer, one install covers both.

| Where | Install | Update |
| --- | --- | --- |
| Server: tools, routes, the alert job | `hermes -p <profile> plugins install https://github.com/studioluftbruecke/hermes-eselsbruecke --enable` | `hermes -p <profile> plugins update eselsbruecke` |
| Desktop computer: Desktop half | `hermes plugins install https://github.com/studioluftbruecke/hermes-eselsbruecke` | `hermes plugins update eselsbruecke` |

- After either step on the Desktop computer: Capabilities → Plugins → Rescan. A new install's
  Desktop half arrives switched off; switch it on there.
- No Hermes on the Desktop computer: Capabilities → Plugins → Install from Git with the URL; to
  update, the same with Advanced → Force reinstall. Desktop's Update button updates the server only.
- After an update on the server, Desktop chats and the plugin's routes keep the old code: in
  Capabilities → Plugins, switch **Agent in <profile>** off and on, then start a new chat.
- Same version in both places? Compare the Version column of `hermes plugins list` on the Desktop
  computer and `hermes -p <profile> plugins list` on the server, or run
  `git -C ~/.hermes/profiles/<profile>/plugins/eselsbruecke log -1 --oneline` on each
  (`~/.hermes/plugins/eselsbruecke` for the default profile).
- The plugin's settings page shows a reminder with the Desktop-side update command whenever Desktop
  is connected to a Hermes on another computer.

## License

MIT, see `LICENSE`. Third-party parts: `THIRD_PARTY_NOTICES.md`.
