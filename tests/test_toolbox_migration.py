"""A toolbox file and saved versions written by 0.1 (schema 1) keep working: they are read as
schema 2, never reported as broken, and the next save writes schema 2."""
import copy
import json

import pytest

from esb_fakes import FakeCtx, load_plugin, make_store, sub

# toolbox.json as 0.1 wrote it after the user switched the QR code off, docked the pad, chose the flat
# rail and a 50/10 pomodoro, added a tip and turned alerts on.
V01 = {
    "schema": 1, "preset": "custom", "first_run": False,
    "modules": {
        "pad": {"on": True, "order": 0, "options": {}}, "pomodoro": {"on": True, "order": 1, "options": {}},
        "timelog": {"on": True, "order": 2, "options": {}}, "formatter": {"on": True, "order": 3, "options": {}},
        "diff": {"on": True, "order": 4, "options": {}}, "regex": {"on": True, "order": 5, "options": {}},
        "tokens": {"on": True, "order": 6, "options": {}}, "cron": {"on": True, "order": 7, "options": {}},
        "encode": {"on": True, "order": 8, "options": {}}, "timezones": {"on": True, "order": 9, "options": {}},
        "generate": {"on": True, "order": 10, "options": {}}, "colour": {"on": True, "order": 11, "options": {}},
        "qr": {"on": False, "order": 12, "options": {}}, "calc": {"on": True, "order": 13, "options": {}},
    },
    "layout": {"rail": "flat", "dock": "pad", "chip": "auto"},
    "pomodoro": {"rhythm": "50/10", "work": 50, "short": 10, "long": 20, "cycles": 3},
    "tips": [{"id": "user-1a2b3c4d", "title": "Stand up", "why": "Every hour"}],
    "alerts": {"while_closed": True},
}
# The same file with every setting as 0.1 shipped it.
V01_PLAIN = {**copy.deepcopy(V01), "preset": "everything", "layout": {"rail": "groups", "dock": None, "chip": "auto"},
             "pomodoro": {"rhythm": "25/5", "work": 25, "short": 5, "long": 15, "cycles": 4}, "tips": [],
             "alerts": {"while_closed": False}}
V01_PLAIN["modules"]["qr"]["on"] = True


@pytest.fixture
def tb():
    return sub("toolbox")


@pytest.fixture
def api(tmp_path):
    a = sub("api")
    store = make_store(tmp_path)
    a.set_store_factory(lambda: store)
    yield a
    a.set_store_factory(None)


def _write(s, doc):
    s.root.mkdir(parents=True, exist_ok=True)
    (s.root / "toolbox.json").write_text(json.dumps(doc), encoding="utf-8")


def _version(s, n, doc, summary="QR code off"):
    folder = s.root / "toolbox.versions"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{n}.json").write_text(json.dumps({"n": n, "author": "user", "time": "2026-11-09T10:00:00+01:00",
                                                  "summary": summary, "doc": doc}), encoding="utf-8")


@pytest.mark.parametrize("old", [V01, V01_PLAIN], ids=["edited", "plain"])
def test_a_file_from_0_1_loads_as_schema_2_and_is_not_broken(tmp_path, tb, old):
    s = make_store(tmp_path)
    _write(s, old)
    on_disk = (s.root / "toolbox.json").read_text(encoding="utf-8")
    doc, problem = tb.load_state(s)
    assert problem is None
    assert doc["schema"] == 2 and "preset" not in doc
    assert doc["layout"] == {"chip": "auto", "chip_visible": True}
    for kept in ("first_run", "modules", "pomodoro", "tips", "alerts"):
        assert doc[kept] == old[kept], kept
    assert doc["dashboard"] == tb.default_doc()["dashboard"] and doc["clocks"] == tb.default_doc()["clocks"]
    assert tb.validate(doc)[1] == []
    assert tb.is_on(s, "qr") is old["modules"]["qr"]["on"]
    assert (s.root / "toolbox.json").read_text(encoding="utf-8") == on_disk  # reading never writes
    assert not (s.root / "toolbox.versions").exists()


@pytest.mark.parametrize("chip,expect", [
    ("auto", {"chip": "auto", "chip_visible": True}),
    ("pomodoro", {"chip": "pomodoro", "chip_visible": True}),
    ("timelog", {"chip": "timelog", "chip_visible": True}),
    ("off", {"chip": "auto", "chip_visible": False}),
])
def test_each_chip_setting_of_0_1_carries_over(tmp_path, tb, chip, expect):
    s = make_store(tmp_path)
    _write(s, {**V01, "layout": {"rail": "groups", "dock": None, "chip": chip}})
    doc, problem = tb.load_state(s)
    assert problem is None and doc["layout"] == expect


def test_the_next_save_writes_schema_2_and_keeps_no_broken_copy(tmp_path, tb):
    s = make_store(tmp_path)
    _write(s, V01)
    out = tb.set_switch(s, "diff", False, "user")
    assert out["version"] == 1 and out["summary"] == "Text diff off" and "kept_broken" not in out
    saved = json.loads((s.root / "toolbox.json").read_text(encoding="utf-8"))
    assert saved["schema"] == 2 and "preset" not in saved and set(saved["layout"]) == {"chip", "chip_visible"}
    assert saved["modules"]["qr"]["on"] is False and saved["modules"]["diff"]["on"] is False
    assert saved["pomodoro"] == V01["pomodoro"] and saved["tips"] == V01["tips"]
    assert not [p for p in s.root.iterdir() if p.name.startswith("toolbox.broken-")]


