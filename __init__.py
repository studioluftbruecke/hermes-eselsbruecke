"""Eselsbrücke: a helper toolbox for Hermes, with tools you switch on and off.

`register(ctx)` adds the agent tools listed in `REGISTERED` (one row each in `registry.TOOLS`), each
with a `check_fn` that hides it once every tool behind it is switched off, and the bundled skill.
Every handler runs through `env.run_tool`, which refuses a switched-off tool's actions in a running
session too (constraint 16). State lives in `ctx.state.data_dir`; the dashboard routes
(`dashboard/plugin_api.py`) compute the same folder per call.

Sibling modules load lazily: pytest imports this file on its own, and the package name differs
between Hermes, the dashboard and the tests.
"""
from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

PLUGIN = "eselsbruecke"
TOOLSET = "eselsbruecke"
SKILL_NAME = "toolbox"

# Agent tools registered by this version, in registry order. Each milestone adds its tools here and
# to plugin.yaml provides_tools together.
REGISTERED = ("eselsbruecke_toolbox", "eselsbruecke_pad", "eselsbruecke_timer", "eselsbruecke_timelog",
              "eselsbruecke_calc", "eselsbruecke_format",
              "eselsbruecke_convert", "eselsbruecke_text", "eselsbruecke_generate")

logger = logging.getLogger(__name__)


def _mod(name: str):
    return importlib.import_module(f".{name}", __package__ or __name__)


def _state_or_none(ctx) -> Any:
    try:
        state = ctx.state
    except Exception:
        return None
    return state if hasattr(state, "get") and hasattr(state, "set") and hasattr(state, "data_dir") else None


def make_store(ctx):
    """The data folder: `ctx.state.data_dir`, read per call so it follows the turn's profile."""
    store_mod = _mod("store")
    state = _state_or_none(ctx)
    if state is not None:
        return store_mod.Store(lambda: Path(state.data_dir))
    return store_mod.Store(lambda: store_mod.default_root())


def make_env(ctx, store, get_setting):
    env_mod = _mod("env")
    bridge = _mod("hermes_bridge")
    return env_mod.Env(store=store, author="agent", get_setting=get_setting,
                       unattended=lambda: bridge.unattended_reason(ctx), bridge=bridge,
                       package=__package__ or __name__)


def make_handler(tool: str, env_factory):
    def handler(args: dict, **kwargs) -> str:
        bridge = _mod("hermes_bridge")
        token = bridge.CURRENT_CTX.set(getattr(env_factory, "ctx", None))
        try:
            result = _mod("env").run_tool(tool, args, env_factory())
        except Exception as exc:  # never a traceback into the chat
            logger.warning("eselsbruecke: %s failed", tool, exc_info=True)
            result = {"ok": False, "error": "internal", "message": f"{type(exc).__name__}: {exc}"}
        finally:
            bridge.CURRENT_CTX.reset(token)
        return json.dumps(result, ensure_ascii=False)

    handler.__name__ = tool
    return handler


def make_check_fn(tool: str, store):
    registry = _mod("registry")
    toolbox = _mod("toolbox")

    def check() -> bool:
        try:
            return registry.tool_visible(tool, lambda m: toolbox.is_on(store, m))
        except Exception:
            return True  # an unreadable toolbox never hides tools; the handler reports the error

    # Hermes caches check_fn verdicts for 30 s and serves a False within 60 s of the last True as
    # True ("flake grace", tools/registry.py). The switch is config-backed, not a flaky probe, so
    # opt out like Hermes' own config-backed kanban checks do: a switch-off reaches the next session.
    try:
        from tools.registry import no_cache_check_fn

        return no_cache_check_fn(check)
    except Exception:
        return check


