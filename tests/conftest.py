"""Make the helpers in esb_fakes.py importable by name (pytest runs with --import-mode=importlib), and
make every test an attended chat unless it says otherwise: outside Hermes the one-shot marker cannot be
read, which the plugin treats as unattended (fail closed)."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def attended(monkeypatch):
    from esb_fakes import sub

    bridge = sub("hermes_bridge")
    monkeypatch.setattr(bridge, "_finite_turn", lambda: False)
    monkeypatch.delenv("HERMES_PLUGIN_HOST_PROCESS", raising=False)
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    monkeypatch.delenv("HERMES_SINGLE_QUERY_SESSION", raising=False)
    yield
    sub("clock").set_clock(None)
