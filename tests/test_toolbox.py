"""The toolbox file: validation, presets, switches, preview + apply by id, versions and restore,
require_on, and the agent tool's refusal of a switched-off tool in a running session."""
import json

import pytest

from esb_fakes import FakeCtx, load_plugin, make_store, sub


@pytest.fixture
def tb():
    return sub("toolbox")


def test_first_run_is_everything_on(tmp_path, tb):
    s = make_store(tmp_path)
    doc = tb.load(s)
    assert doc["first_run"] is True and doc["preset"] == "everything"
    assert all(row["on"] for row in doc["modules"].values())
    assert len(doc["modules"]) == 14


def test_validate_rejects_unknown_keys_and_tools(tb):
    _, errors = tb.validate({"modules": {"nope": {"on": True}}, "colour": 1})
    assert any("unknown tool 'nope'" in e for e in errors)
    assert any("unknown key 'colour'" in e for e in errors)
    _, errors = tb.validate({"modules": {"qr": {"on": "yes"}}})
    assert any("modules.qr.on" in e for e in errors)
    _, errors = tb.validate({"pomodoro": {"work": 0}})
    assert any("pomodoro.work" in e for e in errors)
    clean, errors = tb.validate({"modules": {"qr": {"on": False}}})
    assert errors == [] and clean["modules"]["qr"]["on"] is False and clean["modules"]["pad"]["on"] is True


def test_switch_keeps_a_version_with_author(tmp_path, tb):
    s = make_store(tmp_path)
    out = tb.set_switch(s, "regex", False, "agent")
    assert out["version"] == 1 and out["summary"] == "Regex tester off"
    assert tb.is_on(s, "regex") is False and tb.load(s)["preset"] == "custom"
    tb.set_switch(s, "regex", True, "user")
    vs = tb.versions(s)
    assert [v["n"] for v in vs] == [2, 1]
    assert vs[0]["author"] == "user" and vs[0]["current"] and vs[1]["author"] == "agent"


def test_preset_and_restore(tmp_path, tb):
    s = make_store(tmp_path)
    tb.apply_preset(s, "focus", "user")
    on = {k for k, v in tb.load(s)["modules"].items() if v["on"]}
    assert on == {"pad", "pomodoro", "timelog", "calc"}
    tb.apply_preset(s, "developer", "user")
    out = tb.restore(s, 1, "user")
    assert out["summary"] == "Restored v1" and out["version"] == 3
    assert {k for k, v in tb.load(s)["modules"].items() if v["on"]} == on
    with pytest.raises(tb.ToolboxError) as exc:
        tb.restore(s, 99, "user")
    assert exc.value.code == "unknown_version"


def test_versions_keep_the_last_20(tmp_path, tb):
    s = make_store(tmp_path)
    for i in range(23):
        tb.set_switch(s, "qr", i % 2 == 0, "user")
    nums = [v["n"] for v in tb.versions(s)]
    assert len(nums) == 20 and nums[0] == 23 and nums[-1] == 4


def test_preview_then_apply_by_id_and_stale_preview(tmp_path, tb):
    s = make_store(tmp_path)
    p = tb.preview(s, {"modules": {"qr": {"on": False}}, "pomodoro": {"rhythm": "50/10", "work": 50, "short": 10}},
                   "agent")
    assert "QR code off" in p["changes"] and any("pomodoro.work" in c for c in p["changes"])
    assert tb.is_on(s, "qr")  # nothing saved by a preview
    out = tb.apply(s, p["preview_id"], "agent")
    assert out["version"] == 1 and not tb.is_on(s, "qr")
    p2 = tb.preview(s, {"modules": {"qr": {"on": True}}}, "agent")
    tb.set_switch(s, "diff", False, "user")  # the file changes under the preview
    with pytest.raises(tb.ToolboxError) as exc:
        tb.apply(s, p2["preview_id"], "agent")
    assert exc.value.code in ("stale_preview", "unknown_preview")


def test_preview_refuses_invalid_changes(tmp_path, tb):
    s = make_store(tmp_path)
    with pytest.raises(tb.ToolboxError) as exc:
        tb.preview(s, {"layout": {"chip": "sideways"}}, "agent")
    assert exc.value.code == "invalid" and "layout.chip" in str(exc.value)


def test_require_on(tmp_path, tb):
    s = make_store(tmp_path)
    tb.require_on(s, "colour")
    tb.require_on(s, None)
    tb.set_switch(s, "colour", False, "user")
    with pytest.raises(tb.SwitchedOff) as exc:
        tb.require_on(s, "colour")
    assert exc.value.code == "switched_off" and "Colour picker" in str(exc.value)


