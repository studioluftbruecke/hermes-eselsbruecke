"""The toolbox file: validation, switches, the dashboard's pins, the world clock's places, preview +
apply by id, the sentences a save is described with, versions and restore, require_on, and the agent
tool's refusal of a switched-off tool in a running session."""
import json

import pytest

from esb_fakes import FakeCtx, load_plugin, make_store, sub


@pytest.fixture
def tb():
    return sub("toolbox")


def test_first_run_is_everything_on_with_a_dashboard_and_three_clocks(tmp_path, tb):
    s = make_store(tmp_path)
    doc = tb.load(s)
    assert doc["schema"] == 2 and doc["first_run"] is True and "preset" not in doc
    assert all(row["on"] for row in doc["modules"].values())
    assert len(doc["modules"]) == 14
    assert doc["dashboard"] == ["timezones", "pad", "pomodoro", "timelog", "generate", "colour", "formatter",
                                "diff", "encode"]
    assert doc["clocks"] == [{"zone": "UTC", "label": "UTC"}, {"zone": "America/New_York", "label": "New York"},
                             {"zone": "Asia/Tokyo", "label": "Tokyo"}]
    assert doc["layout"] == {"chip": "auto", "chip_visible": True}
    assert tb.validate(doc)[1] == []


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
    assert tb.is_on(s, "regex") is False and tb.load(s)["first_run"] is False
    tb.set_switch(s, "regex", True, "user")
    vs = tb.versions(s)
    assert [v["n"] for v in vs] == [2, 1]
    assert vs[0]["author"] == "user" and vs[0]["current"] and vs[1]["author"] == "agent"


def test_restore_brings_back_switches_pins_and_places(tmp_path, tb):
    s = make_store(tmp_path)
    tb.set_switch(s, "qr", False, "user")
    tb.set_clock(s, "Mumbai", "user")
    tb.set_pin(s, "regex", True, "user")
    before = tb.load(s)
    tb.set_switch(s, "qr", True, "user")
    tb.set_clock(s, "Mumbai", "user", remove=True)
    tb.set_pin(s, "regex", False, "user")
    out = tb.restore(s, 3, "user")
    assert out["summary"] == "Restored v3" and out["version"] == 7
    assert tb.load(s) == before
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
    assert p["changes"] == ["QR code off", "Pomodoro: 50/10"]
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
    {"layout": "flat"}, {"pomodoro": [25, 5]}, {"alerts": None}, {"dashboard": {"pad": True}},
    {"clocks": "Tokyo"}, {"clocks": [["Asia/Tokyo", "Tokyo"]]}, {"modules": {"qr": {"order": "first"}}},
    {"tips": [{"title": ["x"]}]},
], ids=["layout-str", "pomodoro-list", "alerts-null", "dashboard-object", "clocks-str", "clock-row-list", "order-str",
        "tip-title-list"])
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


@pytest.mark.parametrize("action", ["clock", "pin", "restore", "switch"])
def test_a_save_from_the_fallback_writes_a_valid_file_and_keeps_the_broken_one(tmp_path, tb, action):
    s = make_store(tmp_path)
    tb.set_switch(s, "qr", False, "user")
    _break(s, "{broken")
    if action == "clock":
        out = tb.set_clock(s, "Lisbon", "user")
    elif action == "pin":
        out = tb.set_pin(s, "qr", True, "user")
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
    out = ctx.call("eselsbruecke_toolbox", action="set_switch", tool="qr", on=False)
    assert out["ok"] and "file_error" not in ctx.call("eselsbruecke_toolbox", action="list")


# --- the dashboard, the world clock and the status bar in the file --------------------------------

BAD_DASHBOARDS = [
    ("not-a-list", "pad"),
    ("listed-twice", ["pad", "timelog", "pad"]),
    ("calculator", ["pad", "calc"]),
    ("unknown-tool", ["pad", "nope"]),
    ("not-text", ["pad", 3]),
    ("more-than-20", ["pad"] * 21),
]


@pytest.mark.parametrize("name,dashboard", BAD_DASHBOARDS, ids=[c[0] for c in BAD_DASHBOARDS])
def test_validate_refuses_a_bad_dashboard(tb, name, dashboard):
    _, errors = tb.validate({"dashboard": dashboard})
    assert errors and all(e.startswith("dashboard") for e in errors), errors


def test_a_switched_off_tool_may_stay_on_the_dashboard_and_the_order_is_kept(tb):
    clean, errors = tb.validate({"dashboard": ["qr", "pad", "regex"], "modules": {"qr": {"on": False}}})
    assert errors == [] and clean["dashboard"] == ["qr", "pad", "regex"]
    assert tb.validate({"dashboard": []})[1] == []


def _clocks(*labels):
    return [{"zone": "Asia/Tokyo", "label": label} for label in labels]


