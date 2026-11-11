"""The route logic (api.py) for the toolbox: health, view, switch, save with a stale base, restore."""
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
    assert status == 200 and len(view["tools"]) == 14 and len(view["presets"]) == 4
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


def test_bad_requests(api):
    assert api.toolbox_post(None)[0] == 400
    assert api.toolbox_post({"op": "nope"})[0] == 400
    status, body = api.toolbox_post({"op": "preset", "preset": "gamer"})
    assert status == 400 and body["error"] == "unknown_preset"
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
    status, body = api.toolbox_post({"op": "preset", "preset": "everything"})
    assert status == 200 and "file_error" not in body
    status, body = api.toolbox_post({"op": "restore", "version": 1})
    assert status == 200 and "file_error" not in body
