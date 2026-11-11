"""The store: atomic JSON, append-only JSONL with a truncated last line skipped, paths stay inside the
data folder, and the route folder equals the agent's `ctx.state.data_dir` for the same home."""
import hashlib
import os

import pytest

from esb_fakes import sub


def test_json_round_trip_and_atomic_replace(tmp_path):
    store = sub("store").Store(tmp_path / "d")
    store.write_json("a.json", {"x": 1})
    store.write_json(("sub", "b.json"), [1, 2])
    assert store.read_json("a.json") == {"x": 1}
    assert store.read_json("sub", "b.json") == [1, 2]
    assert store.read_json("missing.json", default="none") == "none"
    assert not [n for n in os.listdir(tmp_path / "d") if n.startswith(".tmp-")]


def test_jsonl_skips_a_truncated_last_line(tmp_path):
    store = sub("store").Store(tmp_path / "d")
    store.append_jsonl("log.jsonl", {"n": 1})
    store.append_jsonl("log.jsonl", {"n": 2})
    with open(tmp_path / "d" / "log.jsonl", "a") as fh:
        fh.write('{"n": 3, "trunc')
    rows, bad = store.read_jsonl("log.jsonl")
    assert [r["n"] for r in rows] == [1, 2] and bad == 1


def test_paths_cannot_leave_the_data_folder(tmp_path):
    st = sub("store")
    store = st.Store(tmp_path / "d")
    with pytest.raises(st.StoreError):
        store.path("..", "x.json")
    with pytest.raises(st.StoreError):
        st.check_slug("../etc")
    assert st.check_slug("2026-11-09") == "2026-11-09"


def test_lock_is_reentrant_in_one_thread(tmp_path):
    store = sub("store").Store(tmp_path / "d")
    with store.lock():
        with store.lock():
            store.write_json("x.json", 1)
    assert store.read_json("x.json") == 1


def test_route_folder_equals_the_namespace_rule(tmp_path):
    st = sub("store")
    digest = hashlib.sha256(b"eselsbruecke").hexdigest()[:8]
    assert st.namespace() == f"agent-plugin-eselsbruecke-{digest}"
    assert st.default_root(tmp_path) == tmp_path / "plugin-data" / f"agent-plugin-eselsbruecke-{digest}"


def test_route_folder_equals_ctx_state_data_dir_under_hermes(tmp_path, monkeypatch):
    plugins_state = pytest.importorskip("hermes_cli.plugins_state", reason="needs Hermes on sys.path")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    state = plugins_state.PluginState("eselsbruecke")
    assert sub("store").default_root(tmp_path) == state.data_dir


def test_append_after_a_truncated_line_starts_a_new_line(tmp_path):
    from esb_fakes import make_store

    s = make_store(tmp_path)
    s.append_jsonl("x.jsonl", {"a": 1})
    with open(s.path("x.jsonl"), "a", encoding="utf-8") as fh:
        fh.write('{"a": 2, "b"')
    s.append_jsonl("x.jsonl", {"a": 3})
    assert s.read_jsonl("x.jsonl") == ([{"a": 1}, {"a": 3}], 1)