BAD_CLOCKS = [
    ("not-a-list", {"zone": "Asia/Tokyo", "label": "Tokyo"}),
    ("a-13th", _clocks(*[f"Place {i}" for i in range(13)])),
    ("no-label", [{"zone": "Asia/Tokyo"}]),
    ("no-zone", [{"label": "Tokyo"}]),
    ("extra-key", [{"zone": "Asia/Tokyo", "label": "Tokyo", "home": True}]),
    ("row-is-text", ["Asia/Tokyo"]),
    ("unknown-zone", [{"zone": "Mars/Phobos", "label": "Phobos"}]),
    ("city-as-zone", [{"zone": "Tokyo", "label": "Tokyo"}]),
    ("zone-not-text", [{"zone": 9, "label": "Tokyo"}]),
    ("empty-label", _clocks("")),
    ("blank-label", _clocks("   ")),
    ("label-41-characters", _clocks("x" * 41)),
    ("label-not-text", _clocks(7)),
    ("same-label-twice", _clocks("Tokyo", "Tokyo")),
    ("labels-differ-only-by-case", _clocks("Office", "OFFICE")),
]


@pytest.mark.parametrize("name,clocks", BAD_CLOCKS, ids=[c[0] for c in BAD_CLOCKS])
def test_validate_refuses_bad_clocks(tb, name, clocks):
    _, errors = tb.validate({"clocks": clocks})
    assert errors and all(e.startswith("clocks") for e in errors), errors


def test_clocks_at_the_limits_are_valid_and_labels_are_trimmed(tb):
    clean, errors = tb.validate({"clocks": _clocks(*[f"Place {i}" for i in range(12)])})
    assert errors == [] and len(clean["clocks"]) == 12
    clean, errors = tb.validate({"clocks": [{"zone": "Asia/Kolkata", "label": "  Mumbai office  "},
                                            {"zone": "Asia/Kolkata", "label": "x" * 40}]})
    assert errors == [] and clean["clocks"][0] == {"zone": "Asia/Kolkata", "label": "Mumbai office"}
    assert tb.validate({"clocks": []})[1] == []


@pytest.mark.parametrize("layout,needle", [
    ({"chip": "off"}, "layout.chip"), ({"chip_visible": "no"}, "layout.chip_visible"),
    ({"rail": "groups"}, "unknown key 'rail'"), ({"dock": None}, "unknown key 'dock'"),
], ids=["chip-off", "visible-as-text", "rail", "dock"])
def test_validate_refuses_what_the_status_bar_setting_no_longer_has(tb, layout, needle):
    _, errors = tb.validate({"schema": 2, "layout": layout})
    assert any(needle in e for e in errors), errors
    assert any("unknown key 'preset'" in e for e in tb.validate({"schema": 2, "preset": "focus"})[1])


# --- the world clock's places ---------------------------------------------------------------------

def test_set_clock_adds_a_city_under_its_name_and_keeps_a_version(tmp_path, tb):
    s = make_store(tmp_path)
    out = tb.set_clock(s, "mumbai", "agent")
    assert out["version"] == 1 and out["summary"] == "Mumbai added to the world clock"
    doc = tb.load(s)
    assert doc["clocks"][-1] == {"zone": "Asia/Kolkata", "label": "Mumbai"} and len(doc["clocks"]) == 4
    assert doc["first_run"] is False
    assert tb.versions(s)[0]["author"] == "agent" and tb.versions(s)[0]["summary"] == out["summary"]


def test_set_clock_takes_a_zone_name_and_an_own_label(tmp_path, tb):
    s = make_store(tmp_path)
    tb.set_clock(s, "Europe/Berlin", "user")
    out = tb.set_clock(s, "Europe/Berlin", "user", label="  Office ")
    assert out["summary"] == "Office added to the world clock"
    assert tb.load(s)["clocks"][-2:] == [{"zone": "Europe/Berlin", "label": "Berlin"},
                                         {"zone": "Europe/Berlin", "label": "Office"}]


def test_adding_a_label_that_is_there_changes_nothing_and_says_so(tmp_path, tb):
    s = make_store(tmp_path)
    tb.set_clock(s, "Tokyo", "user", label="Office")
    for place, label in (("TOKYO", None), ("Lisbon", "office")):
        out = tb.set_clock(s, place, "user", label=label)
        assert out["unchanged"] is True and "already on the world clock" in out["summary"]
    assert [v["n"] for v in tb.versions(s)] == [1] and len(tb.load(s)["clocks"]) == 4


