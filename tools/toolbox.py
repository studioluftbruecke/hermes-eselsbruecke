"""eselsbruecke_toolbox: list the tools and switches, switch one, add or remove a world clock place,
pin a tool to the dashboard, preview and apply any other change, saved versions and restore."""
from __future__ import annotations

from .. import toolbox
from ..registry import MODULE_IDS

SCHEMA = {
    "name": "eselsbruecke_toolbox",
    "description": (
        "The user's Eselsbrücke toolbox: which helper tools are switched on, their dashboard, the world clock's "
        "places and saved versions. action=list shows every tool (ids: " + ", ".join(MODULE_IDS) + ") with its "
        "switch, the dashboard, the clocks and the status bar; set_switch {tool, on} switches one; "
        "set_clock {place, remove?, label?} adds or removes a world clock place (a city like Tokyo or a zone like "
        "Europe/Berlin); set_pin {tool, on} puts a tool on the dashboard or takes it off; "
        "preview {changes} returns the changes in words and a preview_id for any other edit (order, options, "
        "status bar, pomodoro rhythm, tips, or dashboard and clocks as whole lists), then apply {preview_id}; "
        "versions lists saved versions (author, time, summary); restore {version}. Change the toolbox only when "
        "the user asks. Every save is a version the user can restore. A switched-off tool's agent actions answer "
        "switched_off."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["list", "set_switch", "set_clock", "set_pin", "preview", "apply",
                                               "versions", "restore"]},
        "tool": {"type": "string", "enum": list(MODULE_IDS), "description": "set_switch, set_pin: the tool id."},
        "on": {"type": "boolean", "description": "set_switch: true to switch on. set_pin: true to pin."},
        "place": {"type": "string", "description": "set_clock: a city or a zone name."},
        "remove": {"type": "boolean", "description": "set_clock: true to remove the place."},
        "label": {"type": "string", "description": "set_clock: the name to show, up to 40 characters "
                                                   "(default: the city)."},
        "changes": {"type": "object", "description": (
            "preview: a partial toolbox, merged into the current one, e.g. {\"modules\": {\"qr\": {\"order\": 0}}, "
            "\"pomodoro\": {\"rhythm\": \"50/10\", \"work\": 50, \"short\": 10}, \"tips\": [{\"title\": ..., \"why\": ...}]}. "
            "Keys: modules, layout {chip: auto|pomodoro|timelog, chip_visible}, pomodoro {rhythm, work, short, "
            "long, cycles}, tips, alerts, dashboard [tool ids], clocks [{zone, label}]. A list replaces the "
            "current list, so send dashboard and clocks whole, in the order wanted.")},
        "preview_id": {"type": "string"},
        "version": {"type": "integer"},
    }, "required": ["action"]},
}


def _saved(out: dict) -> dict:
    if out.get("unchanged"):
        return {"summary": out["summary"], "unchanged": True}
    return {"version": out["version"], "summary": out["summary"]}


def handle(action: str, args: dict, env) -> dict:
    store, who = env.store, env.author
    if action == "list":
        v = toolbox.view(store)
        doc = v["toolbox"]
        return {"tools": [{"id": t["id"], "title": t["title"], "on": t["on"], "group": t["group"],
                           "agent_tool": t["agent_tool"]} for t in v["tools"]],
                "dashboard": doc["dashboard"], "clocks": doc["clocks"],
                "status_bar": {"visible": doc["layout"]["chip_visible"], "shows": doc["layout"]["chip"]},
                "pomodoro": doc["pomodoro"], "alerts": doc["alerts"],
                **({"file_error": v["file_error"]} if v.get("file_error") else {})}
    if action == "set_switch":
        out = toolbox.set_switch(store, str(args.get("tool", "")), args.get("on"), who)
        return {"version": out["version"], "summary": out["summary"],
                "note": "The tool list of an open chat changes from the next session on; its actions refuse at once."}
    if action == "set_clock":
        remove = args.get("remove", False)
        if not isinstance(remove, bool):  # a guess here would add a place the user asked to remove
            raise ValueError("remove must be true or false")
        out = toolbox.set_clock(store, args.get("place"), who, remove=remove, label=args.get("label"))
        return {**_saved(out), "clocks": out["toolbox"]["clocks"]}
    if action == "set_pin":
        tool = str(args.get("tool", ""))
        out = toolbox.set_pin(store, tool, args.get("on"), who)
        res = {**_saved(out), "dashboard": out["toolbox"]["dashboard"]}
        if args.get("on") and not out["toolbox"]["modules"][tool]["on"]:
            res["note"] = "This tool is switched off, so the dashboard skips it until it is switched on."
        return res
    if action == "preview":
        out = toolbox.preview(store, args.get("changes"), who)
        return {"preview_id": out["preview_id"], "changes": out["changes"],
                "next": "Show the changes to the user; apply with action=apply and this preview_id when they agree."}
    if action == "apply":
        out = toolbox.apply(store, str(args.get("preview_id", "")), who)
        return {"version": out["version"], "summary": out["summary"]}
    if action == "versions":
        return {"versions": toolbox.versions(store)}
    if action == "restore":
        out = toolbox.restore(store, args.get("version"), who)
        return {"version": out["version"], "summary": out["summary"]}
    raise ValueError(action)
