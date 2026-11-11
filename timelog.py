"""The time log (A14, A16): billable timers per client and project, only ever appended.

    timelog/<ISO year>-W<ISO week>.jsonl   one TimeOp per line, filed by the op's time:
        {"op_id", "op": start|stop|add|edit|delete|undo, "entry_id", "at", "by": user|agent,
         "source": chip|page|palette|agent|pomodoro|outbox, "fields"?: {client, project, note, start, end,
         billable}, "undoes"?}
    clients.json  {"clients": [{"name", "rate"?, "currency"?}]}

An entry is the fold of its ops in time order; an `undo` op reverts one named op (the agent's undo
defaults to its own newest op, a click to the newest op). An `op_id` already stored is acknowledged
and not written again, so an op replayed from the Desktop outbox lands once with its click time
(A16). Every write is one appended, fsynced line; a truncated last line is skipped and counted.
"""
from __future__ import annotations

import contextlib
import copy
import csv
import datetime as dt
import io
import os
import secrets
import threading
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterator, Optional

from . import clock
from .store import Store

DIR = "timelog"
CLIENTS = "clients.json"
OPS = ("start", "stop", "add", "edit", "delete", "undo")
OUTBOX_OPS = ("start", "stop", "add")
FIELDS = ("client", "project", "note", "start", "end", "billable")
LONG_RUNNING_H = 10


class TimelogError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _parse(value: Any) -> dt.datetime:
    try:
        when = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise TimelogError("invalid", f"not a time: {value!r} (use ISO, e.g. 2026-11-09T09:30)") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=clock.now().tzinfo)
    return when


def _iso(when: dt.datetime) -> str:
    return when.isoformat(timespec="seconds")


def week_file(when: dt.datetime) -> str:
    y, w, _ = when.isocalendar()
    return f"{y}-W{w:02d}.jsonl"


