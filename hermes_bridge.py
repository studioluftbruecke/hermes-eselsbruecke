"""Where the plugin talks to Hermes beyond `hermes_constants` and `hermes_time`.

- `dispatch(tool, args, ctx=None)`: inside an agent turn through `ctx.dispatch_tool` (the plugin's
  scope). A dashboard route has no ctx: there the alert job and kanban cards go through Hermes'
  public CLI (`hermes cron ...`, `hermes kanban create --json`) as an argument list for the profile's
  home, and any other tool through `tools.registry` when this process has it registered.
- `has_tool(name)`: whether a tool (Unblockbrücke's card) is registered in this process.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# The ctx of the agent turn this call runs in (set by the plugin's handler), so code deep below a
# tool call (a toolbox save that reconciles the alert job) dispatches with the plugin's scope.
CURRENT_CTX: contextvars.ContextVar = contextvars.ContextVar("eselsbruecke_ctx", default=None)

CLI_TIMEOUT_S = 60


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
    if tool in _CLI_TOOLS:
        return _CLI_TOOLS[tool](args)
    try:
        from tools.registry import registry

        if registry.get_entry(tool) is None:
            raise BridgeError(f"{tool} is not available in this Hermes")
        return _json(registry.dispatch(tool, args))
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError(f"{tool} failed: {type(exc).__name__}: {exc}") from exc


# --- Hermes' public CLI, for routes -----------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_JOB_HEAD = re.compile(r"^  (\S+) \[([^\]]+)\]\s*$")
_JOB_ROW = re.compile(r"^    ([A-Za-z ]+):\s+(.*?)\s*$")
_ROW_KEYS = {"Name": "name", "Schedule": "schedule", "Next run": "next_run_at", "Overdue": "next_run_at",
             "Script": "script", "Last run": "last_run"}


def _hermes_command() -> str:
    """The `hermes` of the install this process runs in (a venv keeps it beside its Python), else PATH's:
    on a host with two installs, PATH's could be another version."""
    beside = Path(sys.executable).with_name("hermes")
    if beside.is_file() and os.access(beside, os.X_OK):
        return str(beside)
    found = shutil.which("hermes")
    if found:
        return found
    raise BridgeError("the `hermes` command is not on PATH")


def _profile_home() -> str:
    try:
        from hermes_constants import get_hermes_home

        return str(get_hermes_home())
    except Exception as exc:
        raise BridgeError(f"the profile's Hermes home is unknown here ({type(exc).__name__})") from exc


