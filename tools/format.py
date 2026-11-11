"""eselsbruecke_format: format JSON and YAML, convert between them."""
from __future__ import annotations

from ..engines import fmt

SCHEMA = {
    "name": "eselsbruecke_format",
    "description": (
        "Format or validate JSON and YAML exactly as the user's Formatter page does, or convert JSON <-> "
        "YAML. action=format {text, lang: json|yaml, indent?, sort_keys?}; action=convert {text, from: "
        "json|yaml, to: yaml|json}. Parse errors come back with line and column. Markdown, TypeScript, "
        "JavaScript, CSS and HTML are formatted by Prettier on the Formatter page in Hermes Desktop, not here."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["format", "convert"]},
        "text": {"type": "string"},
        "lang": {"type": "string", "enum": ["json", "yaml"]},
        "from": {"type": "string", "enum": ["json", "yaml"]},
        "to": {"type": "string", "enum": ["json", "yaml"]},
        "indent": {"type": "integer"},
        "sort_keys": {"type": "boolean"},
    }, "required": ["action", "text"]},
}


def handle(action: str, args: dict, env) -> dict:
    text = args.get("text", "")
    try:
        if action == "format":
            lang = args.get("lang") or fmt.guess(text)
            return fmt.format_text(text, lang, args.get("indent") or 2, bool(args.get("sort_keys")))
        return fmt.convert(text, args.get("from") or fmt.guess(text), args.get("to") or "", args.get("indent") or 2)
    except fmt.FormatError as exc:
        return {"ok": False, "error": "parse", "message": str(exc), "line": exc.line, "column": exc.column}
