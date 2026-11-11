"""The tool registry: one row per toolbox tool (MODULES) and one per agent tool (TOOLS).

Read by the toolbox file's validation, the settings page and the Toolbox page (through `/toolbox`),
`check_fn` and every agent handler. Adding a tool is one MODULES row plus its engine. Every agent
action belongs to exactly one module (`TOOLS[...]["actions"]`); a tool is hidden from the agent only
when all its modules are off, and its handler refuses an action whose module is off (constraint 16).
`None` as a module means the action is the toolbox's own and never switched off.
"""
from __future__ import annotations

from typing import Optional

GROUPS = ("focus", "code", "convert", "design", "engine")

# id, title, group, default_on, surfaces, agent_tool, engine, offline (works without the backend),
# fixture (unit fixture file), blurb (one line, the settings page and "what is this").
MODULES: list[dict] = [
    {"id": "pad", "title": "Today's pad", "group": "focus", "agent_tool": "eselsbruecke_pad",
     "engine": "python", "offline": "read-only", "surfaces": ["page", "dock", "palette", "keybind"],
     "blurb": "Short lines for today. Unchecked lines roll to tomorrow."},
    {"id": "pomodoro", "title": "Pomodoro", "group": "focus", "agent_tool": "eselsbruecke_timer",
     "engine": "both", "offline": "outbox", "surfaces": ["page", "dock", "chip", "palette"],
     "blurb": "Work and break follow each other without a click."},
    {"id": "timelog", "title": "Time log", "group": "focus", "agent_tool": "eselsbruecke_timelog",
     "engine": "python", "offline": "outbox", "surfaces": ["page", "dock", "chip", "palette"],
     "blurb": "Billable time per client and project, weekly totals, CSV."},
    {"id": "formatter", "title": "Formatter", "group": "code", "agent_tool": "eselsbruecke_format",
     "engine": "both", "offline": "yes", "surfaces": ["page", "dock", "palette"],
     "blurb": "Format JSON, YAML, Markdown, TypeScript, CSS, HTML. JSON to YAML and back."},
    {"id": "diff", "title": "Text diff", "group": "code", "agent_tool": "eselsbruecke_text",
     "engine": "python", "offline": "no", "surfaces": ["page", "dock", "palette"],
     "blurb": "Two texts, the lines and words that changed."},
    {"id": "regex", "title": "Regex tester", "group": "code", "agent_tool": "eselsbruecke_text",
     "engine": "desktop", "offline": "yes", "surfaces": ["page", "dock", "palette"],
     "blurb": "Matches and groups highlighted as you type (JavaScript flavour)."},
    {"id": "tokens", "title": "Token counter", "group": "code", "agent_tool": "eselsbruecke_text",
     "engine": "desktop", "offline": "estimate", "surfaces": ["page", "dock", "palette"],
     "blurb": "Characters, words, lines and tokens of a prompt."},
    {"id": "cron", "title": "Cron explainer", "group": "code", "agent_tool": "eselsbruecke_convert",
     "engine": "python", "offline": "no", "surfaces": ["page", "dock", "palette"],
     "blurb": "A cron expression in words, with the next runs."},
    {"id": "encode", "title": "Encode, decode", "group": "convert", "agent_tool": "eselsbruecke_convert",
     "engine": "both", "offline": "yes", "surfaces": ["page", "dock", "palette"],
     "blurb": "Base64 and URL encoding, both ways."},
    {"id": "timezones", "title": "Time zones", "group": "convert", "agent_tool": "eselsbruecke_convert",
     "engine": "both", "offline": "yes", "surfaces": ["page", "dock", "palette"],
     "blurb": "A time in several zones, Unix timestamps to dates and back."},
    {"id": "generate", "title": "UUID, password", "group": "convert", "agent_tool": "eselsbruecke_generate",
     "engine": "both", "offline": "yes", "surfaces": ["page", "dock", "palette"],
     "blurb": "UUID v4 and v7, passwords and passphrases."},
    {"id": "colour", "title": "Colour picker", "group": "design", "agent_tool": "eselsbruecke_convert",
     "engine": "both", "offline": "yes", "surfaces": ["page", "dock", "palette"],
     "blurb": "hex, rgb, hsl, oklch side by side; contrast against a background."},
    {"id": "qr", "title": "QR code", "group": "design", "agent_tool": None,
     "engine": "desktop", "offline": "yes", "surfaces": ["page", "dock", "palette"],
     "blurb": "Any text or link as a QR code, saved as SVG or PNG."},
    {"id": "calc", "title": "Calculator", "group": "engine", "agent_tool": "eselsbruecke_calc",
     "engine": "python", "offline": "no", "surfaces": [],
     "blurb": "Exact arithmetic for the pad's = lines and the agent: percentages, units, durations, dates."},
]
for _row in MODULES:
    _row.setdefault("default_on", True)
    _row.setdefault("network", "none")
    _row.setdefault("fixture", f"tests/test_{_row['id']}.py")

MODULE_IDS = tuple(m["id"] for m in MODULES)
MODULE_BY_ID = {m["id"]: m for m in MODULES}

# Agent tools: name -> {"module": python module under tools/, "actions": {action: module id or None},
# "writes": actions refused in unattended runs}.
TOOLS: dict[str, dict] = {
    "eselsbruecke_toolbox": {"module": "toolbox",
                             "actions": {a: None for a in ("list", "set_switch", "preview", "apply",
                                                           "versions", "restore", "preset")},
                             "writes": {"set_switch", "apply", "restore", "preset"}},
    "eselsbruecke_pad": {"module": "pad", "actions": {"add": "pad", "undo": "pad"},
                         "writes": {"add", "undo"}},
    "eselsbruecke_timer": {"module": "timer",
                           "actions": {a: "pomodoro" for a in ("start", "pause", "resume", "stop", "status")},
                           "writes": {"start", "pause", "resume", "stop"}},
    "eselsbruecke_timelog": {"module": "timelog",
                             "actions": {a: "timelog" for a in ("start", "stop", "add", "edit", "delete",
                                                                "undo", "week", "export", "clients")},
                             "writes": {"start", "stop", "add", "edit", "delete", "undo", "export"}},
    "eselsbruecke_calc": {"module": "calc", "actions": {"calc": "calc"}, "writes": set()},
    "eselsbruecke_format": {"module": "format", "actions": {"format": "formatter", "convert": "formatter"},
                            "writes": set()},
    "eselsbruecke_convert": {"module": "convert",
                             "actions": {"time": "timezones", "timestamp": "timezones",
                                         "encode": "encode", "decode": "encode",
                                         "colour": "colour", "cron": "cron"},
                             "writes": set()},
    "eselsbruecke_text": {"module": "text", "actions": {"diff": "diff", "regex": "regex", "count": "tokens"},
                          "writes": set()},
    "eselsbruecke_generate": {"module": "generate",
                              "actions": {"uuid": "generate", "password": "generate", "passphrase": "generate"},
                              "writes": set()},
}


def module_of(tool: str, action: str) -> Optional[str]:
    """The module an action belongs to; KeyError for an unknown tool or action."""
    return TOOLS[tool]["actions"][action]


def tool_modules(tool: str) -> set[str]:
    return {m for m in TOOLS[tool]["actions"].values() if m is not None}


def tool_visible(tool: str, is_on) -> bool:
    """A tool is shown to the agent unless every module behind it is switched off."""
    mods = tool_modules(tool)
    return not mods or any(is_on(m) for m in mods)


def public_modules() -> list[dict]:
    """MODULES as the page and the agent see them."""
    return [dict(m) for m in MODULES]
