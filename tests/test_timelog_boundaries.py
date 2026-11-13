"""Time-log values from a click, the outbox or the agent that must be refused before they are stored,
and values an older version stored that later reads must skip instead of failing on."""
import csv
import datetime as dt
import io
import json

import pytest

from esb_fakes import BERLIN, FakeCtx, load_plugin, make_store, set_clock, sub

MON = dt.datetime(2026, 11, 9, 9, 0, tzinfo=BERLIN)  # a Monday


def at(h: float) -> dt.datetime:
    return MON + dt.timedelta(hours=h)


@pytest.fixture
def tl():
    return sub("timelog")


@pytest.fixture
def routes(tmp_path):
    api = sub("api")
    store = make_store(tmp_path)
    api.set_store_factory(lambda: store)
    set_clock(at(1))
    yield api, store
    api.set_store_factory(None)


@pytest.mark.parametrize("op", ["start", "stop", "edit", "delete"])
@pytest.mark.parametrize("bad", [["x"], {"a": 1}, 7, "e" * 65])
def test_an_entry_id_that_is_not_an_id_is_refused(routes, op, bad):
    api, store = routes
    body = {"op": op, "entry_id": bad, "fields": {"client": "Acme"} if op != "delete" else {}}
    status, out = api.timelog_post(body)
    assert status == 400 and out["error"] == "invalid", out
    assert api.timelog_get()[0] == 200


def test_a_stored_op_with_an_unusable_entry_id_is_skipped_and_counted(routes, tl):
    api, store = routes
    tl.apply_op(store, {"op": "add", "fields": {"client": "Acme", "minutes": 30, "end": at(0.5).isoformat()}},
                "user", now=at(1))
    week = store.path(tl.DIR, tl.week_file(at(1)))
    with open(week, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"op_id": "old-1", "op": "start", "entry_id": ["x"], "at": at(0.75).isoformat(),
                             "by": "user", "source": "page", "fields": {"client": "Old"}}) + "\n")
        fh.write(json.dumps({"op_id": ["y"], "op": "stop", "entry_id": "e1", "at": at(0.8).isoformat()}) + "\n")
        fh.write(json.dumps({"op_id": "old-3", "op": "edit", "entry_id": "e2", "at": at(0.8).isoformat(),
                             "fields": ["not", "an", "object"]}) + "\n")
    status, body = api.timelog_get()
    assert status == 200
    assert [e["client"] for e in body["week"]["entries"]] == ["Acme"]
    assert body["week"]["skipped_lines"] == 3


LONG = "x" * 70


