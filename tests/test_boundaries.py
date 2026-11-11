"""Route boundaries: a malformed body answers a JSON 4xx and leaves the state readable, and the
last-resort guard answers a JSON 500 `internal`."""
import datetime as dt
import json
import time

import pytest

from esb_fakes import BERLIN, set_clock, sub


@pytest.fixture
def api(tmp_path):
    a = sub("api")
    store = sub("store").Store(tmp_path / "data")
    a.set_store_factory(lambda: store)
    set_clock(dt.datetime(2026, 11, 10, 9, 0, tzinfo=BERLIN))
    a.pad_lines({"op": "add", "text": "a"})
    yield a
    a.set_store_factory(None)


def _line_id(api):
    return api.pad_get()[1]["day"]["lines"][0]["id"]


PAD_CASES = [
    ("restore text=int", lambda lid: {"op": "restore", "line": {"id": "x1", "text": 123}}),
    ("restore position=None", lambda lid: {"op": "restore", "line": {"id": "x2", "text": "b"}, "position": None}),
    ("restore position=str", lambda lid: {"op": "restore", "line": {"id": "x3", "text": "b"}, "position": "1"}),
    ("restore kind=bogus", lambda lid: {"op": "restore", "line": {"id": "x4", "text": "b", "kind": "boss"}}),
    ("restore id=dict", lambda lid: {"op": "restore", "line": {"id": {"a": 1}, "text": "b"}}),
    ("restore rolled_days=str", lambda lid: {"op": "restore", "line": {"id": "x5", "text": "b", "rolled_days": "2"}}),
    ("update position=None", lambda lid: {"op": "update", "id": lid, "changes": {"position": None}}),
    ("update position=float", lambda lid: {"op": "update", "id": lid, "changes": {"position": 1.5}}),
    ("update changes=list", lambda lid: {"op": "update", "id": lid, "changes": ["done"]}),
    ("update text=list", lambda lid: {"op": "update", "id": lid, "changes": {"text": ["x"]}}),
    ("update done=str", lambda lid: {"op": "update", "id": lid, "changes": {"done": "no"}}),
    ("update remind_at=int", lambda lid: {"op": "update", "id": lid, "changes": {"remind_at": 930}}),
    ("add text=dict", lambda lid: {"op": "add", "text": {"a": 1}}),
    ("add kind=list", lambda lid: {"op": "add", "text": "b", "kind": ["todo"]}),
    ("add remind_at=dict", lambda lid: {"op": "add", "text": "b", "kind": "reminder", "remind_at": {"h": 9}}),
    ("add date=int", lambda lid: {"op": "add", "text": "b", "date": 20261110}),
]


@pytest.mark.parametrize("name,make", PAD_CASES, ids=[c[0] for c in PAD_CASES])
def test_malformed_pad_bodies_answer_400_and_the_pad_stays_readable(api, name, make):
    before = api.pad_get()[1]["day"]["lines"]
    status, body = api.pad_lines(make(before[0]["id"]))
    assert status == 400 and body["ok"] is False and body["error"] == "invalid", (name, status, body)
    status, body = api.pad_get()
    assert status == 200, body
    assert [line["text"] for line in body["day"]["lines"]] == [line["text"] for line in before]


def test_restore_puts_a_valid_line_back_in_place(api):
    api.pad_lines({"op": "add", "text": "b"})
    lines = api.pad_get()[1]["day"]["lines"]
    status, body = api.pad_lines({"op": "delete", "id": lines[0]["id"]})
    deleted = body["deleted"]
    status, body = api.pad_lines({"op": "restore", "line": deleted, "position": 0})
    assert status == 200
    back = body["day"]["lines"][0]
    assert back["id"] == deleted["id"] and back["text"] == "a" and back["created"] == deleted["created"]
    # restoring the same line again changes nothing; the position defaults to the end when missing
    assert api.pad_lines({"op": "restore", "line": deleted})[0] == 200
    assert [x["text"] for x in api.pad_get()[1]["day"]["lines"]] == ["a", "b"]


def test_restore_runs_the_new_line_rules(api):
    status, body = api.pad_lines({"op": "restore", "line": {"id": "x1", "text": "  spaced   out  ", "kind": "reminder",
                                                             "remind_at": "2026-11-10T15:00", "done": True,
                                                             "result": "stale", "author": "agent", "rolled_days": 2}})
    assert status == 200
    line = next(x for x in body["day"]["lines"] if x["id"] == "x1")
    assert line["text"] == "spaced out" and line["remind_at"] == "2026-11-10T15:00" and line["done"] is True
    assert line["author"] == "agent" and line["rolled_days"] == 2 and "result" not in line
    status, body = api.pad_lines({"op": "restore", "line": {"id": "x2", "text": "x" * 600}})
    assert status == 400


def test_update_position_still_moves_a_line(api):
    api.pad_lines({"op": "add", "text": "b"})
    lid = api.pad_get()[1]["day"]["lines"][1]["id"]
    status, body = api.pad_lines({"op": "update", "id": lid, "changes": {"position": 0}})
    assert status == 200 and [x["text"] for x in body["day"]["lines"]] == ["b", "a"]


def test_a_client_plan_is_ignored_and_the_timer_stays_readable(api):
    status, body = api.timer_post({"op": "start", "plan": [{"phase": "work", "minutes": "abc"}]})
    assert status == 200, body
    assert body["timer"]["plan"][0] == {"phase": "work", "minutes": 25}
    status, body = api.timer_get()
    assert status == 200 and body["state"]["phase"] == "work"
    status, body = api.timer_post({"op": "stop"})
    assert status == 200


