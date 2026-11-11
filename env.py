"""One dispatcher for every agent tool: action lookup, the module switch, the unattended refusal.

Every agent handler runs through `run_tool`:
1. the action must be one the tool declares (`registry.TOOLS`),
2. the action's module must be switched on (`toolbox.require_on`, constraint 16), because a running
   session keeps its tool list after a switch-off and `registry.dispatch` never calls `check_fn`,
3. a write action from the agent is refused in an unattended run (design rule 2) before anything
   changes, unless a setting allows it (`unattended_pad_writes` for pad additions),
4. then `tools/<module>.handle(action, args, env)` runs and returns a dict.

Routes do not use this: they are the user's clicks and call the domain modules with author "user".
"""
from __future__ import annotations

import importlib
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
        out = tool_module(tool, env.package).handle(action, args, env)
    except toolbox.ToolboxError as exc:
        return {"ok": False, "error": exc.code, "message": str(exc), **exc.extra}
    except StoreError as exc:
        return {"ok": False, "error": "store", "message": str(exc)}
    except ValueError as exc:
        return {"ok": False, "error": "invalid", "message": str(exc)}
    if isinstance(out, dict) and "ok" not in out:
        out = {"ok": True, **out}
    return out
