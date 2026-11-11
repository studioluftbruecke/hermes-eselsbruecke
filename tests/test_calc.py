"""The calculator engine: numbers in both decimal styles, percentages, units, durations x rates,
dates in Hermes' zone, pad lines with labels, and clear errors (no eval)."""
import datetime as dt

import pytest

from esb_fakes import BERLIN, sub

NOW = dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN)


@pytest.fixture
def calc():
    return sub("engines.calc")


@pytest.mark.parametrize("expr,shown", [
    ("16,90 * 12", "202,8"),
    ("3 * 4,50 + 19%", "16,065"),
    ("19% of 240", "45.6"),
    ("240 - 25%", "180"),
    ("1/3", "0.3333333333"),
    ("2^10", "1024"),
    ("(1 + 2) * 3", "9"),
    ("-4 + 10", "6"),
    ("0.1 + 0.2", "0.3"),
    ("1.234,56 + 1", "1235,56"),
    ("1,234.56 + 1", "1235.56"),
    ("12 x 3", "36"),
    ("2h 30m * 85 €/h", "212.50 €"),
    ("2h 30m", "2 h 30 min (2.5 h)"),
    ("90 min in h", "1.5 h"),
    ("5 km in mi", "3.1068559612 mi"),
    ("1.5 GiB to MB", "1610.612736 MB"),
    ("10 inch in cm", "25.4 cm"),
    ("1 km + 200 m", "1.2 km"),
    ("16,90 € * 12", "202,80 €"),
    ("$12.5 * 3", "$37.50"),
    ("100 km / 2 h", "50 km/h"),
    ("2026-11-09 + 30 days", "2026-12-09"),
    ("2026-01-31 + 1 month", "2026-02-28"),
    ("2026-12-24 - 2026-11-09", "45 days"),
    ("2026-12-24 - today", "45 days"),
    ("today + 2 weeks", "2026-11-23"),
    ("19%", "19%"),
])
def test_examples(calc, expr, shown):
    assert calc.evaluate(expr, NOW)["result"] == shown


@pytest.mark.parametrize("expr,needle", [
    ("1 / 0", "division by zero"),
    ("2 km + 3 kg", "different units"),
    ("__import__('os')", "unexpected"),
    ("(1 + 2", "not closed"),
    ("5 km in kg", "cannot show"),
    ("2^1.5", "whole number"),
    ("", "empty"),
    ("1 +", "ends too early"),
    ("2026-11-09 + 2026-11-10", "cannot be added"),
])
def test_errors(calc, expr, needle):
    with pytest.raises(calc.CalcError) as exc:
        calc.evaluate(expr, NOW)
    assert needle in str(exc.value)


DEEP = "(" * 200 + "1" + ")" * 200


@pytest.mark.parametrize("expr,needle", [
    ("2026-11-10 + 99999999 days", "years 1 to 9999"),
    ("2026-11-10 - 99999999 days", "years 1 to 9999"),
    ("9999-12-31 + 1 day", "years 1 to 9999"),
    ("2026-11-10 + 99999 years", "years 1 to 9999"),
    ("2026-11-10 - 3000 years", "years 1 to 9999"),
    ("(10^1000)^1000", "too large"),
    (DEEP, "nested too deep"),
    ("2^" * 249 + "2", "nested too deep"),
    ("-" * 300 + "1", "nested too deep"),
])
def test_out_of_range_and_deep_nesting_are_calc_errors(calc, expr, needle):
    """X2: anything else escaping evaluate() broke the pad line for good (500 on every read)."""
    with pytest.raises(calc.CalcError) as exc:
        calc.evaluate(expr, NOW)
    assert needle in str(exc.value)
    assert "error" in calc.evaluate_line(f"Due: {expr} =", NOW)


def test_nesting_below_the_cap_still_works(calc):
    assert calc.evaluate("(" * 30 + "2" + ")" * 30 + " * 3", NOW)["result"] == "6"
    assert calc.evaluate("2^2^3", NOW)["result"] == "256"
    assert calc.evaluate("--4", NOW)["result"] == "4"


def test_a_big_amount_shows_every_digit(calc):
    """Rounding a currency to cents needs more than 40 digits of precision for a big amount."""
    assert calc.evaluate("(10^100) €", NOW)["result"] == "1" + "0" * 100 + ".00 €"


def test_random_input_raises_only_calc_errors(calc):
    """Every string of calculator tokens either answers or raises CalcError, never anything else."""
    import random

    rng = random.Random(73)
    pieces = ["(", ")", "+", "-", "*", "/", "^", "%", " ", "1", "9", "999", "0", "0,5", "1.5", "10^999",
              "2026-11-10", "9999-12-31", "0001-01-01", "today", "now", "days", "years", "months", "h", "€",
              "km", "in", "to", "of", "x", "GiB", "=", ":"]
    for _ in range(3000):
        expr = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 40)))
        try:
            calc.evaluate(expr, NOW)
        except calc.CalcError:
            pass


def test_length_cap(calc):
    with pytest.raises(calc.CalcError):
        calc.evaluate("1+" * 300 + "1", NOW)


def test_pad_lines(calc):
    assert calc.evaluate_line("Hosting: 16,90 * 12 =", NOW)["result"] == "202,8"
    assert calc.evaluate_line("Server: 3 * 4,50 + 19% =", NOW)["result"] == "16,065"
    assert calc.evaluate_line("Call mom", NOW) is None
    assert "error" in calc.evaluate_line("what is love =", NOW)


def test_value_is_dot_decimal_for_machines(calc):
    out = calc.evaluate("16,90 * 12", NOW)
    assert out["value"] == "202.8" and out["kind"] == "number"
