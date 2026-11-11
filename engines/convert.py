"""Conversions for `eselsbruecke_convert` and the page's Python-side tools: time zones and Unix
timestamps (zoneinfo; a zone is named by its tz name or by a city, see `places.py`), base64 and URL
encoding, colours (hex, rgb, hsl, oklch, WCAG contrast) and cron expressions (croniter, a core Hermes
dependency, plus our own wording).

The Desktop half computes encode, colour and time zones in JavaScript as you type; both halves run
`tests/fixtures/parity.json`, so their answers are the same. Rounding is half away from zero in both
(`rnd`), never Python's banker's rounding.
"""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import math
import re
import urllib.parse
from typing import Optional
from zoneinfo import ZoneInfo

from . import places


class ConvertError(ValueError):
    pass


def rnd(x: float, places: int = 0) -> float:
    """Half away from zero, like JavaScript's Math.round for positives: identical in both halves."""
    f = 10 ** places
    v = math.floor(abs(x) * f + 0.5) / f
    return -v if x < 0 else v


def _num(x: float) -> str:
    """Shortest text for a rounded number: 160.0 -> 160, 0.5 -> 0.5 (as JavaScript prints it)."""
    if x == int(x):
        return str(int(x))
    return repr(float(x))


# --- time zones and timestamps ---------------------------------------------------------------------

def place(name: str) -> tuple[str, Optional[str]]:
    """The tz name behind what was typed, and the city's label when it was a city.

    A name the tz database knows is taken as it is, so a zone name answers exactly as it always did;
    anything else is looked up as a city."""
    text = str(name).strip()
    if places.zone_loads(text):
        return text, None
    hit = places.resolve(text)
    if hit and places.zone_loads(hit["zone"]):
        return hit["zone"], (hit["label"] if hit["zone"] != "UTC" else None)
    raise ConvertError(f"unknown place or time zone {name!r} (use a city like Tokyo or a zone like Europe/Berlin)")


def zone(name: str) -> ZoneInfo:
    return ZoneInfo(place(name)[0])


def _row(when: dt.datetime, name: str) -> dict:
    tz_name, label = place(name)
    local = when.astimezone(ZoneInfo(tz_name))
    off = local.utcoffset() or dt.timedelta(0)
    mins = int(off.total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    row = {"zone": tz_name, "time": local.strftime("%Y-%m-%d %H:%M"), "weekday": local.strftime("%a"),
           "offset": f"UTC{sign}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}", "abbr": local.tzname()}
    if label:
        row["place"] = label
    return row


def convert_time(time: str, from_zone: str, to_zones: list[str], now: Optional[dt.datetime] = None) -> dict:
    src = zone(from_zone)
    text = (time or "now").strip()
    if text.lower() == "now":
        when = (now or dt.datetime.now(dt.timezone.utc)).astimezone(src)
    else:
        try:
            parsed = dt.datetime.fromisoformat(text.replace("T", " ").replace("Z", "+00:00"))
        except ValueError:
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
            if not m:
                raise ConvertError(f"cannot read the time {text!r}; use 2026-11-09 14:30, 14:30 or now")
            base = (now or dt.datetime.now(dt.timezone.utc)).astimezone(src)
            parsed = base.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0,
                                  tzinfo=None)
        when = parsed if parsed.tzinfo else parsed.replace(tzinfo=src)
    zones = [z for z in (to_zones or []) if str(z).strip()] or ["UTC"]
    if len(zones) > 12:
        raise ConvertError("at most 12 zones")
    return {"from": _row(when, from_zone), "to": [_row(when, z) for z in zones],
            "unix": int(when.timestamp())}


def convert_timestamp(value, zones: Optional[list[str]] = None) -> dict:
    zones = [z for z in (zones or []) if str(z).strip()] or ["UTC"]
    text = str(value).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        num = float(text)
        unit = "ms" if abs(num) >= 1e11 else "s"
        secs = num / 1000 if unit == "ms" else num
        when = dt.datetime.fromtimestamp(secs, dt.timezone.utc)
        return {"input_unit": unit, "unix": int(math.floor(secs)), "unix_ms": int(rnd(secs * 1000)),
                "iso_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "zones": [_row(when, z) for z in zones]}
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConvertError(f"cannot read {text!r}: give Unix seconds, milliseconds or an ISO date") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone(zones[0]))
    secs = parsed.timestamp()
    return {"input_unit": "iso", "unix": int(math.floor(secs)), "unix_ms": int(rnd(secs * 1000)),
            "iso_utc": parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "zones": [_row(parsed, z) for z in zones]}


# --- encode and decode -----------------------------------------------------------------------------

SCHEMES = ("base64", "base64url", "url")
_URL_SAFE = "-_.!~*'()"  # what JavaScript's encodeURIComponent leaves alone


def encode(text: str, scheme: str) -> str:
    data = str(text).encode("utf-8")
    if scheme == "base64":
        return base64.b64encode(data).decode("ascii")
    if scheme == "base64url":
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    if scheme == "url":
        return urllib.parse.quote(str(text), safe=_URL_SAFE)
    raise ConvertError(f"scheme must be one of {', '.join(SCHEMES)}")


