"""eselsbruecke_pad: add lines to today's pad when the user asks, and undo the agent's last addition.
There is no read action on purpose (A2, R8): the agent sees the pad only through `@pad:`."""
from __future__ import annotations

from .. import pad

SCHEMA = {
    "name": "eselsbruecke_pad",
    "description": (
        "Add lines to the user's today pad, only when the user asks. action=add {lines: [{text, kind?: "
        "todo|note|reminder|prompt, remind_at?: 'HH:MM' or 'YYYY-MM-DDTHH:MM' for a reminder, queued_for?: "
        "'YYYY-MM-DD' for a prompt the user wants to send another day (default tomorrow)}]}; action=undo removes "
        "your last addition. Short lines only: long notes belong in the brain or Obsidian. You cannot read the "
        "pad with this tool: it is the user's, and they attach it with @pad:today when they want you to see it. "
        "Tell the user they can undo."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["add", "undo"]},
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "enum": list(pad.KINDS)},
            "remind_at": {"type": "string"},
            "queued_for": {"type": "string"},
        }, "required": ["text"]}},
    }, "required": ["action"]},
}


def handle(action: str, args: dict, env) -> dict:
    try:
        if action == "add":
            lines = args.get("lines")
            if isinstance(lines, dict):
                lines = [lines]
            if not isinstance(lines, list) and args.get("text"):
                lines = [{"text": args.get("text"), "kind": args.get("kind")}]
            out = pad.add_lines(env.store, [x if isinstance(x, dict) else {"text": x} for x in (lines or [])], "agent")
            return {"date": out["date"], "added": [{"id": x["id"], "text": x["text"], "kind": x["kind"],
                                                    **({"remind_at": x["remind_at"]} if "remind_at" in x else {}),
                                                    **({"queued_for": x["queued_for"]} if "queued_for" in x else {})}
                                                   for x in out["added"]],
                    "undo": "eselsbruecke_pad action=undo removes these lines again"}
        if action == "undo":
            return pad.undo_agent(env.store)
    except pad.PadError as exc:
        return {"ok": False, "error": exc.code, "message": str(exc)}
    raise ValueError(action)
