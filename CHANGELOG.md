# Changelog

## 0.2.2

- Time-zone conversion returns the canonical spelling of a known zone on case-insensitive hosts,
  including `UTC` for `utc` and `Europe/Berlin` for `europe/berlin`. Unlisted zones still work.
- Toolbox previews now follow the same unattended-write boundary as applies and restores. A cron or
  one-shot run refuses before creating the preview file.

## 0.2.1

A review round on security and correctness before the catalog's next review. Update both halves: the plugin where Hermes runs and the one Hermes Desktop loads.

- A pad line whose calculation has no finite answer (`0 ^ -1 =`, a huge duration) shows as an error; the rest of the pad, its Markdown and `@pad:` keep working, also for such lines saved by 0.2.0. Markdown and `@pad:` now add the reason to a calculation without an answer (`1 / 0 = (no answer: division by zero)`); a note that only ends in `=` stays as written.
- The calculator computes with the same precision in every Hermes process.
- The time log refuses new entry ids that are not text of up to 64 characters, and rates that are not an amount from 0 to under 1,000,000,000. Entries 0.2.0 stored under a number or a longer id keep working (stop, edit, delete, and a new start stops them); a week-file line or rate 0.2.0 stored that cannot be read at all is skipped and counted instead of breaking the time log.
- A time-log start never replaces an existing entry (also from the agent with "Agent edits to time-log entries: never").
- One malformed op in Desktop's outbox is refused alone; the rest still land.
- Clearing an entry's end while another timer runs is refused, so only one timer runs.
- Time-log CSV cells that start with = + - @ get a leading ' so spreadsheets do not run them.
- During a break the timer draws one Unblockbrücke card per break, not one per page refresh.
- While the plugin is disabled in a profile, the alert job sends nothing (one notice the first time). It reads the profile's config the way Hermes does, managed scope (`/etc/hermes`) included. The README says how to remove the job.
- The alert ledger `alerts_sent.jsonl` keeps its newest 500 rows.
- Tool arguments of the wrong type, and dates or timestamps out of range, get a clear refusal instead of an internal error. Whole numbers sent as `3.0` and booleans sent as `1`/`0` still work as in 0.2.0.
- A regex test answers at most about 50,000 characters of match text (`clipped`, `truncated`).
- Desktop clicks that set up the alert job or make a kanban card run Hermes' own CLI for their profile (`hermes -p <profile> cron`, `hermes -p <profile> kanban create`) instead of importing Hermes' tool modules; the `-p` keeps the default profile's job in the default profile after `hermes profile use <other>`.
- When Hermes does not say whether a person is present in a turn, agent writes are refused everywhere, with one sentence saying so.
- A GitHub Actions job rebuilds the Desktop bundle, the vocabulary and the notices and fails when they differ from the committed files.
- README: install by the catalog name; disclosures for the regex worker, the vocabulary escape and the Hermes packages used.
- The status-bar chip is listed as "Eselsbrücke" in Desktop's right-click menu on the status bar, so it can be hidden there too. "Show in status bar" in the settings now removes the chip from the status bar instead of leaving an empty item, and brings it back when switched on; a change the agent makes shows within a minute or when the window gains focus.

## 0.2.0

Update both halves: the plugin where Hermes runs and the one Hermes Desktop loads. An existing
`toolbox.json` is carried over on first load.

- **Dashboard.** The page opens on a dashboard of the tools you pinned: world clock, open pad lines,
  pomodoro, time-log timer, UUID and colour as live widgets, the other tools as one-click tiles.
  "Edit" moves, removes and adds them. A paste field recognises JSON, a Unix timestamp, a colour,
  Base64, a cron line or a link and opens the matching tool with it.
- **World clock** replaces "Time zones". Search a city to add a place (no zone names to type), see
  each place's time, offset and working hours, move all rows with a slider, copy the result as one
  line. The agent takes city names too and answers "what time is it" for your saved places.
- **No presets.** Every tool is on by default; the first visit shows one card that names each tool
  with a switch.
- **Status-bar chip** is at most 60 px wide (an icon while idle, a ring and minutes while a pomodoro
  runs) and has a "Show in status bar" switch.
- **Today's pad:** the line menu is Desktop's own menu (solid, closes on Escape and on a click
  outside). Click a line to edit it.
- **Time log:** finished entries can be edited in place; a client's rate has a currency, and totals
  and the CSV carry it.
- **Settings page** rebuilt in sections with space between them; tool ids moved into tooltips.
- **Sidebar row:** "Eselsbrücke" sits first in the plugin block below Kanban (position 51). The
  settings page has a "Sidebar" section with a switch "Show in the sidebar" and a position; both
  are kept per Desktop. With the row hidden, the command palette's "Open Eselsbrücke" opens the page.
- What you typed into a tool survives a look at another tool (in memory only).
- The page and the settings say so when Desktop and the Hermes backend run different versions.
- The agent's `eselsbruecke_toolbox` gained `set_clock` and `set_pin` and lost `preset`.

## 0.1.1

- The cards plugin is spelled **Unblockbrücke** (pomodoro break note, docstrings). No behaviour change.
- The sidebar row, page header, beside-chat tab, settings page and status chip read **Eselsbrücke** instead of "Toolbox".

## 0.1.0

- First release: the toolbox with a switch per tool, today's pad, the self-running pomodoro, the time
  log, the formatter, the colour picker and eight small tools, all usable by the agent too.
