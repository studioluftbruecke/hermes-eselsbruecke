"""Test helpers (conftest.py puts this folder on sys.path): load the plugin without Hermes, a temp
store, a fake ctx, a fixed clock."""
from __future__ import annotations

import datetime as dt
import importlib
import importlib.util
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = "eselsbruecke_under_test"
BERLIN = ZoneInfo("Europe/Berlin")


def load_plugin():
    if PKG in sys.modules:
        return sys.modules[PKG]
    spec = importlib.util.spec_from_file_location(PKG, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = module
    spec.loader.exec_module(module)
    return module


def sub(name: str):
    load_plugin()
    return importlib.import_module(f"{PKG}.{name}")


def hermes_source() -> "pathlib.Path | None":
    """Hermes' source tree, found like scripts/check.sh finds it: HERMES_SOURCE, a PYTHONPATH entry
    holding hermes_cli, /opt/hermes (the Docker image), then the installer's path. None when there is none."""
    import os

    candidates = [os.environ.get("HERMES_SOURCE", "")]
    candidates += os.environ.get("PYTHONPATH", "").split(os.pathsep)
    candidates += ["/opt/hermes", str(pathlib.Path.home() / ".hermes" / "hermes-agent")]
    for candidate in candidates:
        if candidate and (pathlib.Path(candidate) / "hermes_cli" / "__init__.py").is_file():
            return pathlib.Path(candidate)
    return None


def hermes_python(source: "pathlib.Path | None") -> "pathlib.Path | None":
    """The interpreter that runs Hermes: HERMES_PYTHON (scripts/check.sh sets it), else the source's venv."""
    import os

    candidates = [os.environ.get("HERMES_PYTHON", "")]
    if source is not None:
        candidates += [str(source / ".venv" / "bin" / "python"), str(source / "venv" / "bin" / "python")]
    for candidate in candidates:
        if candidate and pathlib.Path(candidate).exists():
            return pathlib.Path(candidate)
    return None


def make_store(tmp_path):
    return sub("store").Store(tmp_path / "data")


class FixedClock:
    """A settable aware clock; `advance(minutes=...)` steps it."""

    def __init__(self, when: dt.datetime):
        self.when = when

    def __call__(self) -> dt.datetime:
        return self.when

    def advance(self, **kw) -> dt.datetime:
        self.when = self.when + dt.timedelta(**kw)
        return self.when


def set_clock(when: dt.datetime, zone: str = "Europe/Berlin") -> FixedClock:
    c = FixedClock(when)
    sub("clock").set_clock(c, zone)
    return c


class FakeState:
    def __init__(self, data_dir):
        self.data_dir = data_dir

    def get(self, key, default=None):
        return default

    def set(self, key, value):
        pass


class FakeCtx:
    """Records registrations; `call(tool, **args)` runs a registered handler like Hermes would."""

    def __init__(self, data_dir, settings=None):
        self.state = FakeState(data_dir)
        self.settings = dict(settings or {})
        self.tools: dict = {}
        self.skills: list = []
        self.references: list = []
        self.cli: list = []
        self.dispatched: list = []

    def register_tool(self, **kw):
        self.tools[kw["name"]] = kw

    def register_skill(self, name, path, description=""):
        self.skills.append(name)

    def register_context_reference(self, provider):
        self.references.append(provider)

    def register_cli_command(self, **kw):
        self.cli.append(kw["name"])

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def dispatch_tool(self, name, args, **kw):
        self.dispatched.append((name, args))
        return json.dumps({"success": True, "job_id": "job-1"})

    def call(self, _tool, **args):
        return json.loads(self.tools[_tool]["handler"](args))

    def visible(self, tool):
        return self.tools[tool]["check_fn"]()


def home_store(tmp_path):
    """A store laid out like a profile: <home>/plugin-data/<namespace>, so <home>/scripts/ is right."""
    return sub("store").Store(tmp_path / "home" / "plugin-data" / sub("store").namespace())
