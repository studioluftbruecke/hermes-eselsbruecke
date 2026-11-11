"""The alert tick (A13): run once a minute by the profile's no-model Hermes job `eselsbruecke-alerts`
through the script that `alerts.py` writes. Stdlib only, no Hermes import: it reads the data folder
given to `main()` and prints one line per due alert, which Hermes delivers to the profile's home
channels. Empty stdout is a silent run.

Rules (PLAN M4):
- nothing is printed while the switch `alerts.while_closed` in toolbox.json is off;
- a due event is a phase end (timers.json) or a pad reminder whose time passed since the last tick,
  keyed `<timer id>:<phase index>` or `<line id>:<remind_at>`;
- a key already in alerts_sent.jsonl is skipped;
- a fresh Desktop heartbeat (presence.json younger than 90 s) means Desktop showed the alert: the key is
  recorded with by=desktop and nothing is printed;
- otherwise one line per event is printed and recorded with by=tick.
The caller (the script) catches every exception into tick_errors.jsonl and exits 0.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
from typing import Optional

PRESENCE_FRESH_S = 90
FIRST_TICK_LOOKBACK_S = 120
MAX_LOOKBACK_S = 6 * 3600  # after an outage, older events are not announced


def _json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def _append(path: Path, row: dict) -> None:
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with open(path, "a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell():
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":  # never glue a row onto a truncated last line
                line = "\n" + line
        fh.write(line.encode("utf-8"))
        fh.flush()
        os.fsync(fh.fileno())


def _sent_keys(path: Path) -> set:
    keys = set()
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                try:
                    keys.add(json.loads(raw)["key"])
                except (ValueError, KeyError, TypeError):
                    continue
    except FileNotFoundError:
        pass
    return keys


def _timers_module(plugin_dir: Path):
    spec = importlib.util.spec_from_file_location("eselsbruecke_tick_timers", plugin_dir / "timers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _zone(name: str):
    if name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:
            pass
    return dt.datetime.now().astimezone().tzinfo


def _reminders(data_dir: Path, since: dt.datetime, now: dt.datetime, tz) -> list[dict]:
    """Pad reminder lines due in (since, now], from the newest three day files up to today (days written
    ahead are not due yet; a rolled copy wins)."""
    pad_dir = data_dir / "pad"
    today = now.astimezone(tz).date().isoformat()
    try:
        files = sorted(p for p in pad_dir.iterdir()
                       if p.suffix == ".json" and len(p.name) == 15 and p.stem <= today)[-3:]
    except FileNotFoundError:
        return []
    found: dict = {}
    for path in files:
        day = _json(path, {}) or {}
        for line in day.get("lines", []):
            at = line.get("remind_at")
            if line.get("kind") != "reminder" or not at:
                continue
            try:
                when = dt.datetime.strptime(at, "%Y-%m-%dT%H:%M").replace(tzinfo=tz)
            except ValueError:
                continue
            if since < when <= now:
                found[(line.get("id"), at)] = line
    return [{"key": f"{lid}:{at}", "kind": "reminder", "at": at, "text": line.get("text", "")}
            for (lid, at), line in found.items() if not line.get("done")]


def tick(data_dir, plugin_dir, zone: str = "", now: Optional[dt.datetime] = None) -> list[str]:
    """The lines to print (and the ledger written). Pure apart from the data folder."""
    data_dir, plugin_dir = Path(data_dir), Path(plugin_dir)
    tz = _zone(zone)
    now = now or dt.datetime.now(tz)
    toolbox = _json(data_dir / "toolbox.json", {}) or {}
    state_path = data_dir / "tick_state.json"
    state = _json(state_path, {}) or {}
    since = None
    if state.get("last_tick"):
        try:
            since = dt.datetime.fromisoformat(state["last_tick"])
        except ValueError:
            since = None
    if since is None or (now - since).total_seconds() > MAX_LOOKBACK_S:
        since = now - dt.timedelta(seconds=FIRST_TICK_LOOKBACK_S if since is None else MAX_LOOKBACK_S)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"last_tick": now.isoformat(timespec="seconds")}), encoding="utf-8")
    os.replace(tmp, state_path)
    if not ((toolbox.get("alerts") or {}).get("while_closed")):
        return []
    events: list[dict] = []
    timers = _json(data_dir / "timers.json", {}) or {}
    tm = _timers_module(plugin_dir)
    candidates = ([timers["active"]] if timers.get("active") else []) + (timers.get("history") or [])[-3:]
    for t in candidates:
        try:
            for ev in tm.due_events(t, since, now):
                if t.get("ended") and tm.parse(ev["at"]) > tm.parse(t["ended"]):
                    continue  # phases after a stop never happened
                events.append({**ev, "text": tm.alert_text(ev)})
        except Exception:
            continue
    mods = toolbox.get("modules") or {}
    if (mods.get("pad") or {}).get("on", True):
        for ev in _reminders(data_dir, since, now, tz):
            events.append({**ev, "text": f"Eselsbrücke reminder: {ev['text']}"})
    if not events:
        return []
    sent_path = data_dir / "alerts_sent.jsonl"
    sent = _sent_keys(sent_path)
    presence = _json(data_dir / "presence.json", {}) or {}
    fresh = False
    if presence.get("at"):
        try:
            fresh = (now - dt.datetime.fromisoformat(presence["at"])).total_seconds() < PRESENCE_FRESH_S
        except ValueError:
            fresh = False
    out = []
    for ev in events:
        if ev["key"] in sent:
            continue
        sent.add(ev["key"])
        _append(sent_path, {"key": ev["key"], "at": now.isoformat(timespec="seconds"),
                            "by": "desktop" if fresh else "tick"})
        if not fresh:
            out.append(ev["text"])
    return out


def main(data_dir, plugin_dir, zone: str = "") -> None:
    lines = tick(data_dir, plugin_dir, zone)
    if lines:
        print("\n".join(lines))