def register(ctx) -> None:
    for name in ("store", "clock", "registry", "toolbox", "env", "hermes_bridge", "pad", "reference", "timers",
                 "tips", "alerts", "alerts_tick", "timer_service", "timelog"):
        _mod(name)  # a broken install fails at load, not mid-turn
    registry = _mod("registry")
    env_mod = _mod("env")
    store = make_store(ctx)

    def get_setting(key: str, default: Any = None) -> Any:
        try:
            value = ctx.get_config(key, default)
        except Exception:
            return default
        return default if value is None else value

    def env_factory():
        return make_env(ctx, store, get_setting)

    env_factory.ctx = ctx  # type: ignore[attr-defined]

    for tool in REGISTERED:
        schema = env_mod.tool_module(tool, __package__ or __name__).SCHEMA
        ctx.register_tool(name=tool, toolset=TOOLSET, schema=schema, handler=make_handler(tool, env_factory),
                          check_fn=make_check_fn(tool, store), description=schema["description"], emoji="🧰")
    assert set(REGISTERED) <= set(registry.TOOLS)
    _register_skill(ctx)
    _register_reference(ctx, store)
    if callable(getattr(ctx, "register_cli_command", None)):
        ctx.register_cli_command(name="eselsbruecke", help="Eselsbrücke: the helper toolbox",
                                 setup_fn=_cli_setup, handler_fn=_cli_handler,
                                 description="Eselsbrücke commands: doctor, tick (print due alerts once).")


def _cli_setup(parser) -> None:
    sub = parser.add_subparsers(dest="esel_cmd")
    sub.add_parser("doctor", help="Data folder, time zone, switches, the alert job and the newest tick error")
    sub.add_parser("tick", help="Run the alert tick once and print due alerts (what the scheduled job does)")


def _cli_handler(args) -> int:
    store_mod, alerts = _mod("store"), _mod("alerts")
    store = store_mod.Store(store_mod.default_root())
    if getattr(args, "esel_cmd", None) == "tick":
        lines = _mod("alerts_tick").tick(store.root, Path(__file__).resolve().parent, _mod("clock").zone_name())
        if lines:
            print("\n".join(lines))
        return 0
    print(json.dumps(doctor_report(store, alerts), indent=1, ensure_ascii=False))
    return 0


def doctor_report(store, alerts=None) -> dict:
    """What the plugin can tell about its own state in the running profile."""
    import os

    alerts = alerts or _mod("alerts")
    out: dict = {"data_dir": str(store.root), "data_dir_exists": store.root.exists(),
                 "time_zone": _mod("clock").zone_info()}
    try:
        view = _mod("toolbox").view(store)
        out["tools_on"] = [t["id"] for t in view["tools"] if t["on"]]
    except Exception as exc:
        out["toolbox_error"] = f"{type(exc).__name__}: {exc}"
    out["pad_reference"] = ("not registered: plugins.isolation is host" if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1"
                            else "@pad: (today, yesterday, YYYY-MM-DD, queued)")
    try:
        out["reconcile"] = _mod("timer_service").reconcile_quiet(store)
        out["alerts"] = alerts.status(store, _mod("hermes_bridge").dispatch)
    except Exception as exc:
        out["alerts_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _register_reference(ctx, store) -> None:
    """`@pad:` (M3). Skipped in a plugin host child: there one process would serve the first
    profile's pad to every profile (constraint 12)."""
    import os

    if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1":
        logger.info("eselsbruecke: @pad: not registered under plugins.isolation: host (one host per profile "
                    "cannot tell the calling profile apart)")
        return
    provider = _mod("reference").make_provider(__package__ or __name__, lambda: store)
    if provider is not None and callable(getattr(ctx, "register_context_reference", None)):
        try:
            ctx.register_context_reference(provider)  # a second load's duplicate is refused with a warning
        except Exception:
            logger.info("eselsbruecke: @pad: already registered in this process")


def _register_skill(ctx) -> None:
    skill = Path(__file__).resolve().parent / "skills" / SKILL_NAME / "SKILL.md"
    if callable(getattr(ctx, "register_skill", None)) and skill.exists():
        try:
            ctx.register_skill(SKILL_NAME, skill, "Use Eselsbrücke's helper tools: which tool answers what, "
                                                  "the pad and time-log rules, undo, the toolbox file.")
        except ValueError:
            pass  # already registered by an earlier load in this process
