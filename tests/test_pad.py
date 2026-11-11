"""Today's pad: lazy idempotent roll-over in Hermes' zone (not UTC), kinds, agent add and undo,
Markdown, `=` results, queued prompts, and the routes."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from esb_fakes import BERLIN, FakeCtx, load_plugin, make_store, set_clock, sub


@pytest.fixture
def pad():
    return sub("pad")


def test_roll_over_once_in_the_hermes_zone(tmp_path, pad):
    s = make_store(tmp_path)
    clock = set_clock(dt.datetime(2026, 11, 9, 23, 30, tzinfo=BERLIN))
    pad.add_lines(s, [{"text": "Fix the two Pressbrücke features"}, {"text": "Call mom", "kind": "todo"},
                      {"text": "Reply to Weber"}], "user")
    day = pad.load_day(s)
    pad.update_line(s, day["date"], day["lines"][2]["id"], {"done": True})
    # 00:30 Berlin is still 23:30 UTC on the 9th: "today" must already be the 10th
    clock.when = dt.datetime(2026, 11, 10, 0, 30, tzinfo=BERLIN)
    assert clock.when.astimezone(ZoneInfo("UTC")).date() == dt.date(2026, 11, 9)
    today = pad.load_day(s)
    assert today["date"] == "2026-11-10" and today["rolled_from"] == "2026-11-09"
    assert [(x["text"], x["rolled_days"]) for x in today["lines"]] == [
        ("Fix the two Pressbrücke features", 1), ("Call mom", 1)]
    again = pad.load_day(s)  # a second read the same day changes nothing
    assert again == today
    pad.add_lines(s, [{"text": "new today"}], "user")
    assert len(pad.load_day(s)["lines"]) == 3
    clock.when = dt.datetime(2026, 11, 13, 9, 0, tzinfo=BERLIN)  # skipped two days
    later = pad.load_day(s)
    assert later["rolled_from"] == "2026-11-10" and later["lines"][0]["rolled_days"] == 4


def test_kinds_reminder_and_prompt(tmp_path, pad):
    s = make_store(tmp_path)
    set_clock(dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    out = pad.add_lines(s, [{"text": "Call mom", "kind": "reminder", "remind_at": "18:30"},
                            {"text": "Write the deploy check", "kind": "prompt"}], "user")
    rem, prompt = out["added"]
    assert rem["remind_at"] == "2026-11-09T18:30" and prompt["queued_for"] == "2026-11-10"
    with pytest.raises(pad.PadError):
        pad.add_lines(s, [{"text": "x", "kind": "reminder"}], "user")
    with pytest.raises(pad.PadError):
        pad.add_lines(s, [{"text": "x", "kind": "essay"}], "user")
    assert pad.queued(s) == []
    set_clock(dt.datetime(2026, 11, 10, 8, 0, tzinfo=BERLIN))
    q = pad.queued(s)
    assert [x["text"] for x in q] == ["Write the deploy check"]
    due = pad.reminders_due(s, "2026-11-09T18:00", "2026-11-09T18:31")
    assert [d["text"] for d in due] == ["Call mom"]


def test_agent_add_and_undo_leave_the_pad_as_before(tmp_path, pad):
    s = make_store(tmp_path)
    set_clock(dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    pad.add_lines(s, [{"text": "mine"}], "user")
    before = pad.load_day(s)
    out = pad.add_lines(s, [{"text": "Domain renewal check (Lindner)"}, {"text": "second"}], "agent")
    assert out["op_id"] and [x["author"] for x in out["added"]] == ["agent", "agent"]
    undo = pad.undo_agent(s)
    assert undo["removed"] == ["Domain renewal check (Lindner)", "second"]
    assert pad.load_day(s) == before
    with pytest.raises(pad.PadError) as exc:
        pad.undo_agent(s)
    assert exc.value.code == "nothing_to_undo"


def test_markdown_and_results(tmp_path, pad):
    s = make_store(tmp_path)
    now = dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN)
    set_clock(now)
    pad.add_lines(s, [{"text": "Hosting: 16,90 * 12 ="}, {"text": "Call mom", "kind": "reminder", "remind_at": "18:30"}],
                  "user")
    day = pad.with_results(pad.load_day(s), True, now)
    assert day["lines"][0]["result"] == "202,8"
    assert "result" not in pad.with_results(pad.load_day(s), False, now)["lines"][0]
    md = pad.markdown(day)
    assert md.splitlines() == ["## Pad 2026-11-09", "- [ ] Hosting: 16,90 * 12 = (= 202,8)",
                               "- [ ] Call mom (reminder 18:30)"]


def test_line_limits_and_unknown_line(tmp_path, pad):
    s = make_store(tmp_path)
    with pytest.raises(pad.PadError):
        pad.add_lines(s, [{"text": "x" * 501}], "user")
    with pytest.raises(pad.PadError) as exc:
        pad.update_line(s, None, "nope", {"done": True})
    assert exc.value.code == "unknown_line"


def test_pad_tool_add_undo_and_no_read_action(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    schema = ctx.tools["eselsbruecke_pad"]["schema"]
    assert schema["parameters"]["properties"]["action"]["enum"] == ["add", "undo"]
    out = ctx.call("eselsbruecke_pad", action="add", lines=[{"text": "Domain renewal check"}])
    assert out["ok"] and out["added"][0]["text"] == "Domain renewal check"
    assert ctx.call("eselsbruecke_pad", action="undo")["removed"] == ["Domain renewal check"]
    assert ctx.call("eselsbruecke_pad", action="read")["error"] == "unknown_action"


def test_pad_routes(tmp_path):
    api = sub("api")
    store = make_store(tmp_path)
    api.set_store_factory(lambda: store)
    set_clock(dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    try:
        status, body = api.pad_lines({"op": "add", "text": "Server: 3 * 4,50 + 19% ="})
        assert status == 200 and body["day"]["lines"][0]["result"] == "16,065"
        lid = body["day"]["lines"][0]["id"]
        status, body = api.pad_lines({"op": "update", "date": "2026-11-09", "id": lid, "changes": {"done": True}})
        assert body["day"]["lines"][0]["done"] is True
        status, body = api.pad_lines({"op": "delete", "date": "2026-11-09", "id": lid})
        assert body["day"]["lines"] == [] and body["deleted"]["id"] == lid
        status, body = api.pad_lines({"op": "restore", "date": "2026-11-09", "line": body["deleted"], "position": 0})
        assert [x["id"] for x in body["day"]["lines"]] == [lid]
        assert api.pad_lines({"op": "update", "date": "2026-11-09", "id": "nope", "changes": {}})[0] == 404
        status, body = api.pad_markdown()
        assert body["markdown"].startswith("## Pad 2026-11-09")
        sub("toolbox").set_switch(store, "pad", False, "user")
        assert api.pad_get()[0] == 409
    finally:
        api.set_store_factory(None)


POISON = ["Deadline: 2026-11-10 + 99999999 days =", "(" * 200 + "1" + ")" * 200 + " ="]


@pytest.mark.parametrize("text", POISON)
def test_a_calculation_out_of_range_never_breaks_the_pad(tmp_path, pad, text):
    """X2: the line is stored and shown with its error, today, after roll-over, and to the agent."""
    api = sub("api")
    store = make_store(tmp_path)
    api.set_store_factory(lambda: store)
    clock = set_clock(dt.datetime(2026, 11, 10, 9, 0, tzinfo=BERLIN))
    try:
        status, body = api.pad_lines({"op": "add", "text": text})
        assert status == 200
        row = body["day"]["lines"][0]
        assert row["result"] is None and row["result_error"]
        shown = pad.with_results(pad.load_day(store), True, clock.when)["lines"][0]
        assert shown["result_error"] == row["result_error"]
        assert api.pad_get()[0] == 200 and api.pad_markdown()[0] == 200
        clock.when = dt.datetime(2026, 11, 11, 9, 0, tzinfo=BERLIN)
        status, body = api.pad_get()
        assert status == 200 and body["day"]["rolled_from"] == "2026-11-10"
        assert body["day"]["lines"][0]["text"] == text.replace("  ", " ") and body["day"]["lines"][0]["result_error"]
        attached = sub("reference").expand_text(store, "today", lambda: True, clock.when)
        assert "## Pad 2026-11-11" in attached and text[:20] in attached
    finally:
        api.set_store_factory(None)
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    out = ctx.call("eselsbruecke_calc", expr=text)
    assert out["ok"] is False and out["error"] == "calc"


def test_a_day_written_ahead_still_rolls_over_once(tmp_path, pad):
    """X3a: a line added on the next day (the page's "Next day" button) must not cancel that day's roll-over."""
    api = sub("api")
    store = make_store(tmp_path)
    api.set_store_factory(lambda: store)
    clock = set_clock(dt.datetime(2026, 11, 10, 9, 0, tzinfo=BERLIN))
    try:
        api.pad_lines({"op": "add", "text": "unfinished task from today"})
        _, body = api.pad_lines({"op": "add", "text": "finished today"})
        api.pad_lines({"op": "update", "date": "2026-11-10", "id": body["day"]["lines"][1]["id"], "changes": {"done": True}})
        api.pad_lines({"op": "add", "text": "dentist", "date": "2026-11-11"})
        clock.when = dt.datetime(2026, 11, 11, 8, 0, tzinfo=BERLIN)
        _, body = api.pad_get()
        day = body["day"]
        assert [(x["text"], x["rolled_days"]) for x in day["lines"]] == [
            ("unfinished task from today", 1), ("dentist", 0)]
        assert day["rolled_from"] == "2026-11-10"
        # a second roll of the same day copies nothing again, not even a line the user deleted after it
        api.pad_lines({"op": "delete", "date": "2026-11-11", "id": day["lines"][0]["id"]})
        assert [x["text"] for x in pad.load_day(store)["lines"]] == ["dentist"]
        assert [x["text"] for x in api.pad_get()[1]["day"]["lines"]] == ["dentist"]
    finally:
        api.set_store_factory(None)


def test_a_merge_never_copies_a_line_id_twice(tmp_path, pad):
    s = make_store(tmp_path)
    set_clock(dt.datetime(2026, 11, 10, 9, 0, tzinfo=BERLIN))
    line = pad.add_lines(s, [{"text": "carry me"}], "user")["added"][0]
    # a day file written ahead that already holds the same line (an older copy, not rolled yet)
    s.write_json(("pad", "2026-11-11.json"), {"date": "2026-11-11", "lines": [dict(line)], "rolled_from": None})
    day = pad.load_day(s, today=dt.date(2026, 11, 11))
    assert [x["id"] for x in day["lines"]] == [line["id"]] and day["rolled_from"] == "2026-11-10"
    assert pad.load_day(s, today=dt.date(2026, 11, 11)) == day


def test_a_reminder_and_a_prompt_belong_to_their_lines_day(tmp_path, pad):
    """X3b: a time without a date means the line's day, not today."""
    s = make_store(tmp_path)
    set_clock(dt.datetime(2026, 11, 10, 9, 0, tzinfo=BERLIN))
    out = pad.add_lines(s, [{"text": "standup", "kind": "reminder", "remind_at": "09:30"},
                            {"text": "plan the week", "kind": "prompt"},
                            {"text": "flight", "kind": "reminder", "remind_at": "2026-11-20T07:15"}], "user", "2026-11-11")
    rem, prompt, flight = out["added"]
    assert rem["remind_at"] == "2026-11-11T09:30" and prompt["queued_for"] == "2026-11-12"
    assert flight["remind_at"] == "2026-11-20T07:15"
    moved = pad.update_line(s, "2026-11-11", rem["id"], {"remind_at": "10:45"})["line"]
    assert moved["remind_at"] == "2026-11-11T10:45"
    assert pad.add_lines(s, [{"text": "today", "kind": "reminder", "remind_at": "18:00"}], "user")[
        "added"][0]["remind_at"] == "2026-11-10T18:00"


def test_reminders_due_ignores_days_written_ahead(tmp_path, pad):
    """X3c: future day files must not push today out of the window the tick reads."""
    s = make_store(tmp_path)
    set_clock(dt.datetime(2026, 11, 10, 9, 0, tzinfo=BERLIN))
    pad.add_lines(s, [{"text": "Call mom", "kind": "reminder", "remind_at": "18:30"}], "user")
    for date in ("2026-11-11", "2026-11-12", "2026-11-13"):
        pad.add_lines(s, [{"text": f"later {date}"}], "user", date)
    due = pad.reminders_due(s, "2026-11-10T18:00", "2026-11-10T18:31")
    assert [d["text"] for d in due] == ["Call mom"]


def test_card_line_action_uses_the_bridge_or_falls_back(tmp_path, monkeypatch):
    api, bridge = sub("api"), sub("hermes_bridge")
    store = make_store(tmp_path)
    api.set_store_factory(lambda: store)
    set_clock(dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    calls = []
    monkeypatch.setattr(bridge, "dispatch", lambda tool, args, ctx=None: calls.append((tool, args)) or {
        "ok": True, "task_id": "t_1", "status": "triage"})
    monkeypatch.setattr(bridge, "current_profile", lambda: "scratch")
    try:
        _, body = api.pad_lines({"op": "add", "text": "Write the health check"})
        lid = body["day"]["lines"][0]["id"]
        status, body = api.pad_lines({"op": "card", "date": "2026-11-09", "id": lid})
        assert status == 200 and body["card"]["task_id"] == "t_1" and body["day"]["lines"][0]["card_id"] == "t_1"
        assert calls[0][0] == "kanban_create" and calls[0][1]["triage"] is True and calls[0][1]["assignee"] == "scratch"
        assert api.pad_lines({"op": "card", "date": "2026-11-09", "id": lid})[0] == 409

        def broken(*a, **k):
            raise bridge.BridgeError("no kanban here")
        monkeypatch.setattr(bridge, "dispatch", broken)
        _, body = api.pad_lines({"op": "add", "text": "Second"})
        lid2 = body["day"]["lines"][1]["id"]
        status, body = api.pad_lines({"op": "card", "date": "2026-11-09", "id": lid2})
        assert status == 200 and body["card"] is None and body["fallback_draft"] == "Create a kanban card: Second"
    finally:
        api.set_store_factory(None)
