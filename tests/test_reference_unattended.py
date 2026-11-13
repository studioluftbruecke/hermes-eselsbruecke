"""`@pad:` and the unattended lane.

The reference provider is process-wide in Hermes, so it must answer only for a profile that enables
the plugin; under plugins.isolation: host it is not registered at all. Agent writes are refused in
unattended runs before anything changes; route writes (the user's clicks) work inside a plugin host
child, which always has HERMES_PLUGIN_HOST_PROCESS=1."""
import abc
import asyncio
import dataclasses
import datetime as dt
import sys
import types

import pytest

from esb_fakes import BERLIN, FakeCtx, load_plugin, make_store, set_clock, sub

PLUGIN_DIR_NAME = "eselsbruecke"


def _home(tmp_path, name, enabled):
    home = tmp_path / name
    home.mkdir()
    entries = "[eselsbruecke]" if enabled else "[]"
    (home / "config.yaml").write_text(f"plugins:\n  enabled: {entries}\n", encoding="utf-8")
    return home


@pytest.fixture
def fake_hermes(monkeypatch):
    """Just enough of agent.context_references and hermes_constants to build the real provider."""
    cr = types.ModuleType("agent.context_references")

    @dataclasses.dataclass
    class ContextCompletionItem:
        text: str
        display: str = ""
        meta: str = ""

    class ContextReferenceProvider(abc.ABC):
        prefix = ""
        description = ""

    cr.ContextCompletionItem = ContextCompletionItem
    cr.ContextReferenceProvider = ContextReferenceProvider
    agent = types.ModuleType("agent")
    agent.context_references = cr
    hc = types.ModuleType("hermes_constants")
    state = {"home": None, "loads": 0}
    hc.get_hermes_home = lambda: state["home"]
    config = types.ModuleType("hermes_cli.config")  # Hermes' public loader, for the bound profile

    def load_config_readonly():
        import yaml

        state["loads"] += 1
        return yaml.safe_load((state["home"] / "config.yaml").read_text(encoding="utf-8")) or {}

    config.load_config_readonly = load_config_readonly
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.context_references", cr)
    monkeypatch.setitem(sys.modules, "hermes_constants", hc)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config)
    return state


