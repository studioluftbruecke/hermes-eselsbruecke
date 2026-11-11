"""eselsbruecke_timer: start, pause, resume, stop and read a pomodoro or a countdown."""
from __future__ import annotations

from .. import timer_service, timers

SCHEMA = {
    "name": "eselsbruecke_timer",
    "description": (
        "The user's pomodoro and countdown timer (shown in Hermes Desktop's status bar; work and break follow "
        "each other without a click). action=start {kind: pomodoro|countdown, minutes (countdown), client?, "
        "project?, label?} uses the rhythm from the toolbox (default 25/5, long break 15 after four); "
        "pause, resume; stop {result?: what the user finished, which goes into the pad as a done line}; "
        "status gives the phase, minutes left and, in a break, a tip. One timer runs at a time. A pomodoro with "
        "a client adds its work minutes to the time log when it stops."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["start", "pause", "resume", "stop", "status"]},
        "kind": {"type": "string", "enum": ["pomodoro", "countdown"]},
        "minutes": {"type": "number"},
        "client": {"type": "string"},
        "project": {"type": "string"},
        "label": {"type": "string"},
        "result": {"type": "string"},
    }, "required": ["action"]},
}


def handle(action: str, args: dict, env) -> dict:
    try:
        if action == "status":
            out = timer_service.status(env.store)
        else:
            body = {"op": action}
            for key in ("kind", "minutes", "client", "project", "label", "result"):
                if args.get(key) is not None:
                    body[key] = args[key]
            out = timer_service.run_op(env.store, body, env.author)
    except timers.TimerError as exc:
        return {"ok": False, "error": exc.code, "message": str(exc)}
    state = out.get("state")
    if state:
        out["summary"] = (f"{state['title']}, {state['remaining_min']} min left" + (" (paused)" if state["paused"] else "")
                          if not state["done"] else "Done")
    return out