def test_set_clock_removes_by_label_by_city_and_by_zone(tmp_path, tb):
    s = make_store(tmp_path)
    tb.set_clock(s, "Europe/Berlin", "user", label="Office")
    assert tb.set_clock(s, "office", "user", remove=True)["summary"] == "Office removed from the world clock"
    assert tb.set_clock(s, "new york", "user", remove=True)["summary"] == "New York removed from the world clock"
    tb.set_clock(s, "Mumbai", "user", label="Priya")
    assert tb.set_clock(s, "Asia/Kolkata", "user", remove=True)["summary"] == "Priya removed from the world clock"
    assert [c["label"] for c in tb.load(s)["clocks"]] == ["UTC", "Tokyo"]


def test_removing_a_place_that_is_not_there_changes_nothing_and_says_so(tmp_path, tb):
    s = make_store(tmp_path)
    for place in ("Lisbon", "Nowhere"):
        out = tb.set_clock(s, place, "user", remove=True)
        assert out["unchanged"] is True and out["summary"] == f"{place} is not on the world clock"
    # Boston shares New York's zone; a city name never removes another city's row
    assert tb.set_clock(s, "Boston", "user", remove=True)["unchanged"] is True
    assert tb.versions(s) == [] and len(tb.load(s)["clocks"]) == 3


def test_set_clock_refuses_what_is_no_place_and_a_13th(tmp_path, tb):
    s = make_store(tmp_path)
    for place in ("Nowhere", "Mars/Phobos", "Tok"):
        with pytest.raises(tb.ToolboxError) as exc:
            tb.set_clock(s, place, "user")
        assert exc.value.code == "unknown_place" and "Tokyo" in str(exc.value)
    for bad in ("", "   ", None, 5):
        with pytest.raises(tb.ToolboxError) as exc:
            tb.set_clock(s, bad, "user")
        assert exc.value.code == "invalid"
    with pytest.raises(tb.ToolboxError) as exc:
        tb.set_clock(s, "Tokyo", "user", label="x" * 41)
    assert exc.value.code == "invalid"
    assert tb.versions(s) == []
    for i in range(9):
        tb.set_clock(s, "Europe/Berlin", "user", label=f"Desk {i}")
    assert len(tb.load(s)["clocks"]) == 12
    with pytest.raises(tb.ToolboxError) as exc:
        tb.set_clock(s, "Lisbon", "user")
    assert exc.value.code == "full" and "12" in str(exc.value)
    assert len(tb.load(s)["clocks"]) == 12


# --- the dashboard's pins -------------------------------------------------------------------------

def test_set_pin_adds_at_the_end_and_removes(tmp_path, tb):
    s = make_store(tmp_path)
    out = tb.set_pin(s, "regex", True, "agent")
    assert out["version"] == 1 and out["summary"] == "Regex tester added to the dashboard"
    assert tb.load(s)["dashboard"][-1] == "regex" and tb.load(s)["first_run"] is False
    out = tb.set_pin(s, "pad", False, "user")
    assert out["summary"] == "Today's pad removed from the dashboard"
    assert tb.load(s)["dashboard"] == ["timezones", "pomodoro", "timelog", "generate", "colour", "formatter", "diff",
                                       "encode", "regex"]


def test_pinning_what_is_pinned_changes_nothing_and_says_so(tmp_path, tb):
    s = make_store(tmp_path)
    out = tb.set_pin(s, "pad", True, "user")
    assert out["unchanged"] is True and out["summary"] == "Today's pad is already on the dashboard"
    out = tb.set_pin(s, "qr", False, "user")
    assert out["unchanged"] is True and out["summary"] == "QR code is not on the dashboard"
    assert tb.versions(s) == []


def test_set_pin_refuses_the_calculator_an_unknown_tool_and_a_guess(tmp_path, tb):
    s = make_store(tmp_path)
    for tool, on, code, says in (("calc", True, "invalid", "Calculator has no place on the dashboard"),
                                 ("nope", True, "unknown_tool", "Unknown tool 'nope'"),
                                 ("qr", "yes", "invalid", "on must be true or false")):
        with pytest.raises(tb.ToolboxError) as exc:
            tb.set_pin(s, tool, on, "user")
        assert exc.value.code == code and says in str(exc.value)
    assert tb.versions(s) == []


