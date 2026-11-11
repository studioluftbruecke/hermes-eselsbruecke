"""The toolbox file: which tools are on, their order and options, the dashboard, the world clock's
places and saved versions.

`toolbox.json` in the data folder is the one file the settings page, the dashboard, the World clock
and the agent's `eselsbruecke_toolbox` all edit. Every save keeps a version in
`toolbox.versions/<n>.json` with author (`user` or `agent`), time and a one-line summary; the last 20
stay, and restoring one is a new save. Agent edits go through `preview` (a diff and an id) and
`apply(id)`, which refuses when the file changed since the preview.

Shape (schema 2):
    {"schema": 2, "first_run": false,
     "modules": {<id>: {"on": bool, "order": int, "options": {}}},
     "dashboard": [<id>, ...],                       pinned tools in order (a switched-off one is skipped)
     "clocks": [{"zone": <tz name>, "label": <text>}, ...],   never the user's own zone: the page adds it
     "layout": {"chip": "auto"|"pomodoro"|"timelog", "chip_visible": bool},
     "pomodoro": {"rhythm": "25/5"|"50/10"|"custom", "work": 25, "short": 5, "long": 15, "cycles": 4},
     "tips": [{"id", "title", "why"}],
     "alerts": {"while_closed": false}}

Schema 1 had `preset`, `layout.rail`, `layout.dock` and `layout.chip: "off"`, and no `dashboard` or
`clocks`. Such a document (a file or a saved version from before) is read through `migrate`.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from typing import Any, Callable, Optional

from . import clock
from .engines import places
from .registry import MODULE_BY_ID, MODULE_IDS, MODULES
from .store import Store, StoreError

SCHEMA = 2
FILE = "toolbox.json"
VERSIONS = "toolbox.versions"
PREVIEW = "toolbox.preview.json"
KEEP_VERSIONS = 20
RHYTHMS = ("25/5", "50/10", "custom")
CHIPS = ("auto", "pomodoro", "timelog")
CHIP_NAMES = {"auto": "What is running", "pomodoro": "Pomodoro", "timelog": "Time log"}
MAX_TIPS = 50
MAX_PINS = 20
MAX_CLOCKS = 12
MAX_LABEL = 40
PINNABLE = tuple(m["id"] for m in MODULES if m.get("dashboard"))
DEFAULT_DASHBOARD = ("timezones", "pad", "pomodoro", "timelog", "generate", "colour", "formatter", "diff",
                     "encode")
DEFAULT_CLOCKS = (("UTC", "UTC"), ("America/New_York", "New York"), ("Asia/Tokyo", "Tokyo"))

# Called after every save with (old_doc, new_doc); M4's alert reconcile registers here.
AFTER_SAVE: list[Callable[[Store, dict, dict], None]] = []


class ToolboxError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.extra = extra


class SwitchedOff(ToolboxError):
    def __init__(self, module: str):
        title = MODULE_BY_ID.get(module, {}).get("title", module)
        super().__init__("switched_off", f"{title} is switched off in the toolbox. Ask the user to switch it on "
                                         f"(Eselsbrücke settings, or eselsbruecke_toolbox set_switch).",
                         module=module)


def _default_clocks() -> list[dict]:
    return [{"zone": zone, "label": label} for zone, label in DEFAULT_CLOCKS]


def default_doc(first_run: bool = True) -> dict:
    return {
        "schema": SCHEMA,
        "first_run": first_run,
        "modules": {m["id"]: {"on": m["default_on"], "order": i, "options": {}} for i, m in enumerate(MODULES)},
        "dashboard": list(DEFAULT_DASHBOARD),
        "clocks": _default_clocks(),
        "layout": {"chip": "auto", "chip_visible": True},
        "pomodoro": {"rhythm": "25/5", "work": 25, "short": 5, "long": 15, "cycles": 4},
        "tips": [],
        "alerts": {"while_closed": False},
    }


def migrate(raw: Any) -> Any:
    """A schema-1 document as schema 2; anything else unchanged. `raw` is never modified.

    A document without `schema` counts as schema 1 (a hand-edited file from before), so what it
    already says about the dashboard, the clocks or the chip is kept and only the gaps are filled."""
    if not isinstance(raw, dict):
        return raw
    schema = raw.get("schema", 1)
    if isinstance(schema, bool) or schema != 1:
        return raw
    doc = copy.deepcopy(raw)
    doc["schema"] = SCHEMA
    doc.pop("preset", None)
    layout = doc.get("layout")
    if isinstance(layout, dict):
        layout.pop("rail", None)
        layout.pop("dock", None)
        if layout.get("chip") == "off":
            layout["chip"], layout["chip_visible"] = "auto", False
        else:
            layout.setdefault("chip_visible", True)
    doc.setdefault("dashboard", list(DEFAULT_DASHBOARD))
    doc.setdefault("clocks", _default_clocks())
    return doc


def _merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        out = dict(base)
        for k, v in patch.items():
            out[k] = _merge(base.get(k), v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(patch)


def validate(doc: Any) -> tuple[dict, list[str]]:
    """A clean copy of `doc` filled from the defaults, and the list of problems (empty = valid)."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return default_doc(), ["the toolbox must be an object"]
    known = set(default_doc())
    for key in doc:
        if key not in known:
            errors.append(f"unknown key {key!r} (known: {', '.join(sorted(known))})")
    defaults = default_doc(first_run=False)
    clean = _merge(defaults, {k: v for k, v in doc.items() if k in known})
    for key in ("layout", "pomodoro", "alerts"):  # a wrong shape is a problem to report, never a crash
        if not isinstance(clean.get(key), dict):
            errors.append(f"{key} must be an object")
            clean[key] = defaults[key]
    if clean.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if not isinstance(clean.get("first_run"), bool):
        errors.append("first_run must be true or false")
    mods = clean.get("modules")
    if not isinstance(mods, dict):
        errors.append("modules must be an object")
    else:
        for mid in list(mods):
            if mid not in MODULE_BY_ID:
                errors.append(f"unknown tool {mid!r} (tools: {', '.join(MODULE_IDS)})")
                continue
            row = mods[mid]
            if not isinstance(row, dict):
                errors.append(f"modules.{mid} must be an object")
                continue
            if not isinstance(row.get("on"), bool):
                errors.append(f"modules.{mid}.on must be true or false")
            if not isinstance(row.get("order"), int) or isinstance(row.get("order"), bool):
                errors.append(f"modules.{mid}.order must be a whole number")
            opts = row.get("options", {})
            if not isinstance(opts, dict) or len(json.dumps(opts)) > 4000:
                errors.append(f"modules.{mid}.options must be an object under 4000 characters")
            for extra in set(row) - {"on", "order", "options"}:
                errors.append(f"modules.{mid}: unknown key {extra!r}")
    errors += _dashboard_errors(clean.get("dashboard"))
    errors += _clock_errors(clean.get("clocks"))
    layout = clean.get("layout") or {}
    if layout.get("chip") not in CHIPS:
        errors.append(f"layout.chip must be one of {', '.join(CHIPS)}")
    if not isinstance(layout.get("chip_visible"), bool):
        errors.append("layout.chip_visible must be true or false")
    for extra in set(layout) - {"chip", "chip_visible"}:
        errors.append(f"layout: unknown key {extra!r}")
    pomo = clean.get("pomodoro") or {}
    if pomo.get("rhythm") not in RHYTHMS:
        errors.append(f"pomodoro.rhythm must be one of {', '.join(RHYTHMS)}")
    for key, lo, hi in (("work", 1, 240), ("short", 1, 60), ("long", 1, 120), ("cycles", 1, 12)):
        v = pomo.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            errors.append(f"pomodoro.{key} must be a whole number from {lo} to {hi}")
    tips = clean.get("tips")
    if not isinstance(tips, list) or len(tips) > MAX_TIPS:
        errors.append(f"tips must be a list of at most {MAX_TIPS}")
    else:
        for i, tip in enumerate(tips):
            if not isinstance(tip, dict) or not isinstance(tip.get("title"), str) or not tip["title"].strip():
                errors.append(f"tips[{i}] needs a title")
                continue
            if len(tip["title"]) > 120 or len(str(tip.get("why", ""))) > 400:
                errors.append(f"tips[{i}]: title up to 120 and why up to 400 characters")
            tip.setdefault("id", "user-" + hashlib.sha256(tip["title"].encode()).hexdigest()[:8])
            tip.setdefault("why", "")
    alerts = clean.get("alerts") or {}
    if not isinstance(alerts.get("while_closed"), bool):
        errors.append("alerts.while_closed must be true or false")
    return clean, errors