def _old_rows(store, tl, rows):
    """Ops as 0.2.0 stored them: the agent's ids as the model sent them (a number, a long string)."""
    path = store.path(tl.DIR, tl.week_file(at(1)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({"by": "agent", "source": "agent", **row}) + "\n")


def test_entries_0_2_0_stored_under_a_number_or_a_long_id_can_be_stopped_edited_and_deleted(routes, tl):
    api, store = routes
    _old_rows(store, tl, [
        {"op_id": "a1", "op": "start", "entry_id": LONG, "at": at(-0.5).isoformat(), "fields": {"client": "Echo"}},
        {"op_id": "a2", "op": "stop", "entry_id": LONG, "at": at(-0.25).isoformat(), "fields": {}},
        {"op_id": "a3", "op": "start", "entry_id": 5, "at": at(0.5).isoformat(), "fields": {"client": "Delta"}},
    ])
    status, body = api.timelog_get()
    running = [e for e in body["week"]["entries"] if e["running"]]
    assert status == 200 and [e["id"] for e in running] == ["5"] and body["week"]["skipped_lines"] == 0
    status, out = api.timelog_post({"op": "stop", "entry_id": running[0]["id"], "source": "chip"})
    assert status == 200 and out["result"]["entry"]["end"], out
    for eid in (5, "5", LONG):  # an outbox queued by 0.2.0's page may still hold the number
        status, out = api.timelog_post({"op": "edit", "entry_id": eid, "fields": {"note": "fixed"}})
        assert status == 200 and out["result"]["entry"]["note"] == "fixed", (eid, out)
    for eid in ("5", LONG):
        status, out = api.timelog_post({"op": "delete", "entry_id": eid})
        assert status == 200 and out["result"]["entry"]["deleted"], (eid, out)
    assert [e["id"] for e in api.timelog_get()[1]["week"]["entries"]] == []


def test_a_new_start_stops_a_running_entry_0_2_0_stored_under_a_number(routes, tl):
    api, store = routes
    _old_rows(store, tl, [{"op_id": 7, "op": "start", "entry_id": 5, "at": at(0.5).isoformat(),
                           "fields": {"client": "Delta"}}])
    status, out = api.timelog_post({"op": "start", "fields": {"client": "Acme"}})
    assert status == 200, out
    entries = {e["client"]: e for e in api.timelog_get()[1]["week"]["entries"]}
    assert entries["Delta"]["end"] and entries["Acme"]["running"]
    status, out = api.timelog_post({"op": "undo"})  # the undo restarts it again
    assert status == 200 and [e["client"] for e in api.timelog_get()[1]["week"]["entries"] if e["running"]] == ["Delta"]


def test_ids_that_name_no_entry_keep_the_text_rule(routes, tl):
    """Ordinary use is unchanged: page ids work, and an unknown number or long id is still refused."""
    api, store = routes
    _old_rows(store, tl, [{"op_id": "a3", "op": "start", "entry_id": 5, "at": at(0.5).isoformat(),
                           "fields": {"client": "Delta"}}])
    for bad in (6, "y" * 65, LONG):
        status, out = api.timelog_post({"op": "edit", "entry_id": bad, "fields": {"note": "x"}})
        assert status == 400 and out["error"] == "invalid", (bad, out)
    status, out = api.timelog_post({"op": "start", "entry_id": "5", "fields": {"client": "Other"}})
    assert status == 409 and out["error"] == "entry_exists"
    status, out = api.timelog_post({"op": "start", "entry_id": "e-page-1", "fields": {"client": "Acme"}})
    assert status == 200 and out["result"]["entry"]["id"] == "e-page-1"
    status, out = api.timelog_post({"op": "stop", "entry_id": "e-page-1"})
    assert status == 200 and out["result"]["entry"]["end"]


@pytest.mark.parametrize("rate", ["inf", float("inf"), 1e30, "1e308", float("nan"), "nan", -1, [1], True, "abc"])
def test_a_rate_that_is_no_sane_amount_is_refused(routes, tl, rate):
    api, store = routes
    status, out = api.timelog_post({"op": "client", "name": "Acme", "rate": rate})
    assert status == 400 and out["error"] == "invalid", out
    assert tl.clients(store) == []
    assert api.timelog_get()[0] == 200 and api.timelog_export()[0] == 200


def test_a_stored_rate_that_is_no_number_is_ignored_with_a_note(routes, tl):
    api, store = routes
    store.write_json("clients.json", {"clients": [{"name": "Acme", "rate": float("inf"), "currency": "EUR"},
                                                  {"name": "Big", "rate": 1e30},
                                                  {"name": "Fine", "rate": 80.0, "currency": "EUR"}]})
    for client in ("Acme", "Big", "Fine"):
        tl.apply_op(store, {"op": "add", "fields": {"client": client, "minutes": 60, "end": at(1).isoformat()}},
                    "user", now=at(1))
    status, body = api.timelog_get()
    assert status == 200
    json.dumps(body, allow_nan=False)  # the real route renders with Starlette, which refuses NaN and inf
    by_name = {c["name"]: c for c in body["clients"]}
    assert "rate" not in by_name["Acme"] and "rate" not in by_name["Big"] and by_name["Fine"]["rate"] == 80.0
    assert "rate" in by_name["Acme"]["note"]
    amounts = {t["client"]: t["amount"] for t in body["week"]["totals"]}
    assert amounts == {"Acme": None, "Big": None, "Fine": "80.00"}
    assert api.timelog_export()[0] == 200
    tl.set_client(store, "Acme", 90)
    assert {c["name"]: c for c in tl.clients(store)}["Acme"] == {"name": "Acme", "rate": 90.0, "currency": "EUR"}


def test_a_large_rate_keeps_every_cent_on_any_thread(tmp_path, tl):
    import threading

    s = make_store(tmp_path)
    tl.set_client(s, "Acme", 999_999_999.99)
    tl.apply_op(s, {"op": "add", "fields": {"client": "Acme", "minutes": 60, "end": at(1).isoformat()}}, "user",
                now=at(1))
    seen = []
    worker = threading.Thread(target=lambda: seen.append(tl.week(s, now=at(2))["totals"][0]["amount"]))
    worker.start()
    worker.join()
    assert seen == ["999999999.99"]


@pytest.mark.parametrize("edits", ["never", "allow"])
def test_a_start_never_replaces_an_existing_entry(tmp_path, tl, edits):
    ctx = FakeCtx(tmp_path / "data", settings={"agent_timelog_edits": edits})
    load_plugin().register(ctx)
    store = make_store(tmp_path)
    set_clock(at(2))
    mine = tl.apply_op(store, {"op": "add", "fields": {"client": "Acme", "note": "kickoff", "minutes": 60,
                                                        "end": at(1).isoformat()}}, "user", now=at(2))["entry"]
    out = ctx.call("eselsbruecke_timelog", action="start", entry_id=mine["id"], client="Other")
    assert out["ok"] is False and out["error"] == "entry_exists", out
    kept = [e for e in tl.entries(store, now=at(2)) if e["id"] == mine["id"]][0]
    assert (kept["client"], kept["note"], kept["running"]) == ("Acme", "kickoff", False)
    assert ctx.call("eselsbruecke_timelog", action="start", client="Other")["entry"]["id"] != mine["id"]


def test_a_click_start_with_an_existing_entry_id_is_refused(routes, tl):
    api, store = routes
    mine = tl.apply_op(store, {"op": "add", "fields": {"client": "Acme", "minutes": 30, "end": at(0.5).isoformat()}},
                       "user", now=at(1))["entry"]
    status, out = api.timelog_post({"op": "start", "entry_id": mine["id"], "fields": {"client": "Other"}})
    assert status == 409 and out["error"] == "entry_exists"
    status, out = api.timelog_ops({"ops": [{"op": "start", "op_id": "o-new", "at": at(1).isoformat(),
                                            "entry_id": mine["id"], "fields": {"client": "Other"}}]})
    assert out["results"][0]["error"] == "entry_exists"
    assert [e["client"] for e in tl.entries(store, now=at(1))] == ["Acme"]


@pytest.mark.parametrize("bad", [
    {"op": "add", "op_id": "b1", "at": "MON", "fields": {"client": "Acme", "minutes": 1e300}},
    {"op": "add", "op_id": "b2", "at": "MON", "fields": {"client": "Acme", "minutes": "inf"}},
    {"op": "add", "op_id": "b3", "at": "0001-01-01T00:30:00+00:00", "fields": {"client": "Acme", "minutes": 90}},
    {"op": "add", "op_id": "b4", "at": "MON", "fields": {"client": "Acme", "minutes": [1]}},
])
def test_one_bad_outbox_op_is_refused_alone(routes, tl, bad):
    api, store = routes
    bad = {**bad, "at": at(0.5).isoformat() if bad["at"] == "MON" else bad["at"]}
    good = {"op": "start", "op_id": "g1", "at": at(0.75).isoformat(), "fields": {"client": "Good"}}
    status, out = api.timelog_ops({"ops": [bad, good]})
    assert status == 200, out
    assert out["results"][0]["error"] == "invalid" and out["results"][1]["applied"] is True
    assert out["week"]["running"]["client"] == "Good"


@pytest.mark.parametrize("minutes", [0, -5, float("nan"), 1e300, 525601])
def test_add_minutes_must_be_a_sane_length(tmp_path, tl, minutes):
    s = make_store(tmp_path)
    with pytest.raises(tl.TimelogError):
        tl.apply_op(s, {"op": "add", "fields": {"client": "Acme", "minutes": minutes}}, "user", now=at(1))


def test_add_leaves_the_callers_fields_as_they_were(tmp_path, tl):
    s = make_store(tmp_path)
    fields = {"client": "Acme", "minutes": 30}
    tl.apply_op(s, {"op": "add", "fields": fields}, "user", now=at(1))
    assert fields == {"client": "Acme", "minutes": 30}


def test_csv_cells_that_a_spreadsheet_would_run_as_formulas_are_quoted(tmp_path, tl):
    s = make_store(tmp_path)
    for client, project, note in [("=HYPERLINK(\"http://x\")", "+1", "@SUM(A1)"), ("-2", "\tTab", "\rCR"),
                                  ("Acme", "Site", "plain - text")]:
        tl.apply_op(s, {"op": "add", "fields": {"client": client, "project": project, "note": note, "minutes": 30,
                                                "end": at(1).isoformat()}}, "user", now=at(1))
    rows = list(csv.DictReader(io.StringIO(tl.to_csv(tl.week(s, now=at(2))))))
    cells = [r[k] for r in rows for k in ("client", "project", "note")]
    assert all(not c or c[0] not in "=+-@\t\r" for c in cells), cells
    assert {"'=HYPERLINK(\"http://x\")", "'+1", "'@SUM(A1)", "'-2"} <= set(cells)
    assert "Acme" in cells and "plain - text" in cells


def test_clearing_end_never_leaves_two_timers_running(tmp_path, tl):
    s = make_store(tmp_path)
    done = tl.apply_op(s, {"op": "add", "fields": {"client": "Old", "minutes": 30, "end": at(0.5).isoformat()}},
                       "user", now=at(1))["entry"]
    tl.apply_op(s, {"op": "start", "fields": {"client": "Now"}}, "user", now=at(1))
    with pytest.raises(tl.TimelogError) as err:
        tl.apply_op(s, {"op": "edit", "entry_id": done["id"], "fields": {"end": ""}}, "user", now=at(2))
    assert err.value.code == "running" and "Now" in str(err.value)
    assert [e["client"] for e in tl.entries(s, now=at(2)) if e["running"]] == ["Now"]
    tl.apply_op(s, {"op": "stop"}, "user", now=at(2))
    reopened = tl.apply_op(s, {"op": "edit", "entry_id": done["id"], "fields": {"end": ""}}, "user", now=at(2))
    assert reopened["entry"]["end"] is None
