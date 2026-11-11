"""The Desktop half's build box (M6): the committed desktop/plugin.js, data/o200k_base.json and
THIRD_PARTY_NOTICES.md equal a fresh build, the runtime loader accepts the bundle, module evaluation
stays in budget (constraint 20) and register() makes its contributions, Hermes' admission lint is clean
and the install scan says `safe`, and the JavaScript engines equal the Python ones on the parity
fixture. The Desktop behaviour tests (tests/test_desktop_outbox.mjs, tests/test_desktop_surfaces.mjs)
run here too.

Needs node and `npm ci` in desktop/build (the pinned packages); without them these tests are skipped,
and the PR says so. The loader scan reads Hermes' Desktop source and the Hermes checks run with
Hermes' own Python: both are found from HERMES_SOURCE (tests/esb_fakes.py `hermes_source`).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from esb_fakes import ROOT, hermes_python, hermes_source

BUILD = ROOT / "desktop" / "build"
NODE = shutil.which("node")
SOURCE = hermes_source()
HERMES_PY = hermes_python(SOURCE)
needs_node = pytest.mark.skipif(not NODE or not (BUILD / "node_modules" / "esbuild").is_dir(),
                                reason="node and desktop/build/node_modules (npm ci) are needed for the Desktop build box")
needs_source = pytest.mark.skipif(SOURCE is None, reason="Hermes' source tree is needed: set HERMES_SOURCE")


def _last_json(text: str) -> dict:
    return json.loads(text.strip().splitlines()[-1])


def _build_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "HERMES_SOURCE"}
    if SOURCE is not None:
        env["HERMES_SOURCE"] = str(SOURCE)
    env.update(extra)
    return {k: v for k, v in env.items() if v is not None}


@pytest.fixture(scope="module")
def fresh_build(tmp_path_factory):
    out = tmp_path_factory.mktemp("esb-build")
    run = subprocess.run([NODE, str(BUILD / "build.mjs"), "--out", str(out)], capture_output=True, text=True,
                         timeout=600, env=_build_env())
    report = _last_json(run.stdout)
    report["_out"] = out
    return report


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


@needs_node
def test_committed_bundle_equals_a_fresh_build(fresh_build):
    assert fresh_build["plugin_js"]["sha256"] == _sha(ROOT / "desktop" / "plugin.js"), \
        "desktop/plugin.js is stale: run node desktop/build/build.mjs and commit it (milestone-closing commits only)"
    assert fresh_build["ranks"]["sha256"] == _sha(ROOT / "data" / "o200k_base.json")
    assert fresh_build["notices"]["sha256"] == _sha(ROOT / "THIRD_PARTY_NOTICES.md"), \
        "THIRD_PARTY_NOTICES.md is stale: run node desktop/build/build.mjs and commit it"
    assert fresh_build["plugin_js"]["underCap"] and fresh_build["plugin_js"]["bytes"] < 4 * 1024 * 1024


@needs_node
@needs_source
def test_loader_accepts_it_and_evaluation_is_in_budget(fresh_build):
    scan = fresh_build["loaderScan"]
    assert scan.get("ok") and scan["unsupported"] == [] and scan["controlRefused"], scan
    ev = fresh_build["evaluation"]
    print("evaluation CPU ms", ev["cpuMsRuns"], "min", ev["cpuMsMin"], "median", ev["cpuMsMedian"], "load", ev["loadAverage"])
    assert ev["withinBudget"], f"module evaluation {ev['cpuMsMin']} ms CPU (min of 5) is over {ev['budgetMs']} ms"
    assert ev["registered"]
    assert {":page", ":nav", ":chip", ":open", ":pad-add", "settings:toolbox"} <= set(ev["contributions"])
    assert fresh_build["ok"] is True


@needs_node
@pytest.mark.parametrize("source", [None, "empty"])
def test_build_fails_loudly_without_the_desktop_loader(source, tmp_path):
    """X20: a missing runtime-loader.ts is a failed check, never a passed one."""
    env = _build_env(HERMES_SOURCE=str(tmp_path) if source else None)
    if not source:
        env.pop("HERMES_SOURCE", None)
    run = subprocess.run([NODE, str(BUILD / "build.mjs"), "--check-only"], capture_output=True, text=True, timeout=600, env=env)
    report = _last_json(run.stdout)
    scan = report["loaderScan"]
    assert run.returncode == 1 and report["ok"] is False, report
    assert "skipped" not in scan and not scan.get("ok")
    assert "HERMES_SOURCE" in scan["error"]
    if source:
        assert "runtime-loader.ts" in scan["error"] and str(tmp_path) in scan["error"]


@needs_node
@needs_source
@pytest.mark.skipif(HERMES_PY is None, reason="Hermes' own Python is needed for its lint and install scan")
def test_admission_lint_clean_and_install_scan_safe():
    run = subprocess.run([str(HERMES_PY), str(ROOT / "tests" / "hermes_checks.py"), str(ROOT)], capture_output=True, text=True,
                         timeout=600, env={**os.environ, "PYTHONPATH": str(SOURCE)})
    assert run.returncode == 0, run.stderr[-2000:]
    out = _last_json(run.stdout)
    print("install scan findings", out["findings"])
    print("private core imports", out["private_imports"])
    assert out["lint"] == []
    assert out["verdict"] == "safe" and out["high"] == []
    # X20: what `hermes plugins validate` warns about is exactly the two guarded imports test_release.py accepts
    assert {site.split(" ", 1)[1].split(".finite_turn_required")[0] for site in out["private_imports"]} == \
        {"hermes_time", "gateway.session_finite"}, out["private_imports"]


@needs_node
def test_javascript_engines_equal_the_python_ones():
    run = subprocess.run([NODE, str(ROOT / "tests" / "test_desktop_parity.mjs"), str(BUILD / "node_modules")],
                         capture_output=True, text=True, timeout=300)
    out = _last_json(run.stdout)
    assert out["failed"] == 0, out["failures"]
    assert out["cases"] >= 60


@pytest.mark.skipif(not NODE, reason="node is needed")
def test_parity_script_without_its_argument_says_how_to_run_it():
    run = subprocess.run([NODE, str(ROOT / "tests" / "test_desktop_parity.mjs")], capture_output=True, text=True, timeout=60)
    assert run.returncode == 2
    assert "usage: node test_desktop_parity.mjs <desktop/build/node_modules>" in run.stderr
    assert "TypeError" not in run.stderr


# Desktop behaviour in node against a fake backend (tests/desktop_harness.mjs): the outbox, timer
# errors, alerts and the hours label (outbox), the beside pane, palette rows and the regex worker
# (surfaces). Each prints one JSON line { cases, failed, failures }.
@needs_node
@pytest.mark.parametrize("name, minimum", [("test_desktop_outbox.mjs", 11), ("test_desktop_surfaces.mjs", 9)])
def test_desktop_behaviour(name, minimum):
    run = subprocess.run([NODE, str(ROOT / "tests" / name), str(BUILD / "node_modules")],
                         capture_output=True, text=True, timeout=300)
    assert run.stdout.strip(), run.stderr[-2000:]
    out = _last_json(run.stdout)
    assert out["failed"] == 0, out["failures"]
    assert out["cases"] >= minimum
    assert run.returncode == 0
