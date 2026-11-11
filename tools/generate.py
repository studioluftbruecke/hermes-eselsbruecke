"""eselsbruecke_generate: UUIDs (v4, v7), passwords and passphrases from a cryptographic source."""
from __future__ import annotations

from ..engines import generate

SCHEMA = {
    "name": "eselsbruecke_generate",
    "description": (
        "Random values from Python's `secrets`. action=uuid {version: 4|7, count?}; action=password {length?: 20, "
        "lower?, upper?, digits?, symbols?: true, avoid_ambiguous?: false} returns the password and its "
        "entropy in bits; action=passphrase {words?: 6, separator?: '-', capitalize?, number?} from the EFF "
        "short wordlist (1,296 words). Never store or repeat a generated secret beyond the answer."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["uuid", "password", "passphrase"]},
        "version": {"type": "integer", "enum": [4, 7]},
        "count": {"type": "integer"},
        "length": {"type": "integer"},
        "lower": {"type": "boolean"}, "upper": {"type": "boolean"},
        "digits": {"type": "boolean"}, "symbols": {"type": "boolean"},
        "avoid_ambiguous": {"type": "boolean"},
        "words": {"type": "integer"},
        "separator": {"type": "string"},
        "capitalize": {"type": "boolean"},
        "number": {"type": "boolean"},
    }, "required": ["action"]},
}


def _flag(args: dict, key: str, default: bool) -> bool:
    v = args.get(key)
    return default if v is None else bool(v)


def handle(action: str, args: dict, env) -> dict:
    try:
        if action == "uuid":
            version = int(args.get("version") or 4)
            return {"version": version, "uuids": generate.uuids(version, int(args.get("count") or 1))}
        if action == "password":
            return generate.password(int(args.get("length") or 20), _flag(args, "lower", True),
                                     _flag(args, "upper", True), _flag(args, "digits", True),
                                     _flag(args, "symbols", True), _flag(args, "avoid_ambiguous", False))
        if action == "passphrase":
            return generate.passphrase(int(args.get("words") or 6), str(args.get("separator", "-")),
                                       _flag(args, "capitalize", False), _flag(args, "number", False))
    except generate.GenerateError as exc:
        return {"ok": False, "error": action, "message": str(exc)}
    raise ValueError(action)