def test_a_saved_version_from_0_1_restores(tmp_path, tb):
    s = make_store(tmp_path)
    _version(s, 1, V01)
    tb.set_clock(s, "Mumbai", "user")  # v2, a current file with everything on
    assert tb.is_on(s, "qr") is True
    out = tb.restore(s, 1, "user")
    assert out["version"] == 3 and out["summary"] == "Restored v1"
    doc, problem = tb.load_state(s)
    assert problem is None and doc["schema"] == 2
    assert doc["modules"]["qr"]["on"] is False and doc["pomodoro"]["rhythm"] == "50/10"
    assert doc["alerts"]["while_closed"] is True and doc["tips"] == V01["tips"]
    assert json.loads((s.root / "toolbox.json").read_text(encoding="utf-8"))["schema"] == 2


def test_restoring_a_version_from_0_1_keeps_todays_places_and_pins(tmp_path, tb):
    s = make_store(tmp_path)
    _version(s, 1, V01)
    tb.set_clock(s, "Mumbai", "user")
    tb.set_pin(s, "qr", True, "user")
    today = tb.load(s)
    tb.restore(s, 1, "user")
    doc = tb.load(s)
    assert doc["clocks"] == today["clocks"] and {"zone": "Asia/Kolkata", "label": "Mumbai"} in doc["clocks"]
    assert doc["dashboard"] == today["dashboard"] and "qr" in doc["dashboard"]
    assert doc["modules"]["qr"]["on"] is False  # what the old version did say is restored


def test_restoring_a_current_version_restores_its_places_and_pins(tmp_path, tb):
    s = make_store(tmp_path)
    first = tb.set_clock(s, "Mumbai", "user")["version"]
    tb.set_clock(s, "Mumbai", "user", remove=True)
    tb.restore(s, first, "user")
    assert {"zone": "Asia/Kolkata", "label": "Mumbai"} in tb.load(s)["clocks"]


def test_a_saved_version_from_0_1_restores_through_the_page_and_the_agent(tmp_path, api):
    s = api.store()
    _version(s, 1, V01)
    status, body = api.toolbox_post({"op": "restore", "version": 1})
    assert status == 200 and "file_error" not in body
    assert body["toolbox"]["schema"] == 2 and body["toolbox"]["modules"]["qr"]["on"] is False
    assert [v["n"] for v in api.toolbox_versions()[1]["versions"]] == [2, 1]
    ctx = FakeCtx(s.root)
    load_plugin().register(ctx)
    assert ctx.call("eselsbruecke_toolbox", action="restore", version=1)["summary"] == "Restored v1"


def test_a_broken_file_falls_back_to_a_version_from_0_1(tmp_path, tb):
    s = make_store(tmp_path)
    _version(s, 4, {**V01, "layout": {"rail": "groups", "dock": None, "chip": "off"}})
    (s.root / "toolbox.json").write_text("{broken", encoding="utf-8")
    doc, problem = tb.load_state(s)
    assert problem["using"] == "version 4"
    assert doc["schema"] == 2 and doc["modules"]["qr"]["on"] is False
    assert doc["layout"] == {"chip": "auto", "chip_visible": False}


def test_the_page_and_the_agent_see_a_file_from_0_1_without_a_file_error(tmp_path, api):
    s = api.store()
    _write(s, V01)
    status, view = api.toolbox_get()
    assert status == 200 and "file_error" not in view
    assert view["schema"] == 2 and view["toolbox"]["schema"] == 2 and "presets" not in view
    assert {t["id"]: t["on"] for t in view["tools"]}["qr"] is False
    assert api.pad_get()[0] == 200 and api.timer_get()[0] == 200
    ctx = FakeCtx(s.root)
    load_plugin().register(ctx)
    listed = ctx.call("eselsbruecke_toolbox", action="list")
    assert listed["ok"] and "file_error" not in listed and listed["pomodoro"]["rhythm"] == "50/10"


def test_the_page_saves_on_top_of_a_file_from_0_1(tmp_path, api):
    s = api.store()
    _write(s, V01)
    _, view = api.toolbox_get()
    doc = view["toolbox"]
    doc["clocks"].append({"zone": "Europe/Lisbon", "label": "Lisbon"})
    status, body = api.toolbox_post({"op": "save", "base_hash": view["hash"], "toolbox": doc})
    assert status == 200 and body["saved"]["summary"] == "Lisbon added to the world clock"
    assert json.loads((s.root / "toolbox.json").read_text(encoding="utf-8"))["clocks"][-1]["label"] == "Lisbon"


def test_a_file_from_0_1_that_is_really_broken_is_still_reported(tmp_path, tb):
    s = make_store(tmp_path)
    bad = copy.deepcopy(V01)
    bad["modules"]["qr"]["order"] = "first"
    _write(s, bad)
    doc, problem = tb.load_state(s)
    assert problem["using"] == "defaults" and "modules.qr.order" in problem["reason"]
    assert "preset" not in problem["reason"] and "rail" not in problem["reason"]


def test_a_hand_edited_file_without_schema_keeps_what_it_says(tmp_path, tb):
    s = make_store(tmp_path)
    _write(s, {"preset": "focus", "layout": {"chip_visible": False},
               "clocks": [{"zone": "Europe/Lisbon", "label": "Lisbon"}], "dashboard": ["pad"]})
    doc, problem = tb.load_state(s)
    assert problem is None and doc["schema"] == 2
    assert doc["layout"] == {"chip": "auto", "chip_visible": False}
    assert doc["clocks"] == [{"zone": "Europe/Lisbon", "label": "Lisbon"}] and doc["dashboard"] == ["pad"]


def test_migrate_leaves_schema_2_and_its_argument_alone(tb):
    current = tb.default_doc()
    assert tb.migrate(current) is current
    old = copy.deepcopy(V01)
    new = tb.migrate(old)
    assert old == V01 and new["schema"] == 2 and new is not old
    for odd in (None, [], "text", {"schema": 3, "preset": "focus"}):
        assert tb.migrate(odd) == odd