class _Log:
    """The time log of one data folder, folded and kept in memory between calls.

    Week files are only ever appended, so a file whose (inode, size, mtime_ns) is unchanged holds the
    rows read last time, and a file that grew holds them as its first rows. Each call stats the week
    files, reads only a file that changed (normally the current week), and refolds only the entries
    its new ops touch. Anything else (a file shrank, was replaced or removed) rebuilds from scratch.
    Each process (gateway, dashboard, plugin host) keeps its own log and sees the others' appends
    through the stat. Callers get snapshots and copies, never the cached dicts themselves."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[tuple, int, int]] = {}  # name -> ((ino, size, mtime_ns), rows, bad)
        self.by_entry: dict[Any, list[tuple]] = {}  # entry_id -> its ops as (POSIX seconds, file, line, op)
        self.op_entry: dict[Any, Any] = {}  # op_id -> entry_id: dedupe across all history
        self.undone: set = set()
        self.entries: dict[str, dict] = {}
        self.starts: dict[str, float] = {}  # entry_id -> start in POSIX seconds
        self.bad_at = 0  # lines whose `at` is no time

    def sync(self, store: Store, only: Optional[set] = None) -> bool:
        """Read what changed on disk; False when the files are no longer an append of what this log
        holds (the caller rebuilds). `only` names the files a writer holding the store lock just
        appended to, so the other weeks need no stat."""
        base = store.path(DIR)
        stats = {}
        for name in (sorted(only) if only is not None else store.listdir(DIR)):
            if name.endswith(".jsonl"):
                try:
                    st = os.stat(base / name)
                except FileNotFoundError:
                    continue
                stats[name] = (st.st_ino, st.st_size, st.st_mtime_ns)  # before reading: a later append re-reads
        if (set(only) if only is not None else set(self.files)) - set(stats):
            return False
        touched: set = set()
        for name, sig in stats.items():
            old = self.files.get(name)
            if old and old[0] == sig:
                continue
            if old and (old[0][0] != sig[0] or sig[1] < old[0][1]):
                return False
            rows, bad = store.read_jsonl(DIR, name)
            seen = old[1] if old else 0
            if len(rows) < seen:
                return False
            touched |= self._add(name, rows, seen)
            self.files[name] = (sig, len(rows), bad)
        self._refold(touched)
        return True

    def _add(self, name: str, rows: list[dict], first: int) -> set:
        touched: set = set()
        for i in range(first, len(rows)):
            row = rows[i]
            try:
                key = (_parse(row.get("at")).timestamp(), name, i, row)
            except TimelogError:
                self.bad_at += 1
                continue
            eid = row.get("entry_id")
            self.op_entry[row.get("op_id")] = eid
            self.by_entry.setdefault(eid, []).append(key)
            touched.add(eid)
            if row.get("op") == "undo":
                also = row.get("also_undoes")
                for victim in [row.get("undoes"), *(also if isinstance(also, list) else ())]:
                    self.undone.add(victim)
                    touched.add(self.op_entry.get(victim))
        return touched

    def _refold(self, touched: set) -> None:
        for eid in touched:
            keys = self.by_entry.get(eid)
            if not keys:
                continue
            keys.sort(key=_order_key)
            folded = fold([k[3] for k in keys], self.undone).get(eid)
            self.entries.pop(eid, None)
            self.starts.pop(eid, None)
            if folded:
                try:
                    self.starts[eid] = _parse(folded["start"]).timestamp()
                except TimelogError:  # a hand-edited start that is no time: the entry is left out
                    continue
                self.entries[eid] = folded

    def ops(self) -> list[dict]:
        """Every op in time order (an undo picks its target from them)."""
        return [k[3] for k in sorted((k for keys in self.by_entry.values() for k in keys), key=_order_key)]


def _order_key(key: tuple) -> tuple:
    return key[:3]


_LOGS: dict[str, _Log] = {}
_LOGS_GUARD = threading.RLock()


@contextlib.contextmanager
def _live(store: Store) -> Iterator[_Log]:
    """This folder's log brought up to date, held for the block (writes hold it across the append).
    `at` carries the writer's UTC offset (a Desktop click the Mac's, the agent Hermes' zone), so ops
    are ordered by the instant, not the string; ops of the same instant keep file order (file name,
    then line). A line that is no JSON object or whose `at` is no time counts as skipped."""
    with _LOGS_GUARD:
        yield _synced(store)


def _synced(store: Store) -> _Log:
    key = str(store.path(DIR))
    log = _LOGS.get(key) or _Log()
    if not log.sync(store):
        log = _Log()
        log.sync(store)
    _LOGS[key] = log
    return log


def _snapshot(store: Store) -> tuple[dict, dict, int]:
    """Entries, their starts and the skipped-line count, copied for one read (folded dicts are
    replaced on refold, never changed in place, so a shallow copy is a consistent snapshot)."""
    with _live(store) as log:
        return dict(log.entries), dict(log.starts), log.bad_at + sum(f[2] for f in log.files.values())


def _undone(ops: list[dict]) -> set:
    """Op ids an undo reverted: the named op plus the ops it caused (a start's auto-stops)."""
    out: set = set()
    for o in ops:
        if o.get("op") == "undo":
            out.add(o.get("undoes"))
            also = o.get("also_undoes")
            out.update(also if isinstance(also, list) else ())
    return out


def fold(ops: list[dict], undone: Optional[set] = None) -> dict[str, dict]:
    """Entries from ops in time order; `undone` names reverted op_ids (default: the undos in `ops`)."""
    undone = _undone(ops) if undone is None else undone
    entries: dict[str, dict] = {}
    for o in ops:
        if o.get("op_id") in undone or o.get("op") == "undo":
            continue
        eid, kind, f = o.get("entry_id"), o.get("op"), o.get("fields") or {}
        if kind in ("start", "add"):
            entries[eid] = {"id": eid, "client": f.get("client") or "", "project": f.get("project") or "",
                            "note": f.get("note") or "", "start": f.get("start") or o.get("at"),
                            "end": f.get("end") if kind == "add" else None, "billable": f.get("billable", True),
                            "by": o.get("by"), "source": o.get("source"), "deleted": False}
        elif eid in entries:
            e = entries[eid]
            if kind == "stop":
                e["end"] = f.get("end") or o.get("at")
            elif kind == "edit":
                for k in FIELDS:
                    if k in f:
                        e[k] = f[k]
            elif kind == "delete":
                e["deleted"] = True
    return entries


def _hours(e: dict, now: dt.datetime) -> float:
    start = _parse(e["start"])
    end = _parse(e["end"]) if e.get("end") else now
    return max(0.0, (end - start).total_seconds() / 3600)


def _append(store: Store, op: dict) -> dict:
    store.append_jsonl((DIR, week_file(_parse(op["at"]))), op)
    return op


def _validate_fields(fields: dict, partial: bool) -> dict:
    if not isinstance(fields, dict):
        raise TimelogError("invalid", "fields must be an object")
    out = {}
    for k, v in fields.items():
        if k not in FIELDS:
            raise TimelogError("invalid", f"unknown field {k!r} (fields: {', '.join(FIELDS)})")
        if k in ("start", "end"):
            out[k] = _iso(_parse(v)) if v else None
        elif k == "billable":
            out[k] = bool(v)
        else:
            out[k] = " ".join(str(v or "").split())[:200]
    if not partial and not out.get("client"):
        raise TimelogError("invalid", "a time-log entry needs a client (a name; use 'internal' for your own work)")
    if out.get("start") and out.get("end") and _parse(out["end"]) < _parse(out["start"]):
        raise TimelogError("invalid", "end lies before start")
    return out


def apply_op(store: Store, body: dict, by: str, source: str = "page", now: Optional[dt.datetime] = None) -> dict:
    """One op from a click, the agent or the outbox. Returns {"applied", "duplicate"?, "op", "entry"}."""
    now = now or clock.now()
    kind = body.get("op")
    if kind not in OPS:
        raise TimelogError("invalid", f"op must be one of {', '.join(OPS)}")
    op_id = str(body.get("op_id") or ("s-" + secrets.token_hex(6)))[:64]
    at = _parse(body["at"]) if body.get("at") else now
    if at > now + dt.timedelta(minutes=2):
        raise TimelogError("invalid", "at lies in the future")
    with store.lock(), _live(store) as log:
        if op_id in log.op_entry:
            return {"applied": False, "duplicate": True, "op_id": op_id}
        entries = log.entries
        op: dict = {"op_id": op_id, "op": kind, "at": _iso(at), "by": by, "source": source}
        extra: list[dict] = []  # ops this op causes (a start's auto-stops)
        caused: list[dict] = []  # for an undo: the ops its target caused, reverted with it
        note: Optional[str] = None  # for an undo: why nothing was restarted
        if kind == "start":
            fields = _validate_fields({**(body.get("fields") or {}), "start": (body.get("fields") or {}).get("start") or _iso(at)}, False)
            for e in entries.values():  # starting a timer stops the running one at the same moment
                if not e["end"] and not e["deleted"]:
                    extra.append({"op_id": op_id + ":stop-" + e["id"], "op": "stop", "entry_id": e["id"],
                                  "at": _iso(at), "by": by, "source": source, "caused_by": op_id})
            op["entry_id"] = body.get("entry_id") or "e" + secrets.token_hex(5)
            op["fields"] = fields
        elif kind == "stop":
            eid = body.get("entry_id") or next((e["id"] for e in entries.values() if not e["end"] and not e["deleted"]), None)
            if not eid or eid not in entries or entries[eid]["deleted"]:
                raise TimelogError("not_running", "no time-log timer is running")
            if entries[eid]["end"]:
                raise TimelogError("not_running", "that entry is already stopped")
            op["entry_id"] = eid
            op["fields"] = {"end": _iso(at)}
        elif kind == "add":
            f = body.get("fields") or {}
            if f.get("minutes") and not f.get("start"):
                end = _parse(f["end"]) if f.get("end") else at
                f = {**f, "start": _iso(end - dt.timedelta(minutes=float(f.pop("minutes")))), "end": _iso(end)}
            f.pop("minutes", None)
            fields = _validate_fields(f, False)
            if not fields.get("start") or not fields.get("end"):
                raise TimelogError("invalid", "add needs start and end (or minutes)")
            op["entry_id"] = "e" + secrets.token_hex(5)
            op["fields"] = fields
        elif kind in ("edit", "delete"):
            eid = body.get("entry_id")
            if eid not in entries or entries[eid]["deleted"]:
                raise TimelogError("unknown_entry", f"no entry {eid!r}")
            op["entry_id"] = eid
            if kind == "edit":
                fields = _validate_fields(body.get("fields") or {}, True)
                if not fields:
                    raise TimelogError("invalid", "edit needs fields")
                merged = {**entries[eid], **fields}
                if merged.get("end") and _parse(merged["end"]) < _parse(merged["start"]):
                    raise TimelogError("invalid", "end lies before start")
                op["fields"] = fields
        elif kind == "undo":
            target = body.get("undoes")
            undone, ops = log.undone, log.ops()
            # an op another op caused (a start's auto-stop) is undone with its cause, never alone
            candidates = [o for o in ops if o.get("op") != "undo" and o.get("op_id") not in undone
                          and not o.get("caused_by")]
            if by == "agent" and not target:
                candidates = [o for o in candidates if o.get("by") == "agent"]
            if target:
                candidates = [o for o in candidates if o.get("op_id") == target]
            if not candidates:
                raise TimelogError("nothing_to_undo", "nothing to undo" + (" from the agent" if by == "agent" else ""))
            victim = candidates[-1]
            op["undoes"] = victim["op_id"]
            op["entry_id"] = victim.get("entry_id")
            op["reverted"] = copy.deepcopy({k: victim.get(k) for k in ("op", "fields", "at", "by")})
            caused = [o for o in ops if o.get("caused_by") == victim["op_id"]]
            # restart what the target stopped only while no other timer runs now (N2): a newer start
            # the undo does not revert would otherwise leave two timers running
            others = [e for e in entries.values() if not e["end"] and not e["deleted"]
                      and e["id"] != victim.get("entry_id")]
            if caused and others:
                names = ", ".join(sorted({e.get("client") or e["id"] for e in others}))
                note = (f"nothing restarted: {names} is running now, so the timer this start had stopped "
                        "stays stopped (only one timer runs at a time)")
                caused = []
            if caused:
                op["also_undoes"] = [o["op_id"] for o in caused]
        for e in extra:
            _append(store, e)
        _append(store, op)
        if not log.sync(store, only={week_file(_parse(o["at"])) for o in (*extra, op)}):
            log = _synced(store)
        after = log.entries
    entry = after.get(op.get("entry_id"))
    out = {"applied": True, "op": op, "entry": dict(entry) if entry else None}
    if caused:  # the entries a start had stopped run again
        out["restarted"] = [dict(after[o["entry_id"]]) for o in caused if o.get("entry_id") in after]
    if note:
        out["restarted"] = []
        out["note"] = note
    return out


def _row(e: dict, now: dt.datetime) -> dict:
    """A copy of a folded entry with its hours and running flags."""
    row = dict(e)
    row["hours"] = round(_hours(e, now), 4)
    row["running"] = not e["end"]
    row["long_running"] = row["running"] and row["hours"] >= LONG_RUNNING_H
    return row


def entries(store: Store, now: Optional[dt.datetime] = None, include_deleted: bool = False) -> list[dict]:
    now = now or clock.now()
    folded, starts, _bad = _snapshot(store)
    ids = sorted((eid for eid, e in folded.items() if include_deleted or not e["deleted"]), key=starts.__getitem__)
    return [_row(folded[eid], now) for eid in ids]


def week_range(day: dt.date, week_starts: str = "monday") -> tuple[dt.date, dt.date]:
    offset = day.weekday() if week_starts != "sunday" else (day.weekday() + 1) % 7
    first = day - dt.timedelta(days=offset)
    return first, first + dt.timedelta(days=7)


def clients(store: Store) -> list[dict]:
    return (store.read_json(CLIENTS) or {}).get("clients") or []


def set_client(store: Store, name: str, rate: Optional[float], currency: str = "EUR") -> list[dict]:
    name = " ".join(str(name or "").split())[:200]
    if not name:
        raise TimelogError("invalid", "a client needs a name")
    with store.lock():
        rows = [c for c in clients(store) if c.get("name") != name]
        rows.append({"name": name, **({"rate": float(rate), "currency": currency} if rate is not None else {})})
        store.write_json(CLIENTS, {"clients": sorted(rows, key=lambda c: c["name"].lower())})
    return clients(store)


def _money(hours: float, rate: Optional[float]) -> Optional[str]:
    if rate is None:
        return None
    return str((Decimal(str(hours)) * Decimal(str(rate))).quantize(Decimal("0.01"), ROUND_HALF_UP))


def week(store: Store, day: Optional[dt.date] = None, week_starts: str = "monday",
         now: Optional[dt.datetime] = None) -> dict:
    now = now or clock.now()
    day = day or now.date()
    first, last = week_range(day, week_starts)
    rates = {c["name"]: c.get("rate") for c in clients(store)}
    folded, starts, bad = _snapshot(store)
    lo, hi = (dt.datetime.combine(d, dt.time(), tzinfo=now.tzinfo).timestamp() for d in (first, last))  # local midnights
    ids = sorted((eid for eid, e in folded.items() if not e["deleted"] and lo <= starts[eid] < hi), key=starts.__getitem__)
    rows = [_row(folded[eid], now) for eid in ids]
    running = min((e for e in folded.values() if not e["end"] and not e["deleted"]),
                  key=lambda e: starts[e["id"]], default=None)
    totals: dict[tuple, dict] = {}
    for e in rows:
        key = (e["client"], e["project"])
        t = totals.setdefault(key, {"client": e["client"], "project": e["project"], "hours": 0.0, "billable_hours": 0.0})
        t["hours"] += e["hours"]
        if e["billable"]:
            t["billable_hours"] += e["hours"]
    out_totals = []
    for t in totals.values():
        rate = rates.get(t["client"])
        out_totals.append({**t, "hours": round(t["hours"], 2), "billable_hours": round(t["billable_hours"], 2),
                           "rate": rate, "amount": _money(round(t["billable_hours"], 2), rate)})
    return {"from": first.isoformat(), "to": (last - dt.timedelta(days=1)).isoformat(), "week_starts": week_starts,
            "entries": rows, "totals": sorted(out_totals, key=lambda t: (t["client"].lower(), t["project"].lower())),
            "hours": round(sum(e["hours"] for e in rows), 2),
            "running": _row(running, now) if running else None,
            "skipped_lines": bad}


CSV_HEADER = ["date", "start", "end", "hours", "client", "project", "note", "billable", "rate", "amount"]


def to_csv(view: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_HEADER)
    rates = {t["client"]: t.get("rate") for t in view["totals"]}
    for e in view["entries"]:
        start = _parse(e["start"])
        end = _parse(e["end"]) if e.get("end") else None
        hours = round(e["hours"], 2)
        rate = rates.get(e["client"])
        w.writerow([start.date().isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M") if end else "running",
                    f"{hours:.2f}", e["client"], e["project"], e["note"], "yes" if e["billable"] else "no",
                    "" if rate is None else rate, _money(hours, rate) if e["billable"] and rate is not None else ""])
    return buf.getvalue()


def replay(store: Store, ops: list[dict], now: Optional[dt.datetime] = None) -> list[dict]:
    """The outbox (A16): start, stop and add ops with client op_id and at, in order. Each answers
    applied, duplicate or an error; an error does not stop the rest."""
    results = []
    for body in ops if isinstance(ops, list) else []:
        if not isinstance(body, dict) or body.get("op") not in OUTBOX_OPS or not body.get("op_id") or not body.get("at"):
            results.append({"op_id": isinstance(body, dict) and body.get("op_id"), "error": "invalid",
                            "message": "outbox ops need op (start, stop, add), op_id and at"})
            continue
        try:
            out = apply_op(store, body, "user", source="outbox", now=now)
            results.append({"op_id": body["op_id"], "applied": out["applied"], "duplicate": out.get("duplicate", False)})
        except TimelogError as exc:
            results.append({"op_id": body["op_id"], "error": exc.code, "message": str(exc)})
    return results
