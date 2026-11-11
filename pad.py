"""Today's pad: short lines for today that roll to tomorrow when unchecked.

    pad/<YYYY-MM-DD>.json = {"date", "lines": [PadLine], "rolled_from": <date>|null, "rolled": bool}
    PadLine = {"id", "text", "done", "kind": note|todo|reminder|prompt, "author": user|agent,
               "created", "rolled_days", "remind_at"?, "card_id"?, "queued_for"?}
    pad/agent_log.jsonl = one line per agent addition {op_id, at, date, line_ids, undone_by?}

Roll-over is lazy and idempotent: the first read of today (under the lock) copies the unchecked lines
of the newest earlier day, with `rolled_days + 1`, in front of today's lines and records `rolled`. A
day written ahead (the page's "Next day") has a file but no `rolled` yet, so it still rolls once it is
today; a line id already on the day is never copied again. A second read finds `rolled` and does
nothing. "Today" is Hermes' time zone (`clock`, constraint 15).

A prompt line queued for a date ("prompt for tomorrow", D4) is listed under "Queued for today" on that
date, with "Start this chat" on the page, and under `@pad:queued`.
"""
from __future__ import annotations

import datetime as dt
import secrets
from typing import Any, Optional

from . import clock
from .store import Store, StoreError, check_slug

KINDS = ("note", "todo", "reminder", "prompt")
MAX_LINE = 500
MAX_LINES = 200
ROLL_LOOKBACK_DAYS = 60
AGENT_LOG = ("pad", "agent_log.jsonl")


class PadError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _date(value: Any) -> str:
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value or "").strip()
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise PadError("invalid", f"not a date: {text!r} (use YYYY-MM-DD)") from exc


def _file(date: str) -> tuple[str, str]:
    return ("pad", check_slug(date, "date") + ".json")


def new_id() -> str:
    return "l" + secrets.token_hex(5)


def _day_files(store: Store) -> list[str]:
    return sorted(n[:-5] for n in store.listdir("pad") if n.endswith(".json") and len(n) == 15)


def _read(store: Store, date: str) -> Optional[dict]:
    return store.read_json(*_file(date))


def _write(store: Store, day: dict) -> None:
    store.write_json(_file(day["date"]), day)


def _rolled(day: dict) -> bool:
    # files from before `rolled` existed were written by a roll-over exactly when rolled_from is set
    return bool(day.get("rolled") or day.get("rolled_from"))


def load_day(store: Store, date: Optional[str] = None, today: Optional[dt.date] = None) -> dict:
    """A day's pad. Today's rolls over the newest earlier day on its first read as today."""
    today_s = (today or clock.today()).isoformat()
    date = _date(date) if date else today_s
    day = _read(store, date)
    if date != today_s or (day is not None and _rolled(day)):
        return day or {"date": date, "lines": [], "rolled_from": None}
    with store.lock():
        day = _read(store, date) or {"date": date, "lines": [], "rolled_from": None}
        if _rolled(day):
            return day
        earlier = [d for d in _day_files(store) if d < date]
        prev = None
        if earlier:
            cand = earlier[-1]
            if (dt.date.fromisoformat(date) - dt.date.fromisoformat(cand)).days <= ROLL_LOOKBACK_DAYS:
                prev = _read(store, cand)
        carried = []
        if prev:
            have = {line["id"] for line in day["lines"]}
            gap = (dt.date.fromisoformat(date) - dt.date.fromisoformat(prev["date"])).days
            for line in prev.get("lines", []):
                if line.get("done") or line["id"] in have:
                    continue
                carried.append({**line, "rolled_days": int(line.get("rolled_days", 0)) + gap})
        day = {**day, "lines": carried + day["lines"], "rolled_from": prev["date"] if prev else None, "rolled": True}
        _write(store, day)
        return day


def _find(day: dict, line_id: str) -> dict:
    for line in day["lines"]:
        if line["id"] == line_id:
            return line
    raise PadError("unknown_line", f"no line {line_id!r} on {day['date']}")


def _clean_text(text: Any) -> str:
    text = " ".join(str(text or "").split())
    if not text:
        raise PadError("invalid", "a line needs text")
    if len(text) > MAX_LINE:
        raise PadError("invalid", f"a line is at most {MAX_LINE} characters (long notes belong in the brain or Obsidian)")
    return text


