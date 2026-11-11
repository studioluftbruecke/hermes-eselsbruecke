"""eselsbruecke_timelog: billable time per client and project, every change undoable."""
from __future__ import annotations

import datetime as dt

from .. import clock, timelog

SCHEMA = {
    "name": "eselsbruecke_timelog",
    "description": (
        "The user's billable time log (append-only; every change you make carries your name and can be undone). "
        "action=start {client, project?, note?, billable?: true} starts a timer (a running one stops); stop; "
        "add {client, project?, note?, start and end (ISO) or minutes}; edit {entry_id, fields: {client, project, "
        "note, start, end, billable}}; delete {entry_id}; undo reverts your newest change (undoing a start also "
        "restarts the timer it stopped, unless another timer runs now; `restarted` lists it, `note` says why "
        "not); week {date?} lists "
        "entries and totals per client and project (with amounts when the client has a rate); export {date?} "
        "writes that week as CSV into the plugin's data folder and returns the path; clients lists clients and "
        "rates. If edits answer agent_timelog_edits, the user turned agent edits off: say so."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["start", "stop", "add", "edit", "delete", "undo", "week", "export",
                                               "clients"]},
        "client": {"type": "string"}, "project": {"type": "string"}, "note": {"type": "string"},
        "billable": {"type": "boolean"},
        "start": {"type": "string"}, "end": {"type": "string"}, "minutes": {"type": "number"},
        "entry_id": {"type": "string"},
        "fields": {"type": "object"},
        "date": {"type": "string", "description": "week/export: any day of the week, YYYY-MM-DD (default today)"},
    }, "required": ["action"]},
}


def _day(args: dict) -> dt.date:
    return dt.date.fromisoformat(args["date"]) if args.get("date") else clock.today()


def _brief(view: dict) -> dict:
    return {**view, "entries": [{k: e[k] for k in ("id", "client", "project", "note", "start", "end", "hours",
                                                  "billable", "running", "long_running")} for e in view["entries"]]}


def handle(action: str, args: dict, env) -> dict:
    store = env.store
    week_starts = str(env.get_setting("week_starts", "monday") or "monday")
    try:
        if action in ("edit", "delete") and str(env.get_setting("agent_timelog_edits", "allow")) == "never":
            return {"ok": False, "error": "agent_timelog_edits",
                    "message": "The user set 'Agent edits to time-log entries' to never: you may start, stop and add, "
                               "not edit or delete. Ask them to make the change on the Time log page."}
        if action == "week":
            return _brief(timelog.week(store, _day(args), week_starts))
        if action == "clients":
            return {"clients": timelog.clients(store)}
        if action == "export":
            view = timelog.week(store, _day(args), week_starts)
            text = timelog.to_csv(view)
            name = f"timelog-{view['from']}.csv"
            target = store.path("exports", name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            return {"path": str(target), "rows": len(view["entries"]), "head": text.splitlines()[:4]}
        fields = dict(args.get("fields") or {})
        for key in ("client", "project", "note", "billable", "start", "end", "minutes"):
            if args.get(key) is not None and key not in fields:
                fields[key] = args[key]
        body: dict = {"op": action, "entry_id": args.get("entry_id")}
        if action in ("start", "add", "edit"):
            body["fields"] = fields
        out = timelog.apply_op(store, body, "agent", source="agent")
        res = {"entry": out.get("entry"), "op_id": out["op"]["op_id"]}
        if action == "undo":
            res["reverted"] = out["op"].get("reverted")
            res["restarted"] = out.get("restarted", [])
            if out.get("note"):
                res["note"] = out["note"]
        else:
            res["undo"] = "eselsbruecke_timelog action=undo reverts this change"
        return res
    except timelog.TimelogError as exc:
        return {"ok": False, "error": exc.code, "message": str(exc)}
    except ValueError as exc:
        return {"ok": False, "error": "invalid", "message": str(exc)}
