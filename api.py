"""The routes' logic, without FastAPI, so tests call it directly: each function returns (status, body).

`dashboard/plugin_api.py` only adapts these to FastAPI. Every body carries `schema` (the page shows
\"update the plugin\" on a mismatch). Author is always `user`: these are clicks.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

from . import clock, timer_service, toolbox  # timer_service: alert reconcile after every toolbox save
from .store import Store, StoreError, default_root

SCHEMA = 1
log = logging.getLogger(__name__)


def _version() -> str:
    text = (Path(__file__).resolve().parent / "plugin.yaml").read_text(encoding="utf-8")
    found = re.search(r'(?m)^version:\s*"?([^"\n]+)"?', text)
    return found.group(1) if found else "?"


VERSION = _version()

# Tests point this at a temp folder; in Hermes it follows the bound home per call.
_store_factory: Callable[[], Store] = lambda: Store(lambda: default_root())  # noqa: E731


def set_store_factory(factory: Optional[Callable[[], Store]]) -> None:
    global _store_factory
    _store_factory = factory or (lambda: Store(lambda: default_root()))


def store() -> Store:
    return _store_factory()


def ok(body: dict, status: int = 200) -> "tuple[int, dict]":
    return status, {"ok": True, "schema": SCHEMA, **body}


def fail(status: int, code: str, message: str, **extra: Any) -> "tuple[int, dict]":
    return status, {"ok": False, "schema": SCHEMA, "error": code, "message": message, **extra}


def _guard(fn):
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except toolbox.SwitchedOff as exc:
            return fail(409, exc.code, str(exc), **exc.extra)
        except toolbox.ToolboxError as exc:
            status = {"stale": 409, "stale_preview": 409, "unknown_version": 404}.get(exc.code, 400)
            return fail(status, exc.code, str(exc), **exc.extra)
        except StoreError as exc:
            return fail(500, "store", str(exc))
        except ValueError as exc:
            return fail(400, "invalid", str(exc))
        except Exception as exc:  # last resort: the page gets JSON it can show, never a bare 500
            log.exception("eselsbruecke route %s failed", fn.__name__)
            return fail(500, "internal", f"Something went wrong inside the plugin ({type(exc).__name__}: {exc})"[:400])
    wrapped.__name__ = fn.__name__
    return wrapped


# --- body checks: a malformed body is a 400 before it reaches the state -----------------------------

_NAMES = {str: "text", bool: "true or false", int: "a whole number", dict: "an object", list: "a list"}


def _typed(value: Any, kind: type) -> bool:
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def _need(obj: dict, key: str, kind: type, *, null: bool = True, where: str = "") -> None:
    """When `key` is present it must be `kind` (or None, when `null`)."""
    if key not in obj or (null and obj[key] is None):
        return
    if not _typed(obj[key], kind):
        raise ValueError(f"{where}{key} must be {_NAMES[kind]}")


@_guard
def health() -> "tuple[int, dict]":
    return ok({"plugin": "eselsbruecke", "version": VERSION, "time_zone": clock.zone_info(),
               "now": clock.iso()})


@_guard
def toolbox_get() -> "tuple[int, dict]":
    return ok(toolbox.view(store()))


@_guard
def toolbox_post(body: Any) -> "tuple[int, dict]":
    if not isinstance(body, dict):
        return fail(400, "invalid", "send a JSON object with op")
    s, op = store(), body.get("op")
    if op == "switch":
        out = toolbox.set_switch(s, str(body.get("module", "")), body.get("on"), "user")
    elif op == "save":
        with s.lock():
            current = toolbox.load(s)
            if body.get("base_hash") != toolbox.doc_hash(current):
                return fail(409, "stale", "The toolbox changed since you opened it (another window or the agent). "
                                          "Reload to see the newest version.", current=toolbox.view(s))
            out = toolbox.save(s, body.get("toolbox"), "user")
    elif op == "restore":
        out = toolbox.restore(s, body.get("version"), "user")
    else:
        return fail(400, "invalid", "op must be switch, save or restore")
    return ok({"saved": {"version": out["version"], "summary": out["summary"]}, **toolbox.view(s)})


@_guard
def toolbox_versions() -> "tuple[int, dict]":
    return ok({"versions": toolbox.versions(store())})


ENGINE_TOOLS = {"calc": "eselsbruecke_calc", "format": "eselsbruecke_format", "convert": "eselsbruecke_convert",
                "text": "eselsbruecke_text", "generate": "eselsbruecke_generate"}


@_guard
def run_engine(engine: str, body: Any) -> "tuple[int, dict]":
    """The page's Python-side tools (constraint 8): the same handler the agent tool runs, author user.
    Engine answers (a parse error included) are 200 with ok true/false; a switched-off tool is 409."""
    from . import env as env_mod

    tool = ENGINE_TOOLS.get(engine)
    if tool is None:
        return fail(404, "unknown_engine", f"engine must be one of {', '.join(ENGINE_TOOLS)}")
    if not isinstance(body, dict):
        return fail(400, "invalid", "send a JSON object")
    out = env_mod.run_tool(tool, body, env_mod.Env(store=store(), author="user", package=__package__))
    if out.get("error") == "switched_off":
        return fail(409, "switched_off", out.get("message", ""), module=out.get("module"))
    if out.get("error") == "unknown_action":
        return fail(400, "unknown_action", out.get("message", ""))
    return 200, {"schema": SCHEMA, **out}


# --- M3: today's pad -------------------------------------------------------------------------------

def _pad_guard(fn):
    def wrapped(*args, **kwargs):
        from . import pad

        try:
            return fn(*args, **kwargs)
        except pad.PadError as exc:
            status = {"unknown_line": 404, "full": 409}.get(exc.code, 400)
            return fail(status, exc.code, str(exc))
    wrapped.__name__ = fn.__name__
    return _guard(wrapped)


# update: (key, type, None allowed); None for remind_at clears the reminder
_PAD_CHANGES = (("done", bool, False), ("text", str, False), ("kind", str, False), ("remind_at", str, True),
                ("queued_for", str, False), ("card_id", str, False), ("position", int, False))
_LINE_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _restored_line(line: dict) -> dict:
    """Undo of a delete: the line comes back from the page, so it runs the rules of a new line
    (text, kind, reminder, queue) and keeps only its own identity (id, created, author, done, rolled
    days, card) when those are well formed."""
    from . import pad

    if not isinstance(line.get("id"), str) or not _LINE_ID.match(line["id"]):
        raise ValueError("line.id must be the deleted line's id")
    for key, kind in (("text", str), ("kind", str), ("remind_at", str), ("queued_for", str), ("created", str),
                      ("author", str), ("card_id", str), ("done", bool), ("rolled_days", int)):
        _need(line, key, kind, where="line.")
    if line.get("author", "user") not in ("user", "agent"):
        raise ValueError("line.author must be user or agent")
    if line.get("rolled_days", 0) < 0:
        raise ValueError("line.rolled_days must be 0 or more")
    if line.get("created"):
        dt.datetime.fromisoformat(line["created"])  # ValueError -> 400
    out = pad.make_line(line.get("text"), line.get("kind") or "todo", line.get("author") or "user",
                        line.get("remind_at"), line.get("queued_for"))
    out.update(id=line["id"], done=bool(line.get("done")), rolled_days=line.get("rolled_days") or 0)
    if line.get("created"):
        out["created"] = line["created"]
    if line.get("card_id"):
        out["card_id"] = line["card_id"][:40]
    return out


def _pad_view(s: Store, date: Optional[str] = None) -> dict:
    from . import pad

    toolbox.require_on(s, "pad")
    now = clock.now()
    day = pad.load_day(s, date, now.date())
    calc_on = toolbox.is_on(s, "calc")
    out = {"day": pad.with_results(day, calc_on, now), "today": now.date().isoformat(), "calc_on": calc_on,
           "time_zone": clock.zone_info()}
    if day["date"] == now.date().isoformat():
        out["queued"] = pad.queued(s, now.date())
    return out


@_pad_guard
def pad_get(date: Optional[str] = None) -> "tuple[int, dict]":
    return ok(_pad_view(store(), date))


@_pad_guard
def pad_markdown(date: Optional[str] = None) -> "tuple[int, dict]":
    from . import pad

    s = store()
    toolbox.require_on(s, "pad")
    day = pad.load_day(s, date)
    return ok({"date": day["date"], "markdown": pad.markdown(pad.with_results(day, toolbox.is_on(s, "calc")))})


@_pad_guard
def pad_lines(body: Any) -> "tuple[int, dict]":
    """The user's clicks on the pad: add, update (done, text, kind, reminder, queue, position), delete,
    and card (a kanban card in triage through Hermes' own tool, Q5)."""
    from . import hermes_bridge, pad

    if not isinstance(body, dict):
        return fail(400, "invalid", "send a JSON object with op")
    s, op = store(), body.get("op")
    toolbox.require_on(s, "pad")
    _need(body, "date", str)
    date = body.get("date")
    extra: dict = {}
    if op == "add":
        for key in ("text", "kind", "remind_at", "queued_for"):
            _need(body, key, str)
        pad.add_lines(s, [{"text": body.get("text"), "kind": body.get("kind") or "todo",
                           "remind_at": body.get("remind_at"), "queued_for": body.get("queued_for")}], "user", date)
    elif op == "update":
        _need(body, "changes", dict)
        changes = body.get("changes") or {}
        for key, kind, null in _PAD_CHANGES:
            _need(changes, key, kind, null=null, where="changes.")
        pad.update_line(s, date, str(body.get("id", "")), changes)
    elif op == "delete":
        out = pad.delete_line(s, date, str(body.get("id", "")))
        extra["deleted"] = out["deleted"]
    elif op == "restore":  # Undo of a delete: put the line back as it was
        if not isinstance(body.get("line"), dict):
            return fail(400, "invalid", "restore needs the deleted line")
        _need(body, "position", int, null=False)
        line = _restored_line(body["line"])
        with s.lock():
            day = pad.load_day(s, date)
            if not any(x["id"] == line["id"] for x in day["lines"]):
                if len(day["lines"]) >= pad.MAX_LINES:
                    raise pad.PadError("full", f"a day holds at most {pad.MAX_LINES} lines")
                pos = max(0, min(body.get("position", len(day["lines"])), len(day["lines"])))
                day["lines"].insert(pos, line)
                pad._write(s, day)
    elif op == "card":
        day = pad.load_day(s, date)
        line = pad._find(day, str(body.get("id", "")))
        if line.get("card_id"):
            return fail(409, "already_card", f"this line is card {line['card_id']}")
        profile = hermes_bridge.current_profile() or "default"
        try:
            answer = hermes_bridge.dispatch("kanban_create", {
                "title": line["text"][:200], "assignee": profile, "triage": True,
                "body": f"From the Eselsbrücke pad, {day['date']}. Promote it to ready when it should run."})
        except hermes_bridge.BridgeError as exc:
            return ok({"card": None, "fallback_draft": f"Create a kanban card: {line['text']}",
                       "message": f"Hermes' kanban tool could not be reached here ({exc}); the line is in a chat "
                                  "draft instead.", **_pad_view(s, date)})
        tid = answer.get("task_id")
        if not answer.get("ok", True) or not tid:
            return ok({"card": None, "fallback_draft": f"Create a kanban card: {line['text']}",
                       "message": str(answer.get("error") or answer)[:300], **_pad_view(s, date)})
        pad.update_line(s, date, line["id"], {"card_id": tid})
        extra["card"] = {"task_id": tid, "status": answer.get("status"), "assignee": profile}
    else:
        return fail(400, "invalid", "op must be add, update, delete, restore or card")
    return ok({**extra, **_pad_view(s, date)})


# --- M4: timers, alerts, tips ----------------------------------------------------------------------

def _timer_guard(fn):
    def wrapped(*args, **kwargs):
        from . import timers

        try:
            return fn(*args, **kwargs)
        except timers.TimerError as exc:
            status = {"running": 409, "not_running": 409, "paused": 409, "not_paused": 409}.get(exc.code, 400)
            return fail(status, exc.code, str(exc))
    wrapped.__name__ = fn.__name__
    return _guard(wrapped)


@_timer_guard
def timer_get() -> "tuple[int, dict]":
    from . import timer_service

    s = store()
    toolbox.require_on(s, "pomodoro")
    return ok(timer_service.status(s))


@_timer_guard
def timer_post(body: Any) -> "tuple[int, dict]":
    """The outbox contract (A16): {op, op_id, at}; an op_id already applied answers duplicate: true."""
    from . import timer_service

    if not isinstance(body, dict):
        return fail(400, "invalid", "send a JSON object with op")
    s = store()
    toolbox.require_on(s, "pomodoro")
    return ok(timer_service.run_op(s, body, "user"))


@_guard
def presence() -> "tuple[int, dict]":
    from . import alerts

    return ok(alerts.touch_presence(store()))


@_guard
def alerts_get() -> "tuple[int, dict]":
    from . import alerts, hermes_bridge

    s = store()
    return ok({"alerts": alerts.status(s, hermes_bridge.dispatch),
               "last_reconcile": s.read_json("alerts_state.json")})


@_guard
def alerts_reconcile() -> "tuple[int, dict]":
    from . import alerts, hermes_bridge, timer_service

    s = store()
    out = timer_service.reconcile_quiet(s)
    return ok({"reconcile": out, "alerts": alerts.status(s, hermes_bridge.dispatch)})


@_guard
def tips_get() -> "tuple[int, dict]":
    from . import tips

    return ok({"tips": tips.all_tips(toolbox.load(store()).get("tips"))})


# --- M5: time log ----------------------------------------------------------------------------------

def _setting(key: str, default: Any = None) -> Any:
    """A plugin setting of the profile that owns the data folder (routes have no ctx)."""
    from . import reference

    try:
        cfg = reference.read_config(store().root.parent.parent)
        value = (((cfg.get("plugins") or {}).get("entries") or {}).get("eselsbruecke") or {}).get("settings", {}).get(key)
    except Exception:
        value = None
    return default if value is None else value


def _timelog_guard(fn):
    def wrapped(*args, **kwargs):
        from . import timelog

        try:
            return fn(*args, **kwargs)
        except timelog.TimelogError as exc:
            status = {"unknown_entry": 404, "not_running": 409, "nothing_to_undo": 409}.get(exc.code, 400)
            return fail(status, exc.code, str(exc))
    wrapped.__name__ = fn.__name__
    return _guard(wrapped)


def _week_view(s, date: Optional[str]) -> dict:
    import datetime as dt

    from . import timelog

    day = dt.date.fromisoformat(date) if date else None
    return {"week": timelog.week(s, day, str(_setting("week_starts", "monday"))), "clients": timelog.clients(s)}


@_timelog_guard
def timelog_get(date: Optional[str] = None) -> "tuple[int, dict]":
    s = store()
    toolbox.require_on(s, "timelog")
    return ok(_week_view(s, date))


@_timelog_guard
def timelog_post(body: Any) -> "tuple[int, dict]":
    """A click: {op: start|stop|add|edit|delete|undo, ...}, or {op: client, name, rate}."""
    from . import timelog

    if not isinstance(body, dict):
        return fail(400, "invalid", "send a JSON object with op")
    s = store()
    toolbox.require_on(s, "timelog")
    _need(body, "fields", dict)
    _need(body, "date", str)
    if body.get("op") == "client":
        timelog.set_client(s, body.get("name"), body.get("rate"), body.get("currency") or "EUR")
        return ok(_week_view(s, body.get("date")))
    out = timelog.apply_op(s, body, "user", source=str(body.get("source") or "page")[:20])
    return ok({"result": {k: out.get(k) for k in ("applied", "duplicate", "op", "entry")}, **_week_view(s, body.get("date"))})


@_timelog_guard
def timelog_ops(body: Any) -> "tuple[int, dict]":
    """The Desktop outbox (A16): {ops: [{op, op_id, at, entry_id?, fields?}, ...]} replayed in order."""
    from . import timelog

    if not isinstance(body, dict) or not isinstance(body.get("ops"), list):
        return fail(400, "invalid", "send {ops: [...]}")
    s = store()
    toolbox.require_on(s, "timelog")
    results = []
    for op in body["ops"]:  # one malformed op is refused alone; the rest still replay in order
        if isinstance(op, dict) and op.get("fields") is not None and not isinstance(op["fields"], dict):
            results.append({"op_id": op.get("op_id"), "error": "invalid", "message": "fields must be an object"})
        else:
            results.extend(timelog.replay(s, [op]))
    return ok({"results": results, **_week_view(s, None)})


@_timelog_guard
def timelog_export(date: Optional[str] = None) -> "tuple[int, dict]":
    from . import timelog

    s = store()
    toolbox.require_on(s, "timelog")
    view = _week_view(s, date)["week"]
    return ok({"filename": f"timelog-{view['from']}.csv", "csv": timelog.to_csv(view), "rows": len(view["entries"])})


# --- M6: the o200k ranks for the Desktop's exact token count (A15) --------------------------------

RANKS_FILE = Path(__file__).resolve().parent / "data" / "o200k_base.json"


def ranks_path() -> "tuple[int, Any]":
    """The file the route streams, or a 404 when the build has not written it."""
    if not RANKS_FILE.is_file():
        return fail(404, "missing", "data/o200k_base.json is missing; run desktop/build/build.mjs")
    return 200, RANKS_FILE
