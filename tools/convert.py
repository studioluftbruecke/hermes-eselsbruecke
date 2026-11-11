"""eselsbruecke_convert: time zones and Unix timestamps, base64 and URL, colours and contrast, cron."""
from __future__ import annotations

from .. import clock
from ..engines import convert

SCHEMA = {
    "name": "eselsbruecke_convert",
    "description": (
        "Exact conversions, the same engine as the user's Toolbox page. action=time {time: '2026-11-09 14:30'|"
        "'14:30'|'now', from_zone?, to_zones: [IANA names]}; action=timestamp {value: Unix seconds, "
        "milliseconds or an ISO date, zones?}; action=encode / decode {text, scheme: base64|base64url|url}; "
        "action=colour {colour: '#2f9e6b'|'rgb(47 158 107)'|'hsl(153 54% 40%)'|'oklch(62% 0.13 160)', "
        "background?} gives hex, rgb, hsl, oklch and, with a background, the WCAG contrast ratio with AA/AAA; "
        "action=cron {expression, zone?, count?} explains a cron expression in words with its next runs. "
        "from_zone and zone default to Hermes' time zone."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["time", "timestamp", "encode", "decode", "colour", "cron"]},
        "time": {"type": "string"},
        "from_zone": {"type": "string"},
        "to_zones": {"type": "array", "items": {"type": "string"}},
        "value": {"type": "string"},
        "zones": {"type": "array", "items": {"type": "string"}},
        "text": {"type": "string"},
        "scheme": {"type": "string", "enum": list(convert.SCHEMES)},
        "colour": {"type": "string"},
        "background": {"type": "string"},
        "expression": {"type": "string"},
        "zone": {"type": "string"},
        "count": {"type": "integer"},
    }, "required": ["action"]},
}


def _here() -> str:
    return clock.zone_name() or "UTC"


def handle(action: str, args: dict, env) -> dict:
    try:
        if action == "time":
            return convert.convert_time(str(args.get("time") or "now"), args.get("from_zone") or _here(),
                                        list(args.get("to_zones") or []), clock.now())
        if action == "timestamp":
            return convert.convert_timestamp(args.get("value", ""), list(args.get("zones") or [_here(), "UTC"]))
        if action == "encode":
            return {"scheme": args.get("scheme"), "text": convert.encode(args.get("text", ""), args.get("scheme", ""))}
        if action == "decode":
            return {"scheme": args.get("scheme"), "text": convert.decode(args.get("text", ""), args.get("scheme", ""))}
        if action == "colour":
            return convert.colour(str(args.get("colour", "")), args.get("background"))
        if action == "cron":
            return convert.cron(str(args.get("expression", "")), args.get("zone") or _here(),
                                int(args.get("count") or 5), clock.now())
    except convert.ConvertError as exc:
        return {"ok": False, "error": action, "message": str(exc)}
    raise ValueError(action)