def test_the_agent_adds_a_place_and_pins_a_tool(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    out = ctx.call("eselsbruecke_toolbox", action="set_clock", place="San Francisco")
    assert out["ok"] and out["summary"] == "San Francisco added to the world clock" and out["version"] == 1
    assert out["clocks"][-1] == {"zone": "America/Los_Angeles", "label": "San Francisco"}
    again = ctx.call("eselsbruecke_toolbox", action="set_clock", place="San Francisco")
    assert again["ok"] and again["unchanged"] is True and "version" not in again
    gone = ctx.call("eselsbruecke_toolbox", action="set_clock", place="San Francisco", remove=True)
    assert gone["ok"] and len(gone["clocks"]) == 3
    bad = ctx.call("eselsbruecke_toolbox", action="set_clock", place="Atlantis")
    assert bad["ok"] is False and bad["error"] == "unknown_place"
    guess = ctx.call("eselsbruecke_toolbox", action="set_clock", place="Tokyo", remove="yes")
    assert guess["ok"] is False and guess["error"] == "invalid"

    ctx.call("eselsbruecke_toolbox", action="set_switch", tool="qr", on=False)
    pinned = ctx.call("eselsbruecke_toolbox", action="set_pin", tool="qr", on=True)
    assert pinned["ok"] and pinned["dashboard"][-1] == "qr" and "switched off" in pinned["note"]
    listed = ctx.call("eselsbruecke_toolbox", action="list")
    assert listed["dashboard"][-1] == "qr" and [c["label"] for c in listed["clocks"]] == ["UTC", "New York", "Tokyo"]
    assert listed["status_bar"] == {"visible": True, "shows": "auto"}
    assert "preset" not in listed and "presets" not in listed
    assert ctx.call("eselsbruecke_toolbox", action="preset", preset="focus")["error"] == "unknown_action"


# --- a save in words, as the settings page's history shows it -------------------------------------

def _words(tb, s, changes):
    out = tb.preview(s, changes, "user")
    tb.apply(s, out["preview_id"], "user")
    return out["changes"]


def test_a_save_is_described_in_sentences_never_in_keys(tmp_path, tb):
    s = make_store(tmp_path)
    tb.set_switch(s, "qr", False, "user")  # first run done, so each change below stands alone
    seen = []

    def words(changes):
        lines = _words(tb, s, changes)
        seen.extend(lines)
        return lines

    assert words({"layout": {"chip_visible": False}}) == ["Status bar: hidden"]
    assert words({"layout": {"chip_visible": True}}) == ["Status bar: shown"]
    assert words({"layout": {"chip": "pomodoro"}}) == ["Status bar shows: Pomodoro"]
    assert words({"layout": {"chip": "timelog"}}) == ["Status bar shows: Time log"]
    assert words({"layout": {"chip": "auto"}}) == ["Status bar shows: What is running"]
    assert words({"alerts": {"while_closed": True}}) == ["Alerts while Desktop is closed: on"]
    assert words({"alerts": {"while_closed": False}}) == ["Alerts while Desktop is closed: off"]
    assert words({"pomodoro": {"rhythm": "50/10", "work": 50, "short": 10}}) == ["Pomodoro: 50/10"]
    assert words({"pomodoro": {"rhythm": "custom", "work": 30, "short": 5}}) == [
        "Pomodoro: work 30, short 5, long 15, 4 cycles"]
    assert words({"pomodoro": {"rhythm": "25/5", "work": 25, "short": 5}}) == ["Pomodoro: 25/5"]
    assert words({"pomodoro": {"long": 20, "cycles": 1}}) == ["Pomodoro: work 25, short 5, long 20, 1 cycle"]
    assert words({"dashboard": ["pad", "timezones", "regex"]}) == [
        "Regex tester added to the dashboard", "Pomodoro removed from the dashboard",
        "Time log removed from the dashboard", "UUID, password removed from the dashboard",
        "Colour picker removed from the dashboard", "Formatter removed from the dashboard",
        "Text diff removed from the dashboard", "Encode, decode removed from the dashboard", "Dashboard reordered"]
    assert words({"dashboard": ["regex", "pad", "timezones"]}) == ["Dashboard reordered"]
    tokyo, utc = {"zone": "Asia/Tokyo", "label": "Tokyo"}, {"zone": "UTC", "label": "UTC"}
    assert words({"clocks": [tokyo, utc, {"zone": "Europe/Lisbon", "label": "Lisbon"}]}) == [
        "Lisbon added to the world clock", "New York removed from the world clock", "World clock reordered"]
    assert words({"clocks": [utc, tokyo]}) == ["Lisbon removed from the world clock", "World clock reordered"]
    assert words({"clocks": [utc, {"zone": "Asia/Tokyo", "label": "Yuki"}]}) == ["Tokyo renamed to Yuki on the world clock"]
    assert words({"tips": [{"title": "Stand up"}]}) == ["Tip added: Stand up"]
    for raw in ("layout", "chip", "while_closed", "clocks", "rhythm", "timezones", "->", "True", "False"):
        assert not any(raw in line for line in seen), (raw, seen)


def test_the_first_save_that_changes_nothing_else_is_first_run_done(tmp_path, tb):
    s = make_store(tmp_path)
    doc = tb.load(s)
    doc["first_run"] = False
    assert tb.save(s, doc, "user")["summary"] == "First run done"
    assert tb.save(s, doc, "user")["summary"] == "No change"
