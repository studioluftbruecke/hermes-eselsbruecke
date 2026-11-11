# Changelog

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
