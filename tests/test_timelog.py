"""Time log: entries as a fold of appended ops, undo by name, outbox ops landing once with click times,
week totals with rates, CSV, a truncated line, the agent tool and its setting, the routes."""
import csv
import datetime as dt
import io

import pytest

from esb_fakes import BERLIN, FakeCtx, load_plugin, make_store, set_clock, sub

MON = dt.datetime(2026, 11, 9, 9, 0, tzinfo=BERLIN)  # a Monday


def at(h: float) -> dt.datetime:
    return MON + dt.timedelta(hours=h)


@pytest.fixture
def tl():
    return sub("timelog")


def test_start_stop_add_and_week_totals(tmp_path, tl):
    s = make_store(tmp_path)
    tl.set_client(s, "Acme", 80)
    tl.apply_op(s, {"op": "start", "fields": {"client": "Acme", "project": "Site"}}, "user", now=at(0))
    tl.apply_op(s, {"op": "stop"}, "user", now=at(1.5))
    tl.apply_op(s, {"op": "add", "fields": {"client": "Acme", "project": "Site", "minutes": 30, "end": at(3).isoformat()}},
                "user", now=at(4))
    tl.apply_op(s, {"op": "add", "fields": {"client": "Internal", "start": at(5).isoformat(), "end": at(6).isoformat(),
                                            "billable": False}}, "user", now=at(6))
    w = tl.week(s, now=at(7))
    assert (w["from"], w["to"], w["hours"]) == ("2026-11-09", "2026-11-15", 3.0)
    acme = [t for t in w["totals"] if t["client"] == "Acme"][0]
    assert (acme["hours"], acme["billable_hours"], acme["amount"]) == (2.0, 2.0, "160.00")
    internal = [t for t in w["totals"] if t["client"] == "Internal"][0]
    assert (internal["billable_hours"], internal["amount"]) == (0.0, None)
    rows = list(csv.reader(io.StringIO(tl.to_csv(w))))
    assert rows[0] == tl.CSV_HEADER
    assert rows[1] == ["2026-11-09", "09:00", "10:30", "1.50", "Acme", "Site", "", "yes", "80.0", "120.00", "EUR"]


def test_a_currency_is_three_letters_stored_in_capitals(tmp_path, tl):
    s = make_store(tmp_path)
    tl.set_client(s, "Acme", 80, " usd ")
    assert tl.clients(s) == [{"name": "Acme", "rate": 80.0, "currency": "USD"}]
    for bad in ("dollars", "$", "U1D"):
        with pytest.raises(tl.TimelogError) as err:
            tl.set_client(s, "Acme", 90, bad)
        assert "three letters" in str(err.value)
    assert tl.clients(s)[0]["rate"] == 80.0


def test_totals_and_the_csv_name_each_clients_currency(tmp_path, tl):
    s = make_store(tmp_path)
    tl.set_client(s, "Acme", 80, "USD")
    tl.set_client(s, "Internal", None)
    s.write_json("clients.json", {"clients": [*tl.clients(s), {"name": "Oldie", "rate": 50.0}]})  # a rate, no currency
    for client in ("Acme", "Internal", "Oldie", "Walk-in"):
        tl.apply_op(s, {"op": "add", "fields": {"client": client, "minutes": 60, "end": at(2).isoformat()}}, "user",
                    now=at(3))
    w = tl.week(s, now=at(4))
    assert {t["client"]: (t["amount"], t["currency"]) for t in w["totals"]} == {
        "Acme": ("80.00", "USD"), "Internal": (None, None), "Oldie": ("50.00", "EUR"), "Walk-in": (None, None)}
    rows = list(csv.reader(io.StringIO(tl.to_csv(w))))
    assert rows[0][-1] == "currency" and len(rows[0]) == 11
    assert {r[4]: (r[9], r[10]) for r in rows[1:]} == {
        "Acme": ("80.00", "USD"), "Internal": ("", ""), "Oldie": ("50.00", "EUR"), "Walk-in": ("", "")}


def test_starting_stops_the_running_timer(tmp_path, tl):
    s = make_store(tmp_path)
    tl.apply_op(s, {"op": "start", "fields": {"client": "A"}}, "user", now=at(0))
    tl.apply_op(s, {"op": "start", "fields": {"client": "B"}}, "user", now=at(1))
    rows = tl.entries(s, at(2))
    assert [(r["client"], r["end"] is None) for r in rows] == [("A", False), ("B", True)]
    assert rows[0]["hours"] == 1.0


