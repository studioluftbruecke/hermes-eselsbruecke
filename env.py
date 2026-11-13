"""One dispatcher for every agent tool: action lookup, the module switch, the unattended refusal.

Every agent handler runs through `run_tool`:
1. the action must be one the tool declares (`registry.TOOLS`), and every argument must have the
   type the tool's schema declares (numbers and booleans sent as text are converted),
2. the action's module must be switched on (`toolbox.require_on`), because a running session keeps
   its tool list after a switch-off and `registry.dispatch` never calls `check_fn`,
3. a write action from the agent is refused in an unattended run before anything
   changes, unless a setting allows it (`unattended_pad_writes` for pad additions),
4. then `tools/<module>.handle(action, args, env)` runs and returns a dict.

Routes do not use this: they are the user's clicks and call the domain modules with author "user".
"""
from __future__ import annotations

import importlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import registry, toolbox
from .store import Store, StoreError


def _no_setting(key: str, default: Any = None) -> Any:
    return default


@dataclass
class Env:
    store: Store
    author: str = "agent"
    get_setting: Callable[[str, Any], Any] = _no_setting
    unattended: Callable[[], Optional[str]] = field(default=lambda: None)
    bridge: Any = None
    package: str = __package__ or "eselsbruecke"


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip():
        return value.strip().lower() not in ("0", "false", "no", "off")
    return default


def tool_module(tool: str, package: str):
    return importlib.import_module(f".tools.{registry.TOOLS[tool]['module']}", package)


_KINDS = {"string": "text", "number": "a number", "integer": "a whole number", "boolean": "true or false",
          "object": "an object", "array": "a list"}


def _typed(value: Any, kind: str) -> Any:
    """`value` as the schema type `kind`; ValueError when it is not one. Agents often send numbers and
    booleans as text and a number where text goes, so "3", "4.5", "false" and 1794245079 are converted;
    some providers send integers as 3.0 and booleans as 1 or 0, which 0.2.0 took, so those are too."""
    if kind == "string":
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return str(value)
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        if isinstance(value, (int, float)) and value in (0, 1):
            return value == 1
    if kind == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float) and math.isfinite(value) and value.is_integer() and abs(value) < 1e18:
            return int(value)
        if isinstance(value, str) and re.fullmatch(r"\s*-?\d{1,18}\s*", value):
            return int(value)
    if kind == "number":
        number = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if isinstance(value, str) and re.fullmatch(r"\s*-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*", value):
            number = float(value)
        if number is not None and math.isfinite(number):
            return number
    if kind == "object" and isinstance(value, dict):
        return value
    if kind == "array" and isinstance(value, list):
        return value
    raise ValueError(_KINDS.get(kind, kind))


def check_args(schema: dict, args: dict) -> dict:
    """The arguments with each declared one checked against its schema type (null means absent). A
    single value where a list goes becomes a one-item list, and a list of objects also takes plain
    text items (the handlers read them as {"text": ...})."""
    props = (schema.get("parameters") or {}).get("properties") or {}
    out = dict(args)
    for key, spec in props.items():
        kind = spec.get("type")
        if out.get(key) is None or kind not in _KINDS:
            continue
        try:
            if kind == "array" and not isinstance(out[key], list):
                out[key] = [out[key]]
            out[key] = _typed(out[key], kind)
            items = (spec.get("items") or {}).get("type")
            if kind == "array" and items in _KINDS:
                out[key] = [item if items == "object" and isinstance(item, str) else _typed(item, items)
                            for item in out[key]]
        except ValueError as exc:
            raise ValueError(f"{key} must be {exc}" + (" (each item)" if kind == "array" else "")) from None
    return out


def run_tool(tool: str, args: Any, env: Env) -> dict:
    spec = registry.TOOLS[tool]
    args = dict(args) if isinstance(args, dict) else {}
    actions = spec["actions"]
    action = args.get("action")
    if action is None and len(actions) == 1:
        action = next(iter(actions))
    if action not in actions:
        return {"ok": False, "error": "unknown_action",
                "message": f"{tool} takes action = one of: {', '.join(actions)}."}
    try:
        module = tool_module(tool, env.package)
        args = check_args(getattr(module, "SCHEMA", {}), args)
        toolbox.require_on(env.store, actions[action])
        if env.author == "agent" and action in spec["writes"]:
            reason = env.unattended()
            if reason and not (tool == "eselsbruecke_pad" and action == "add"
                               and as_bool(env.get_setting("unattended_pad_writes", False))):
                return {"ok": False, "error": "unattended",
                        "message": (f"Refused: {tool} {action} changes the user's data, and this run has no "
                                    f"person at the keyboard ({reason}). Nothing was changed."
                                    + (" The setting 'unattended_pad_writes' allows pad additions from the "
                                       "user's own automations." if tool == "eselsbruecke_pad" else ""))}
        out = module.handle(action, args, env)
    except toolbox.ToolboxError as exc:
        return {"ok": False, "error": exc.code, "message": str(exc), **exc.extra}
    except StoreError as exc:
        return {"ok": False, "error": "store", "message": str(exc)}
    except ValueError as exc:
        return {"ok": False, "error": "invalid", "message": str(exc)}
    except OverflowError as exc:  # a date or timestamp past what Python's datetime can hold
        return {"ok": False, "error": "invalid", "message": f"a value is out of range ({exc})"}
    if isinstance(out, dict) and "ok" not in out:
        out = {"ok": True, **out}
    return out
