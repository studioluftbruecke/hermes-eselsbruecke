"""Places for the world clock: a typed city or zone name as a tz database zone and a label.

The list is `data/places.json` (the tz database's zone.tab plus a city list), the same file the
Desktop half resolves names with (`desktop/src/clockmath.js` `resolvePlace`), so "Mumbai" means the
same zone for the page and the agent. `tests/fixtures/places.json` holds the answers both must give.
Matching is exact after folding; searching by prefix is the page picker's job.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Read once at import, with the code: a file read per call could differ from the code that reads it.
_DATA = json.loads((Path(__file__).resolve().parents[1] / "data" / "places.json").read_text(encoding="utf-8"))
_NAMES: dict[str, str] = _DATA["names"]


def fold(text: str) -> str:
    """One spelling for matching: lower case, no accents, no dots or apostrophes, hyphens as spaces."""
    plain = "".join(c for c in unicodedata.normalize("NFD", str(text)) if not "\u0300" <= c <= "\u036f")
    plain = re.sub(r"[.'\u2019]", "", plain.lower()).replace("-", " ")
    return re.sub(r"\s+", " ", plain).strip()


def city_name(zone: str) -> str:
    """The name a zone is shown under: its display name, else its last path segment."""
    if zone == "UTC":
        return "UTC"
    return _NAMES.get(zone) or zone.split("/")[-1].replace("_", " ")


def _by_key() -> dict[str, tuple[str, str]]:
    """Folded city -> (zone, city as written); the first place with a name wins, in the page's order:
    UTC, the city list, then every zone under its display name."""
    out: dict[str, tuple[str, str]] = {}
    rows = [("UTC", "UTC")]
    rows += [(city, zone) for city, zone, _country in _DATA["cities"]]
    rows += [(city_name(zone), zone) for zone in _DATA["zones"]]
    for city, zone in rows:
        out.setdefault(fold(city), (zone, city))
    return out


_BY_KEY = _by_key()
# Intl in the Desktop ignores the case of a zone name and zoneinfo does not, so a typed zone name is
# looked up here and answered in the list's own spelling by both halves.
_ZONE_BY_LOWER = {zone.lower(): zone for zone in _DATA["zones"]}


def zone_loads(zone: str) -> bool:
    """Whether this Python's tz database has the zone (a new name can be missing from an old one)."""
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


def resolve(name: str) -> Optional[dict]:
    """{"zone", "label"} for "UTC", a zone name from the list (typed in any case), or a city by its
    exact folded name; None when the text is not a place."""
    text = str(name or "").strip()
    if not text:
        return None
    if text.lower() == "utc":
        return {"zone": "UTC", "label": "UTC"}
    if "/" in text:
        zone = _ZONE_BY_LOWER.get(text.lower())
        return {"zone": zone, "label": city_name(zone)} if zone and zone_loads(zone) else None
    hit = _BY_KEY.get(fold(text))
    return {"zone": hit[0], "label": hit[1]} if hit else None
