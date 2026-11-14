"""The registry: every action maps to exactly one module, schema enums equal handler actions, and a
tool with several modules stays visible while one of them is on."""
import importlib

import pytest

from esb_fakes import FakeCtx, load_plugin, sub, PKG


def test_fourteen_modules_nine_tools():
    reg = sub("registry")
    assert len(reg.MODULES) == 14 and len(reg.TOOLS) == 9
    assert len(set(reg.MODULE_IDS)) == 14
    for m in reg.MODULES:
        assert m["network"] == "none" and m["group"] in reg.GROUPS
        assert m["agent_tool"] is None or m["agent_tool"] in reg.TOOLS


def test_the_rows_say_how_a_tool_sits_on_the_dashboard():
    reg = sub("registry")
    kinds = {m["id"]: m["dashboard"] for m in reg.MODULES}
    assert {k for k, v in kinds.items() if v == "widget"} == {"pad", "pomodoro", "timelog", "timezones", "generate",
                                                              "colour"}
    assert {k for k, v in kinds.items() if v == "tile"} == {"formatter", "diff", "regex", "tokens", "cron", "encode",
                                                            "qr"}
    assert kinds["calc"] is None
    assert all("dashboard" in row for row in reg.public_modules())


def test_the_world_clock_keeps_its_id_and_the_daily_group_replaces_focus():
    reg = sub("registry")
    assert "focus" not in reg.GROUPS and reg.GROUPS[0] == "daily"
    assert {m["id"] for m in reg.MODULES if m["group"] == "daily"} == {"pad", "pomodoro", "timelog", "timezones"}
    row = reg.MODULE_BY_ID["timezones"]
    assert row["title"] == "World clock" and row["blurb"] == "The time in your places, and Unix timestamps."
    assert reg.module_of("eselsbruecke_convert", "time") == "timezones"


def test_the_toolbox_tool_has_no_preset_and_guards_its_writes():
    spec = sub("registry").TOOLS["eselsbruecke_toolbox"]
    assert list(spec["actions"]) == ["list", "set_switch", "set_clock", "set_pin", "preview", "apply", "versions",
                                     "restore"]
    assert set(spec["actions"]) - spec["writes"] == {"list", "versions"}


def test_every_action_maps_to_one_known_module():
    reg = sub("registry")
    for tool, spec in reg.TOOLS.items():
        assert spec["writes"] <= set(spec["actions"]), tool
        for action, module in spec["actions"].items():
            assert module is None or module in reg.MODULE_BY_ID, (tool, action)
    # Every module with an agent tool is reachable through one of that tool's actions.
    for m in reg.MODULES:
        if m["agent_tool"]:
            assert m["id"] in reg.tool_modules(m["agent_tool"]), m["id"]


@pytest.mark.parametrize("tool", sorted(load_plugin().REGISTERED))
def test_schema_enum_equals_handler_actions(tool):
    reg = sub("registry")
    schema = importlib.import_module(f"{PKG}.tools.{reg.TOOLS[tool]['module']}").SCHEMA
    assert schema["name"] == tool
    enum = schema["parameters"]["properties"]["action"]["enum"]
    assert sorted(enum) == sorted(reg.TOOLS[tool]["actions"])


def test_tool_visible_rule():
    reg = sub("registry")
    on = {"timezones": False, "encode": False, "colour": True, "cron": False}
    assert reg.tool_visible("eselsbruecke_convert", lambda m: on[m]) is True
    on["colour"] = False
    assert reg.tool_visible("eselsbruecke_convert", lambda m: on[m]) is False
    assert reg.tool_visible("eselsbruecke_toolbox", lambda m: False) is True


def test_check_fn_hides_a_tool_whose_modules_are_all_off(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    assert ctx.visible("eselsbruecke_toolbox") is True
    tb, store = sub("toolbox"), sub("store").Store(tmp_path / "data")
    for m in sub("registry").MODULE_IDS:
        tb.set_switch(store, m, False, "user")
    assert ctx.visible("eselsbruecke_toolbox") is True  # the toolbox itself never hides
