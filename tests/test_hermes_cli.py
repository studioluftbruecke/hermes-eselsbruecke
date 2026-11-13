"""Hermes tools a route needs (the alert job, a kanban card) go through Hermes' public CLI as an
argument list in the profile's home: `hermes cron list --all | create | remove`, `hermes kanban create
--json`. A fake `hermes` on PATH records each call and answers in the CLI's own output format."""
import json
import os
import stat
import sys
import textwrap

import pytest

from esb_fakes import BERLIN, home_store, set_clock, sub

FAKE = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    from pathlib import Path
    log = os.environ["FAKE_HERMES_LOG"]
    args = sys.argv[1:]
    # the profile the way Hermes picks it: an explicit -p wins; a HERMES_HOME under profiles/ is used
    # as is; otherwise (the root) the sticky active_profile from `hermes profile use` applies
    env_home = Path(os.environ["HERMES_HOME"])
    root = env_home.parent.parent if env_home.parent.name == "profiles" else env_home
    name = None
    if "-p" in args:
        i = args.index("-p")
        name = args[i + 1]
        del args[i:i + 2]
    elif env_home.parent.name != "profiles" and (root / "active_profile").exists():
        name = (root / "active_profile").read_text().strip() or None
    home = env_home if name is None else (root if name == "default" else root / "profiles" / name)
    state_path = home / "fake-cron-jobs.json"
    jobs = json.loads(state_path.read_text()) if state_path.exists() else []
    with open(log, "a") as fh:
        fh.write(json.dumps({{"argv": args, "home": str(home), "env_home": str(env_home),
                             "host": os.environ.get("HERMES_PLUGIN_HOST_PROCESS")}}) + "\\n")
    if args[:2] == ["cron", "list"] and os.environ.get("FAKE_CRON_LAYOUT") == "other":
        print(f"{{len(jobs)}} job(s)")  # a layout a later Hermes might print
        for j in jobs:
            print(f"- {{j['id']}}: {{j['name']}} (every 1m, script {{j['script']}})")
    elif args[:2] == ["cron", "list"]:
        if not jobs:
            print(f"No scheduled jobs in profile '{{name or 'default'}}'.")
        else:
            print("\\x1b[33m+---+\\x1b[0m\\n|  Scheduled Jobs (profile: x)  |\\n+---+\\n")
        for j in jobs:
            print(f"  \\x1b[33m{{j['id']}}\\x1b[0m [active]")
            print(f"    Name:      {{j['name']}}")
            print("    Schedule:  every 1m")
            print("    Repeat:    \\u221e")
            print("    Next run:  2026-11-13T00:59:14+00:00")
            print("    Deliver:   all")
            print(f"    Script:    {{j['script']}}")
            print("    Last run:  2026-11-13T00:58:14+00:00  ok")
            print()
    elif args[:2] == ["cron", "create"]:
        if not (home / "scripts" / args[args.index("--script") + 1]).exists():
            print(f"Script file not found: {{home / 'scripts'}}", file=sys.stderr)
            sys.exit(1)
        job = {{"id": f"job{{len(jobs) + 1}}", "name": args[args.index("--name") + 1],
               "script": args[args.index("--script") + 1]}}
        jobs.append(job)
        print(f"Created job: {{job['id']}}\\n  Name: {{job['name']}}\\n  Schedule: every 1m")
    elif args[:2] == ["cron", "remove"]:
        jobs = [j for j in jobs if j["id"] != args[2]]
        print(f"Removed job {{args[2]}}")
    elif args[:2] == ["kanban", "create"]:
        rest = args[2:]
        title = rest[rest.index("--") + 1] if "--" in rest else rest[0]
        if title.startswith("-") and "--" not in rest:
            print(f"hermes: error: unrecognized arguments: {{title}}", file=sys.stderr)
            sys.exit(2)
        print(json.dumps({{"id": "t_card1", "title": title, "status": "triage", "assignee": "coding"}}))
    else:
        print("unexpected", args, file=sys.stderr)
        sys.exit(2)
    home.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(jobs))
