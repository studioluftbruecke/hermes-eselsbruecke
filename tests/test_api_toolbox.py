"""The route logic (api.py) for the toolbox: health, view, switch, save with a stale base, the saves
the Desktop makes for the dashboard, the world clock, the status bar and the welcome card, restore."""
import pytest

from esb_fakes import sub


@pytest.fixture
def api(tmp_path):
    a = sub("api")
    store = sub("store").Store(tmp_path / "data")
    a.set_store_factory(lambda: store)
    yield a
    a.set_store_factory(None)


def test_health(api):
    status, body = api.health()
    assert status == 200 and body["ok"] and body["schema"] == 1 and body["plugin"] == "eselsbruecke"
    assert body["version"] and "time_zone" in body


def test_switch_save_and_stale(api):
    status, view = api.toolbox_get()
    assert status == 200 and len(view["tools"]) == 14
    status, body = api.toolbox_post({"op": "switch", "module": "qr", "on": False})
    assert status == 200 and body["saved"]["summary"] == "QR code off"
    doc = body["toolbox"]
    doc["modules"]["diff"]["on"] = False
    status, body = api.toolbox_post({"op": "save", "toolbox": doc, "base_hash": view["hash"]})
    assert status == 409 and body["error"] == "stale" and body["current"]["toolbox"]["modules"]["qr"]["on"] is False
    _, fresh = api.toolbox_get()
    status, body = api.toolbox_post({"op": "save", "toolbox": doc, "base_hash": fresh["hash"]})
    assert status == 200 and body["saved"]["summary"] == "Text diff off"
    status, body = api.toolbox_post({"op": "restore", "version": 1})
    assert status == 200 and body["toolbox"]["modules"]["diff"]["on"] is True
    status, body = api.toolbox_versions()
    assert [v["n"] for v in body["versions"]] == [3, 2, 1]


def test_the_view_is_the_documented_shape(api):
    status, view = api.toolbox_get()
    assert status == 200 and set(view) == {"ok", "schema", "toolbox", "tools", "hash"}
    assert view["ok"] is True and view["schema"] == 2
    assert set(view["toolbox"]) == {"schema", "first_run", "modules", "dashboard", "clocks", "layout", "pomodoro",
                                    "tips", "alerts"}
    tools = {t["id"]: t for t in view["tools"]}
    assert tools["timezones"]["title"] == "World clock" and tools["timezones"]["group"] == "daily"
    assert tools["pad"]["dashboard"] == "widget" and tools["qr"]["dashboard"] == "tile"
    assert tools["calc"]["dashboard"] is None
    assert all({"on", "options", "blurb", "surfaces"} <= set(t) for t in view["tools"])


def test_the_desktop_saves_pins_places_the_status_bar_and_the_welcome_card(api):
    _, view = api.toolbox_get()
    doc = view["toolbox"]
    assert doc["first_run"] is True
    doc["first_run"] = False
    status, body = api.toolbox_post({"op": "save", "base_hash": view["hash"], "toolbox": doc})
    assert status == 200 and body["saved"]["summary"] == "First run done" and body["toolbox"]["first_run"] is False

    doc = body["toolbox"]
    doc["dashboard"] = ["qr", "pad", "timezones"]
    status, body = api.toolbox_post({"op": "save", "base_hash": body["hash"], "toolbox": doc})
    assert status == 200, body
    doc["clocks"] = [{"zone": "Asia/Kolkata", "label": " Mumbai "}, {"zone": "Asia/Tokyo", "label": "Tokyo"}]
    status, body = api.toolbox_post({"op": "save", "base_hash": body["hash"], "toolbox": doc})
    assert status == 200, body
    doc["layout"] = {"chip": "timelog", "chip_visible": False}
    status, body = api.toolbox_post({"op": "save", "base_hash": body["hash"], "toolbox": doc})
    assert status == 200 and body["saved"]["summary"] == "Status bar: hidden, Status bar shows: Time log"
    saved = api.toolbox_get()[1]["toolbox"]
    assert saved["dashboard"] == ["qr", "pad", "timezones"]
    assert saved["clocks"] == [{"zone": "Asia/Kolkata", "label": "Mumbai"}, {"zone": "Asia/Tokyo", "label": "Tokyo"}]
    assert saved["layout"] == {"chip": "timelog", "chip_visible": False}
    assert [v["author"] for v in api.toolbox_versions()[1]["versions"]] == ["user"] * 4


@pytest.mark.parametrize("change,needle", [
    ({"dashboard": ["pad", "pad"]}, "dashboard[1]"),
    ({"dashboard": ["calc"]}, "dashboard[0]"),
    ({"clocks": [{"zone": "Mars/Phobos", "label": "Phobos"}]}, "clocks[0].zone"),
    ({"clocks": [{"zone": "Asia/Tokyo", "label": ""}]}, "clocks[0].label"),
    ({"layout": {"chip": "off", "chip_visible": True}}, "layout.chip"),
    ({"preset": "focus"}, "unknown key 'preset'"),
], ids=["pin-twice", "pin-calculator", "unknown-zone", "empty-label", "chip-off", "preset"])
def test_an_invalid_save_answers_400_and_changes_nothing(api, change, needle):
    _, view = api.toolbox_get()
    status, body = api.toolbox_post({"op": "save", "base_hash": view["hash"], "toolbox": {**view["toolbox"], **change}})
    assert status == 400 and body["error"] == "invalid" and needle in body["message"], body
    assert api.toolbox_get()[1]["hash"] == view["hash"] and api.toolbox_versions()[1]["versions"] == []


def test_bad_requests(api):
    assert api.toolbox_post(None)[0] == 400
    assert api.toolbox_post({"op": "nope"})[0] == 400
    status, body = api.toolbox_post({"op": "preset", "preset": "focus"})
    assert status == 400 and body["error"] == "invalid" and "preset" not in body["message"]
    assert api.toolbox_versions()[1]["versions"] == []
    status, body = api.toolbox_post({"op": "restore", "version": 7})
    assert status == 404


@pytest.mark.parametrize("raw", ['{"schema": 1,', '{"modules": {"qr": {"order": "first"}}}'],
                         ids=["invalid-json", "order-as-text"])
def test_a_broken_toolbox_file_keeps_every_route_up(api, raw):
    s = api.store()
    s.root.mkdir(parents=True, exist_ok=True)
    (s.root / "toolbox.json").write_text(raw)
    status, view = api.toolbox_get()
    assert status == 200 and view["file_error"]["using"] == "defaults" and view["file_error"]["reason"]
    assert api.pad_get()[0] == 200 and api.timer_get()[0] == 200 and api.tips_get()[0] == 200
    assert (s.root / "toolbox.json").read_text() == raw
    status, body = api.toolbox_post({"op": "restore", "version": 1})
    assert status == 404 and body["error"] == "unknown_version"
    status, body = api.toolbox_post({"op": "switch", "module": "qr", "on": False})
    assert status == 200 and "file_error" not in body
    status, body = api.toolbox_post({"op": "restore", "version": 1})
    assert status == 200 and "file_error" not in body