def make_line(text: str, kind: str = "todo", author: str = "user", remind_at: Optional[str] = None,
              queued_for: Optional[str] = None, now: Optional[dt.datetime] = None, day: Optional[str] = None) -> dict:
    """A new line for `day` (YYYY-MM-DD, today by default): a bare reminder time and the default prompt
    date count from that day."""
    day = day or clock.today(now).isoformat()
    if kind not in KINDS:
        raise PadError("invalid", f"kind must be one of {', '.join(KINDS)}")
    line = {"id": new_id(), "text": _clean_text(text), "done": False, "kind": kind, "author": author,
            "created": clock.iso(now), "rolled_days": 0}
    if kind == "reminder":
        if not remind_at:
            raise PadError("invalid", "a reminder needs remind_at (YYYY-MM-DDTHH:MM or HH:MM)")
        line["remind_at"] = normalise_time(remind_at, day, now)
    if kind == "prompt":
        line["queued_for"] = _date(queued_for) if queued_for else (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    return line


def normalise_time(value: str, day: str, now: Optional[dt.datetime] = None) -> str:
    """HH:MM (on the line's `day`) or an ISO date-time, in Hermes' zone, as 'YYYY-MM-DDTHH:MM'."""
    text = str(value).strip()
    base = now or clock.now()
    try:
        if len(text) <= 5 and ":" in text:
            hh, mm = text.split(":")
            when = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(int(hh), int(mm)))
        else:
            when = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if when.tzinfo is not None:
                when = when.astimezone(base.tzinfo)
    except ValueError as exc:
        raise PadError("invalid", f"not a time: {text!r}") from exc
    return when.strftime("%Y-%m-%dT%H:%M")


def add_lines(store: Store, items: list[dict], author: str, date: Optional[str] = None) -> dict:
    """Append lines to a day (today by default). Agent additions are logged for undo."""
    if not items:
        raise PadError("invalid", "nothing to add")
    if len(items) > 20:
        raise PadError("invalid", "at most 20 lines at once")
    with store.lock():
        day = load_day(store, date)
        if len(day["lines"]) + len(items) > MAX_LINES:
            raise PadError("full", f"a day holds at most {MAX_LINES} lines")
        new = [make_line(i.get("text"), i.get("kind") or "todo", author, i.get("remind_at"), i.get("queued_for"),
                         day=day["date"]) for i in items]
        day["lines"].extend(new)
        _write(store, day)
        op = None
        if author == "agent":
            op = {"op_id": "a" + secrets.token_hex(6), "at": clock.iso(), "date": day["date"],
                  "line_ids": [line["id"] for line in new]}
            store.append_jsonl(AGENT_LOG, op)
    return {"date": day["date"], "added": new, "op_id": op and op["op_id"]}


def undo_agent(store: Store) -> dict:
    """Remove the agent's newest addition that is not undone yet. Lines the user already removed are
    skipped; nothing else changes."""
    with store.lock():
        rows, _bad = store.read_jsonl(*AGENT_LOG)
        undone = {r["undoes"] for r in rows if r.get("undoes")}
        adds = [r for r in rows if r.get("line_ids") and r["op_id"] not in undone]
        if not adds:
            raise PadError("nothing_to_undo", "the agent has no pad addition left to undo")
        last = adds[-1]
        day = load_day(store, last["date"])
        ids = set(last["line_ids"])
        removed = [line for line in day["lines"] if line["id"] in ids]
        day["lines"] = [line for line in day["lines"] if line["id"] not in ids]
        _write(store, day)
        store.append_jsonl(AGENT_LOG, {"op_id": "u" + secrets.token_hex(6), "at": clock.iso(), "undoes": last["op_id"]})
    return {"date": last["date"], "removed": [line["text"] for line in removed], "undid": last["op_id"]}


