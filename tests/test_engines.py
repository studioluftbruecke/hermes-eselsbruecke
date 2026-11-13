"""Text, generate and format engines: diff rows and words, Python regex in a child process with a
time limit and no inherited environment, counts with Hermes' estimate, UUID shapes, passwords."""
import json
import re

import pytest

from esb_fakes import ROOT, sub

PARITY = json.loads((ROOT / "tests" / "fixtures" / "parity.json").read_text(encoding="utf-8"))


def test_diff_rows_and_words():
    t = sub("engines.text")
    out = t.diff("a\nb\nc\n", "a\nB x\nc\nd\n")
    ops = [r["op"] for r in out["rows"]]
    assert ops == ["same", "change", "same", "add"] and out["added"] == 1 and out["changed"] == 1
    words = out["rows"][1]["words"]
    assert words == [{"op": "del", "text": "b"}, {"op": "add", "text": "B x"}]
    assert {"op": "same", "text": "the "} in t.diff("the cat", "the dog")["rows"][0]["words"]
    assert out["unified"].startswith("--- left\n+++ right")
    assert t.diff("x", "x")["identical"] is True


def test_regex_python_flavour():
    t = sub("engines.text")
    out = t.regex(r"(?P<y>\d{4})-(\d{2})", "on 2026-11 and 2027-01", "")
    assert out["flavour"] == "python re" and out["count"] == 2
    assert out["matches"][0] == {"match": "2026-11", "start": 3, "end": 10, "groups": ["2026", "11"],
                                 "named": {"y": "2026"}}
    assert t.regex("abc", "ABC", "i")["count"] == 1
    bad = t.regex("(", "x")
    assert bad["valid"] is False and "position" in bad
    with pytest.raises(t.TextError):
        t.regex("a", "a", "q")


def test_regex_answer_size_is_capped():
    t = sub("engines.text")
    out = t.regex("(?=(.*))", "a" * 199_000)
    size = len(json.dumps(out))
    assert size < 200_000, size
    assert out["truncated"] is True and out["clipped"] is True
    assert out["matches"][0]["groups"][0].startswith("aaa")
    small = t.regex(r"(\w+)@(\w+)", "me@host you@there")
    assert small["clipped"] is False and [m["groups"] for m in small["matches"]] == [["me", "host"], ["you", "there"]]


def test_regex_catastrophic_pattern_is_stopped():
    t = sub("engines.text")
    with pytest.raises(t.TextError) as exc:
        t.regex(r"(a+)+$", "a" * 40 + "!", timeout_s=1.0)
    assert "longer than" in str(exc.value)


def test_regex_child_gets_no_environment(monkeypatch):
    t = sub("engines.text")
    monkeypatch.setenv("ESB_SENTINEL_SECRET", "s3cr3t-value")
    env = t._child_env()
    assert "ESB_SENTINEL_SECRET" not in env and set(env) == {"PATH", "LANG", "LC_ALL", "PYTHONIOENCODING"}


def test_counts_match_the_parity_fixture():
    t = sub("engines.text")
    for row in PARITY["count"]:
        out = t.count(row["text"])
        out.pop("tokens_label")
        assert out == row["out"]
    assert "estimate" in t.count("x")["tokens_label"]


def test_uuid_shapes_and_v7_order():
    g = sub("engines.generate")
    v4 = g.uuids(4, 20)
    assert all(re.match(PARITY["uuid"]["v4"], u) for u in v4) and len(set(v4)) == 20
    v7 = [g.uuid7(ms) for ms in (1794245079976, 1794245079977)]
    assert all(re.match(PARITY["uuid"]["v7"], u) for u in v7)
    assert v7[0][:13].replace("-", "") == format(1794245079976, "012x") and v7[0] < v7[1]


def test_passwords_and_passphrases():
    g = sub("engines.generate")
    out = g.password(24, symbols=False)
    assert len(out["password"]) == 24 and re.fullmatch(r"[A-Za-z0-9]+", out["password"])
    assert any(c.isdigit() for c in out["password"]) and out["entropy_bits"] == round(24 * 5.954196310386876, 1)
    assert not set(g.password(64, avoid_ambiguous=True)["password"]) & set("Il1O0o")
    with pytest.raises(g.GenerateError):
        g.password(10, False, False, False, False)
    p = g.passphrase(5, ".")
    assert len(p["passphrase"].split(".")) == 5 and p["wordlist_size"] == 1296
    assert all(w in g.WORDS for w in p["passphrase"].split("."))


def test_format_json_and_yaml():
    f = sub("engines.fmt")
    out = f.format_text('{"b":1,"a":[1,2]}', "json")
    assert out["text"] == '{\n  "b": 1,\n  "a": [\n    1,\n    2\n  ]\n}\n'
    with pytest.raises(f.FormatError) as exc:
        f.format_text('{"a": 1,\n "b": }', "json")
    assert exc.value.line == 2 and exc.value.column == 7
    assert f.format_text("x", "typescript")["error"] == "not_here"
    pytest.importorskip("ruamel.yaml")
    y = f.format_text("a:   1\nlist:\n- x\n- y\n", "yaml")
    assert y["text"] == "a: 1\nlist:\n  - x\n  - y\n"
    assert f.convert('{"a": {"b": [1, "two"]}}', "json", "yaml")["text"] == "a:\n  b:\n    - 1\n    - two\n"
    assert json.loads(f.convert("a:\n  b: [1, two]\n", "yaml", "json")["text"]) == {"a": {"b": [1, "two"]}}
    with pytest.raises(f.FormatError) as exc:
        f.format_text("a: [1, 2\nb: 3\n", "yaml")
    assert exc.value.line is not None
