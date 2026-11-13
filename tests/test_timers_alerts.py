"""Timers (phase math across pauses and plans, ops applied once, replayed click times), the alert tick
(presence, switch, ledger, corrupt input through the real script), the job reconcile, break tips."""
import datetime as dt
import json
import os
import subprocess
import sys

import pytest

from esb_fakes import BERLIN, FakeCtx, ROOT, home_store, load_plugin, make_store, set_clock, sub

T0 = dt.datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN)


def at(minutes: float) -> dt.datetime:
    return T0 + dt.timedelta(minutes=minutes)


@pytest.fixture
def tm():
    return sub("timers")


def _timer(tm, plan=None, paused=None):
    return {"id": "t1", "kind": "pomodoro", "plan": plan or tm.pomodoro_plan(), "started": tm.iso(T0),
            "paused": paused or []}


def test_pomodoro_moves_to_the_break_without_a_click(tm):
    t = _timer(tm)
    s = tm.phase_at(t, at(26))
    assert (s["phase"], s["remaining_min"], s["index"]) == ("short", 4, 1)  # "Break 4 min" at 10:26
    assert tm.phase_at(t, at(24.5))["phase"] == "work"
    assert tm.phase_at(t, at(3 * 30 + 25 + 1))["phase"] == "long"
    assert tm.phase_at(t, at(200))["done"] is True
    assert [s["phase"] for s in t["plan"]] == ["work", "short"] * 3 + ["work", "long"]


def test_pauses_shift_phases_and_freeze_the_clock(tm):
    t = _timer(tm, paused=[[tm.iso(at(10)), tm.iso(at(15))]])
    assert tm.phase_at(t, at(26))["phase"] == "work"
    assert tm.phase_at(t, at(31))["phase"] == "short"
    assert tm.wall_at(t, 25 * 60) == at(30)
    open_pause = _timer(tm, paused=[[tm.iso(at(10)), None]])
    s = tm.phase_at(open_pause, at(60))
    assert s["paused"] and s["remaining_min"] == 15 and s["ends_at"] is None
    assert tm.due_events(open_pause, at(0), at(60)) == []


def test_due_events_keys_and_text(tm):
    t = _timer(tm)
    ev = tm.due_events(t, at(24), at(26))
    assert [e["key"] for e in ev] == ["t1:0"] and ev[0]["at"] == tm.iso(at(25))
    assert tm.alert_text(ev[0]) == "Eselsbrücke: Work done (25 min). Break 5 min."
    assert tm.due_events(t, at(25), at(26)) == []  # (since, now]: an event at `since` was the last tick's
    cd = {"id": "c1", "kind": "countdown", "plan": [{"phase": "countdown", "minutes": 2}], "started": tm.iso(T0),
          "paused": [], "label": "tea"}
    assert tm.alert_text(tm.due_events(cd, at(1), at(3))[0]) == "Eselsbrücke: countdown (tea) done (2 min)."


def test_ops_apply_once_and_keep_click_times(tmp_path, tm):
    s = make_store(tmp_path)
    tm.apply_op(s, {"op": "start", "op_id": "o1", "at": tm.iso(T0)}, at(0))
    again = tm.apply_op(s, {"op": "start", "op_id": "o1", "at": tm.iso(T0)}, at(1))
    assert again["applied"] is False and again["duplicate"] is True
    # an outbox pause clicked at 10:10, replayed at 10:20
    tm.apply_op(s, {"op": "pause", "op_id": "o2", "at": tm.iso(at(10))}, at(20))
    tm.apply_op(s, {"op": "pause", "op_id": "o2", "at": tm.iso(at(10))}, at(21))
    t = tm.load(s)["active"]
    assert t["paused"] == [[tm.iso(at(10)), None]]
    tm.apply_op(s, {"op": "resume", "op_id": "o3", "at": tm.iso(at(22))}, at(22))
    assert tm.phase_at(tm.load(s)["active"], at(30))["remaining_min"] == 7
    with pytest.raises(tm.TimerError) as exc:
        tm.apply_op(s, {"op": "start"}, at(31))
    assert exc.value.code == "running"
    out = tm.apply_op(s, {"op": "stop", "op_id": "o4", "result": "export fixed"}, at(40))
    assert out["ended"]["result"] == "export fixed" and tm.load(s)["active"] is None
    assert round(tm.work_seconds(out["ended"]) / 60) == 25  # 25 work + 3 of the break, pause excluded
    with pytest.raises(tm.TimerError):
        tm.apply_op(s, {"op": "start", "at": tm.iso(at(200))}, at(41))  # future click time


