"""eselsbruecke_toolbox: list the tools and switches, switch one, preview and apply a change, presets,
saved versions and restore."""
from __future__ import annotations

from .. import toolbox
from ..registry import MODULE_IDS

SCHEMA = {
    "name": "eselsbruecke_toolbox",
    "description": (
        "The user's Eselsbrücke toolbox: which helper tools are switched on, their order, presets and saved "
        "versions. action=list shows every tool (ids: " + ", ".join(MODULE_IDS) + ") with its switch; "
        "set_switch {tool, on} switches one; preset {preset: everything|focus|developer|designer}; "
        "preview {changes} returns the diff and a preview_id for any other edit (order, options, layout, "
        "pomodoro rhythm, tips), then apply {preview_id}; versions lists saved versions (author, time, summary); "
        "restore {version}. Change the toolbox only when the user asks. Every save is a version the user can "
        "restore. A switched-off tool's agent actions answer switched_off."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["list", "set_switch", "preview", "apply", "versions", "restore",
                                               "preset"]},
        "tool": {"type": "string", "enum": list(MODULE_IDS), "description": "set_switch: the tool id."},
        "on": {"type": "boolean", "description": "set_switch: true to switch on."},
        "preset": {"type": "string", "enum": list(toolbox.PRESET_ORDER)},
        "changes": {"type": "object", "description": (
            "preview: a partial toolbox, merged into the current one, e.g. {\"modules\": {\"qr\": {\"order\": 0}}, "
            "\"pomodoro\": {\"rhythm\": \"50/10\", \"work\": 50, \"short\": 10}, \"tips\": [{\"title\": ..., \"why\": ...}]}. "
            "Keys: modules, layout {rail, dock, chip}, pomodoro {rhythm, work, short, long, cycles}, tips, alerts.")},
        "preview_id": {"type": "string"},
        "version": {"type": "integer"},
    }, "required": ["action"]},
}


def handle(action: str, args: dict, env) -> dict:
    store, who = env.store, env.author
    if action == "list":
        v = toolbox.view(store)
        return {"preset": v["toolbox"]["preset"],
                "tools": [{"id": t["id"], "title": t["title"], "on": t["on"], "group": t["group"],
                           "agent_tool": t["agent_tool"]} for t in v["tools"]],
                "presets": [p["name"] for p in v["presets"]],
                "pomodoro": v["toolbox"]["pomodoro"], "alerts": v["toolbox"]["alerts"],
                **({"file_error": v["file_error"]} if v.get("file_error") else {})}
    if action == "set_switch":
        out = toolbox.set_switch(store, str(args.get("tool", "")), args.get("on"), who)
        return {"version": out["version"], "summary": out["summary"],
                "note": "The tool list of an open chat changes from the next session on; its actions refuse at once."}
    if action == "preset":
        out = toolbox.apply_preset(store, str(args.get("preset", "")), who)
        return {"version": out["version"], "summary": out["summary"]}
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