def _dashboard_errors(pins: Any) -> list[str]:
    if not isinstance(pins, list) or len(pins) > MAX_PINS:
        return [f"dashboard must be a list of at most {MAX_PINS} tool ids"]
    errors = []
    seen: set = set()
    for i, mid in enumerate(pins):
        if not isinstance(mid, str) or mid not in PINNABLE:
            errors.append(f"dashboard[{i}]: {mid!r} cannot be on the dashboard (tools: {', '.join(PINNABLE)})")
        elif mid in seen:
            errors.append(f"dashboard[{i}]: {mid!r} is listed twice")
        else:
            seen.add(mid)
    return errors


def _clock_errors(clocks: Any) -> list[str]:
    """Problems with the world clock's places. A valid row's label is trimmed in place."""
    if not isinstance(clocks, list) or len(clocks) > MAX_CLOCKS:
        return [f"clocks must be a list of at most {MAX_CLOCKS} places"]
    errors = []
    seen: set = set()
    for i, row in enumerate(clocks):
        if not isinstance(row, dict) or set(row) != {"zone", "label"}:
            errors.append(f"clocks[{i}] must be an object with zone and label")
            continue
        zone, label = row["zone"], row["label"]
        if not isinstance(zone, str) or not places.zone_loads(zone):
            errors.append(f"clocks[{i}].zone: {zone!r} is not a time zone this Hermes knows (e.g. Europe/Berlin)")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= MAX_LABEL:
            errors.append(f"clocks[{i}].label must be text of 1 to {MAX_LABEL} characters")
            continue
        row["label"] = label.strip()
        if row["label"].lower() in seen:
            errors.append(f"clocks[{i}].label: {row['label']!r} is used twice (upper and lower case count as the same)")
        seen.add(row["label"].lower())
    return errors