def test_week_starts_sunday(tmp_path, tl):
    s = make_store(tmp_path)
    tl.apply_op(s, {"op": "add", "fields": {"client": "A", "start": (MON - dt.timedelta(hours=20)).isoformat(),
                                            "end": (MON - dt.timedelta(hours=19)).isoformat()}}, "user", now=at(0))
    assert tl.week(s, now=at(0))["hours"] == 0
    assert tl.week(s, week_starts="sunday", now=at(0))["hours"] == 1.0


def test_agent_undo_reverts_its_own_newest_op_and_only_that(tmp_path, tl):
    s = make_store(tmp_path)
    user = tl.apply_op(s, {"op": "add", "fields": {"client": "A", "minutes": 60}}, "user", now=at(1))
    eid = user["entry"]["id"]
    tl.apply_op(s, {"op": "edit", "entry_id": eid, "fields": {"note": "agent note"}}, "agent", now=at(2))
    tl.apply_op(s, {"op": "edit", "entry_id": eid, "fields": {"project": "P"}}, "user", now=at(3))
    out = tl.apply_op(s, {"op": "undo"}, "agent", now=at(4))
    assert out["op"]["reverted"]["fields"] == {"note": "agent note"}
    e = tl.entries(s, at(5))[0]
    assert (e["note"], e["project"]) == ("", "P")
    with pytest.raises(tl.TimelogError) as exc:
        tl.apply_op(s, {"op": "undo"}, "agent", now=at(6))
    assert exc.value.code == "nothing_to_undo"
    files = s.listdir("timelog")
    assert files == ["2026-W46.jsonl"]
    assert len(s.read_jsonl("timelog", files[0])[0]) == 4  # every change is a new line, nothing rewritten


def test_delete_and_edit_validation(tmp_path, tl):
    s = make_store(tmp_path)
    eid = tl.apply_op(s, {"op": "add", "fields": {"client": "A", "minutes": 30}}, "user", now=at(1))["entry"]["id"]
    with pytest.raises(tl.TimelogError):
        tl.apply_op(s, {"op": "edit", "entry_id": eid, "fields": {"end": at(-5).isoformat()}}, "user", now=at(2))
    with pytest.raises(tl.TimelogError):
        tl.apply_op(s, {"op": "edit", "entry_id": eid, "fields": {"rate": 3}}, "user", now=at(2))
    with pytest.raises(tl.TimelogError):
        tl.apply_op(s, {"op": "add", "fields": {"minutes": 30}}, "user", now=at(2))  # no client
    tl.apply_op(s, {"op": "delete", "entry_id": eid}, "user", now=at(3))
    assert tl.entries(s, at(4)) == []
    tl.apply_op(s, {"op": "undo"}, "user", now=at(5))
    assert len(tl.entries(s, at(6))) == 1


def test_outbox_replay_lands_once_with_click_times(tmp_path, tl):
    s = make_store(tmp_path)
    ops = [{"op": "start", "op_id": "d-1", "at": at(0).isoformat(), "entry_id": "eoff1", "fields": {"client": "Acme"}},
           {"op": "stop", "op_id": "d-2", "at": at(0.75).isoformat(), "entry_id": "eoff1"}]
    first = tl.replay(s, ops, now=at(2))
    again = tl.replay(s, ops, now=at(2.1))
    assert [r["applied"] for r in first] == [True, True]
    assert [r["duplicate"] for r in again] == [True, True]
    e = tl.entries(s, at(3))[0]
    assert (e["start"], e["end"], e["hours"], e["source"]) == (at(0).isoformat(), at(0.75).isoformat(), 0.75, "outbox")
    bad = tl.replay(s, [{"op": "edit", "op_id": "x", "at": at(1).isoformat()}, {"op": "stop", "op_id": "y", "at": at(1).isoformat()}],
                    now=at(3))
    assert [r.get("error") for r in bad] == ["invalid", "not_running"]