def update_line(store: Store, date: str, line_id: str, changes: dict) -> dict:
    """A click: done, text, kind, remind_at, queued_for, card_id; or move to another position."""
    allowed = {"done", "text", "kind", "remind_at", "queued_for", "card_id", "position"}
    bad = set(changes) - allowed
    if bad:
        raise PadError("invalid", f"cannot change {', '.join(sorted(bad))}")
    with store.lock():
        day = load_day(store, date)
        line = _find(day, line_id)
        if "done" in changes:
            line["done"] = bool(changes["done"])
        if "text" in changes:
            line["text"] = _clean_text(changes["text"])
        if "kind" in changes:
            if changes["kind"] not in KINDS:
                raise PadError("invalid", f"kind must be one of {', '.join(KINDS)}")
            line["kind"] = changes["kind"]
            if line["kind"] == "prompt" and not line.get("queued_for"):
                line["queued_for"] = (dt.date.fromisoformat(day["date"]) + dt.timedelta(days=1)).isoformat()
        if "remind_at" in changes:
            if changes["remind_at"]:
                line["remind_at"] = normalise_time(changes["remind_at"], day["date"])
                line["kind"] = "reminder"
            else:
                line.pop("remind_at", None)
                if line["kind"] == "reminder":
                    line["kind"] = "todo"
        if "queued_for" in changes:
            line["queued_for"] = _date(changes["queued_for"])
            line["kind"] = "prompt"
        if "card_id" in changes:
            line["card_id"] = str(changes["card_id"])[:40]
        if "position" in changes:
            pos = max(0, min(int(changes["position"]), len(day["lines"]) - 1))
            day["lines"].remove(line)
            day["lines"].insert(pos, line)
        _write(store, day)
    return {"date": day["date"], "line": line}


def delete_line(store: Store, date: str, line_id: str) -> dict:
    with store.lock():
        day = load_day(store, date)
        line = _find(day, line_id)
        day["lines"].remove(line)
        _write(store, day)
    return {"date": day["date"], "deleted": line}


def queued(store: Store, today: Optional[dt.date] = None) -> list[dict]:
    """Prompt lines whose day has come and that are not done, from today's pad."""
    t = (today or clock.today()).isoformat()
    day = load_day(store, t, today)
    return [line for line in day["lines"] if line.get("kind") == "prompt" and not line.get("done")
            and (line.get("queued_for") or "") <= t]


def reminders_due(store: Store, since: str, until: str) -> list[dict]:
    """Reminder lines with remind_at in (since, until], not done, from the newest three day files up to
    until's day (days written ahead are not due yet). Times are 'YYYY-MM-DDTHH:MM' in Hermes' zone;
    alerts_tick._reminders is the tick's stdlib twin."""
    out: dict = {}
    for date in [d for d in _day_files(store) if d <= until[:10]][-3:]:  # oldest first: a rolled copy wins
        day = _read(store, date) or {}
        for line in day.get("lines", []):
            at = line.get("remind_at")
            if line.get("kind") == "reminder" and at and since < at <= until:
                out[(line["id"], at)] = {**line, "date": date}
    return [v for v in out.values() if not v.get("done")]


def with_results(day: dict, calc_on: bool, now: Optional[dt.datetime] = None) -> dict:
    """The day as the page shows it: each `=` line with its result when the calculator is on."""
    from .engines import calc

    out = {**day, "lines": []}
    for line in day["lines"]:
        row = dict(line)
        if calc_on and row["text"].rstrip().endswith("="):
            res = calc.evaluate_line(row["text"], now)
            if res is not None:
                row["result"] = res.get("result") if "result" in res else None
                if "error" in res:
                    row["result_error"] = res["error"]
        out["lines"].append(row)
    return out


def markdown(day: dict) -> str:
    rows = [f"## Pad {day['date']}"]
    for line in day["lines"]:
        box = "[x]" if line.get("done") else "[ ]"
        marks = []
        if line.get("rolled_days"):
            marks.append(f"rolled {line['rolled_days']} day{'s' if line['rolled_days'] != 1 else ''}")
        if line.get("kind") == "reminder" and line.get("remind_at"):
            marks.append(f"reminder {line['remind_at'][11:16]}")
        if line.get("kind") == "prompt":
            marks.append(f"prompt for {line.get('queued_for')}")
        if line.get("author") == "agent":
            marks.append("added by Hermes")
        if line.get("result"):
            marks.append(f"= {line['result']}")
        rows.append(f"- {box} {line['text']}" + (f" ({'; '.join(marks)})" if marks else ""))
    if len(rows) == 1:
        rows.append("(empty)")
    return "\n".join(rows)


__all__ = ["PadError", "StoreError"]
