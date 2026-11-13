"""The plugin's data folder: one folder for both halves, locked writes, append-only JSONL.

The agent half gets its folder from `ctx.state.data_dir`; dashboard routes have no ctx and compute
the same folder per call (`default_root()`): Hermes' portable namespace
`agent-plugin-eselsbruecke-<sha256[:8]>` under `<hermes home>/plugin-data/`. The gateway, the
dashboard and a profile's plugin host child are separate processes, so every write takes an
`fcntl` lock on `<root>/.lock`.

Paths are built only from fixed names plus validated slugs (dates, week ids, version numbers), and
every resolved path is checked to stay under the root.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Union

PLUGIN = "eselsbruecke"
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_HELD = threading.local()


class StoreError(Exception):
    """A path outside the data folder or an unreadable file."""


def namespace() -> str:
    """The folder name Hermes gives `ctx.state.data_dir` for this plugin, for code that runs without a
    ctx (routes, the CLI, the alert tick). Hermes' rule restated, because its helper is private:
    `agent-plugin-<slug>-<first 8 hex of sha256(name)>`, and the slug of "eselsbruecke" is the name.
    tests/test_release.py checks it against Hermes' own helper whenever Hermes is importable."""
    return f"agent-plugin-{PLUGIN}-{hashlib.sha256(PLUGIN.encode()).hexdigest()[:8]}"


def hermes_home() -> Path:
    from hermes_constants import get_hermes_home

    return Path(get_hermes_home())


def default_root(home: Optional[Path] = None) -> Path:
    """The data folder for the profile whose home is bound now (routes, CLI, the tick)."""
    return (home or hermes_home()) / "plugin-data" / namespace()


def check_slug(value: str, what: str = "name") -> str:
    if not isinstance(value, str) or not SLUG_RE.match(value) or ".." in value:
        raise StoreError(f"invalid {what}: {value!r}")
    return value


class Store:
    """Locked JSON and JSONL files under one root folder."""

    def __init__(self, root: Union[Path, str, Callable[[], Path]]):
        self._root = root

    @property
    def root(self) -> Path:
        root = self._root() if callable(self._root) else self._root
        return Path(root)

    def path(self, *parts: str) -> Path:
        root = self.root.resolve()
        target = root.joinpath(*parts).resolve()
        if target != root and root not in target.parents:
            raise StoreError(f"path leaves the data folder: {'/'.join(parts)}")
        return target

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        """One lock for the whole data folder: a thread lock (re-entrant) plus an fcntl lock."""
        root = self.root
        key = str(root)
        with _THREAD_LOCKS_GUARD:
            tlock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with tlock:
            held = getattr(_HELD, "keys", None)
            if held is None:
                held = _HELD.keys = {}
            if held.get(key):
                held[key] += 1
                try:
                    yield
                finally:
                    held[key] -= 1
                return
            root.mkdir(parents=True, exist_ok=True)
            fd = os.open(root / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                held[key] = 1
                try:
                    yield
                finally:
                    held[key] = 0
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def read_json(self, *parts: str, default: Any = None) -> Any:
        p = self.path(*parts)
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return default
        except ValueError as exc:
            raise StoreError(f"{'/'.join(parts)} is not valid JSON: {exc}") from exc

    def write_json(self, parts: Union[str, tuple], value: Any) -> Path:
        parts = (parts,) if isinstance(parts, str) else tuple(parts)
        p = self.path(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(value, ensure_ascii=False, indent=1, sort_keys=False).encode("utf-8")
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, p)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise
        return p

    def append_jsonl(self, parts: Union[str, tuple], row: dict) -> None:
        parts = (parts,) if isinstance(parts, str) else tuple(parts)
        p = self.path(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(p, "a+b") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell():
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":  # a truncated last line stays alone; the new row is not glued to it
                    line = "\n" + line
            fh.write(line.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())

    def read_jsonl(self, *parts: str) -> tuple[list[dict], int]:
        """Rows and the number of lines that were not valid JSON objects (a truncated last line)."""
        p = self.path(*parts)
        rows: list[dict] = []
        bad = 0
        try:
            with open(p, encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        row = json.loads(raw)
                    except ValueError:
                        bad += 1
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
                    else:
                        bad += 1
        except FileNotFoundError:
            pass
        return rows, bad

    def listdir(self, *parts: str) -> list[str]:
        p = self.path(*parts)
        try:
            return sorted(x.name for x in p.iterdir())
        except FileNotFoundError:
            return []

    def remove(self, *parts: str) -> bool:
        p = self.path(*parts)
        try:
            p.unlink()
            return True
        except FileNotFoundError:
            return False