def test_plan_switch_mid_session_keeps_the_running_plan(tmp_path):
    svc, tb = sub("timer_service"), sub("toolbox")
    s = make_store(tmp_path)
    set_clock(T0)
    svc.run_op(s, {"op": "start"}, "user", now=T0, dispatch=lambda *a: {"jobs": []})
    p = tb.preview(s, {"pomodoro": {"rhythm": "50/10", "work": 50, "short": 10, "long": 10}}, "user")
    tb.apply(s, p["preview_id"], "user")
    st = svc.status(s, at(26))
    assert st["state"]["phase"] == "short" and st["tip"]["title"]
    svc.run_op(s, {"op": "stop"}, "user", now=at(27), dispatch=lambda *a: {"jobs": []})
    out = svc.run_op(s, {"op": "start"}, "user", now=at(28), dispatch=lambda *a: {"jobs": []})
    assert out["timer"]["plan"][0] == {"phase": "work", "minutes": 50}


def test_stop_with_result_writes_a_done_pad_line(tmp_path):
    svc, pad = sub("timer_service"), sub("pad")
    s = make_store(tmp_path)
    set_clock(T0)
    svc.run_op(s, {"op": "start"}, "user", now=T0, dispatch=lambda *a: {"jobs": []})
    out = svc.run_op(s, {"op": "stop", "result": "fixed the export"}, "user", now=at(30),
                     dispatch=lambda *a: {"jobs": []})
    line = pad.load_day(s)["lines"][0]
    assert line["text"] == "Finished: fixed the export" and line["done"] is True and out["pad_line"] == line["id"]


# --- the tick ---------------------------------------------------------------------------------------

def _tick_setup(tmp_path, tm, switch=True):
    s = home_store(tmp_path)
    s.write_json("toolbox.json", {**sub("toolbox").default_doc(first_run=False), "alerts": {"while_closed": switch}})
    tm.apply_op(s, {"op": "start", "kind": "countdown", "minutes": 2, "label": "tea"}, T0)
    return s


def test_tick_prints_once_then_silent(tmp_path, tm):
    tick = sub("alerts_tick")
    s = _tick_setup(tmp_path, tm)
    assert tick.tick(s.root, ROOT, "Europe/Berlin", now=at(1)) == []
    lines = tick.tick(s.root, ROOT, "Europe/Berlin", now=at(2.5))
    assert lines == ["Eselsbrücke: countdown (tea) done (2 min)."]
    assert tick.tick(s.root, ROOT, "Europe/Berlin", now=at(3.5)) == []
    ledger = [json.loads(x) for x in (s.root / "alerts_sent.jsonl").read_text().splitlines()]
    assert [(r["key"].split(":")[1], r["by"]) for r in ledger] == [("0", "tick")]


def test_tick_with_fresh_presence_records_but_prints_nothing(tmp_path, tm):
    tick = sub("alerts_tick")
    s = _tick_setup(tmp_path, tm)
    tick.tick(s.root, ROOT, "Europe/Berlin", now=at(1))
    s.write_json("presence.json", {"at": tm.iso(at(2))})
    assert tick.tick(s.root, ROOT, "Europe/Berlin", now=at(2.5)) == []
    assert json.loads((s.root / "alerts_sent.jsonl").read_text())["by"] == "desktop"


def test_tick_with_stale_presence_prints(tmp_path, tm):
    tick = sub("alerts_tick")
    s = _tick_setup(tmp_path, tm)
    tick.tick(s.root, ROOT, "Europe/Berlin", now=at(1))
    s.write_json("presence.json", {"at": tm.iso(at(0))})  # 150 s old at 10:02:30
    assert tick.tick(s.root, ROOT, "Europe/Berlin", now=at(2.5)) != []


