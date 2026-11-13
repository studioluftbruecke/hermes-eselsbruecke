"""eselsbruecke_text: diff two texts, test a Python regex, count characters, words, lines, tokens."""
from __future__ import annotations

from ..engines import text as engine

SCHEMA = {
    "name": "eselsbruecke_text",
    "description": (
        "Text tools. action=diff {left, right} gives changed, added and removed lines with word changes and a "
        "unified diff; action=regex {pattern, text, flags?: i m s x} tests a Python `re` pattern (the user's "
        "Regex tester page uses JavaScript RegExp, so name the flavour) and lists up to 200 matches and groups "
        "(clipped: true when long match text was cut); "
        "action=count {text} gives characters, words, lines, bytes and tokens_estimate, Hermes' own estimate "
        "(UTF-8 bytes / 4), labelled as an estimate; the exact o200k count is on the Token counter page."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["diff", "regex", "count"]},
        "left": {"type": "string"},
        "right": {"type": "string"},
        "pattern": {"type": "string"},
        "text": {"type": "string"},
        "flags": {"type": "string"},
    }, "required": ["action"]},
}


def handle(action: str, args: dict, env) -> dict:
    try:
        if action == "diff":
            out = engine.diff(args.get("left", ""), args.get("right", ""))
            if len(out["rows"]) > 400:  # the model gets the unified diff; the page asks the route for rows
                out["rows"] = out["rows"][:400]
                out["rows_truncated"] = True
            return out
        if action == "regex":
            return engine.regex(args.get("pattern", ""), args.get("text", ""), args.get("flags", "") or "")
        if action == "count":
            return engine.count(args.get("text", ""))
    except engine.TextError as exc:
        return {"ok": False, "error": action, "message": str(exc)}
    raise ValueError(action)