def decode(text: str, scheme: str) -> str:
    raw = str(text).strip()
    try:
        if scheme in ("base64", "base64url"):
            cleaned = re.sub(r"\s+", "", raw)
            if scheme == "base64url":
                cleaned = cleaned.replace("-", "+").replace("_", "/")
            if re.search(r"[^A-Za-z0-9+/=]", cleaned):
                raise ConvertError("not base64: only A-Z, a-z, 0-9, + / (or - _ for base64url) and = are allowed")
            cleaned += "=" * (-len(cleaned) % 4)
            data = base64.b64decode(cleaned, validate=True)
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ConvertError("decoded bytes are not UTF-8 text") from exc
        if scheme == "url":
            if re.search(r"%(?![0-9A-Fa-f]{2})", raw):
                raise ConvertError("not URL-encoded: a % must be followed by two hex digits")
            return urllib.parse.unquote(raw, errors="strict")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ConvertError(f"cannot decode: {exc}") from exc
    raise ConvertError(f"scheme must be one of {', '.join(SCHEMES)}")


# --- colour ----------------------------------------------------------------------------------------

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _srgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    r, g, b = _lin(r), _lin(g), _lin(b)
    l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l_ ** (1 / 3), m_ ** (1 / 3), s_ ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def _oklab_to_srgb(L: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bb = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    return _gam(r) if r > 0 else r * 12.92, _gam(g) if g > 0 else g * 12.92, _gam(bb) if bb > 0 else bb * 12.92


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    h = (h % 360) / 360
    if s == 0:
        return l, l, l

    def hue(p, q, t):
        t %= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    return hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)


def _rgb_to_hsl(r: float, g: float, b: float) -> tuple[float, float, float]:
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60, s, l


_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)"
NAMED = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
         "yellow": "#ffff00", "orange": "#ffa500", "purple": "#800080", "gray": "#808080", "grey": "#808080",
         "transparent": "#00000000"}


def parse_colour(text: str) -> tuple[float, float, float, float, bool]:
    """sRGB 0..1 channels, alpha, and whether an oklch input was outside sRGB (clamped)."""
    t = str(text).strip().lower()
    t = NAMED.get(t, t)
    m = re.fullmatch(r"#?([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})", t)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a, False
    m = re.fullmatch(rf"(rgba?|hsla?|oklch)\(\s*({_NUM})(%?)[\s,]+({_NUM})(%?)[\s,]+({_NUM})(%?)\s*(?:[,/]\s*({_NUM})(%?))?\s*\)", t)
    if not m:
        raise ConvertError(f"cannot read the colour {text!r}; use #2f9e6b, rgb(47 158 107), hsl(153 54% 40%) or oklch(62% 0.13 160)")
    fn = m.group(1)
    v1, p1, v2, p2, v3, p3, va, pa = (float(m.group(2)), m.group(3), float(m.group(4)), m.group(5),
                                      float(m.group(6)), m.group(7), m.group(8), m.group(9))
    alpha = 1.0 if va is None else _clamp(float(va) / (100 if pa else 1))
    if fn.startswith("rgb"):
        ch = [v / 100 if p else v / 255 for v, p in ((v1, p1), (v2, p2), (v3, p3))]
        return _clamp(ch[0]), _clamp(ch[1]), _clamp(ch[2]), alpha, False
    if fn.startswith("hsl"):
        r, g, b = _hsl_to_rgb(v1, _clamp(v2 / 100), _clamp(v3 / 100))
        return r, g, b, alpha, False
    L = v1 / 100 if p1 else v1
    C = v2 / 100 * 0.4 if p2 else v2
    hrad = math.radians(v3)
    r, g, b = _oklab_to_srgb(L, C * math.cos(hrad), C * math.sin(hrad))
    out = any(c < -0.01 or c > 1.01 for c in (r, g, b))  # slack for rounded oklch text (2.5 8-bit steps)
    return _clamp(r), _clamp(g), _clamp(b), alpha, out


def _hex(r: float, g: float, b: float, a: float = 1.0) -> str:
    out = "#" + "".join(f"{int(rnd(c * 255)):02x}" for c in (r, g, b))
    return out + (f"{int(rnd(a * 255)):02x}" if a < 1 else "")