def test_tick_switch_off_is_silent(tmp_path, tm):
    tick = sub("alerts_tick")
    s = _tick_setup(tmp_path, tm, switch=False)
    tick.tick(s.root, ROOT, "Europe/Berlin", now=at(1))
    assert tick.tick(s.root, ROOT, "Europe/Berlin", now=at(2.5)) == []
    assert not (s.root / "alerts_sent.jsonl").exists()


def test_tick_reminders(tmp_path, tm):
    tick, pad = sub("alerts_tick"), sub("pad")
    s = home_store(tmp_path)
    s.write_json("toolbox.json", {**sub("toolbox").default_doc(first_run=False), "alerts": {"while_closed": True}})
    set_clock(T0)
    pad.add_lines(s, [{"text": "Call mom", "kind": "reminder", "remind_at": "10:05"}], "user")
    tick.tick(s.root, ROOT, "Europe/Berlin", now=at(4))
    assert tick.tick(s.root, ROOT, "Europe/Berlin", now=at(5.5)) == ["Eselsbrücke reminder: Call mom"]
    assert tick.tick(s.root, ROOT, "Europe/Berlin", now=at(6.5)) == []


def test_tick_reminders_with_days_written_ahead(tmp_path, tm):
    """Three future day files used to push today's file out of the tick's window."""
    tick, pad = sub("alerts_tick"), sub("pad")
    s = home_store(tmp_path)
    s.write_json("toolbox.json", {**sub("toolbox").default_doc(first_run=False), "alerts": {"while_closed": True}})
    set_clock(T0)
    pad.add_lines(s, [{"text": "Call mom", "kind": "reminder", "remind_at": "10:05"}], "user")
    for date in ("2026-11-10", "2026-11-11", "2026-11-12"):
        pad.add_lines(s, [{"text": "later", "kind": "reminder", "remind_at": "10:05"}], "user", date)
    tick.tick(s.root, ROOT, "Europe/Berlin", now=at(4))
    assert tick.tick(s.root, ROOT, "Europe/Berlin", now=at(5.5)) == ["Eselsbrücke reminder: Call mom"]


def _script(tmp_path, tm):
    alerts = sub("alerts")
    s = _tick_setup(tmp_path, tm)
    path = alerts.write_script(s)
    return s, path


def test_script_runs_the_tick_and_survives_corrupt_input(tmp_path, tm):
    s, path = _script(tmp_path, tm)
    assert path == tmp_path / "home" / "scripts" / "eselsbruecke_alerts.py"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    run = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, env=env, timeout=30)
    assert run.returncode == 0 and run.stdout == ""  # first tick only sets its start
    (s.root / "timers.json").write_text("{ not json", encoding="utf-8")
    run = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, env=env, timeout=30)
    assert run.returncode == 0 and run.stdout == "" and run.stderr == ""
    errors = (s.root / "tick_errors.jsonl").read_text().splitlines()
    assert len(errors) == 1 and "JSONDecodeError" in json.loads(errors[0])["error"]


def test_script_keeps_only_the_newest_tick_errors(tmp_path, tm):
    """A persistent error appended about 1.7 KB a minute without end; the newest 20 rows stay, and the
    newest error is what the doctor and /alerts show."""
    alerts = sub("alerts")
    s, path = _script(tmp_path, tm)
    old = [json.dumps({"at": "2026-11-01T00:00:00+01:00", "error": f"old {i}", "trace": "x" * 1500}) for i in range(30)]
    (s.root / "tick_errors.jsonl").write_text("\n".join(old) + "\n" + '{"at": "trunc', encoding="utf-8")
    (s.root / "timers.json").write_text("{ not json", encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    for _ in range(2):
        run = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, env=env, timeout=30)
        assert run.returncode == 0 and run.stdout == "" and run.stderr == ""
    rows = (s.root / "tick_errors.jsonl").read_text().splitlines()
    assert len(rows) == 20 and json.loads(rows[0])["error"] == "old 13" and rows[17] == '{"at": "trunc'
    assert ["JSONDecodeError" in json.loads(r)["error"] for r in rows[-2:]] == [True, True]
    assert alerts.newest_error(s) == json.loads(rows[-1])
    assert alerts.status(s)["newest_error"] == json.loads(rows[-1])