@pytest.mark.parametrize("body", [
    {"op": "start", "kind": "countdown", "minutes": "abc"},
    {"op": "start", "kind": "countdown", "minutes": True},
    {"op": "start", "kind": "egg"},
    {"op": "start", "at": 12},
    {"op": "start", "client": {"a": 1}},
    {"op": "stop", "result": ["x"]},
], ids=["countdown-minutes-str", "countdown-minutes-bool", "kind-unknown", "at-int", "client-dict", "result-list"])
def test_malformed_timer_bodies_answer_400(api, body):
    if body["op"] == "stop":
        assert api.timer_post({"op": "start"})[0] == 200
    status, out = api.timer_post(body)
    assert status == 400 and out["error"] == "invalid", out
    assert api.timer_get()[0] == 200


def test_a_countdown_plan_comes_from_minutes(api):
    status, body = api.timer_post({"op": "start", "kind": "countdown", "minutes": 7, "plan": [{"phase": "work", "minutes": 1}]})
    assert status == 200 and body["timer"]["plan"] == [{"phase": "countdown", "minutes": 7}]


@pytest.mark.parametrize("body", [
    {"op": "add", "fields": ["x"]},
    {"op": "start", "fields": "x"},
    {"op": "edit", "entry_id": "e1", "fields": 3},
], ids=["add-list", "start-str", "edit-int"])
def test_timelog_non_object_fields_answer_400(api, body):
    status, out = api.timelog_post(body)
    assert status == 400 and out["error"] == "invalid", out
    assert api.timelog_get()[0] == 200


def test_timelog_outbox_op_with_non_object_fields_is_refused_alone(api):
    ops = [{"op": "add", "op_id": "o1", "at": "2026-11-10T08:00:00+01:00", "fields": "x"},
           {"op": "add", "op_id": "o2", "at": "2026-11-10T08:30:00+01:00",
            "fields": {"client": "A", "start": "2026-11-10T08:00:00+01:00", "end": "2026-11-10T08:30:00+01:00"}}]
    status, body = api.timelog_ops({"ops": ops})
    assert status == 200, body
    assert body["results"][0]["error"] == "invalid" and body["results"][1]["applied"] is True
    assert api.timelog_get()[0] == 200


def test_the_last_resort_guard_answers_json_500_internal(api, monkeypatch):
    toolbox = sub("toolbox")

    def boom(store):
        raise TypeError("unexpected")

    monkeypatch.setattr(toolbox, "view", boom)
    status, body = api.toolbox_get()
    assert status == 500 and body["ok"] is False and body["error"] == "internal" and body["schema"] == 1
    assert "TypeError" in body["message"]


# --- X12: YAML alias expansion --------------------------------------------------------------------

def _bomb(levels: int) -> str:
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    for i in range(1, levels):
        lines.append(f"a{i}: &a{i} [" + ", ".join([f"*a{i - 1}"] * 10) + "]")
    return "\n".join(lines)


@pytest.mark.parametrize("levels", [5, 6, 7])
def test_a_yaml_alias_bomb_is_refused_quickly(levels):
    pytest.importorskip("ruamel.yaml")
    fmt = sub("engines.fmt")
    t = time.perf_counter()
    with pytest.raises(fmt.FormatError) as exc:
        fmt.convert(_bomb(levels), "yaml", "json")
    assert time.perf_counter() - t < 1.5
    assert "alias" in str(exc.value)


def test_a_small_alias_expansion_and_normal_anchors_still_convert():
    pytest.importorskip("ruamel.yaml")
    fmt = sub("engines.fmt")
    out = json.loads(fmt.convert(_bomb(4), "yaml", "json")["text"])
    assert len(out["a3"]) == 10 and out["a3"][0][0][0] == ["x"] * 10
    doc = "base: &b {image: nginx, port: 80}\nweb: *b\napi:\n  <<: *b\n  port: 81\n"
    out = json.loads(fmt.convert(doc, "yaml", "json")["text"])
    assert out["web"] == {"image": "nginx", "port": 80} and out["api"]["port"] == 81


def test_an_aliased_long_string_cannot_blow_up_the_output():
    pytest.importorskip("ruamel.yaml")
    fmt = sub("engines.fmt")
    doc = "s: &s " + "y" * 200_000 + "\nl: [" + ", ".join(["*s"] * 50) + "]\n"
    with pytest.raises(fmt.FormatError):
        fmt.convert(doc, "yaml", "json")


@pytest.mark.parametrize("indent", [100_000, -1, "abc"])
def test_json_indent_is_bounded(indent):
    fmt = sub("engines.fmt")
    with pytest.raises(fmt.FormatError):
        fmt.format_text('{"a": [1, 2, 3]}', "json", indent)


def test_the_format_route_answers_a_bomb_with_ok_false(api):
    pytest.importorskip("ruamel.yaml")
    status, body = api.run_engine("format", {"action": "convert", "text": _bomb(6), "from": "yaml", "to": "json"})
    assert status == 200 and body["ok"] is False and "alias" in body["message"]
    status, body = api.run_engine("format", {"action": "format", "text": "{}", "lang": "json", "indent": "abc"})
    assert status == 200 and body["ok"] is False
