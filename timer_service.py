"""Timer actions shared by the agent tool and the page: apply the op, keep the alert job in step,
put a finished pomodoro's answer into the pad, carry a client's work time into the time log, and
add a break tip."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib
from typing import Any, Callable, Optional

from . import alerts, clock, hermes_bridge, pad, timers, tips, toolbox

ALERT_STATE = "alerts_state.json"


def reconcile_quiet(store, dispatch: Optional[Callable[[str, dict], dict]] = None) -> dict:
    """Reconcile the alert job; never raises. The outcome is kept in alerts_state.json for the page."""
    try:
        out = {"ok": True, **alerts.reconcile(store, dispatch or hermes_bridge.dispatch)}
    except Exception as exc:
        out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    out["at"] = clock.iso()
    try:
        store.write_json(ALERT_STATE, out)
    except Exception:
        pass
    return out


def _after_save(store, old: dict, new: dict) -> None:
    if bool(old.get("alerts", {}).get("while_closed")) != bool(new.get("alerts", {}).get("while_closed")):
        reconcile_quiet(store)


toolbox.AFTER_SAVE[:] = [h for h in toolbox.AFTER_SAVE if getattr(h, "__qualname__", "") != "_after_save"]
toolbox.AFTER_SAVE.append(_after_save)


def _plan_from_toolbox(store) -> list[dict]:
    p = toolbox.load(store)["pomodoro"]
    return timers.pomodoro_plan(p["work"], p["short"], p["long"], p["cycles"])


def with_tip(store, state: Optional[dict]) -> Optional[dict]:
    if not state or state.get("phase") not in ("short", "long"):
        return None
    doc = toolbox.load(store)
    # One break, one tip, in every process: hash() of a str is salted per process (PYTHONHASHSEED),
    # so the page, the agent and the alert job picked different tips for the same break.
    seed = int(hashlib.sha256((state.get("ends_at") or "").encode()).hexdigest()[:4], 16)
    return tips.break_tip(hermes_bridge.has_tool, lambda name, args: hermes_bridge.dispatch(name, args),
                          doc.get("tips"), seed=seed)


def run_op(store, body: dict, author: str, now: Optional[dt.datetime] = None,
           dispatch: Optional[Callable[[str, dict], dict]] = None) -> dict:
    now = now or clock.now()
    body = dict(body)
    plan = None  # the server builds the plan; a client `plan` is ignored
    if body.get("op") == "start" and (body.get("kind") or "pomodoro") == "pomodoro":
        plan = _plan_from_toolbox(store)
    result = timers.apply_op(store, body, now, plan=plan)
    out: dict[str, Any] = {"applied": result["applied"], "duplicate": result.get("duplicate", False),
                           "timer": result["timer"], "state": result["state"]}
    if result["applied"] and body["op"] in ("start", "stop"):
        out["alerts"] = reconcile_quiet(store, dispatch)
    ended = result.get("ended")
    if ended:
        out["ended"] = {"id": ended["id"], "kind": ended["kind"], "started": ended["started"], "ended": ended["ended"],
                        "work_minutes": round(timers.work_seconds(ended) / 60, 1)}
        if ended.get("result") and toolbox.is_on(store, "pad"):
            added = pad.add_lines(store, [{"text": f"Finished: {ended['result']}", "kind": "note"}], author)
            pad.update_line(store, added["date"], added["added"][0]["id"], {"done": True})
            out["pad_line"] = added["added"][0]["id"]
        if ended.get("client") and ended["kind"] == "pomodoro" and toolbox.is_on(store, "timelog"):
            out["timelog"] = _log_pomodoro(store, ended, author)
    tip = with_tip(store, out["state"])
    if tip:
        out["tip"] = tip
    return out


def _log_pomodoro(store, timer: dict, author: str) -> Optional[dict]:
    """A pomodoro that carried a client becomes one time-log entry (its work minutes, M5)."""
    try:
        timelog = importlib.import_module(".timelog", __package__)
    except ImportError:
        return None
    secs = timers.work_seconds(timer)
    if secs < 60:
        return None
    end = timers.parse(timer["ended"])
    start = end - dt.timedelta(seconds=secs)
    return timelog.apply_op(store, {"op": "add", "fields": {
        "client": timer.get("client"), "project": timer.get("project") or "", "note": "Pomodoro",
        "start": timers.iso(start), "end": timers.iso(end), "billable": True}}, author, source="pomodoro")


def status(store, now: Optional[dt.datetime] = None) -> dict:
    now = now or clock.now()
    out = timers.status(store, now)
    tip = with_tip(store, out["state"])
    if tip:
        out["tip"] = tip
    return out