def test_script_is_silent_when_the_plugin_folder_is_gone(tmp_path, tm):
    s, path = _script(tmp_path, tm)
    text = path.read_text().replace(repr(str(ROOT)), repr(str(tmp_path / "uninstalled")))
    path.write_text(text)
    run = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0 and run.stdout == "" and not (s.root / "tick_errors.jsonl").exists()


# --- reconcile -------------------------------------------------------------------------------------

class FakeCron:
    def __init__(self, jobs=None):
        self.jobs = list(jobs or [])
        self.calls = []

    def __call__(self, tool, args):
        assert tool == "cronjob_manage"
        self.calls.append(args)
        if args["action"] == "list":
            return {"success": True, "jobs": [dict(j) for j in self.jobs]}
        if args["action"] == "create":
            job = {"job_id": f"j{len(self.jobs) + 1}", "name": args["name"]}
            self.jobs.append(job)
            return {"success": True, "job_id": job["job_id"]}
        if args["action"] == "remove":
            self.jobs = [j for j in self.jobs if j["job_id"] != args["job_id"]]
            return {"success": True}
        raise AssertionError(args)


def test_reconcile_creates_one_job_and_removes_it_with_the_script(tmp_path):
    alerts, tb = sub("alerts"), sub("toolbox")
    s = home_store(tmp_path)
    cron = FakeCron([{"job_id": "x", "name": "someone-else"}])
    assert alerts.reconcile(s, cron)["wanted"] is False and len(cron.jobs) == 1
    p = tb.preview(s, {"alerts": {"while_closed": True}}, "user")
    tb.apply(s, p["preview_id"], "user")
    out = alerts.reconcile(s, cron)
    create = [c for c in cron.calls if c["action"] == "create"][0]
    assert out["created"] and create == {
        "action": "create", "name": "eselsbruecke-alerts", "schedule": "every 1m", "no_agent": True,
        "script": "eselsbruecke_alerts.py", "deliver": "all", "failure_deliver": "local", "catch_up": False,
        "prompt": create["prompt"]}
    assert alerts.script_path(s).exists()
    assert alerts.reconcile(s, cron)["created"] is False  # idempotent
    cron.jobs.append({"job_id": "dup", "name": "eselsbruecke-alerts"})
    assert alerts.reconcile(s, cron)["removed"] == ["dup"]
    p = tb.preview(s, {"alerts": {"while_closed": False}}, "user")
    tb.apply(s, p["preview_id"], "user")
    off = alerts.reconcile(s, cron)
    assert off["removed"] and not alerts.script_path(s).exists()
    assert [j["name"] for j in cron.jobs] == ["someone-else"]


def test_a_failed_job_list_creates_nothing(tmp_path):
    alerts = sub("alerts")
    s = home_store(tmp_path)
    s.write_json("toolbox.json", {**sub("toolbox").default_doc(first_run=False), "alerts": {"while_closed": True}})
    calls = []

    def failing(tool, args):
        calls.append(args["action"])
        return {"success": False, "error": "the scheduler is busy"} if args["action"] == "list" else {"success": True}

    with pytest.raises(RuntimeError, match="busy"):
        alerts.reconcile(s, failing)
    assert calls == ["list"]


def test_toolbox_save_runs_reconcile_through_the_turns_ctx(tmp_path):
    ctx = FakeCtx(home_store(tmp_path).root)
    load_plugin().register(ctx)
    out = ctx.call("eselsbruecke_toolbox", action="preview", changes={"alerts": {"while_closed": True}})
    ctx.call("eselsbruecke_toolbox", action="apply", preview_id=out["preview_id"])
    assert [name for name, _ in ctx.dispatched][:2] == ["cronjob_manage", "cronjob_manage"]
    assert ctx.dispatched[0][1] == {"action": "list"} and ctx.dispatched[1][1]["action"] == "create"


# --- tips -------------------------------------------------------------------------------------------

