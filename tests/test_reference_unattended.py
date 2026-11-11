"""`@pad:` (constraint 12, Q2) and the unattended lane (design rule 2, constraint 11).

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
    state = {"home": None}
    hc.get_hermes_home = lambda: state["home"]
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.context_references", cr)
    monkeypatch.setitem(sys.modules, "hermes_constants", hc)
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
    assert "moved its one-shot marker" in bridge.unattended_reason(Surface(tmp_path, "desktop"), environ={})


@pytest.mark.parametrize("surface,refused", [("", True), ("cli", True), ("oneshot", True), ("desktop", False),
                                             ("tui", False)])
def test_host_process_fails_closed_on_blind_surfaces(tmp_path, monkeypatch, surface, refused):
    bridge = sub("hermes_bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: None)  # the host child cannot see the marker
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
