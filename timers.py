"""Timers: a pomodoro that moves on by itself, and countdowns. Pure functions of the record and the
clock; nothing ticks. Stdlib only (the alert tick loads this file by path, without Hermes).

    timers.json = {"active": Timer|null, "history": [Timer, ... last 20], "applied_op_ids": [... last 200]}
    Timer = {"id", "kind": "pomodoro"|"countdown", "plan": [{"phase": work|short|long|countdown, "minutes"}],
             "started": ISO with offset, "paused": [[from, to|null], ...], "client"?, "project"?, "label"?,
             "ended"?, "result"?}

The current phase is `phase_at(timer, now)`; a phase end is `due_events(timer, since, now)` with the key
`<timer id>:<phase index>`. Ops carry a client `op_id` and `at` (the click time) so an op replayed from
the Desktop outbox is applied once and keeps its time.
"""
from __future__ import annotations

import datetime as dt
import secrets
from typing import Optional

FILE = "timers.json"
KEEP_HISTORY = 20
KEEP_OPS = 200
PHASE_TITLES = {"work": "Work", "short": "Break", "long": "Long break", "countdown": "Countdown"}


class TimerError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def parse(value: str) -> dt.datetime:
    when = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise TimerError("invalid", f"time without an offset: {value}")
    return when


def iso(when: dt.datetime) -> str:
    return when.isoformat(timespec="seconds")


def pomodoro_plan(work: int = 25, short: int = 5, long: int = 15, cycles: int = 4) -> list[dict]:
    plan: list[dict] = []
    for i in range(cycles):
        plan.append({"phase": "work", "minutes": work})
        plan.append({"phase": "long" if i == cycles - 1 else "short", "minutes": long if i == cycles - 1 else short})
    return plan


def _pauses(timer: dict) -> list[tuple[dt.datetime, Optional[dt.datetime]]]:
    return [(parse(a), parse(b) if b else None) for a, b in timer.get("paused") or []]


def elapsed_s(timer: dict, now: dt.datetime) -> float:
    """Running seconds since start, pauses excluded; an open pause freezes the clock."""
    start = parse(timer["started"])
    end = parse(timer["ended"]) if timer.get("ended") else now
    total = (end - start).total_seconds()
    for a, b in _pauses(timer):
        b = b or end
        a, b = max(a, start), min(b, end)
        if b > a:
            total -= (b - a).total_seconds()
    return max(0.0, total)


def wall_at(timer: dict, target_s: float) -> Optional[dt.datetime]:
    """The wall time at which the running clock reaches `target_s`, or None if an open pause holds
    it before that."""
    t = parse(timer["started"])
    e = 0.0
    for a, b in sorted(_pauses(timer), key=lambda p: p[0]):
        if a < t:
            a = t
        e_at_a = e + (a - t).total_seconds()
        if e_at_a >= target_s:
            break
        if b is None:
            return None
        e, t = e_at_a, max(b, t)
    return t + dt.timedelta(seconds=target_s - e)


def phase_ends(timer: dict) -> list[float]:
    out, acc = [], 0.0
    for step in timer["plan"]:
        acc += step["minutes"] * 60
        out.append(acc)
    return out