def test_truncated_last_line_is_skipped_and_counted(tmp_path, tl):
    s = make_store(tmp_path)
    tl.apply_op(s, {"op": "add", "fields": {"client": "A", "minutes": 30}}, "user", now=at(1))
    with open(s.path("timelog", "2026-W46.jsonl"), "a", encoding="utf-8") as fh:
        fh.write('{"op_id":"half","op":"add","entry_id":"e9","at":"2026-11-0')
    w = tl.week(s, now=at(2))
    assert w["hours"] == 0.5 and w["skipped_lines"] == 1
    tl.apply_op(s, {"op": "add", "fields": {"client": "B", "minutes": 30}}, "user", now=at(3))
    assert tl.week(s, now=at(4))["hours"] == 1.0


def test_long_running_flag(tmp_path, tl):
    s = make_store(tmp_path)
    tl.apply_op(s, {"op": "start", "fields": {"client": "A"}}, "user", now=at(0))
    assert tl.entries(s, at(10.5))[0]["long_running"] is True


UTC = dt.timezone.utc


def test_ops_with_different_offsets_fold_in_time_order(tmp_path, tl):
    """A page click stamped +01:00 (the Mac), then the agent's stop in UTC (Hermes without a timezone)
    30 minutes later: the stop lands, and a second stop is refused."""
    s = make_store(tmp_path)
    tl.apply_op(s, {"op": "start", "op_id": "click-1", "at": "2026-11-10T10:00:00+01:00",
                    "fields": {"client": "Acme"}}, "user", source="page", now=dt.datetime(2026, 11, 10, 10, 0, tzinfo=UTC))
    out = tl.apply_op(s, {"op": "stop"}, "agent", source="agent", now=dt.datetime(2026, 11, 10, 9, 30, tzinfo=UTC))
    assert out["entry"]["end"] == "2026-11-10T09:30:00+00:00"
    e = tl.entries(s, dt.datetime(2026, 11, 10, 12, 0, tzinfo=UTC))[0]
    assert (e["running"], e["hours"]) == (False, 0.5)
    assert tl.week(s, now=dt.datetime(2026, 11, 10, 12, 0, tzinfo=UTC))["running"] is None
    with pytest.raises(tl.TimelogError) as exc:
        tl.apply_op(s, {"op": "stop"}, "agent", now=dt.datetime(2026, 11, 10, 9, 31, tzinfo=UTC))
    assert exc.value.code == "not_running"


def test_an_edit_across_offsets_is_kept(tmp_path, tl):
    s = make_store(tmp_path)
    eid = tl.apply_op(s, {"op": "start", "op_id": "click-1", "at": "2026-11-10T10:00:00+01:00",
                          "fields": {"client": "Acme"}}, "user", now=dt.datetime(2026, 11, 10, 9, 0, tzinfo=UTC))["entry"]["id"]
    out = tl.apply_op(s, {"op": "edit", "entry_id": eid, "fields": {"note": "kickoff"}}, "agent",
                      now=dt.datetime(2026, 11, 10, 9, 20, tzinfo=UTC))  # 10:20 in Berlin, sorts before "10:00+01:00"
    assert out["entry"]["note"] == "kickoff"
    assert tl.entries(s, dt.datetime(2026, 11, 10, 9, 30, tzinfo=UTC))[0]["note"] == "kickoff"


def test_ops_across_the_dst_fall_back_hour(tmp_path, tl):
    """2026-10-25 in Berlin: 02:30+02:00 comes before 02:10+01:00 (40 minutes later)."""
    s = make_store(tmp_path)
    t = dt.datetime.fromisoformat
    tl.apply_op(s, {"op": "start", "fields": {"client": "A"}}, "user", now=t("2026-10-25T02:30:00+02:00"))
    tl.apply_op(s, {"op": "stop"}, "user", now=t("2026-10-25T02:10:00+01:00"))
    tl.apply_op(s, {"op": "add", "fields": {"client": "B", "start": "2026-10-25T02:15:00+01:00",
                                            "end": "2026-10-25T02:45:00+01:00"}}, "user", now=t("2026-10-25T02:50:00+01:00"))
    rows = tl.entries(s, t("2026-10-25T03:00:00+01:00"))
    assert [(r["client"], r["running"], round(r["hours"], 2)) for r in rows] == [("A", False, 0.67), ("B", False, 0.5)]