def test_agent_tool_switch_off_then_refused_in_the_same_session(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    out = ctx.call("eselsbruecke_toolbox", action="set_switch", tool="qr", on=False)
    assert out["ok"] and out["summary"] == "QR code off"
    listed = ctx.call("eselsbruecke_toolbox", action="list")
    assert {t["id"]: t["on"] for t in listed["tools"]}["qr"] is False
    bad = ctx.call("eselsbruecke_toolbox", action="explode")
    assert bad["ok"] is False and bad["error"] == "unknown_action"


def test_after_save_hooks_run_and_never_undo_a_save(tmp_path, tb):
    s = make_store(tmp_path)
    seen = []

    def hook(store, old, new):
        seen.append((old["alerts"]["while_closed"], new["alerts"]["while_closed"]))
        raise RuntimeError("hook failure is contained")

    tb.AFTER_SAVE.append(hook)
    try:
        p = tb.preview(s, {"alerts": {"while_closed": True}}, "user")
        tb.apply(s, p["preview_id"], "user")
    finally:
        tb.AFTER_SAVE.remove(hook)
    assert seen == [(False, True)] and tb.load(s)["alerts"]["while_closed"] is True
    assert json.loads((s.root / "toolbox.json").read_text())["alerts"]["while_closed"] is True


# --- a hand-edited toolbox.json that is broken ----------------------------------------------------

@pytest.mark.parametrize("doc", [
    {"layout": "flat"}, {"pomodoro": [25, 5]}, {"alerts": None}, {"preset": ["focus"]},
    {"layout": {"dock": ["qr"]}}, {"modules": {"qr": {"order": "first"}}}, {"tips": [{"title": ["x"]}]},
], ids=["layout-str", "pomodoro-list", "alerts-null", "preset-list", "dock-list", "order-str", "tip-title-list"])
def test_validate_reports_wrong_shapes_instead_of_raising(tb, doc):
    clean, errors = tb.validate(doc)
    assert errors and isinstance(clean["layout"], dict) and isinstance(clean["pomodoro"], dict)


def _break(s, text):
    s.root.mkdir(parents=True, exist_ok=True)
    (s.root / "toolbox.json").write_text(text)


def test_invalid_json_falls_back_to_the_newest_valid_version_and_keeps_the_file(tmp_path, tb):
    s = make_store(tmp_path)
    tb.set_switch(s, "qr", False, "user")
    tb.set_switch(s, "diff", False, "user")
    _break(s, '{"schema": 1,')
    doc, problem = tb.load_state(s)
    assert doc["modules"]["qr"]["on"] is False and doc["modules"]["diff"]["on"] is False
    assert problem["using"] == "version 2" and "not valid JSON" in problem["reason"]
    assert problem["file"].endswith("toolbox.json")
    assert tb.is_on(s, "pad") and not tb.is_on(s, "qr")
    view = tb.view(s)
    assert view["file_error"]["using"] == "version 2"
    assert (s.root / "toolbox.json").read_text() == '{"schema": 1,'  # reads never overwrite it


def test_an_invalid_version_is_skipped_and_without_any_the_defaults_apply(tmp_path, tb):
    s = make_store(tmp_path)
    tb.set_switch(s, "qr", False, "user")
    (s.root / "toolbox.versions" / "1.json").write_text("nope")
    _break(s, json.dumps({"modules": {"qr": {"order": "first"}}}))
    doc, problem = tb.load_state(s)
    assert problem["using"] == "defaults" and "modules.qr.order" in problem["reason"]
    assert doc["first_run"] is False and doc["modules"]["qr"]["on"] is True
    assert [t["id"] for t in tb.view(s)["tools"]][0] == "pad"


@pytest.mark.parametrize("action", ["preset", "restore", "switch"])
def test_a_save_from_the_fallback_writes_a_valid_file_and_keeps_the_broken_one(tmp_path, tb, action):
    s = make_store(tmp_path)
    tb.set_switch(s, "qr", False, "user")
    _break(s, "{broken")
    if action == "preset":
        out = tb.apply_preset(s, "focus", "user")
    elif action == "restore":
        out = tb.restore(s, 1, "user")
    else:
        out = tb.set_switch(s, "diff", False, "user")
    assert out["version"] == 2
    saved = json.loads((s.root / "toolbox.json").read_text())
    assert tb.validate(saved)[1] == [] and tb.load_state(s)[1] is None
    kept = [p for p in s.root.iterdir() if p.name.startswith("toolbox.broken-")]
    assert len(kept) == 1 and kept[0].read_text() == "{broken" and out["kept_broken"] == kept[0].name


def test_the_agent_list_reports_the_broken_file(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    assert "file_error" not in ctx.call("eselsbruecke_toolbox", action="list")
    s = make_store(tmp_path)
    _break(s, "[1, 2")
    listed = ctx.call("eselsbruecke_toolbox", action="list")
    assert listed["ok"] and listed["file_error"]["using"] == "defaults"
    assert listed["file_error"]["file"].endswith("toolbox.json") and listed["file_error"]["reason"]
    out = ctx.call("eselsbruecke_toolbox", action="preset", preset="everything")
    assert out["ok"] and "file_error" not in ctx.call("eselsbruecke_toolbox", action="list")
