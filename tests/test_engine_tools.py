"""The five engine tools through the agent path (dispatcher, switches) and the page path (/run/{engine}),
and the schema budget of every registered agent tool (constraint 20)."""
import json

import pytest

from esb_fakes import FakeCtx, load_plugin, sub

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