def test_undo_of_a_start_also_restarts_the_entry_it_stopped(tmp_path, tl):
    s = make_store(tmp_path)
    a = tl.apply_op(s, {"op": "start", "fields": {"client": "A"}}, "user", now=at(0))["entry"]["id"]
    tl.apply_op(s, {"op": "start", "fields": {"client": "B"}}, "user", now=at(0.3))
    tl.apply_op(s, {"op": "undo"}, "user", now=at(0.35))
    rows = tl.entries(s, at(0.5))
    assert [(r["id"], r["client"], r["running"]) for r in rows] == [(a, "A", True)]
    tl.apply_op(s, {"op": "stop"}, "user", now=at(0.6))  # one-step undo left one timer, and it stops normally
    assert [r["running"] for r in tl.entries(s, at(0.7))] == [False]


def test_agent_undo_of_its_start_restarts_the_entry_it_stopped(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    set_clock(at(0))
    ctx.call("eselsbruecke_timelog", action="start", client="A")
    set_clock(at(0.5))
    ctx.call("eselsbruecke_timelog", action="start", client="B")
    set_clock(at(0.6))
    undone = ctx.call("eselsbruecke_timelog", action="undo")
    assert undone["reverted"]["op"] == "start" and undone["entry"] is None
    assert [e["client"] for e in undone["restarted"]] == ["A"]
    week = ctx.call("eselsbruecke_timelog", action="week")
    assert [(e["client"], e["running"]) for e in week["entries"]] == [("A", True)]
    assert week["running"]["client"] == "A"


def test_agent_undo_never_restarts_while_another_timer_runs(tmp_path):
    # N2: the agent starts B (stops A), the user starts C (stops B); undoing B must not restart A beside C
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    set_clock(at(0))
    ctx.call("eselsbruecke_timelog", action="start", client="A")
    set_clock(at(0.2))
    ctx.call("eselsbruecke_timelog", action="start", client="B")
    s = make_store(tmp_path)
    sub("timelog").apply_op(s, {"op": "start", "fields": {"client": "C"}}, "user", now=at(0.4))
    set_clock(at(0.5))
    undone = ctx.call("eselsbruecke_timelog", action="undo")
    assert undone["reverted"]["op"] == "start" and undone["entry"] is None
    assert undone["restarted"] == []
    assert "C" in undone.get("note", "") and "running" in undone.get("note", "")
    week = ctx.call("eselsbruecke_timelog", action="week")
    assert [(e["client"], e["running"]) for e in week["entries"]] == [("A", False), ("C", True)]


def test_undo_restarts_the_stopped_entry_once_the_newer_timer_stopped(tmp_path, tl):
    s = make_store(tmp_path)
    tl.apply_op(s, {"op": "start", "fields": {"client": "A"}}, "user", now=at(0))
    tl.apply_op(s, {"op": "start", "fields": {"client": "B"}}, "agent", source="agent", now=at(0.2))
    tl.apply_op(s, {"op": "start", "fields": {"client": "C"}}, "user", now=at(0.4))
    tl.apply_op(s, {"op": "stop"}, "user", now=at(0.5))
    out = tl.apply_op(s, {"op": "undo"}, "agent", source="agent", now=at(0.6))
    assert [e["client"] for e in out["restarted"]] == ["A"] and "note" not in out
    assert [r["client"] for r in tl.entries(s, at(0.7)) if r["running"]] == ["A"]


def test_history_is_read_once_and_then_only_the_changed_week(tmp_path, tl, monkeypatch):
    """Week files are only appended, so a file whose size and mtime are unchanged is not read again;
    op_id dedupe still sees every week ever written."""
    s = make_store(tmp_path)
    for k in range(6):  # six weeks of history
        tl.apply_op(s, {"op": "add", "op_id": f"old-{k}", "at": at(-24 * 7 * (k + 1)).isoformat(),
                        "fields": {"client": "A", "minutes": 30}}, "user", now=at(0))
    tl.week(s, now=at(1))
    reads = []
    real = type(s).read_jsonl
    monkeypatch.setattr(type(s), "read_jsonl", lambda self, *parts: reads.append(parts[-1]) or real(self, *parts))
    w = tl.week(s, now=at(1))
    assert reads == [] and w["hours"] == 0
    assert tl.apply_op(s, {"op": "add", "op_id": "old-5", "fields": {"client": "A", "minutes": 5}}, "user",
                       now=at(1))["duplicate"] is True
    assert reads == []
    tl.apply_op(s, {"op": "add", "fields": {"client": "A", "minutes": 30}}, "user", now=at(1))
    assert reads == ["2026-W46.jsonl"]
    other = type(s)(s.root)  # another process appends: its write is seen
    other.append_jsonl(("timelog", "2026-W46.jsonl"), {"op_id": "x", "op": "add", "entry_id": "ex", "at": at(1.5).isoformat(),
                                                      "by": "user", "fields": {"client": "B", "start": at(1).isoformat(),
                                                                               "end": at(1.5).isoformat()}})
    assert tl.week(s, now=at(2))["hours"] == 1.0


def test_a_returned_entry_is_a_copy(tmp_path, tl):
    """Folded history is cached between calls, so nothing a caller gets back may alias it."""
    s = make_store(tmp_path)
    tl.apply_op(s, {"op": "start", "fields": {"client": "A"}}, "user", now=at(0))["entry"]["client"] = "mutated"
    tl.entries(s, at(0.1))[0]["client"] = "mutated"
    tl.week(s, now=at(0.1))["running"]["client"] = "mutated"
    assert tl.entries(s, at(0.2))[0]["client"] == "A"


def test_agent_tool_and_the_edits_setting(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    set_clock(at(1))
    out = ctx.call("eselsbruecke_timelog", action="add", client="Acme", minutes=45, note="call")
    assert out["ok"] and out["entry"]["by"] == "agent" and "undo" in out["undo"]
    eid = out["entry"]["id"]
    assert ctx.call("eselsbruecke_timelog", action="edit", entry_id=eid, fields={"note": "kickoff"})["entry"]["note"] == "kickoff"
    week = ctx.call("eselsbruecke_timelog", action="week")
    assert week["hours"] == 0.75 and week["entries"][0]["note"] == "kickoff"
    exp = ctx.call("eselsbruecke_timelog", action="export")
    assert exp["rows"] == 1 and exp["path"].endswith("exports/timelog-2026-11-09.csv")
    assert ctx.call("eselsbruecke_timelog", action="undo")["reverted"]["op"] == "edit"

    ctx.settings["agent_timelog_edits"] = "never"
    refused = ctx.call("eselsbruecke_timelog", action="delete", entry_id=eid)
    assert refused["error"] == "agent_timelog_edits"
    assert ctx.call("eselsbruecke_timelog", action="stop")["error"] == "not_running"  # start/stop/add still allowed


def test_agent_writes_refused_unattended(tmp_path, monkeypatch):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    monkeypatch.setattr(sub("hermes_bridge"), "unattended_reason", lambda _ctx=None: "cron job")
    out = ctx.call("eselsbruecke_timelog", action="start", client="Acme")
    assert out["error"] == "unattended"
    assert ctx.call("eselsbruecke_timelog", action="week")["hours"] == 0


def test_routes(tmp_path):
    api, store_mod = sub("api"), sub("store")
    store = store_mod.Store(tmp_path / "data")
    api.set_store_factory(lambda: store)
    set_clock(at(1))
    try:
        status, body = api.timelog_post({"op": "client", "name": "Acme", "rate": 90})
        assert status == 200 and body["clients"] == [{"name": "Acme", "rate": 90.0, "currency": "EUR"}]
        status, body = api.timelog_post({"op": "start", "fields": {"client": "Acme"}, "source": "chip"})
        assert status == 200 and body["week"]["running"]["client"] == "Acme"
        assert api.timelog_post({"op": "edit", "entry_id": "nope", "fields": {"note": "x"}})[0] == 404
        status, body = api.timelog_ops({"ops": [{"op": "stop", "op_id": "o1", "at": at(1).isoformat()}]})
        assert body["results"][0]["applied"] is True
        status, body = api.timelog_export()
        assert body["filename"] == "timelog-2026-11-09.csv" and body["csv"].startswith("date,start,end")
        assert body["csv"].splitlines()[0].endswith(",amount,currency") and body["csv"].splitlines()[1].endswith(",EUR")
        assert api.timelog_get()[1]["week"]["totals"][0]["currency"] == "EUR"
        store.write_json("toolbox.json", {**sub("toolbox").load(store),
                                          "modules": {**sub("toolbox").load(store)["modules"],
                                                      "timelog": {"on": False}}})
        assert api.timelog_get()[0] == 409
    finally:
        api.set_store_factory(None)