''')


@pytest.fixture
def fake_hermes(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "hermes"
    exe.write_text(FAKE.format(python=sys.executable), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "hermes-calls.jsonl"
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_HERMES_LOG", str(log))
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")  # routes run in the plugin host child
    monkeypatch.setattr(sub("hermes_bridge"), "_hermes_command", lambda: str(exe))

    def calls():
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

    return home, calls


def test_the_alert_job_is_reconciled_through_the_cli_in_the_profile_home(tmp_path, fake_hermes):
    home, calls = fake_hermes
    store = home_store(tmp_path)
    tb, alerts = sub("toolbox"), sub("alerts")
    bridge = sub("hermes_bridge")
    doc = tb.load(store)
    doc["alerts"]["while_closed"] = True
    tb.save(store, doc, "user")
    out = alerts.reconcile(store, bridge.dispatch)  # a save may already have reconciled through its hook
    assert out["job_id"] == "job1"
    argv = [c["argv"] for c in calls()]
    assert argv[0] == ["cron", "list", "--all"]
    creates = [a for a in argv if a[:2] == ["cron", "create"]]
    assert len(creates) == 1
    create = creates[0]
    assert create[:3] == ["cron", "create", "every 1m"]
    for flag, value in (("--name", "eselsbruecke-alerts"), ("--script", "eselsbruecke_alerts.py"),
                        ("--deliver", "all"), ("--failure-deliver", "local"), ("--catch-up", "off")):
        assert create[create.index(flag) + 1] == value
    assert "--no-agent" in create
    assert {c["home"] for c in calls()} == {str(home)} and {c["host"] for c in calls()} == {None}

    again = alerts.reconcile(store, bridge.dispatch)  # idempotent: the job is found, nothing created
    assert again["created"] is False and again["job_id"] == "job1"
    listed = alerts.status(store, bridge.dispatch)["jobs"]
    assert listed == [{"job_id": "job1", "schedule": "every 1m", "last_status": "ok",
                       "next_run_at": "2026-11-13T00:59:14+00:00"}]

    doc = tb.load(store)
    doc["alerts"]["while_closed"] = False
    tb.save(store, doc, "user")
    alerts.reconcile(store, bridge.dispatch)
    removes = [c["argv"] for c in calls() if c["argv"][:2] == ["cron", "remove"]]
    assert removes == [["cron", "remove", "job1"]]
    assert bridge.dispatch("cronjob_manage", {"action": "list"})["jobs"] == []


def _switch(store, on: bool) -> None:
    tb = sub("toolbox")
    doc = tb.load(store)
    doc["alerts"]["while_closed"] = on
    tb.save(store, doc, "user")


def _jobs_of(home):
    path = home / "fake-cron-jobs.json"
    return [j["name"] for j in json.loads(path.read_text())] if path.exists() else []


def test_the_default_profiles_job_stays_in_the_default_profile_while_another_is_sticky(
        tmp_path, fake_hermes, monkeypatch):
    """`hermes profile use other` makes the CLI act on `other` whenever HERMES_HOME is the root. The
    default profile's routes must still create and remove only the default profile's job."""
    _home, calls = fake_hermes
    root = tmp_path / "root"
    other = root / "profiles" / "other"
    (other / "scripts").mkdir(parents=True)
    (root / "config.yaml").write_text("plugins:\n  enabled: [eselsbruecke]\n", encoding="utf-8")
    (other / "config.yaml").write_text("plugins:\n  enabled: [eselsbruecke]\n", encoding="utf-8")
    (root / "active_profile").write_text("other\n", encoding="utf-8")
    (other / "scripts" / "eselsbruecke_alerts.py").write_text("", encoding="utf-8")
    (other / "fake-cron-jobs.json").write_text(json.dumps(
        [{"id": "theirs", "name": "eselsbruecke-alerts", "script": "eselsbruecke_alerts.py"}]), encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(root))
    store = sub("store").Store(root / "plugin-data" / sub("store").namespace())
    alerts, bridge = sub("alerts"), sub("hermes_bridge")

    _switch(store, True)
    on = alerts.reconcile(store, bridge.dispatch)
    assert on["job_id"] and on["job_id"] != "theirs"
    assert _jobs_of(root) == ["eselsbruecke-alerts"] and _jobs_of(other) == ["eselsbruecke-alerts"]

    _switch(store, False)
    alerts.reconcile(store, bridge.dispatch)
    assert _jobs_of(root) == [] and _jobs_of(other) == ["eselsbruecke-alerts"]
    assert {c["home"] for c in calls()} == {str(root)}


def test_a_named_profile_names_itself_to_the_cli(tmp_path, fake_hermes, monkeypatch):
    _home, calls = fake_hermes
    root = tmp_path / "root"
    work = root / "profiles" / "work"
    work.mkdir(parents=True)
    for home in (root, work):
        (home / "config.yaml").write_text("plugins:\n  enabled: [eselsbruecke]\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(work))
    bridge = sub("hermes_bridge")
    assert bridge.current_profile() == "work"
    assert bridge.dispatch("cronjob_manage", {"action": "list"})["jobs"] == []
    assert calls()[-1]["home"] == str(work) and calls()[-1]["env_home"] == str(work)


def test_a_cron_list_layout_the_plugin_cannot_read_never_adds_a_second_job(tmp_path, fake_hermes, monkeypatch):
    home, calls = fake_hermes
    store = home_store(tmp_path)
    timer_service, bridge = sub("timer_service"), sub("hermes_bridge")
    _switch(store, True)
    assert timer_service.reconcile_quiet(store)["job_id"] == "job1"
    monkeypatch.setenv("FAKE_CRON_LAYOUT", "other")
    for _ in range(3):
        out = timer_service.reconcile_quiet(store)
        assert out["ok"] is False and "cannot read" in out["error"] and "update the plugin" in out["error"]
    assert _jobs_of(home) == ["eselsbruecke-alerts"]
    _switch(store, False)  # nor removes one it cannot see
    assert timer_service.reconcile_quiet(store)["ok"] is False and _jobs_of(home) == ["eselsbruecke-alerts"]
    assert [c["argv"][:2] for c in calls()].count(["cron", "create"]) == 1


def test_the_job_is_found_by_its_script_after_a_rename(tmp_path, fake_hermes):
    """The plugin's own job is the one that runs its script, also when someone renamed the job."""
    home, calls = fake_hermes
    store = home_store(tmp_path)
    alerts, bridge = sub("alerts"), sub("hermes_bridge")
    (home / "fake-cron-jobs.json").write_text(json.dumps(
        [{"id": "renamed", "name": "my alerts", "script": "eselsbruecke_alerts.py"},
         {"id": "unrelated", "name": "backup", "script": "backup.py"}]), encoding="utf-8")
    _switch(store, True)
    out = alerts.reconcile(store, bridge.dispatch)
    assert out["job_id"] == "renamed" and out["created"] is False
    _switch(store, False)  # the save reconciles: the renamed job goes, the unrelated one stays
    alerts.reconcile(store, bridge.dispatch)
    assert [j["id"] for j in json.loads((home / "fake-cron-jobs.json").read_text())] == ["unrelated"]
    assert ["cron", "remove", "renamed"] in [c["argv"] for c in calls()]


def test_timer_clicks_start_no_cli_child_while_the_job_matches_the_switch(tmp_path, fake_hermes):
    """A day's clicks: start and stop with alerts off, switch on (the save sets up the job), start and
    stop again, switch off (the save removes it), start and stop. Only the two saves reach the CLI."""
    home, calls = fake_hermes
    api = sub("api")
    store = home_store(tmp_path)
    api.set_store_factory(lambda: store)
    set_clock(__import__("datetime").datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))

    def clicks():
        before = len(calls())
        for op in ("start", "stop"):
            status, _ = api.timer_post({"op": op, "kind": "pomodoro"})
            assert status == 200
        return calls()[before:]

    try:
        assert clicks() == []
        _switch(store, True)
        assert _jobs_of(home) == ["eselsbruecke-alerts"]
        assert clicks() == []
        _switch(store, False)
        assert _jobs_of(home) == []
        assert clicks() == []
    finally:
        api.set_store_factory(None)


def test_a_click_reconciles_once_when_the_switch_changed_without_a_reconcile(tmp_path, fake_hermes):
    """toolbox.json switched on outside a save (a restored backup): the next click sets up the job once."""
    home, calls = fake_hermes
    api = sub("api")
    store = home_store(tmp_path)
    store.write_json("toolbox.json", {**sub("toolbox").default_doc(first_run=False), "alerts": {"while_closed": True}})
    api.set_store_factory(lambda: store)
    set_clock(__import__("datetime").datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    try:
        api.timer_post({"op": "start", "kind": "pomodoro"})
        assert _jobs_of(home) == ["eselsbruecke-alerts"]
        before = len(calls())
        api.timer_post({"op": "stop"})
        assert calls()[before:] == []
    finally:
        api.set_store_factory(None)


def test_a_pad_line_becomes_a_kanban_card_through_the_cli(tmp_path, fake_hermes):
    home, calls = fake_hermes
    api = sub("api")
    store = home_store(tmp_path)
    api.set_store_factory(lambda: store)
    set_clock(__import__("datetime").datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    try:
        _, body = api.pad_lines({"op": "add", "text": "Write the --help page"})
        lid = body["day"]["lines"][0]["id"]
        status, body = api.pad_lines({"op": "card", "id": lid})
        assert status == 200 and body["card"]["task_id"] == "t_card1" and body["card"]["status"] == "triage"
    finally:
        api.set_store_factory(None)
    argv = calls()[-1]["argv"]
    assert argv[:2] == ["kanban", "create"] and argv[-1] == "Write the --help page"
    assert "--triage" in argv and "--json" in argv and argv[argv.index("--assignee") + 1] == "default"


def test_a_pad_line_that_looks_like_a_flag_still_becomes_a_card(tmp_path, fake_hermes):
    home, calls = fake_hermes
    api = sub("api")
    store = home_store(tmp_path)
    api.set_store_factory(lambda: store)
    set_clock(__import__("datetime").datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN))
    try:
        for text in ("--draft", "-urgent", "--json", "-v2 release notes", "plain words"):
            _, body = api.pad_lines({"op": "add", "text": text})
            lid = next(x["id"] for x in body["day"]["lines"] if x["text"] == text)
            status, body = api.pad_lines({"op": "card", "id": lid})
            assert status == 200 and body["card"] and body["card"]["task_id"] == "t_card1", (text, body)
            assert calls()[-1]["argv"][-1] == text
    finally:
        api.set_store_factory(None)


def test_the_hermes_beside_the_running_python_wins_over_path(tmp_path, monkeypatch):
    """Two installs on one host: the routes run the CLI of the Hermes they run in, not PATH's."""
    monkeypatch.undo()  # the autouse fixture keeps the real hermes command away from tests; this one reads it
    log = tmp_path / "ran.txt"
    for name in ("running", "on-path"):
        exe = tmp_path / name / "hermes"
        exe.parent.mkdir()
        exe.write_text(f"#!/bin/sh\necho {name} >> {log}\necho 'No scheduled jobs.'\n", encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{tmp_path / 'on-path'}{os.pathsep}/usr/bin{os.pathsep}/bin")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "running" / "python"))
    bridge = sub("hermes_bridge")
    bridge.dispatch("cronjob_manage", {"action": "list"})
    assert log.read_text().split() == ["running"]
    monkeypatch.setattr(sys, "executable", str(tmp_path / "elsewhere" / "python"))  # no hermes beside it
    bridge.dispatch("cronjob_manage", {"action": "list"})
    assert log.read_text().split() == ["running", "on-path"]


def test_a_missing_hermes_command_is_a_bridge_error(tmp_path, monkeypatch):
    monkeypatch.undo()  # the autouse fixture keeps the real hermes command away from tests; this one reads it
    monkeypatch.setenv("PATH", str(tmp_path))  # no hermes here
    bridge = sub("hermes_bridge")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    with pytest.raises(bridge.BridgeError):
        bridge.dispatch("cronjob_manage", {"action": "list"})