def test_break_card_contract_and_fallbacks():
    tips = sub("tips")
    card = tips.break_tip(lambda n: True, lambda n, a: {"title": "Honour thy error", "text": "as a hidden intention"})
    assert card == {"source": "unblockbruecke", "title": "Honour thy error", "text": "as a hidden intention"}
    seen = []
    tips.break_tip(lambda n: True, lambda n, a: seen.append((n, a)) or {})
    assert seen == [("unblockbruecke_card", {"action": "draw", "context": "break"})]
    assert tips.break_tip(lambda n: True, lambda n, a: {"title": 3})["source"] == "builtin"
    assert tips.break_tip(lambda n: True, lambda n, a: (_ for _ in ()).throw(RuntimeError("x")))["source"] == "builtin"
    assert tips.break_tip(lambda n: False, None)["source"] == "builtin"
    own = tips.break_tip(lambda n: False, None, [{"title": "Mine", "why": "because"}], seed=len(tips.BUILTIN))
    assert own == {"source": "user", "title": "Mine", "text": "because"}


def test_break_tip_for_one_break_is_the_same_in_every_process(tmp_path):
    """The seed came from hash(), which Python salts per process, so the page, the
    agent and the alert job showed different tips for the same break."""
    code = ("import pathlib, sys; sys.path.insert(0, sys.argv[1]); from esb_fakes import make_store, sub;"
            "s = make_store(pathlib.Path(sys.argv[2]));"
            "print(sub('timer_service').with_tip(s, {'phase': 'short', 'ends_at': '2026-11-11T10:25:00+01:00'})['title'])")
    titles = set()
    for seed in range(1, 9):
        run = subprocess.run([sys.executable, "-c", code, str(ROOT / "tests"), str(tmp_path / str(seed))], capture_output=True,
                             text=True, timeout=60, env={**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONDONTWRITEBYTECODE": "1"})
        assert run.returncode == 0, run.stderr[-1500:]
        titles.add(run.stdout.strip())
    assert len(titles) == 1, titles


def test_timer_tool_and_routes(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    set_clock(T0)
    out = ctx.call("eselsbruecke_timer", action="start", kind="countdown", minutes=2, label="tea")
    assert out["ok"] and out["state"]["phase"] == "countdown" and out["summary"] == "Countdown, 2 min left"
    assert ctx.call("eselsbruecke_timer", action="start")["error"] == "running"
    api = sub("api")
    store = sub("store").Store(tmp_path / "data")
    api.set_store_factory(lambda: store)
    try:
        status, body = api.timer_post({"op": "pause", "op_id": "c1", "at": T0.isoformat()})
        assert status == 200 and body["applied"] is True
        status, body = api.timer_post({"op": "pause", "op_id": "c1", "at": T0.isoformat()})
        assert status == 200 and body["duplicate"] is True
        assert api.timer_post({"op": "pause"})[0] == 409
        assert api.presence()[0] == 200 and store.read_json("presence.json")["at"]
        assert api.tips_get()[1]["tips"][0]["source"] == "builtin"
    finally:
        api.set_store_factory(None)


def test_one_unblockbruecke_card_per_break_however_often_the_page_polls(tmp_path, monkeypatch):
    api, bridge = sub("api"), sub("hermes_bridge")
    store = make_store(tmp_path)
    api.set_store_factory(lambda: store)
    clock = set_clock(T0)
    draws = []
    monkeypatch.setattr(bridge, "has_tool", lambda name: name == "unblockbruecke_card")
    monkeypatch.setattr(bridge, "dispatch", lambda tool, args, ctx=None: (
        draws.append(tool) or {"title": f"card {len(draws)}", "text": "t"}) if tool == "unblockbruecke_card" else {})
    try:
        assert api.timer_post({"op": "start", "kind": "pomodoro"})[0] == 200
        clock.when = at(26)  # the first short break; the page polls every 30 s
        titles = set()
        for _ in range(10):
            status, body = api.timer_get()
            titles.add(body["tip"]["title"])
            clock.advance(seconds=20)
        assert (len(draws), titles) == (1, {"card 1"})
        clock.when = at(57)  # the second break draws its own card
        assert api.timer_get()[1]["tip"]["title"] == "card 2" and len(draws) == 2
        clock.when = at(40)  # work time: no tip, no draw
        assert "tip" not in api.timer_get()[1] and len(draws) == 2
    finally:
        api.set_store_factory(None)


@pytest.mark.parametrize("plugins,silent", [
    ("enabled: []\n  disabled: [eselsbruecke]", True),
    ("enabled: [other]", True),
    ("enabled: [eselsbruecke]\n  disabled: [eselsbruecke]", True),
    ("enabled: [eselsbruecke]", False),
])
def test_tick_stays_silent_while_the_plugin_is_disabled_and_says_so_once(tmp_path, plugins, silent):
    tick, pad, tb = sub("alerts_tick"), sub("pad"), sub("toolbox")
    s = home_store(tmp_path)
    (tmp_path / "home").mkdir(exist_ok=True)
    (tmp_path / "home" / "config.yaml").write_text(f"plugins:\n  {plugins}\n", encoding="utf-8")
    doc = tb.load(s)
    doc["alerts"]["while_closed"] = True
    tb.save(s, doc, "user")
    set_clock(at(0))
    pad.add_lines(s, [{"text": "call the bank", "kind": "reminder", "remind_at": "10:02"}], "user")
    ticks = [tick.tick(s.root, ROOT, "Europe/Berlin", now=at(m)) for m in (1, 2.5, 3.5)]
    if silent:
        assert len(ticks[0]) == 1 and "disabled" in ticks[0][0] and "hermes cron remove" in ticks[0][0], ticks
        assert ticks[1:] == [[], []]
        assert not (s.root / "alerts_sent.jsonl").exists()
    else:
        assert ticks == [[], ["Eselsbrücke reminder: call the bank"], []]


def _tick_with_config(tmp_path, config_text):
    tick, pad, tb = sub("alerts_tick"), sub("pad"), sub("toolbox")
    s = home_store(tmp_path)
    (tmp_path / "home").mkdir(exist_ok=True)
    if config_text is not None:
        (tmp_path / "home" / "config.yaml").write_text(config_text, encoding="utf-8")
    doc = tb.load(s)
    doc["alerts"]["while_closed"] = True
    tb.save(s, doc, "user")
    set_clock(at(0))
    pad.add_lines(s, [{"text": "call the bank", "kind": "reminder", "remind_at": "10:02"}], "user")
    return [tick.tick(s.root, ROOT, "Europe/Berlin", now=at(m)) for m in (1, 2.5)]


def test_tick_follows_the_managed_scope_that_enables_the_plugin(tmp_path, monkeypatch, capsys):
    pytest.importorskip("hermes_cli.config")
    managed = tmp_path / "managed"
    managed.mkdir()
    (managed / "config.yaml").write_text("plugins:\n  enabled: [eselsbruecke]\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(managed))
    before = os.environ.get("HERMES_HOME")
    assert _tick_with_config(tmp_path, "model:\n  default: a\n") == [[], ["Eselsbrücke reminder: call the bank"]]
    assert os.environ.get("HERMES_HOME") == before and capsys.readouterr().out == ""


@pytest.mark.parametrize("config_text,expected", [
    ("plugins:\n  enabled: [eselsbruecke]\n", [[], ["Eselsbrücke reminder: call the bank"]]),
    ("plugins:\n  enabled: [other]\n", "disabled"),
    ("model:\n  default: a\nmodel:\n  default: b\nplugins:\n  enabled: [eselsbruecke]\n", "disabled"),
    (None, [[], ["Eselsbrücke reminder: call the bank"]]),
])
def test_tick_reads_the_profile_file_alone_where_hermes_cannot_be_imported(tmp_path, monkeypatch, capsys,
                                                                           config_text, expected):
    monkeypatch.setitem(sys.modules, "hermes_cli.config", None)  # an import of it raises ImportError
    ticks = _tick_with_config(tmp_path, config_text)
    if expected == "disabled":
        assert "disabled" in ticks[0][0] and ticks[1] == []
    else:
        assert ticks == expected
    assert capsys.readouterr().out == ""


def test_the_alert_ledger_keeps_only_its_newest_rows(tmp_path):
    tick = sub("alerts_tick")
    s = make_store(tmp_path)
    s.root.mkdir(parents=True, exist_ok=True)
    path = s.root / "alerts_sent.jsonl"
    path.write_text("".join(json.dumps({"key": f"k{i}", "at": "x", "by": "tick"}) + "\n"
                            for i in range(tick.SENT_KEEP * 2 + 5)), encoding="utf-8")
    tick._append_sent(path, {"key": "new", "at": "x", "by": "tick"})
    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == tick.SENT_KEEP and json.loads(rows[-1])["key"] == "new"