def _cli(*args: str) -> str:
    """`hermes -p <this profile> <args>` with this profile's home; stdout, or BridgeError with the CLI's
    own reason. The `-p` matters for the default profile: its home is the Hermes root, and there the CLI
    would otherwise follow a sticky `hermes profile use <other>` and act on that profile."""
    env = {k: v for k, v in os.environ.items() if k != "HERMES_PLUGIN_HOST_PROCESS"}
    home = _profile_home()
    env["HERMES_HOME"] = home
    try:
        run = subprocess.run([_hermes_command(), "-p", _profile_name(home), *args], capture_output=True, text=True,
                             timeout=CLI_TIMEOUT_S, env=env, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BridgeError(f"`hermes {' '.join(args[:2])}` did not run: {type(exc).__name__}") from exc
    if run.returncode != 0:
        lines = [ln.strip() for ln in _ANSI.sub("", run.stderr + "\n" + run.stdout).splitlines() if ln.strip()]
        raise BridgeError(f"`hermes {' '.join(args[:2])}` failed: {lines[-1] if lines else 'no output'}"[:300])
    return _ANSI.sub("", run.stdout)


_NO_JOBS = re.compile(r"^No scheduled jobs\b", re.M)


def parse_cron_list(text: str) -> list[dict]:
    """Jobs from `hermes cron list --all`: a `  <id> [<state>]` line, then indented `Label: value` rows.
    The CLI has no machine-readable form, so output in any other layout is a BridgeError: read as "no
    jobs", it would make every reconcile create one more every-minute job."""
    jobs: list[dict] = []
    for line in text.splitlines():
        head = _JOB_HEAD.match(line)
        if head:
            jobs.append({"job_id": head.group(1), "state": head.group(2)})
            continue
        row = _JOB_ROW.match(line)
        if row and jobs and row.group(1) in _ROW_KEYS:
            jobs[-1][_ROW_KEYS[row.group(1)]] = row.group(2)
    if not (jobs and all(j.get("name") for j in jobs)) and not (not jobs and _NO_JOBS.search(text)):
        raise BridgeError("cannot read the job list `hermes cron list` printed (a layout this plugin does not "
                          "know), so no alert job was created or removed; update the plugin")
    for job in jobs:
        last = job.pop("last_run", "")
        job["last_status"] = last.split()[-1] if len(last.split()) > 1 else None
    return jobs


def _cron(args: dict) -> dict:
    action = args.get("action")
    if action == "list":
        return {"success": True, "jobs": parse_cron_list(_cli("cron", "list", "--all"))}
    if action == "create":
        argv = ["cron", "create", str(args["schedule"]), str(args.get("prompt") or ""), "--name", str(args["name"])]
        if args.get("no_agent"):
            argv.append("--no-agent")
        for key, flag in (("script", "--script"), ("deliver", "--deliver"), ("failure_deliver", "--failure-deliver")):
            if args.get(key):
                argv += [flag, str(args[key])]
        if "catch_up" in args:
            argv += ["--catch-up", "on" if args["catch_up"] else "off"]
        created = re.search(r"^Created job: (\S+)\s*$", _cli(*argv), re.M)
        if not created:
            return {"success": False, "error": "`hermes cron create` did not report a job id"}
        return {"success": True, "job_id": created.group(1)}
    if action == "remove":
        _cli("cron", "remove", str(args["job_id"]))
        return {"success": True}
    raise BridgeError(f"cronjob_manage action {action!r} has no CLI form here")


def _kanban_create(args: dict) -> dict:
    argv = ["kanban", "create", "--json"]
    for key, flag in (("body", "--body"), ("assignee", "--assignee")):
        if args.get(key):
            argv += [flag, str(args[key])]
    if args.get("triage"):
        argv.append("--triage")
    argv += ["--", str(args["title"])]  # a title such as "--draft" is text, not a flag
    task = _json(_cli(*argv))
    if not task.get("id"):
        return {"ok": False, "error": task.get("error") or "`hermes kanban create` did not report a task id"}
    return {"ok": True, "task_id": task["id"], "status": task.get("status")}


_CLI_TOOLS = {"cronjob_manage": _cron, "kanban_create": _kanban_create}


def has_tool(name: str) -> bool:
    try:
        from tools.registry import registry

        return registry.get_entry(name) is not None
    except Exception:
        return False


# --- unattended detection (agent handlers only; routes are the user's clicks and never call it) ----
# Restated from Hermes' own rule (tools/approval_context.py is not a public import): a run is
# unattended when it is a cron job, a single-query `hermes chat -q` / `-z` run, or a session on the
# webhook, msgraph_webhook or api_server surface. Under `plugins.isolation: host` the gateway's
# markers are not visible in the host child, so a CLI or one-shot surface there fails closed.

UNATTENDED_PLATFORMS = frozenset({"webhook", "msgraph_webhook", "api_server"})
HOST_BLIND_SURFACES = frozenset({"", "cli", "oneshot"})
MARKER_UNREADABLE = ("this Hermes version does not say whether a person is present, so writes are refused; "
                     "update the plugin")


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _session_env(name: str) -> str:
    try:
        from gateway.session_context import get_session_env

        return get_session_env(name, "") or ""
    except Exception:
        return os.environ.get(name, "") or ""


def _finite_turn() -> Optional[bool]:
    """True on a gateway-admitted `chat -q`/`-z` turn; None when the marker cannot be read, which
    counts as unattended (fail closed)."""
    try:
        # Hermes 0.23.1 has no public signal for a gateway-admitted chat -q/-z turn, so this stays, guarded.
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
    if finite is None:
        return MARKER_UNREADABLE
    if finite or _truthy(_session_env("HERMES_SINGLE_QUERY_SESSION")):
        return "a single-query run (hermes chat -q or -z)"
    platform = surface or _session_env("HERMES_SESSION_PLATFORM").strip().lower()
    if platform in UNATTENDED_PLATFORMS:
        return f"the unattended {platform} surface"
    return None


def _profile_name(home: str) -> str:
    """The profile id Hermes gives `home`: `<name>` for `<root>/profiles/<name>`, `default` for the root
    (and for a home outside any root, which the CLI then takes as its own root)."""
    try:
        from hermes_constants import profile_name_for_home

        return profile_name_for_home(home) or "default"
    except Exception:
        path = Path(home)
        return path.name if path.parent.name == "profiles" else "default"


def current_profile() -> Optional[str]:
    """The running profile's name (`default` for the root home), or None outside Hermes."""
    try:
        return _profile_name(_profile_home())
    except BridgeError:
        return None