def phase_at(timer: dict, now: dt.datetime) -> dict:
    e = elapsed_s(timer, now)
    ends = phase_ends(timer)
    paused = bool(timer.get("paused")) and timer["paused"][-1][1] is None
    for i, end in enumerate(ends):
        if e < end:
            step = timer["plan"][i]
            ends_at = None if paused else wall_at(timer, end)
            nxt = timer["plan"][i + 1] if i + 1 < len(timer["plan"]) else None
            return {"index": i, "phase": step["phase"], "title": PHASE_TITLES.get(step["phase"], step["phase"]),
                    "minutes": step["minutes"], "remaining_s": round(end - e), "remaining_min": int(-(-(end - e) // 60)),
                    "ends_at": iso(ends_at) if ends_at else None, "paused": paused, "done": False,
                    "next": nxt and {"phase": nxt["phase"], "minutes": nxt["minutes"]},
                    "elapsed_s": round(e), "total_s": round(ends[-1])}
    return {"index": len(ends), "phase": "done", "title": "Done", "remaining_s": 0, "remaining_min": 0,
            "ends_at": None, "paused": paused, "done": True, "next": None, "elapsed_s": round(e),
            "total_s": round(ends[-1]) if ends else 0}


def due_events(timer: dict, since: dt.datetime, now: dt.datetime) -> list[dict]:
    """Phase ends whose wall time falls in (since, now]."""
    out = []
    ends = phase_ends(timer)
    for i, end in enumerate(ends):
        at = wall_at(timer, end)
        if at is None or not (since < at <= now):
            continue
        step = timer["plan"][i]
        nxt = timer["plan"][i + 1] if i + 1 < len(timer["plan"]) else None
        out.append({"key": f"{timer['id']}:{i}", "kind": "phase_end", "timer": timer["id"], "index": i,
                    "phase": step["phase"], "minutes": step["minutes"], "at": iso(at),
                    "next": nxt and {"phase": nxt["phase"], "minutes": nxt["minutes"]},
                    "label": timer.get("label"), "timer_kind": timer["kind"]})
    return out


def alert_text(event: dict) -> str:
    if event.get("timer_kind") == "countdown":
        label = f" ({event['label']})" if event.get("label") else ""
        return f"Eselsbrücke: countdown{label} done ({event['minutes']} min)."
    title = PHASE_TITLES.get(event["phase"], event["phase"])
    nxt = event.get("next")
    if not nxt:
        return f"Eselsbrücke: {title} done. Pomodoro finished. What did you finish?"
    return f"Eselsbrücke: {title} done ({event['minutes']} min). {PHASE_TITLES.get(nxt['phase'])} {nxt['minutes']} min."


# --- the file and its ops --------------------------------------------------------------------------

def load(store) -> dict:
    data = store.read_json(FILE) or {}
    return {"active": data.get("active"), "history": data.get("history") or [],
            "applied_op_ids": data.get("applied_op_ids") or []}


def _save(store, data: dict) -> None:
    data["history"] = data["history"][-KEEP_HISTORY:]
    data["applied_op_ids"] = data["applied_op_ids"][-KEEP_OPS:]
    store.write_json(FILE, data)


KINDS = ("pomodoro", "countdown")


def _check_op(op: dict) -> None:
    """The op as it arrives from a click or the agent; anything malformed is refused before it is stored."""
    for key in ("op_id", "at", "client", "project", "label", "result"):
        if op.get(key) is not None and not isinstance(op[key], str):
            raise TimerError("invalid", f"{key} must be text")
    if op.get("kind") is not None and op["kind"] not in KINDS:
        raise TimerError("invalid", f"kind must be one of {', '.join(KINDS)}")


def apply_op(store, op: dict, now: dt.datetime, plan: Optional[list] = None) -> dict:
    """One timer op: {op: start|pause|resume|stop, op_id?, at?, ...}. Returns {"applied", "timer",
    "state", "ended"?}. An op_id seen before is acknowledged and not applied again.

    The plan is the server's: `plan` (the toolbox rhythm, from timer_service) for a pomodoro, `minutes`
    for a countdown. A `plan` inside the op is never read."""
    kind = op.get("op")
    if kind not in ("start", "pause", "resume", "stop"):
        raise TimerError("invalid", "op must be start, pause, resume or stop")
    _check_op(op)
    op_id = str(op.get("op_id") or ("srv-" + secrets.token_hex(6)))[:64]
    try:
        at = parse(op["at"]) if op.get("at") else now
    except ValueError as exc:
        raise TimerError("invalid", f"at must be a time with an offset: {op['at']!r}") from exc
    if at > now + dt.timedelta(minutes=2):
        raise TimerError("invalid", "at lies in the future")
    with store.lock():
        data = load(store)
        if op_id in data["applied_op_ids"]:
            t = data["active"]
            return {"applied": False, "duplicate": True, "timer": t, "state": t and phase_at(t, now)}
        t = data["active"]
        ended = None
        if kind == "start":
            if t and not phase_at(t, now)["done"]:
                raise TimerError("running", "a timer is already running; stop it first")
            if t:
                data["history"].append({**t, "ended": t.get("ended") or iso(at)})
            timer_kind = op.get("kind") or "pomodoro"
            if timer_kind == "countdown":
                minutes = op.get("minutes")
                if not isinstance(minutes, (int, float)) or isinstance(minutes, bool) or not 0 < minutes <= 24 * 60:
                    raise TimerError("invalid", "a countdown needs minutes between 1 and 1440")
                plan = [{"phase": "countdown", "minutes": minutes}]
            else:
                plan = plan or pomodoro_plan()
            t = {"id": "t" + secrets.token_hex(5), "kind": timer_kind, "plan": plan,
                 "started": iso(at), "paused": []}
            for key in ("client", "project", "label"):
                if op.get(key):
                    t[key] = str(op[key])[:120]
            data["active"] = t
        else:
            if not t:
                raise TimerError("not_running", "no timer is running")
            if kind == "pause":
                if t["paused"] and t["paused"][-1][1] is None:
                    raise TimerError("paused", "the timer is already paused")
                t["paused"].append([iso(at), None])
            elif kind == "resume":
                if not t["paused"] or t["paused"][-1][1] is not None:
                    raise TimerError("not_paused", "the timer is not paused")
                t["paused"][-1][1] = iso(max(at, parse(t["paused"][-1][0])))
            elif kind == "stop":
                if t["paused"] and t["paused"][-1][1] is None:
                    t["paused"][-1][1] = iso(max(at, parse(t["paused"][-1][0])))
                t["ended"] = iso(at)
                if op.get("result"):
                    t["result"] = str(op["result"])[:500]
                data["history"].append(t)
                data["active"] = None
                ended = t
        data["applied_op_ids"].append(op_id)
        _save(store, data)
    current = data["active"]
    return {"applied": True, "timer": current, "state": current and phase_at(current, now), "ended": ended}


def status(store, now: dt.datetime) -> dict:
    data = load(store)
    t = data["active"]
    return {"timer": t, "state": t and phase_at(t, now), "last": data["history"][-1] if data["history"] else None}


def work_seconds(timer: dict) -> float:
    """Seconds spent in work phases (for a pomodoro carrying a client into the time log)."""
    e = elapsed_s(timer, parse(timer["ended"])) if timer.get("ended") else 0.0
    acc = 0.0
    start = 0.0
    for step in timer["plan"]:
        end = start + step["minutes"] * 60
        if step["phase"] in ("work", "countdown"):
            acc += max(0.0, min(e, end) - start)
        start = end
    return acc