def doc_hash(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def load_state(store: Store) -> tuple[dict, Optional[dict]]:
    """The toolbox in effect, and what is wrong with toolbox.json when it cannot be used.

    No file: the defaults (first run). A file from schema 1 is read as schema 2 (`migrate`); it is a
    valid file, and the next save writes it as schema 2. A file that is not JSON or not a valid
    toolbox (people edit it by hand): the newest valid saved version, else the defaults, plus a
    problem {reason, file, using, message}. Reading never writes; the next save keeps the broken file
    beside the new one."""
    try:
        raw = store.read_json(FILE)
    except StoreError as exc:
        reason = str(exc)
    else:
        if raw is None:
            return default_doc(), None
        clean, errors = validate(migrate(raw))
        if not errors:
            return clean, None
        reason = "; ".join(errors[:8])
    doc, using = _fallback(store)
    path = str(store.path(FILE))
    return doc, {"reason": reason, "file": path, "using": using,
                 "message": f"{path} is not a valid toolbox ({reason}). Eselsbrücke uses {using} until the file "
                            "is fixed or a change is saved; a save keeps the broken file beside the new one."}


def _fallback(store: Store) -> tuple[dict, str]:
    for n in reversed(_version_numbers(store)):
        try:
            row = store.read_json(VERSIONS, f"{n}.json")
        except StoreError:
            continue
        if isinstance(row, dict):
            clean, errors = validate(migrate(row.get("doc")))
            if not errors:
                return clean, f"version {n}"
    return default_doc(first_run=False), "defaults"


def load(store: Store) -> dict:
    """The toolbox in effect (see load_state)."""
    return load_state(store)[0]


def is_on(store: Store, module: str) -> bool:
    row = load(store)["modules"].get(module)
    return bool(row and row.get("on"))


def require_on(store: Store, module: Optional[str]) -> None:
    if module is not None and not is_on(store, module):
        raise SwitchedOff(module)


def _moved(before: list, after: list) -> bool:
    """Whether the items both lists hold stand in a different order."""
    return [x for x in before if x in after] != [x for x in after if x in before]


def _clock_changes(old: list[dict], new: list[dict]) -> list[str]:
    lines = []
    gone = [c for c in old if c not in new]
    came = [c for c in new if c not in old]
    renamed: dict[str, str] = {}
    for c in list(came):
        same_label = next((g for g in gone if g["label"] == c["label"]), None)
        same_zone = next((g for g in gone if g["zone"] == c["zone"]), None)
        if same_label:  # the label stayed and now names another zone
            lines.append(f"{c['label']} now shows {places.city_name(c['zone'])} time on the world clock")
            gone.remove(same_label)
            came.remove(c)
        elif same_zone:
            lines.append(f"{same_zone['label']} renamed to {c['label']} on the world clock")
            renamed[same_zone["label"]] = c["label"]
            gone.remove(same_zone)
            came.remove(c)
    lines += [f"{c['label']} added to the world clock" for c in came]
    lines += [f"{g['label']} removed from the world clock" for g in gone]
    if _moved([renamed.get(c["label"], c["label"]) for c in old], [c["label"] for c in new]):
        lines.append("World clock reordered")
    return lines


def _pomodoro_line(old: dict, new: dict) -> str:
    """The rhythm by its name while the name says it all, else every number."""
    named = new.get("rhythm") == f"{new.get('work')}/{new.get('short')}"
    if named and all(old.get(k) == new.get(k) for k in ("long", "cycles")):
        return f"Pomodoro: {new.get('rhythm')}"
    cycles = new.get("cycles")
    return (f"Pomodoro: work {new.get('work')}, short {new.get('short')}, long {new.get('long')}, "
            f"{cycles} {'cycle' if cycles == 1 else 'cycles'}")


def describe_changes(old: dict, new: dict) -> list[str]:
    """What a save changes, one sentence each, as the settings page's history shows them."""
    lines: list[str] = []
    for m in MODULES:
        mid = m["id"]
        a, b = old["modules"].get(mid, {}), new["modules"].get(mid, {})
        if a.get("on") != b.get("on"):
            lines.append(f"{m['title']} {'on' if b.get('on') else 'off'}")
        if a.get("options") != b.get("options"):
            lines.append(f"{m['title']} options changed")
    order_a = sorted(old["modules"], key=lambda k: old["modules"][k]["order"])
    order_b = sorted(new["modules"], key=lambda k: new["modules"][k]["order"])
    if order_a != order_b:
        lines.append("Order: " + ", ".join(MODULE_BY_ID[k]["title"] for k in order_b if new["modules"][k]["on"]))
    pins_a, pins_b = old.get("dashboard") or [], new.get("dashboard") or []
    lines += [f"{MODULE_BY_ID[k]['title']} added to the dashboard" for k in pins_b if k not in pins_a]
    lines += [f"{MODULE_BY_ID[k]['title']} removed from the dashboard" for k in pins_a if k not in pins_b]
    if _moved(pins_a, pins_b):
        lines.append("Dashboard reordered")
    lines += _clock_changes(old.get("clocks") or [], new.get("clocks") or [])
    layout_a, layout_b = old.get("layout") or {}, new.get("layout") or {}
    if layout_a.get("chip_visible") != layout_b.get("chip_visible"):
        lines.append(f"Status bar: {'shown' if layout_b.get('chip_visible') else 'hidden'}")
    if layout_a.get("chip") != layout_b.get("chip"):
        lines.append(f"Status bar shows: {CHIP_NAMES.get(layout_b.get('chip'), layout_b.get('chip'))}")
    if old.get("pomodoro") != new.get("pomodoro"):
        lines.append(_pomodoro_line(old.get("pomodoro") or {}, new.get("pomodoro") or {}))
    closed = (new.get("alerts") or {}).get("while_closed")
    if (old.get("alerts") or {}).get("while_closed") != closed:
        lines.append(f"Alerts while Desktop is closed: {'on' if closed else 'off'}")
    old_tips = {t.get("id"): t for t in old.get("tips", [])}
    new_tips = {t.get("id"): t for t in new.get("tips", [])}
    for tid in new_tips.keys() - old_tips.keys():
        lines.append(f"Tip added: {new_tips[tid]['title']}")
    for tid in old_tips.keys() - new_tips.keys():
        lines.append(f"Tip removed: {old_tips[tid]['title']}")
    if old.get("first_run") and not new.get("first_run") and not lines:
        lines.append("First run done")
    return lines


def _version_numbers(store: Store) -> list[int]:
    nums = []
    for name in store.listdir(VERSIONS):
        stem = name[:-5] if name.endswith(".json") else ""
        if stem.isdigit():
            nums.append(int(stem))
    return sorted(nums)


def save(store: Store, doc: dict, author: str, summary: Optional[str] = None) -> dict:
    """Validate and write the toolbox, keep a version, prune old ones, run AFTER_SAVE.

    Returns {"version", "summary", "changes", "toolbox"}. Raises ToolboxError("invalid", ...)."""
    if author not in ("user", "agent"):
        raise ToolboxError("invalid", "author must be user or agent")
    clean, errors = validate(doc)
    if errors:
        raise ToolboxError("invalid", "The toolbox was not saved: " + "; ".join(errors[:8]), errors=errors)
    with store.lock():
        old, problem = load_state(store)
        changes = describe_changes(old, clean)
        text = summary or (", ".join(changes) if changes else "No change")
        kept = _keep_broken(store) if problem else None
        store.write_json(FILE, clean)
        nums = _version_numbers(store)
        n = (nums[-1] + 1) if nums else 1
        store.write_json((VERSIONS, f"{n}.json"), {"n": n, "author": author, "time": clock.iso(),
                                                   "summary": text[:200], "doc": clean})
        for old_n in nums[: max(0, len(nums) + 1 - KEEP_VERSIONS)]:
            store.remove(VERSIONS, f"{old_n}.json")
    for hook in list(AFTER_SAVE):
        try:
            hook(store, old, clean)
        except Exception:  # a hook (alert reconcile) never undoes a save; it reports elsewhere
            pass
    out = {"version": n, "summary": text, "changes": changes, "toolbox": clean}
    if kept:
        out["kept_broken"] = kept
    return out


def _keep_broken(store: Store) -> Optional[str]:
    """Copy an unusable toolbox.json aside before a save replaces it; returns the copy's name."""
    src = store.path(FILE)
    if not src.exists():
        return None
    name = f"toolbox.broken-{clock.now().strftime('%Y%m%dT%H%M%S')}.json"
    shutil.copy2(src, store.path(name))
    return name


def _unchanged(doc: dict, summary: str) -> dict:
    """The answer of a helper that found nothing to change: no save, so no new version."""
    return {"version": None, "summary": summary, "changes": [], "toolbox": doc, "unchanged": True}


def set_switch(store: Store, module: str, on: bool, author: str) -> dict:
    if module not in MODULE_BY_ID:
        raise ToolboxError("unknown_tool", f"Unknown tool {module!r}. Tools: {', '.join(MODULE_IDS)}")
    if not isinstance(on, bool):
        raise ToolboxError("invalid", "on must be true or false")
    with store.lock():
        doc = load(store)
        doc["modules"][module]["on"] = on
        doc["first_run"] = False
        return save(store, doc, author, f"{MODULE_BY_ID[module]['title']} {'on' if on else 'off'}")


def _same(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def set_clock(store: Store, place: str, author: str, remove: bool = False, label: Optional[str] = None) -> dict:
    """Add a place to the world clock, or remove one. `place` is a city or a zone name; `label` is
    the name to show (default: the city). Adding a label that is there, or removing a place that is
    not, changes nothing and says so."""
    if not isinstance(place, str) or not place.strip():
        raise ToolboxError("invalid", "place must be a city like Tokyo or a zone like Europe/Berlin")
    if label is not None and (not isinstance(label, str) or not 1 <= len(label.strip()) <= MAX_LABEL):
        raise ToolboxError("invalid", f"label must be text of 1 to {MAX_LABEL} characters")
    hit = places.resolve(place)
    with store.lock():
        doc = load(store)
        clocks = doc["clocks"]
        if remove:
            # a label the user chose ("Office") is no city, so the typed text is tried as a label first
            names = [n for n in (label, place, hit and hit["label"]) if n]
            row = next((c for n in names for c in clocks if _same(c["label"], n)), None)
            if row is None and hit and "/" in place:  # a zone name means that zone, whatever its label
                row = next((c for c in clocks if c["zone"] == hit["zone"]), None)
            if row is None:
                return _unchanged(doc, f"{(label or place).strip()} is not on the world clock")
            clocks.remove(row)
            summary = f"{row['label']} removed from the world clock"
        else:
            if hit is None or not places.zone_loads(hit["zone"]):
                raise ToolboxError("unknown_place", f"Unknown place {place!r}. Use a city like Tokyo or a zone "
                                                    "like Europe/Berlin.")
            name = (label or hit["label"]).strip()
            if any(_same(c["label"], name) for c in clocks):
                return _unchanged(doc, f"{name} is already on the world clock")
            if len(clocks) >= MAX_CLOCKS:
                raise ToolboxError("full", f"The world clock holds at most {MAX_CLOCKS} places. Remove one first.")
            clocks.append({"zone": hit["zone"], "label": name})
            summary = f"{name} added to the world clock"
        doc["first_run"] = False
        return save(store, doc, author, summary)


def set_pin(store: Store, module: str, on: bool, author: str) -> dict:
    """Put a tool on the dashboard (at the end) or take it off. A tool that is switched off can be
    pinned; the dashboard skips it until it is switched on."""
    if module not in MODULE_BY_ID:
        raise ToolboxError("unknown_tool", f"Unknown tool {module!r}. Tools: {', '.join(MODULE_IDS)}")
    if not isinstance(on, bool):
        raise ToolboxError("invalid", "on must be true or false")
    title = MODULE_BY_ID[module]["title"]
    if module not in PINNABLE:
        raise ToolboxError("invalid", f"{title} has no place on the dashboard. Tools that have one: "
                                      f"{', '.join(PINNABLE)}")
    with store.lock():
        doc = load(store)
        pins = doc["dashboard"]
        if on == (module in pins):
            return _unchanged(doc, f"{title} is {'already' if on else 'not'} on the dashboard")
        if on:
            pins.append(module)
        else:
            pins.remove(module)
        doc["first_run"] = False
        return save(store, doc, author, f"{title} {'added to' if on else 'removed from'} the dashboard")


def preview(store: Store, patch: dict, author: str) -> dict:
    """The diff a patch would make, and an id that `apply` takes. Nothing is saved."""
    if not isinstance(patch, dict) or not patch:
        raise ToolboxError("invalid", "changes must be a non-empty object, e.g. {\"modules\": {\"qr\": {\"on\": false}}}")
    with store.lock():
        current = load(store)
        merged = _merge(current, patch)
        merged["first_run"] = False
        clean, errors = validate(merged)
        if errors:
            raise ToolboxError("invalid", "These changes are not valid: " + "; ".join(errors[:8]), errors=errors)
        changes = describe_changes(current, clean)
        pid = doc_hash({"base": current, "new": clean})
        store.write_json(PREVIEW, {"id": pid, "base": doc_hash(current), "doc": clean, "changes": changes,
                                   "author": author, "at": clock.iso()})
    return {"preview_id": pid, "changes": changes or ["No change"], "toolbox": clean}


def apply(store: Store, preview_id: str, author: str) -> dict:
    with store.lock():
        pending = store.read_json(PREVIEW)
        if not pending or pending.get("id") != preview_id:
            raise ToolboxError("unknown_preview", "No preview with that id; call preview again.")
        if pending.get("base") != doc_hash(load(store)):
            raise ToolboxError("stale_preview", "The toolbox changed since this preview; call preview again.")
        out = save(store, pending["doc"], author, ", ".join(pending.get("changes") or []) or None)
        store.remove(PREVIEW)
        return out


def versions(store: Store) -> list[dict]:
    nums = _version_numbers(store)
    out = []
    for n in reversed(nums):
        row = store.read_json(VERSIONS, f"{n}.json") or {}
        out.append({"n": n, "author": row.get("author"), "time": row.get("time"), "summary": row.get("summary"),
                    "current": n == nums[-1]})
    return out


def restore(store: Store, n: int, author: str) -> dict:
    if not isinstance(n, int) or isinstance(n, bool):
        raise ToolboxError("invalid", "version must be a whole number")
    try:
        row = store.read_json(VERSIONS, f"{n}.json")
    except StoreError as exc:
        raise ToolboxError("invalid", f"Saved version {n} cannot be read: {exc}") from exc
    if not isinstance(row, dict) or "doc" not in row:
        raise ToolboxError("unknown_version", f"No saved version {n}; the last {KEEP_VERSIONS} are kept.")
    doc = migrate(row["doc"])
    if isinstance(row["doc"], dict) and doc is not row["doc"]:
        # A version saved before the dashboard and the world clock existed says nothing about them:
        # going back to it keeps today's pins and places, where the migration alone would reset both.
        current = load(store)
        doc.update({k: copy.deepcopy(current[k]) for k in ("dashboard", "clocks") if k not in row["doc"]})
    return save(store, doc, author, f"Restored v{n}")


def view(store: Store) -> dict:
    """What the page and the agent's `list` see: the file and the registry rows with their switch."""
    doc, problem = load_state(store)
    tools = []
    for m in sorted(MODULES, key=lambda r: doc["modules"][r["id"]]["order"]):
        tools.append({**m, "on": doc["modules"][m["id"]]["on"], "options": doc["modules"][m["id"]]["options"]})
    return {"schema": SCHEMA, "toolbox": doc, "tools": tools,
            "hash": doc_hash(doc), **({"file_error": problem} if problem else {})}


__all__ = ["StoreError"]
