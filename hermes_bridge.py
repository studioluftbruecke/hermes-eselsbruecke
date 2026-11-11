"""The only module that imports Hermes internals beyond `hermes_constants` and `hermes_time`.

- `dispatch(tool, args, ctx=None)`: inside an agent turn through `ctx.dispatch_tool` (the plugin's
  scope); in a dashboard route (no ctx, P8) by importing the built-in tool module so the tool
  registers, then `tools.registry.registry.dispatch` (P5, Q5).
- `has_tool(name)`: whether a tool (Unblockbrücke's card) is registered in this process.
"""
from __future__ import annotations

import contextvars
import importlib
import json
import os
from typing import Any, Optional

# The ctx of the agent turn this call runs in (set by the plugin's handler), so code deep below a
# tool call (a toolbox save that reconciles the alert job) dispatches with the plugin's scope.
CURRENT_CTX: contextvars.ContextVar = contextvars.ContextVar("eselsbruecke_ctx", default=None)

# Built-in tools a route may need, and the module that registers each (P5, Q5).
TOOL_MODULES = {"cronjob_manage": "tools.cronjob_tools", "kanban_create": "tools.kanban_tools"}


class BridgeError(Exception):
    pass


def _json(result: Any) -> dict:
    if isinstance(result, dict):
        return result
    try:
        out = json.loads(result)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_answer", "raw": str(result)[:500]}
    return out if isinstance(out, dict) else {"ok": False, "error": "bad_answer", "raw": str(out)[:500]}


def dispatch(tool: str, args: dict, ctx: Any = None) -> dict:
    """Call a Hermes tool and return its JSON answer as a dict. Raises BridgeError when it cannot be
    reached at all (the caller falls back to a chat draft)."""
    ctx = ctx if ctx is not None else CURRENT_CTX.get()
    if ctx is not None and callable(getattr(ctx, "dispatch_tool", None)):
        try:
            return _json(ctx.dispatch_tool(tool, args))
        except Exception as exc:
            raise BridgeError(f"{tool} through ctx failed: {type(exc).__name__}: {exc}") from exc
    try:
        from tools.registry import registry

        if registry.get_entry(tool) is None and tool in TOOL_MODULES:
            importlib.import_module(TOOL_MODULES[tool])
        if registry.get_entry(tool) is None:
            raise BridgeError(f"{tool} is not available in this Hermes")
        return _json(registry.dispatch(tool, args))
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError(f"{tool} failed: {type(exc).__name__}: {exc}") from exc


def has_tool(name: str) -> bool:
    try:
        from tools.registry import registry

        return registry.get_entry(name) is not None
    except Exception:
        return False


# --- unattended detection (agent handlers only; routes never call it, constraint 11) ---------------
# Restated from Hermes' own rule (tools/approval_context.py is not a public import): a run is
# unattended when it is a cron job, a single-query `hermes chat -q` / `-z` run, or a session on the
# webhook, msgraph_webhook or api_server surface. Under `plugins.isolation: host` the gateway's
# markers are not visible in the host child, so a CLI or one-shot surface there fails closed.

UNATTENDED_PLATFORMS = frozenset({"webhook", "msgraph_webhook", "api_server"})
HOST_BLIND_SURFACES = frozenset({"", "cli", "oneshot"})


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _session_env(name: str) -> str:
    try:
        from gateway.session_context import get_session_env

        return get_session_env(name, "") or ""
    except Exception:
        return os.environ.get(name, "") or ""


def _finite_turn() -> Optional[bool]:
    """True on a gateway-admitted `chat -q`/`-z` turn; None when the private marker cannot be read.
    `gateway.session_finite` is not in Hermes' published plugin API and no ctx call says it (X20); a
    turn whose marker cannot be read is refused below (fail closed), never treated as attended."""
    try:
        from gateway.session_finite import finite_turn_required
    except ImportError:
        return None
    try:
        return finite_turn_required() is True
    except Exception:
        return None


def unattended_reason(ctx: Any = None, environ: Optional[dict] = None) -> Optional[str]:
    """Why no person is at the keyboard, or None in an attended chat."""
    env = os.environ if environ is None else environ
    surface = ""
    try:
        surface = (ctx.session_surface() if ctx is not None else "") or ""
    except Exception:
        surface = ""
    surface = str(surface).strip().lower()
    if env.get("HERMES_PLUGIN_HOST_PROCESS") == "1" and surface in HOST_BLIND_SURFACES:
        return ("Eselsbrücke runs in a plugin host (plugins.isolation: host), where a one-shot or CLI turn "
                "cannot be told from an attended one; set plugins.isolation: in_process to allow writes here")
    cron = False
    try:
        cron = ctx is not None and ctx.current_cron_execution() is not None
    except Exception:
        cron = False
    if cron or _truthy(_session_env("HERMES_CRON_SESSION")):
        return "a scheduled job"
    finite = _finite_turn()
    if finite is None and env.get("HERMES_PLUGIN_HOST_PROCESS") != "1":
        return "this Hermes version moved its one-shot marker (gateway.session_finite); update Eselsbrücke"
    if finite or _truthy(_session_env("HERMES_SINGLE_QUERY_SESSION")):
        return "a single-query run (hermes chat -q or -z)"
    platform = surface or _session_env("HERMES_SESSION_PLATFORM").strip().lower()
    if platform in UNATTENDED_PLATFORMS:
        return f"the unattended {platform} surface"
    return None


def current_profile() -> Optional[str]:
    """The running profile's name (`default` for the root home), or None outside Hermes."""
    try:
        from hermes_constants import get_hermes_home

        home = get_hermes_home()
    except Exception:
        return None
    parts = str(home).rstrip("/").split("/")
    if len(parts) >= 2 and parts[-2] == "profiles":
        return parts[-1]
    return "default"
