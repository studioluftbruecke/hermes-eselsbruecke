"""The five engine tools through the agent path (dispatcher, switches) and the page path (/run/{engine}),
the time in the user's world clock places, and the schema budget of every registered agent tool
(constraint 20)."""
import datetime as dt
import json

import pytest

from esb_fakes import BERLIN, FakeCtx, load_plugin, set_clock, sub

BUDGET_CHARS = 12_000


@pytest.fixture
def ctx(tmp_path):
    c = FakeCtx(tmp_path / "data")
    load_plugin().register(c)
    return c


def test_each_engine_tool_answers(ctx):
    assert ctx.call("eselsbruecke_calc", expr="16,90 * 12 =")["result"] == "202,8"
    assert ctx.call("eselsbruecke_format", action="format", text='{"a":1}', lang="json")["text"] == '{\n  "a": 1\n}\n'
    assert ctx.call("eselsbruecke_convert", action="encode", text="hi", scheme="base64")["text"] == "aGk="
    assert ctx.call("eselsbruecke_text", action="count", text="hello world")["tokens_estimate"] == 3
    assert len(ctx.call("eselsbruecke_generate", action="uuid", version=7, count=2)["uuids"]) == 2
    err = ctx.call("eselsbruecke_calc", expr="1/0")
    assert err["ok"] is False and err["error"] == "calc"


def test_switch_off_refuses_in_the_running_session_and_hides_after(ctx, tmp_path):
    assert ctx.visible("eselsbruecke_calc")
    out = ctx.call("eselsbruecke_toolbox", action="set_switch", tool="calc", on=False)
    assert out["ok"]
    refused = ctx.call("eselsbruecke_calc", expr="1+1")
    assert refused == {"ok": False, "error": "switched_off", "module": "calc",
                       "message": refused["message"]} and "Calculator is switched off" in refused["message"]
    assert ctx.visible("eselsbruecke_calc") is False


def test_convert_with_colour_off_stays_visible_and_refuses_only_colour(ctx):
    ctx.call("eselsbruecke_toolbox", action="set_switch", tool="colour", on=False)
    assert ctx.visible("eselsbruecke_convert") is True
    assert ctx.call("eselsbruecke_convert", action="colour", colour="#fff")["error"] == "switched_off"
    assert ctx.call("eselsbruecke_convert", action="encode", text="a", scheme="url")["ok"] is True


def test_the_time_tool_takes_city_names(ctx):
    out = ctx.call("eselsbruecke_convert", action="time", time="2026-11-09 10:00", from_zone="Berlin",
                   to_zones=["Mumbai", "America/New_York"])
    assert out["ok"] and out["from"]["zone"] == "Europe/Berlin"
    assert [(r["zone"], r.get("place"), r["time"]) for r in out["to"]] == [
        ("Asia/Kolkata", "Mumbai", "2026-11-09 14:30"), ("America/New_York", None, "2026-11-09 04:00")]
    one = ctx.call("eselsbruecke_convert", action="time", time="2026-11-09 10:00", from_zone="Berlin", to_zones="Lisbon")
    assert [r["place"] for r in one["to"]] == ["Lisbon"]
    stamp = ctx.call("eselsbruecke_convert", action="timestamp", value="1794245079", zones=["Tokyo"])
    assert stamp["zones"][0]["zone"] == "Asia/Tokyo" and stamp["zones"][0]["place"] == "Tokyo"
    bad = ctx.call("eselsbruecke_convert", action="time", to_zones=["Atlantis"])
    assert bad["ok"] is False and "unknown place or time zone 'Atlantis'" in bad["message"]


def test_without_places_the_time_tool_answers_for_the_users_world_clock(ctx):
    set_clock(dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    out = ctx.call("eselsbruecke_convert", action="time")
    assert out["from"]["zone"] == "Europe/Berlin" and out["from"]["time"] == "2026-11-09 10:00"
    assert [(r["place"], r["zone"], r["time"]) for r in out["to"]] == [
        ("UTC", "UTC", "2026-11-09 09:00"), ("New York", "America/New_York", "2026-11-09 04:00"),
        ("Tokyo", "Asia/Tokyo", "2026-11-09 18:00")]
    ctx.call("eselsbruecke_toolbox", action="set_clock", place="Tokyo", remove=True)
    ctx.call("eselsbruecke_toolbox", action="set_clock", place="Europe/Lisbon", label="Inês")
    out = ctx.call("eselsbruecke_convert", action="time", time="18:00")
    assert [(r["place"], r["zone"], r["time"]) for r in out["to"]] == [
        ("UTC", "UTC", "2026-11-09 17:00"), ("New York", "America/New_York", "2026-11-09 12:00"),
        ("Inês", "Europe/Lisbon", "2026-11-09 17:00")]
    asked = ctx.call("eselsbruecke_convert", action="time", to_zones=["Asia/Tokyo"])
    assert [r["zone"] for r in asked["to"]] == ["Asia/Tokyo"] and "place" not in asked["to"][0]


def test_with_an_empty_world_clock_the_time_tool_answers_in_utc(ctx):
    for place in ("UTC", "New York", "Tokyo"):
        ctx.call("eselsbruecke_toolbox", action="set_clock", place=place, remove=True)
    out = ctx.call("eselsbruecke_convert", action="time", time="2026-11-09 10:00", from_zone="Europe/Berlin")
    assert [r["zone"] for r in out["to"]] == ["UTC"] and "place" not in out["to"][0]


def test_run_engine_route(tmp_path):
    api = sub("api")
    store = sub("store").Store(tmp_path / "data")
    api.set_store_factory(lambda: store)
    try:
        status, body = api.run_engine("calc", {"expr": "3 * 4,50 + 19%"})
        assert status == 200 and body["result"] == "16,065" and body["schema"] == 1
        status, body = api.run_engine("text", {"action": "diff", "left": "a", "right": "b"})
        assert status == 200 and body["changed"] == 1
        status, body = api.run_engine("format", {"action": "format", "text": "{", "lang": "json"})
        assert status == 200 and body["ok"] is False and body["line"] == 1
        status, body = api.run_engine("convert", {"action": "time", "time": "2026-11-09 10:00", "from_zone": "Berlin"})
        assert status == 200 and [r["place"] for r in body["to"]] == ["UTC", "New York", "Tokyo"]
        assert api.run_engine("nope", {})[0] == 404
        assert api.run_engine("calc", {"action": "x"})[0] == 400
        sub("toolbox").set_switch(store, "diff", False, "user")
        status, body = api.run_engine("text", {"action": "diff", "left": "a", "right": "b"})
        assert status == 409 and body["error"] == "switched_off"
    finally:
        api.set_store_factory(None)


def test_schema_budget(ctx):
    total = sum(len(json.dumps(t["schema"], ensure_ascii=False)) for t in ctx.tools.values())
    print(f"\nagent tool schemas: {len(ctx.tools)} tools, {total} characters (budget {BUDGET_CHARS}, "
          f"about {total // 4} tokens)")
    assert total <= BUDGET_CHARS
