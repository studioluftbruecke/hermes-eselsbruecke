"""Exact arithmetic for the pad's `=` lines and `eselsbruecke_calc`: Decimal numbers, percentages,
units, durations times rates, and dates. A small recursive-descent parser; nothing is ever `eval`ed.

    16,90 * 12                  -> 202,8          (a comma decimal in the input gives a comma answer)
    3 * 4,50 + 19%              -> 16,065         (+ p% adds p percent of the left side)
    19% of 240                  -> 45.6
    2h 30m * 85 €/h             -> 212.50 €       (a duration times a rate)
    5 km in mi                  -> 3.1068559612 mi
    1.5 GiB to MB               -> 1610.612736 MB
    2026-11-09 + 30 days        -> 2026-12-09
    2026-12-24 - today          -> 45 days        (today in Hermes' time zone)

Numbers: `.` or `,` is the decimal separator; with both in one number the last one is decimal and the
other groups thousands (`1.234,56`, `1,234.56`). Operators: + - * / x × ÷ ^ ( ) and `%`, `of`,
`in`/`to` for conversions.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext
from typing import Optional

MAX_LEN = 500
MAX_DEPTH = 50  # nested ( ), ^ and unary signs; each level costs about six Python frames
DATE_RANGE = "the date falls outside years 1 to 9999"
PREC = 40  # significant digits; set per evaluation, because a Decimal context belongs to one thread
MAX_DURATION_S = Decimal(10) ** 18  # about 31 billion years; longer durations are not spelled out


class CalcError(ValueError):
    pass


class NotACalculation(CalcError):
    """A word or sign the calculator does not read: the text is no calculation (a note ending in `=`)."""


# unit -> (factor to the base unit, dims). Bases: m, kg, s, B; currencies are their own dimension.
_LEN = {"mm": "0.001", "cm": "0.01", "m": "1", "km": "1000", "in": "0.0254", "inch": "0.0254",
        "inches": "0.0254", "ft": "0.3048", "feet": "0.3048", "foot": "0.3048", "yd": "0.9144",
        "mi": "1609.344", "mile": "1609.344", "miles": "1609.344"}
_MASS = {"mg": "0.000001", "g": "0.001", "kg": "1", "t": "1000", "oz": "0.028349523125", "lb": "0.45359237",
         "lbs": "0.45359237"}
_TIME = {"s": "1", "sec": "1", "secs": "1", "second": "1", "seconds": "1", "min": "60", "mins": "60",
         "minute": "60", "minutes": "60", "h": "3600", "hr": "3600", "hrs": "3600", "hour": "3600",
         "hours": "3600", "d": "86400", "day": "86400", "days": "86400", "wk": "604800", "week": "604800",
         "weeks": "604800"}
_DATA = {"b": "1", "kb": "1000", "mb": "1000000", "gb": "1000000000", "tb": "1000000000000",
         "kib": "1024", "mib": "1048576", "gib": "1073741824", "tib": "1099511627776"}
_CAL = {"month": "month", "months": "month", "year": "year", "years": "year"}
_CURRENCY = {"€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR", "$": "USD", "usd": "USD",
             "£": "GBP", "gbp": "GBP", "chf": "CHF"}
_CUR_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}

UNITS: dict[str, tuple[Decimal, dict, str]] = {}
for table, dim in ((_LEN, "L"), (_MASS, "M"), (_TIME, "T"), (_DATA, "D")):
    for name, factor in table.items():
        UNITS[name] = (Decimal(factor), {dim: 1}, name)
for name, code in _CURRENCY.items():
    UNITS[name] = (Decimal(1), {"CUR_" + code: 1}, _CUR_SYMBOL[code])
_DISPLAY_NAMES = {"b": "B", "kb": "KB", "mb": "MB", "gb": "GB", "tb": "TB", "kib": "KiB", "mib": "MiB",
                  "gib": "GiB", "tib": "TiB"}
KEYWORDS = {"in", "to", "of", "today", "now", "x"}


@dataclass
class Q:
    value: Decimal
    dims: dict = field(default_factory=dict)
    hint: Optional[str] = None  # the unit name to show the result in
    percent: bool = False
    cal: Optional[str] = None  # "month" / "year": calendar steps, only for dates


@dataclass
class D:
    when: dt.datetime
    has_time: bool = False


TOKEN_RE = re.compile(r"""
    (?P<date>\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2})?)
  | (?P<num>\d[\d.,_']*)
  | (?P<op>[-+*/×÷^()%=])
  | (?P<cur>[€$£])
  | (?P<word>[A-Za-zÄÖÜäöüß]+)
  | (?P<ws>\s+)
""", re.X)


def _number(text: str) -> tuple[Decimal, Optional[str]]:
    """The value and the decimal separator the user wrote (None when the number has none)."""
    raw = text.replace("_", "").replace("'", "")
    sep = None
    if "," in raw and "." in raw:
        sep = "," if raw.rfind(",") > raw.rfind(".") else "."
        raw = raw.replace("." if sep == "," else ",", "").replace(",", ".")
    elif "," in raw:
        if raw.count(",") > 1:
            raise CalcError(f"cannot read the number {text!r}")
        sep, raw = ",", raw.replace(",", ".")
    elif "." in raw:
        if raw.count(".") > 1:
            raise CalcError(f"cannot read the number {text!r}")
        sep = "."
    raw = raw.rstrip(".")
    try:
        return Decimal(raw), sep
    except InvalidOperation as exc:
        raise CalcError(f"cannot read the number {text!r}") from exc


def tokenize(text: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise NotACalculation(f"unexpected {text[pos]!r} at position {pos + 1}")
        kind = m.lastgroup
        val = m.group(kind)
        pos = m.end()
        if kind == "ws":
            continue
        if kind == "num" and val[-1] in ".,'_":
            # a trailing separator belongs to the sentence, not the number ("12 * 3.")
            out.append(("num", val[:-1]))
            continue
        out.append((kind, val))
    return out


def _merge_dims(a: dict, b: dict, sign: int = 1) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + sign * v
        if out[k] == 0:
            del out[k]
    return out


class Parser:
    def __init__(self, text: str, today: dt.datetime):
        self.toks = tokenize(text)
        self.i = 0
        self.today = today
        self.seps: set[str] = set()
        self.depth = 0

    def peek(self, k: int = 0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def is_op(self, *ops) -> bool:
        kind, val = self.peek()
        return kind == "op" and val in ops

    def is_word(self, *words) -> bool:
        kind, val = self.peek()
        return kind == "word" and val.lower() in words

    def unit_ahead(self) -> bool:
        kind, val = self.peek()
        if kind == "cur":
            return True
        if kind != "word":
            return False
        low = val.lower()
        if low in ("in", "to"):
            # "in" is inches only when no unit follows it ("5 km in mi" converts, "10 in" is inches)
            nk, nv = self.peek(1)
            if low == "to" or nk == "cur" or (nk == "word" and ((nv or "").lower() in UNITS or (nv or "").lower() in _CAL)):
                return False
        return low in UNITS or low in _CAL

    # statement := expr [ (in|to) unitexpr ]
    def statement(self):
        value = self.expr()
        target = None
        if self.is_word("in", "to"):
            self.take()
            target = self.unit_expr(required=True)
        if self.peek()[0] is not None:
            raise NotACalculation(f"unexpected {self.peek()[1]!r}")
        return value, target

    def expr(self):
        left = self.term()
        while self.is_op("+", "-"):
            op = self.take()[1]
            right = self.term()
            left = add(left, right, op)
        return left

    def term(self):
        left = self.factor()
        while self.is_op("*", "/", "×", "÷") or self.is_word("x") or self.is_word("of"):
            kind, val = self.take()
            right = self.factor()
            if val.lower() == "of":
                if not (isinstance(left, Q) and left.percent):
                    raise CalcError("'of' needs a percentage before it, e.g. 19% of 240")
                left = mul(Q(left.value), right)
            elif val in ("*", "×") or val.lower() == "x":
                left = mul(left, right)
            else:
                left = div(left, right)
        return left

    def factor(self):
        # every nesting path (a "(", the right side of "^", a unary sign) passes through here
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise CalcError(f"the expression is nested too deep (at most {MAX_DEPTH} levels)")
        try:
            return self._factor()
        finally:
            self.depth -= 1

    def _factor(self):
        if self.is_op("-"):
            self.take()
            v = self.factor()
            if isinstance(v, D):
                raise CalcError("a date cannot be negative")
            return Q(-v.value, v.dims, v.hint, v.percent, v.cal)
        if self.is_op("+"):
            self.take()
            return self.factor()
        return self.power()

    def power(self):
        base = self.postfix()
        if self.is_op("^"):
            self.take()
            exp = self.factor()
            if not isinstance(base, Q) or not isinstance(exp, Q) or exp.dims or base.dims:
                raise CalcError("^ works on plain numbers")
            if exp.value != exp.value.to_integral_value() or abs(exp.value) > 1000:
                raise CalcError("the exponent must be a whole number up to 1000")
            try:
                value = base.value ** int(exp.value)
            except (InvalidOperation, DivisionByZero) as exc:
                raise CalcError("that power has no finite answer") from exc
            if not value.is_finite():  # 0 ^ -1 gives Infinity without a signal
                raise CalcError("that power has no finite answer")
            return Q(value)
        return base

    def postfix(self):
        v = self.atom()
        if self.is_op("%"):
            self.take()
            if not isinstance(v, Q) or v.dims:
                raise CalcError("% follows a plain number")
            v = Q(v.value / 100, percent=True)
        return v

    def atom(self):
        kind, val = self.peek()
        if kind == "op" and val == "(":
            self.take()
            v = self.expr()
            if not self.is_op(")"):
                raise CalcError("a ( is not closed")
            self.take()
            return self.maybe_units(v)
        if kind == "date":
            self.take()
            fmt = "%Y-%m-%d %H:%M" if (" " in val or "T" in val) else "%Y-%m-%d"
            try:
                when = dt.datetime.strptime(val.replace("T", " "), fmt)
            except ValueError as exc:
                raise CalcError(f"not a date: {val}") from exc
            return D(when, has_time=fmt != "%Y-%m-%d")
        if kind == "word" and val.lower() in ("today", "now"):
            self.take()
            base = self.today.replace(tzinfo=None, second=0, microsecond=0)
            if val.lower() == "today":
                return D(dt.datetime(base.year, base.month, base.day))
            return D(base, has_time=True)
        if kind == "cur":  # "€ 85" or "$12"
            self.take()
            nk, nv = self.peek()
            if nk != "num":
                raise CalcError(f"a number must follow {val}")
            self.take()
            num, sep = _number(nv)
            if sep:
                self.seps.add(sep)
            return self.maybe_units(Q(num, dict(UNITS[val][1]), UNITS[val][2]))
        if kind == "num":
            self.take()
            num, sep = _number(val)
            if sep:
                self.seps.add(sep)
            return self.maybe_units(Q(num))
        if kind is None:
            raise CalcError("the expression ends too early")
        raise NotACalculation(f"unexpected {val!r}")

    def maybe_units(self, v):
        """`85 €/h`, `2h 30m`, `5 km`: unit words after a number, and a sum of adjacent durations."""
        if not isinstance(v, Q) or not self.unit_ahead():
            return v
        factor, dims, hint, cal = self.unit_expr()
        q = Q(v.value * factor, _merge_dims(v.dims, dims), hint or v.hint, cal=cal)
        # adjacent quantities of the same dimension add up: "2h 30m", "1 km 200 m"
        while self.peek()[0] == "num" and q.dims and not q.cal:
            save = self.i
            nk, nv = self.take()
            if not self.unit_ahead():
                self.i = save
                break
            prev_time = q.dims == {"T": 1}
            kind2, word = self.peek()
            if prev_time and kind2 == "word" and word.lower() == "m":
                self.take()
                f2, d2, h2, c2 = Decimal(60), {"T": 1}, "min", None
            else:
                f2, d2, h2, c2 = self.unit_expr()
            if d2 != q.dims or c2:
                self.i = save
                break
            num, sep = _number(nv)
            if sep:
                self.seps.add(sep)
            q = Q(q.value + num * f2, q.dims, q.hint)
        return q

    def unit_expr(self, required: bool = False):
        """unit ['/' unit] -> (factor, dims, display, cal)."""
        kind, val = self.peek()
        if not self.unit_ahead():
            if required:
                raise CalcError(f"unknown unit {val!r}" if val else "a unit must follow 'in'")
            return Decimal(1), {}, None, None
        self.take()
        low = val.lower() if kind == "word" else val
        if low in _CAL:
            return Decimal(1), {"CAL": 1}, _CAL[low], _CAL[low]
        factor, dims, display = UNITS[low]
        display = _DISPLAY_NAMES.get(low, display)
        if self.is_op("/") and self.peek(1)[0] in ("word", "cur") and (
                (self.peek(1)[1] or "").lower() in UNITS):
            self.take()
            _, val2 = self.take()
            f2, d2, disp2 = UNITS[val2.lower() if val2 not in UNITS else val2]
            return factor / f2, _merge_dims(dims, d2, -1), f"{display}/{_DISPLAY_NAMES.get(val2.lower(), disp2)}", None
        return factor, dict(dims), display, None


def add(a, b, op: str):
    sign = 1 if op == "+" else -1
    if isinstance(a, D):
        if isinstance(b, D):
            if sign == 1:
                raise CalcError("two dates cannot be added; subtract them for the days between")
            delta = a.when - b.when
            return Q(Decimal(delta.days) * 86400 + Decimal(delta.seconds), {"T": 1}, "days" if not (
                a.has_time or b.has_time) else None)
        if b.cal:
            n = b.value
            if n != n.to_integral_value():
                raise CalcError("months and years must be whole numbers")
            months = int(n) * (12 if b.cal == "year" else 1) * sign
            return D(_add_months(a.when, months), a.has_time)
        if b.dims != {"T": 1}:
            raise CalcError("add a duration to a date, e.g. + 30 days")
        secs = b.value * sign
        try:
            when = a.when + dt.timedelta(seconds=float(secs))
        except OverflowError as exc:  # past year 9999 or before year 1, or a duration beyond timedelta
            raise CalcError(DATE_RANGE) from exc
        return D(when, a.has_time or secs % 86400 != 0)
    if isinstance(b, D):
        raise CalcError("put the date first, e.g. 2026-11-09 + 30 days")
    if b.percent and not a.percent:
        return Q(a.value * (1 + sign * b.value), a.dims, a.hint)
    if a.dims != b.dims or a.cal != b.cal:
        raise CalcError("these values have different units and cannot be added")
    return Q(a.value + sign * b.value, a.dims, a.hint or b.hint, a.percent and b.percent)


def mul(a, b):
    if isinstance(a, D) or isinstance(b, D):
        raise CalcError("dates cannot be multiplied")
    if a.cal or b.cal:
        raise CalcError("months and years work only with dates")
    dims = _merge_dims(a.dims, b.dims)
    hint = _product_hint(a, b, dims)
    return Q(a.value * b.value, dims, hint, a.percent and b.percent and False)


def div(a, b):
    if isinstance(a, D) or isinstance(b, D):
        raise CalcError("dates cannot be divided")
    if b.value == 0:
        raise CalcError("division by zero")
    dims = _merge_dims(a.dims, b.dims, -1)
    hint = a.hint if dims == a.dims else None
    if hint is None and a.hint and b.hint and "/" not in a.hint + b.hint and dims:
        hint = f"{a.hint}/{b.hint}"
    return Q(a.value / b.value, dims, hint)


def _product_hint(a: Q, b: Q, dims: dict) -> Optional[str]:
    if dims == a.dims:
        return a.hint
    if dims == b.dims:
        return b.hint
    cur = [k for k in dims if k.startswith("CUR_")]
    if len(dims) == 1 and cur:
        return _CUR_SYMBOL[cur[0][4:]]
    return None


def _add_months(when: dt.datetime, months: int) -> dt.datetime:
    y, m = divmod(when.month - 1 + months, 12)
    year, month = when.year + y, m + 1
    if not dt.MINYEAR <= year <= dt.MAXYEAR:
        raise CalcError(DATE_RANGE)
    day = min(when.day, calendar.monthrange(year, month)[1])
    return when.replace(year=year, month=month, day=day)


def fmt_number(value: Decimal, sep: str = ".", places: Optional[int] = None) -> str:
    with localcontext() as ctx:
        ctx.prec = PREC
        if places is not None:
            ctx.prec = max(PREC, value.adjusted() + places + 1)  # quantize needs every digit of a big amount
            q = value.quantize(Decimal(1).scaleb(-places))
        else:
            q = value.quantize(Decimal("1e-10")) if value.as_tuple().exponent < -10 else value
            q = q.normalize()
    text = format(q, "f")
    if "." in text and places is None:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text.replace(".", sep) if sep == "," else text


def _duration_words(seconds: Decimal) -> str:
    if abs(seconds) >= MAX_DURATION_S:
        raise CalcError("the duration is too long to show")
    total = int(seconds)
    sign = "-" if total < 0 else ""
    total = abs(total)
    parts = []
    for size, name in ((86400, "d"), (3600, "h"), (60, "min"), (1, "s")):
        n, total = divmod(total, size)
        if n:
            parts.append(f"{n} {name}")
    return sign + (" ".join(parts) or "0 s")


def render(value, target, seps: set) -> dict:
    sep = "," if seps == {","} else "."
    if isinstance(value, D):
        text = value.when.strftime("%Y-%m-%d %H:%M" if value.has_time else "%Y-%m-%d")
        weekday = value.when.strftime("%A")
        return {"result": text, "kind": "date", "value": text, "weekday": weekday}
    if target is not None:
        factor, dims, display, cal = target
        if cal:
            raise CalcError("months and years work only with dates")
        if dims != value.dims:
            raise CalcError(f"cannot show this value in {display}")
        v = value.value / factor
        return {"result": f"{fmt_number(v, sep)} {display}", "kind": "quantity", "value": fmt_number(v),
                "unit": display}
    if value.cal:
        raise CalcError("months and years work only with dates")
    if value.percent:
        return {"result": f"{fmt_number(value.value * 100, sep)}%", "kind": "percent",
                "value": fmt_number(value.value)}
    dims = value.dims
    if not dims:
        return {"result": fmt_number(value.value, sep), "kind": "number", "value": fmt_number(value.value)}
    cur = [k for k in dims if k.startswith("CUR_")]
    if len(dims) == 1 and cur:
        code = cur[0][4:]
        sym = _CUR_SYMBOL[code]
        num = fmt_number(value.value, sep, places=2)
        text = f"{num} {sym}" if code in ("EUR", "CHF") else f"{sym}{num}"
        return {"result": text, "kind": "currency", "value": fmt_number(value.value, places=2), "unit": code}
    if dims == {"T": 1}:
        if value.hint == "days":
            days = value.value / 86400
            return {"result": f"{fmt_number(days, sep)} days", "kind": "duration", "value": fmt_number(days),
                    "unit": "days"}
        hours = value.value / 3600
        return {"result": f"{_duration_words(value.value)} ({fmt_number(hours, sep)} h)", "kind": "duration",
                "value": fmt_number(hours), "unit": "h"}
    if value.hint and value.hint.lower() in UNITS:
        factor = UNITS[value.hint.lower()][0]
        shown = _DISPLAY_NAMES.get(value.hint.lower(), value.hint)
        return {"result": f"{fmt_number(value.value / factor, sep)} {shown}", "kind": "quantity",
                "value": fmt_number(value.value / factor), "unit": shown}
    if value.hint and "/" in value.hint:
        num, den = value.hint.split("/")
        factor = UNITS[num.lower() if num.lower() in UNITS else num][0] / UNITS[
            den.lower() if den.lower() in UNITS else den][0]
        return {"result": f"{fmt_number(value.value / factor, sep)} {value.hint}", "kind": "quantity",
                "value": fmt_number(value.value / factor), "unit": value.hint}
    base = {"L": "m", "M": "kg", "T": "s", "D": "B"}
    unit = " ".join(f"{base.get(k, k)}{'' if v == 1 else '^' + str(v)}" for k, v in sorted(dims.items()))
    return {"result": f"{fmt_number(value.value, sep)} {unit}", "kind": "quantity", "value": fmt_number(value.value),
            "unit": unit}


def evaluate(text: str, now: Optional[dt.datetime] = None) -> dict:
    """{"result": shown text, "kind", "value" (dot decimal), "unit"?, "expression"}; raises CalcError."""
    if not isinstance(text, str) or not text.strip():
        raise CalcError("empty expression")
    if len(text) > MAX_LEN:
        raise CalcError(f"expressions are limited to {MAX_LEN} characters")
    expr = text.strip()
    if expr.endswith("="):
        expr = expr[:-1].rstrip()
    with localcontext() as ctx:
        ctx.prec = PREC
        try:
            p = Parser(expr, now or dt.datetime.now())
            value, target = p.statement()
            out = render(value, target, p.seps)
        except CalcError:
            raise
        except Overflow as exc:  # a product or sum past Decimal's exponent limit (10^999999)
            raise CalcError("the number is too large") from exc
        except (ArithmeticError, ValueError, TypeError, RecursionError) as exc:
            raise CalcError(f"no answer for this expression ({type(exc).__name__})") from exc
    out["expression"] = expr
    return out


def evaluate_line(line: str, now: Optional[dt.datetime] = None) -> Optional[dict]:
    """A pad line ending in `=`: its result, or None (not a calculation, or no answer).
    A leading label ("Hosting: 16,90 * 12 =") is skipped when the whole line does not parse."""
    text = (line or "").rstrip()
    if not text.endswith("="):
        return None
    body = text[:-1]
    candidates = [body]
    if ":" in body:
        candidates.append(body.rsplit(":", 1)[1])
    last_error = None
    for cand in candidates:
        try:
            return evaluate(cand, now)
        except Exception as exc:  # the pad recomputes every read: one bad line must not take the day down
            last_error = exc if isinstance(exc, CalcError) else CalcError(f"no answer for this line ({type(exc).__name__})")
    if last_error is None:
        return None
    return {"error": str(last_error), **({"not_math": True} if isinstance(last_error, NotACalculation) else {})}