def luminance(r: float, g: float, b: float) -> float:
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: tuple, bg: tuple) -> float:
    l1, l2 = luminance(*fg[:3]), luminance(*bg[:3])
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def colour(text: str, background: Optional[str] = None) -> dict:
    r, g, b, a, out_of_gamut = parse_colour(text)
    # Formats derive from the 8-bit colour (as the picker shows it), so every format names one colour.
    r8, g8, b8 = (int(rnd(c * 255)) for c in (r, g, b))
    r, g, b = r8 / 255, g8 / 255, b8 / 255
    h, s, l = _rgb_to_hsl(r, g, b)
    L, A, B = _srgb_to_oklab(r, g, b)
    C = math.sqrt(A * A + B * B)
    H = math.degrees(math.atan2(B, A)) % 360 if C > 0.0002 else 0.0
    alpha = "" if a >= 1 else f" / {_num(rnd(a, 2))}"
    res = {
        "hex": _hex(r, g, b, a),
        "rgb": f"rgb({r8} {g8} {b8}{alpha})",
        "hsl": f"hsl({_num(rnd(h, 1))} {_num(rnd(s * 100, 1))}% {_num(rnd(l * 100, 1))}%{alpha})",
        "oklch": f"oklch({_num(rnd(L * 100, 1))}% {_num(rnd(C, 3))} {_num(rnd(H, 1))}{alpha})",
        "alpha": rnd(a, 2),
        "out_of_gamut": out_of_gamut,
    }
    if background:
        br, bgc, bb, _ba, _ = parse_colour(background)
        bg8 = tuple(int(rnd(c * 255)) / 255 for c in (br, bgc, bb))
        ratio = rnd(contrast((r, g, b), bg8), 2)
        res["contrast"] = {"background": _hex(*bg8), "ratio": ratio,
                           "aa_normal": ratio >= 4.5, "aa_large": ratio >= 3,
                           "aaa_normal": ratio >= 7, "aaa_large": ratio >= 4.5}
    return res


# --- cron ------------------------------------------------------------------------------------------

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MACROS = {"@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *", "@weekly": "0 0 * * 0",
          "@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@hourly": "0 * * * *"}
_NAMES = {**{m[:3].lower(): str(i + 1) for i, m in enumerate(MONTHS)}, **{d[:3].lower(): str(i) for i, d in enumerate(DAYS)}}


def _names(field: str) -> str:
    return re.sub(r"[a-zA-Z]{3}", lambda m: _NAMES.get(m.group(0).lower(), m.group(0)), field)


def _part(field: str, unit: str, label=lambda v: v) -> str:
    """One cron field in words: '*', '*/n', 'a-b', 'a-b/n', 'a,b,c'."""
    if field == "*":
        return f"every {unit}"
    if field.startswith("*/"):
        return f"every {field[2:]} {unit}s"
    pieces = []
    for item in field.split(","):
        m = re.fullmatch(r"(\d+)-(\d+)(?:/(\d+))?", item)
        if m:
            a, b, step = m.groups()
            text = f"{label(a)} to {label(b)}"
            pieces.append(f"every {step} {unit}s from {text}" if step else text)
        else:
            m2 = re.fullmatch(r"(\d+)/(\d+)", item)
            pieces.append(f"every {m2.group(2)} {unit}s from {label(m2.group(1))}" if m2 else label(item))
    return ", ".join(pieces[:-1]) + (" and " if len(pieces) > 1 else "") + pieces[-1]


def describe_cron(expr: str) -> str:
    raw = expr.strip()
    fields = MACROS.get(raw.lower(), raw).split()
    if len(fields) != 5:
        raise ConvertError("a cron expression has 5 fields: minute hour day-of-month month day-of-week")
    minute, hour, dom, month, dow = (_names(f) for f in fields)
    if re.fullmatch(r"\d+", minute) and re.fullmatch(r"\d+", hour):
        when = f"at {int(hour):02d}:{int(minute):02d}"
    elif re.fullmatch(r"\d+", minute) and hour == "*":
        when = "every hour at minute " + minute
    elif minute == "*" and hour == "*":
        when = "every minute"
    elif minute.startswith("*/") and hour == "*":
        when = f"every {minute[2:]} minutes"
    elif re.fullmatch(r"\d+", minute):
        when = f"at minute {minute} of " + _part(hour, "hour", lambda v: f"{int(v):02d}:00").replace("every hour", "every hour")
    else:
        when = _part(minute, "minute") + " past " + _part(hour, "hour", lambda v: f"{int(v):02d}:00")
    parts = [when]
    if dom != "*":
        parts.append("on day " + _part(dom, "day") + " of the month")
    if month != "*":
        parts.append("in " + _part(month, "month", lambda v: MONTHS[int(v) - 1]))
    if dow != "*":
        joiner = "or on " if dom != "*" else "on "
        parts.append(joiner + _part(dow, "weekday", lambda v: DAYS[int(v) % 7]))
    return " ".join(parts)


def cron(expr: str, zone_name: str = "UTC", count: int = 5, now: Optional[dt.datetime] = None) -> dict:
    try:
        from croniter import croniter
    except ImportError as exc:  # a core Hermes dependency; missing only outside Hermes
        raise ConvertError("croniter is not installed") from exc
    text = (expr or "").strip()
    words = describe_cron(text)
    tz_name, label = place(zone_name)
    tz = ZoneInfo(tz_name)
    start = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    try:
        it = croniter(MACROS.get(text.lower(), text), start)
    except (ValueError, KeyError) as exc:
        raise ConvertError(f"not a valid cron expression: {exc}") from exc
    count = max(1, min(int(count or 5), 20))
    runs = [it.get_next(dt.datetime).astimezone(tz).strftime("%Y-%m-%d %H:%M %a") for _ in range(count)]
    return {"expression": text, "words": words, "zone": tz_name, **({"place": label} if label else {}), "next": runs}
