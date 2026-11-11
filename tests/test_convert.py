"""Conversions: known reference values (not only the generated fixture), the parity fixture, cron."""
import datetime as dt
import json

import pytest

from esb_fakes import BERLIN, ROOT, sub

PARITY = json.loads((ROOT / "tests" / "fixtures" / "parity.json").read_text(encoding="utf-8"))


@pytest.fixture
def conv():
    return sub("engines.convert")


def test_reference_colours(conv):
    red = conv.colour("#ff0000", "#000000")
    assert red["oklch"] == "oklch(62.8% 0.258 29.2)"  # CSS Color 4 reference: 0.62796 0.25768 29.23
    assert red["contrast"]["ratio"] == 5.25
    assert conv.colour("#ffffff", "#000000")["contrast"]["ratio"] == 21
    grey = conv.colour("#777", "#fff")
    assert grey["contrast"]["ratio"] == 4.48 and grey["contrast"]["aa_normal"] is False  # the classic near-miss
    assert conv.colour("oklch(62.8% 0.258 29.2)")["hex"] == "#ff0000"
    assert conv.colour("hsl(120 100% 50%)")["hex"] == "#00ff00"
    assert conv.colour("rgb(100% 0% 0%)")["hex"] == "#ff0000"
    assert conv.colour("oklch(90% 0.4 140)")["out_of_gamut"] is True


def test_reference_encodings(conv):
    assert conv.encode("hello", "base64") == "aGVsbG8="
    assert conv.encode("??>", "base64url") == "Pz8-"
    assert conv.encode("a b&c", "url") == "a%20b%26c"
    assert conv.decode("aGVsbG8", "base64") == "hello"  # missing padding accepted
    assert conv.decode("R3LDvMOfZQ==", "base64") == "Grüße"
    with pytest.raises(conv.ConvertError):
        conv.decode("%zz", "url")
    with pytest.raises(conv.ConvertError):
        conv.decode("not base64!", "base64")
    with pytest.raises(conv.ConvertError):
        conv.decode("/w==", "base64")  # 0xff is no UTF-8 text


def test_parity_fixture_still_matches_the_engine(conv):
    for row in PARITY["encode"]:
        assert conv.encode(row["text"], row["scheme"]) == row["encoded"]
        assert conv.decode(row["encoded"], row["scheme"]) == row["text"]
    for row in PARITY["colour"]:
        assert conv.colour(row["input"], row["background"]) == row["out"], row["input"]
    for row in PARITY["time"]:
        assert conv.convert_time(row["time"], row["from"], row["to"]) == row["out"]
    for row in PARITY["timestamp"]:
        assert conv.convert_timestamp(row["value"], row["zones"]) == row["out"]


def test_time_zones_and_dst(conv):
    out = conv.convert_time("2026-11-09 10:00", "Europe/Berlin", ["Asia/Kolkata", "America/New_York"])
    assert [r["time"] for r in out["to"]] == ["2026-11-09 14:30", "2026-11-09 04:00"]
    summer = conv.convert_time("2026-07-01 10:00", "Europe/Berlin", ["UTC"])
    assert summer["from"]["offset"] == "UTC+02:00" and summer["to"][0]["time"] == "2026-07-01 08:00"
    now = dt.datetime(2026, 11, 9, 9, 0, tzinfo=dt.timezone.utc)
    assert conv.convert_time("14:30", "Europe/Berlin", ["UTC"], now)["to"][0]["time"] == "2026-11-09 13:30"
    with pytest.raises(conv.ConvertError):
        conv.convert_time("now", "Mars/Olympus", ["UTC"])


def test_timestamps(conv):
    s = conv.convert_timestamp("1794245079", ["UTC"])
    assert s["input_unit"] == "s" and s["iso_utc"] == "2026-11-09T17:24:39Z"
    ms = conv.convert_timestamp("1794245079976", ["UTC"])
    assert ms["input_unit"] == "ms" and ms["unix"] == 1794245079 and ms["unix_ms"] == 1794245079976
    iso = conv.convert_timestamp("2026-11-09T10:00:00+01:00", ["UTC"])
    assert iso["unix"] == 1794214800


def test_cron_words_and_next_runs(conv):
    pytest.importorskip("croniter")
    now = dt.datetime(2026, 11, 9, 10, 7, tzinfo=BERLIN)
    out = conv.cron("*/15 * * * *", "Europe/Berlin", 3, now)
    assert out["words"] == "every 15 minutes"
    assert out["next"] == ["2026-11-09 10:15 Mon", "2026-11-09 10:30 Mon", "2026-11-09 10:45 Mon"]
    assert conv.describe_cron("0 9 * * 1-5") == "at 09:00 on Monday to Friday"
    assert conv.describe_cron("30 18 1 * *") == "at 18:30 on day 1 of the month"
    assert conv.describe_cron("@daily") == "at 00:00"
    assert conv.describe_cron("0 * * jan,jul sun") == "every hour at minute 0 in January and July on Sunday"
    nxt = conv.cron("0 9 * * mon-fri", "Europe/Berlin", 2, now)["next"]
    assert nxt == ["2026-11-10 09:00 Tue", "2026-11-11 09:00 Wed"]
    with pytest.raises(conv.ConvertError):
        conv.cron("61 * * * *", "UTC", 1, now)
    with pytest.raises(conv.ConvertError):
        conv.describe_cron("* * *")
