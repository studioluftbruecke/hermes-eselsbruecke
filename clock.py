"""\"Today\" in Hermes' own time zone.

`now()` is `hermes_time.now()`: the profile's `timezone` setting, `HERMES_TIMEZONE` overrides,
empty means server-local time. Tests replace the clock with `set_clock()`.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Optional

_override: Optional[Callable[[], dt.datetime]] = None
_zone_override: Optional[str] = None


def set_clock(fn: Optional[Callable[[], dt.datetime]], zone: Optional[str] = None) -> None:
    """Tests: a fixed or stepping clock (aware datetimes) and the zone name it stands for."""
    global _override, _zone_override
    _override = fn
    _zone_override = zone


def now() -> dt.datetime:
    if _override is not None:
        return _override()
    # `hermes_time` is not in Hermes' published plugin API, and no ctx call gives the zone. It
    # stays, guarded: restating it would miss its per-profile rules under the multiplexed gateway.
    # Without it the plugin uses server-local time, which is what Hermes does with no zone set.
    try:
        import hermes_time

        return hermes_time.now()
    except Exception:
        return dt.datetime.now().astimezone()


def zone_name() -> str:
    """The configured IANA zone, or "" when Hermes uses server-local time."""
    if _zone_override is not None:
        return _zone_override
    try:
        import hermes_time

        return hermes_time.get_timezone_name() or ""
    except Exception:
        return ""


def today(at: Optional[dt.datetime] = None) -> dt.date:
    return (at or now()).date()


def iso(at: Optional[dt.datetime] = None) -> str:
    return (at or now()).isoformat(timespec="seconds")


def parse(value: str) -> dt.datetime:
    """An ISO timestamp; a naive one is read in Hermes' zone."""
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now().tzinfo)
    return parsed


def zone_info() -> dict:
    name = zone_name()
    return {"zone": name or None, "server_local": not name,
            "offset": now().strftime("%z"),
            "note": None if name else ("Hermes has no time zone set, so 'today' follows the server's clock "
                                       "(often UTC). Set `timezone` in Hermes' settings.")}
