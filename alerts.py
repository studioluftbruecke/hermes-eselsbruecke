"""Alerts while Desktop is closed (A13): one no-model Hermes job per profile, `eselsbruecke-alerts`,
`every 1m`, running the script this module writes into the profile's `scripts/` folder.

`reconcile()` makes the job exist exactly when the switch `alerts.while_closed` in toolbox.json is on:
it creates the job (deliver `all`: every home channel the profile has, resolved when it fires;
failure notices `local`, so a broken tick never messages anyone), removes duplicates, and with the
switch off removes the job and the script. It runs after every toolbox save, on timer start and stop,
when the page opens and in the doctor. Jobs go through Hermes' own `cronjob_manage` tool
(`hermes_bridge.dispatch`: `ctx.dispatch_tool` in an agent turn, the P5 import in a route).

The script is stdlib only: it runs `alerts_tick.py` from the plugin folder with `runpy`, prints nothing
and exits 0 when the plugin folder is gone, and adds any exception to `tick_errors.jsonl` instead
of failing (a failing script would alert every minute). That file keeps only the newest ERRORS_KEEP rows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from . import clock, toolbox

JOB_NAME = "eselsbruecke-alerts"
SCRIPT_NAME = "eselsbruecke_alerts.py"
SCHEDULE = "every 1m"
PRESENCE = "presence.json"
ERRORS = "tick_errors.jsonl"
ERRORS_KEEP = 20  # X17: a persistent error once grew the file about 1.7 KB a minute without end

SCRIPT = '''# Eselsbrücke alert tick, written by the Eselsbrücke plugin (alerts.py). It runs once a minute as the
# Hermes job "{job}" while "Alerts while Desktop is closed" is on. To stop it: switch that setting
# off in the plugin's settings page, or remove the job. Prints only due alerts; never fails.
import datetime, json, os, runpy, sys, traceback

PLUGIN_DIR = {plugin_dir!r}
DATA_DIR = {data_dir!r}
ZONE = {zone!r}

tick = os.path.join(PLUGIN_DIR, "alerts_tick.py")
if os.path.isfile(tick) and os.path.isdir(DATA_DIR):
    try:
        runpy.run_path(tick)["main"](DATA_DIR, PLUGIN_DIR, ZONE)
    except BaseException as exc:  # never fail: Hermes would deliver an error alert every minute
        try:
            path = os.path.join(DATA_DIR, "tick_errors.jsonl")
            row = json.dumps({{"at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                              "error": f"{{type(exc).__name__}}: {{exc}}",
                              "trace": traceback.format_exc()[-1500:]}})
            try:
                with open(path, encoding="utf-8") as fh:
                    rows = fh.read().splitlines()
            except FileNotFoundError:
                rows = []
            rows = (rows + [row])[-{keep}:]
            with open(path + ".tmp", "w", encoding="utf-8") as fh:
                fh.write("\\n".join(rows) + "\\n")
            os.replace(path + ".tmp", path)
        except Exception:
            pass
sys.exit(0)
'''


def home_of(store) -> Path:
    """The profile home: the data folder is <home>/plugin-data/<namespace>."""
    return store.root.parent.parent


def script_path(store) -> Path:
    return home_of(store) / "scripts" / SCRIPT_NAME


def plugin_dir() -> Path:
    return Path(__file__).resolve().parent


def write_script(store) -> Path:
    path = script_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = SCRIPT.format(job=JOB_NAME, plugin_dir=str(plugin_dir()), data_dir=str(store.root),
                         zone=clock.zone_name(), keep=ERRORS_KEEP)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return path


def _jobs(dispatch: Callable[[str, dict], dict]) -> list[dict]:
    listed = dispatch("cronjob_manage", {"action": "list"})
    jobs = listed.get("jobs") or []
    return [j for j in jobs if (j.get("name") or "") == JOB_NAME]


def reconcile(store, dispatch: Callable[[str, dict], dict]) -> dict:
    """Make the tick job match the switch. Returns {"wanted", "job_id", "created", "removed", "script"}."""
    wanted = bool(toolbox.load(store).get("alerts", {}).get("while_closed"))
    out: dict = {"wanted": wanted, "created": False, "removed": [], "job_id": None}
    jobs = _jobs(dispatch)
    if wanted:
        out["script"] = str(write_script(store))
        if not jobs:
            created = dispatch("cronjob_manage", {
                "action": "create", "name": JOB_NAME, "schedule": SCHEDULE, "no_agent": True,
                "script": SCRIPT_NAME, "deliver": "all", "failure_deliver": "local", "catch_up": False,
                "prompt": "Eselsbrücke alert tick (no model): prints due pomodoro, countdown and reminder alerts."})
            if not created.get("success"):
                raise RuntimeError(f"cronjob_manage create failed: {created.get('error') or created}")
            out["created"] = True
            out["job_id"] = created.get("job_id")
        else:
            out["job_id"] = jobs[0].get("job_id") or jobs[0].get("id")
            for extra in jobs[1:]:
                jid = extra.get("job_id") or extra.get("id")
                dispatch("cronjob_manage", {"action": "remove", "job_id": jid})
                out["removed"].append(jid)
    else:
        for job in jobs:
            jid = job.get("job_id") or job.get("id")
            dispatch("cronjob_manage", {"action": "remove", "job_id": jid})
            out["removed"].append(jid)
        path = script_path(store)
        if path.exists():
            path.unlink()
            out["script_removed"] = True
    return out


def touch_presence(store) -> dict:
    at = clock.iso()
    store.write_json(PRESENCE, {"at": at})
    return {"at": at}


def has_home_channel() -> Optional[bool]:
    """Whether the running profile has any home channel; None when Hermes cannot be asked."""
    try:
        from gateway.config import load_gateway_config

        cfg = load_gateway_config()
        return any(getattr(pc, "home_channel", None) for pc in (cfg.platforms or {}).values())
    except Exception:
        return None


def newest_error(store) -> Optional[dict]:
    rows, _bad = store.read_jsonl(ERRORS)
    return rows[-1] if rows else None


def status(store, dispatch: Optional[Callable[[str, dict], dict]] = None) -> dict:
    doc = toolbox.load(store)
    out: dict[str, Any] = {"while_closed": bool(doc.get("alerts", {}).get("while_closed")),
                           "home_channel": has_home_channel(), "newest_error": newest_error(store),
                           "script": str(script_path(store)) if script_path(store).exists() else None}
    if out["home_channel"] is False:
        out["warning"] = ("This profile has no home channel, so alerts while Desktop is closed are only kept in the "
                          "job's run output. Set one with /sethome in the chat app you use with Hermes.")
    if dispatch is not None:
        try:
            jobs = _jobs(dispatch)
            out["jobs"] = [{"job_id": j.get("job_id") or j.get("id"), "schedule": j.get("schedule"),
                            "last_status": j.get("last_status"), "next_run_at": j.get("next_run_at")} for j in jobs]
        except Exception as exc:
            out["jobs_error"] = f"{type(exc).__name__}: {exc}"
    out["presence_at"] = (store.read_json(PRESENCE) or {}).get("at")
    return out
