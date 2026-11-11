"""eselsbruecke_calc: exact arithmetic, percentages, units, durations x rates, dates."""
from __future__ import annotations

from .. import clock
from ..engines import calc

SCHEMA = {
    "name": "eselsbruecke_calc",
    "description": (
        "Exact calculator (Decimal, no floating-point drift). Use it instead of mental arithmetic. "
        "expr examples: '16,90 * 12' (comma decimals answer with a comma), '3 * 4,50 + 19%' (+ p% adds p "
        "percent), '19% of 240', '2h 30m * 85 €/h', '5 km in mi', '1.5 GiB to MB', '2026-11-09 + 30 days', "
        "'2026-12-24 - today' (today in Hermes' time zone). Units: mm cm m km in ft yd mi, mg g kg t oz lb, "
        "s min h d wk, B KB MB GB TB KiB MiB GiB, € $ £ CHF, months/years with dates. Returns result (as "
        "the user would read it) and value (dot decimal)."
    ),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["calc"]},
        "expr": {"type": "string", "description": "The expression; a trailing '=' is ignored."},
    }, "required": ["expr"]},
}


def handle(action: str, args: dict, env) -> dict:
    try:
        out = calc.evaluate(str(args.get("expr", "")), clock.now())
    except calc.CalcError as exc:
        return {"ok": False, "error": "calc", "message": str(exc)}
    return out