def test_expand_and_autocomplete_only_where_the_plugin_is_enabled(tmp_path, fake_hermes):
    set_clock(dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    with_plugin = _home(tmp_path, "with", True)
    without = _home(tmp_path, "without", False)
    store = make_store(tmp_path)
    sub("pad").add_lines(store, [{"text": "Call mom"}, {"text": "Hosting: 16,90 * 12 ="}], "user")
    ref = sub("reference")
    provider = ref.make_provider(sub("pad").__package__, lambda: store)
    assert provider.prefix == "pad"

    fake_hermes["home"] = with_plugin
    text = asyncio.run(provider.expand("today"))
    assert "Eselsbrücke pad, day 2026-11-09" in text and "- [ ] Call mom" in text and "(= 202,8)" in text
    items = asyncio.run(provider.autocomplete("to"))
    assert [i.text for i in items] == ["today"]

    fake_hermes["home"] = without
    assert asyncio.run(provider.expand("today")) is None
    assert asyncio.run(provider.autocomplete("")) == []
    assert fake_hermes["loads"] == 4  # each answer asked Hermes' config loader for the calling profile


def test_route_settings_come_from_hermes_config_loader(tmp_path, fake_hermes):
    home = tmp_path / "p"
    home.mkdir()
    (home / "config.yaml").write_text("plugins:\n  entries:\n    eselsbruecke:\n      settings:\n"
                                      "        week_starts: sunday\n", encoding="utf-8")
    fake_hermes["home"] = home
    assert sub("api")._setting("week_starts", "monday") == "sunday" and fake_hermes["loads"] == 1


def test_targets(tmp_path):
    ref = sub("reference")
    today = dt.date(2026, 11, 9)
    assert ref.resolve("yesterday", today) == ("day", "2026-11-08")
    assert ref.resolve("2026-11-01", today) == ("day", "2026-11-01")
    assert ref.resolve("queued", today) == ("queued", None)
    with pytest.raises(ValueError):
        ref.resolve("../etc", today)
    store = make_store(tmp_path)
    set_clock(dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    assert ref.expand_text(store, "nonsense", lambda: True) is None


def test_no_reference_under_host_isolation(tmp_path, monkeypatch, fake_hermes):
    ctx = FakeCtx(tmp_path / "data")
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    load_plugin().register(ctx)
    assert ctx.references == []
    monkeypatch.delenv("HERMES_PLUGIN_HOST_PROCESS")
    ctx2 = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx2)
    assert len(ctx2.references) == 1 and ctx2.references[0].prefix == "pad"


class Surface(FakeCtx):
    def __init__(self, data_dir, surface="", cron=None):
        super().__init__(data_dir)
        self._surface, self._cron = surface, cron

    def session_surface(self):
        return self._surface

    def current_cron_execution(self):
        return self._cron


@pytest.mark.parametrize("case,expect", [
    ({"surface": "desktop"}, None),
    ({"surface": "cli"}, None),
    ({"surface": "api_server"}, "api_server"),
    ({"surface": "webhook"}, "webhook"),
    ({"cron": object()}, "scheduled job"),
])
def test_unattended_reasons(tmp_path, case, expect):
    bridge = sub("hermes_bridge")
    ctx = Surface(tmp_path, **case)
    reason = bridge.unattended_reason(ctx, environ={})
    assert (reason is None) if expect is None else (expect in reason)


def test_single_query_and_unreadable_marker(tmp_path, monkeypatch):
    bridge = sub("hermes_bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: True)
    assert "single-query" in bridge.unattended_reason(Surface(tmp_path, "cli"), environ={})
    monkeypatch.setattr(bridge, "_finite_turn", lambda: None)
    for host in ({}, {"HERMES_PLUGIN_HOST_PROCESS": "1"}):
        reason = bridge.unattended_reason(Surface(tmp_path, "desktop"), environ=host)
        assert reason == ("this Hermes version does not say whether a person is present, so writes are refused; "
                          "update the plugin")


def _finite_module(monkeypatch, answer):
    """gateway.session_finite as Hermes ships it (answer True/False), raising (an exception), or gone (None)."""
    import types

    monkeypatch.undo()  # the autouse fixture replaced _finite_turn; this test reads the real one
    for name in ("HERMES_PLUGIN_HOST_PROCESS", "HERMES_CRON_SESSION", "HERMES_SINGLE_QUERY_SESSION",
                 "HERMES_SESSION_PLATFORM"):
        monkeypatch.delenv(name, raising=False)
    if answer is None:
        monkeypatch.setitem(sys.modules, "gateway.session_finite", None)  # import raises ImportError
        return
    mod = types.ModuleType("gateway.session_finite")

    def finite_turn_required():
        if isinstance(answer, Exception):
            raise answer
        return answer

    mod.finite_turn_required = finite_turn_required
    monkeypatch.setitem(sys.modules, "gateway.session_finite", mod)


@pytest.mark.parametrize("answer,unattended", [(False, False), (True, True), (None, True),
                                               (RuntimeError("moved"), True)],
                         ids=["marker-false", "marker-true", "module-missing", "marker-raises"])
def test_the_one_shot_marker_import_fails_closed(tmp_path, monkeypatch, answer, unattended):
    bridge = sub("hermes_bridge")
    _finite_module(monkeypatch, answer)
    reason = bridge.unattended_reason(Surface(tmp_path, "desktop"), environ={})
    assert (reason is not None) is unattended, reason
    if answer is None or isinstance(answer, Exception):
        assert "does not say whether a person is present" in reason


@pytest.mark.parametrize("environ,surface,expect", [
    ({"HERMES_SINGLE_QUERY_SESSION": "1"}, "desktop", "single-query"),
    ({"HERMES_CRON_SESSION": "1"}, "desktop", "scheduled job"),
    ({}, "msgraph_webhook", "msgraph_webhook"),
    ({"HERMES_SESSION_PLATFORM": "api_server"}, "", "api_server"),
    ({}, "telegram", None),
])
def test_unattended_signals_from_the_environment(tmp_path, monkeypatch, environ, surface, expect):
    bridge = sub("hermes_bridge")
    _finite_module(monkeypatch, False)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    reason = bridge.unattended_reason(Surface(tmp_path, surface), environ=environ)
    assert (reason is None) if expect is None else (expect in reason), reason


@pytest.mark.parametrize("surface,refused", [("", True), ("cli", True), ("oneshot", True), ("desktop", False),
                                             ("tui", False)])
def test_host_process_fails_closed_on_blind_surfaces(tmp_path, monkeypatch, surface, refused):
    bridge = sub("hermes_bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: False)  # the host child reads the host's marker, not the turn's
    reason = bridge.unattended_reason(Surface(tmp_path, surface), environ={"HERMES_PLUGIN_HOST_PROCESS": "1"})
    assert (reason is not None and "isolation" in reason) if refused else reason is None


def test_agent_writes_refused_unattended_reads_answer(tmp_path, monkeypatch):
    bridge = sub("hermes_bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: True)
    ctx = Surface(tmp_path / "data", "cli")
    load_plugin().register(ctx)
    out = ctx.call("eselsbruecke_pad", action="add", lines=[{"text": "x"}])
    assert out["ok"] is False and out["error"] == "unattended" and "Nothing was changed" in out["message"]
    assert not (tmp_path / "data" / "pad").exists()
    assert ctx.call("eselsbruecke_toolbox", action="set_switch", tool="qr", on=False)["error"] == "unattended"
    assert ctx.call("eselsbruecke_toolbox", action="list")["ok"] is True
    assert ctx.call("eselsbruecke_calc", expr="2+2")["result"] == "4"
    ctx.settings["unattended_pad_writes"] = True
    assert ctx.call("eselsbruecke_pad", action="add", lines=[{"text": "from my automation"}])["ok"] is True
    assert ctx.call("eselsbruecke_pad", action="undo")["ok"] is False  # undo stays refused unattended


TOOLBOX_WRITES = [
    ("set_switch", {"tool": "qr", "on": False}),
    ("set_clock", {"place": "Lisbon"}),
    ("set_clock", {"place": "Tokyo", "remove": True}),
    ("set_pin", {"tool": "regex", "on": True}),
    ("set_pin", {"tool": "pad", "on": False}),
    ("restore", {"version": 1}),
]


@pytest.mark.parametrize("action,args", TOOLBOX_WRITES, ids=[f"{a} {' '.join(map(str, kw.values()))}"
                                                             for a, kw in TOOLBOX_WRITES])
def test_agent_toolbox_writes_are_refused_unattended_and_change_nothing(tmp_path, monkeypatch, action, args):
    store = sub("store").Store(tmp_path / "data")
    sub("toolbox").set_switch(store, "diff", False, "user")  # version 1, so restore has something to restore
    before = (store.root / "toolbox.json").read_text(encoding="utf-8")
    bridge = sub("hermes_bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: True)
    ctx = Surface(tmp_path / "data", "cli")
    load_plugin().register(ctx)
    out = ctx.call("eselsbruecke_toolbox", action=action, **args)
    assert out["ok"] is False and out["error"] == "unattended" and "Nothing was changed" in out["message"]
    assert (store.root / "toolbox.json").read_text(encoding="utf-8") == before
    assert [v["n"] for v in sub("toolbox").versions(store)] == [1]
    listed = ctx.call("eselsbruecke_toolbox", action="list")
    assert listed["ok"] is True and len(listed["clocks"]) == 3 and "regex" not in listed["dashboard"]
    assert ctx.call("eselsbruecke_toolbox", action="versions")["ok"] is True
    assert ctx.call("eselsbruecke_toolbox", action="preview", changes={"dashboard": ["pad"]})["ok"] is True


@pytest.mark.parametrize("action,args", TOOLBOX_WRITES[1:5], ids=["add-place", "remove-place", "pin", "unpin"])
def test_agent_toolbox_writes_are_allowed_with_a_person_at_the_keyboard(tmp_path, action, args):
    ctx = Surface(tmp_path / "data", "desktop")
    load_plugin().register(ctx)
    out = ctx.call("eselsbruecke_toolbox", action=action, **args)
    assert out["ok"] is True and out["version"] == 1
    assert sub("toolbox").versions(sub("store").Store(tmp_path / "data"))[0]["author"] == "agent"


def test_route_write_works_inside_a_host_child(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    api = sub("api")
    store = make_store(tmp_path)
    api.set_store_factory(lambda: store)
    set_clock(dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    try:
        status, body = api.pad_lines({"op": "add", "text": "clicked in Desktop"})
        assert status == 200 and body["day"]["lines"][0]["text"] == "clicked in Desktop"
        assert api.toolbox_post({"op": "switch", "module": "qr", "on": False})[0] == 200
    finally:
        api.set_store_factory(None)
