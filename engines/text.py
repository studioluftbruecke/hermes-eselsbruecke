"""Text tools for `eselsbruecke_text` and the page's diff: a line and word diff (difflib), a Python
regex test, and counts with Hermes' own token estimate.

The Regex tester page uses JavaScript `RegExp` (the flavour web developers write); this module tests
Python `re` and names its flavour in every answer. The token estimate is Hermes' own rule
(`agent/model_metadata.py` `estimate_tokens_rough`): ceil(UTF-8 bytes / 4), with each CJK character
one token; it is labelled as an estimate. The exact o200k count lives on the Desktop page.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import tempfile

MAX_TEXT = 200_000
MAX_MATCHES = 200
CHARS_PER_TOKEN = 4
_CJK_DENSE_RE = re.compile("[\u1100-\u11ff\u2e80-\u9fff\ua960-\ua97f\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]")


class TextError(ValueError):
    pass


def _cap(text: str, what: str) -> str:
    text = "" if text is None else str(text)
    if len(text) > MAX_TEXT:
        raise TextError(f"{what} is longer than {MAX_TEXT} characters")
    return text


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    if text.isascii():
        return (len(text) + 3) // CHARS_PER_TOKEN
    stripped = _CJK_DENSE_RE.sub("", text)
    dense = len(text) - len(stripped)
    return dense + ((len(stripped.encode("utf-8", "replace")) + 3) // CHARS_PER_TOKEN)


def count(text: str) -> dict:
    text = _cap(text, "text")
    return {"characters": len(text), "characters_no_spaces": len(re.sub(r"\s", "", text)),
            "words": len(re.findall(r"\S+", text)), "lines": (text.count("\n") + 1) if text else 0,
            "bytes_utf8": len(text.encode("utf-8")),
            "tokens_estimate": estimate_tokens(text),
            "tokens_label": "estimate: Hermes' own rule (UTF-8 bytes / 4, CJK 1 per character); "
                            "the exact o200k count is on the Token counter page"}


def _words(a: str, b: str) -> list[dict]:
    wa, wb = re.findall(r"\s+|\w+|[^\w\s]", a), re.findall(r"\s+|\w+|[^\w\s]", b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=wa, b=wb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "same", "text": "".join(wa[i1:i2])})
        else:
            if i2 > i1:
                out.append({"op": "del", "text": "".join(wa[i1:i2])})
            if j2 > j1:
                out.append({"op": "add", "text": "".join(wb[j1:j2])})
    return out


def diff(left: str, right: str, context: int = 3) -> dict:
    a, b = _cap(left, "left"), _cap(right, "right")
    la, lb = a.splitlines(), b.splitlines()
    rows: list[dict] = []
    added = removed = changed = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=la, b=lb, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                rows.append({"op": "same", "left_no": i1 + k + 1, "right_no": j1 + k + 1, "text": la[i1 + k]})
        elif op == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                changed += 1
                rows.append({"op": "change", "left_no": i1 + k + 1, "right_no": j1 + k + 1,
                             "left": la[i1 + k], "right": lb[j1 + k], "words": _words(la[i1 + k], lb[j1 + k])})
        else:
            for k in range(i1, i2):
                removed += 1
                rows.append({"op": "del", "left_no": k + 1, "text": la[k]})
            for k in range(j1, j2):
                added += 1
                rows.append({"op": "add", "right_no": k + 1, "text": lb[k]})
    unified = "\n".join(difflib.unified_diff(la, lb, "left", "right", n=context, lineterm=""))
    return {"identical": a == b, "added": added, "removed": removed, "changed": changed, "rows": rows,
            "unified": unified}


FLAG_MAP = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}
MATCH_TEXT_BUDGET = 50_000  # characters of match and group text in one answer
MATCH_PIECE = 2_000  # characters of one match or group text


def regex(pattern: str, text: str, flags: str = "", timeout_s: float = 2.0) -> dict:
    """Python `re` over the text, in a short-lived child process with an empty environment and a time
    limit: a catastrophic pattern (`(a+)+$`) would otherwise hold the gateway's GIL, and Python's `re`
    cannot be interrupted from another thread."""
    pattern = _cap(pattern, "pattern")
    text = _cap(text, "text")
    bits = 0
    for ch in flags or "":
        if ch == "g":
            continue  # every match is listed anyway
        if ch not in FLAG_MAP:
            raise TextError(f"unknown flag {ch!r}; Python flags here: i, m, s, x")
        bits |= FLAG_MAP[ch]
    try:
        re.compile(pattern, bits)
    except re.error as exc:
        return {"flavour": "python re", "valid": False, "error": str(exc),
                "position": getattr(exc, "pos", None)}
    payload = json.dumps({"p": pattern, "t": text, "f": bits, "max": MAX_MATCHES, "budget": MATCH_TEXT_BUDGET,
                          "piece": MATCH_PIECE})
    try:
        with tempfile.TemporaryDirectory(prefix="esb-rx-") as cwd:
            done = subprocess.run([sys.executable, "-I", "-S", "-c", _CHILD], input=payload, capture_output=True,
                                  text=True, timeout=timeout_s, cwd=cwd, env=_child_env(), close_fds=True)
    except subprocess.TimeoutExpired as exc:
        raise TextError(f"the pattern took longer than {timeout_s} s (catastrophic backtracking?)") from exc
    if done.returncode != 0:
        raise TextError("the regex test failed: " + (done.stderr.strip().splitlines() or ["no output"])[-1])
    result = json.loads(done.stdout)
    return {"flavour": "python re", "valid": True, "count": len(result["matches"]), "truncated": result["truncated"],
            "clipped": result["clipped"], "matches": result["matches"],
            "note": "Python re. The Regex tester page uses JavaScript RegExp; lookbehind, named groups "
                    "((?P<n>...) here, (?<n>...) there) and flags differ."}


_CHILD = """
import json, re, resource, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
a = json.loads(sys.stdin.read())
rx = re.compile(a["p"], a["f"])
out, trunc, left, clipped = [], False, a["budget"], False
def cut(s):
    global left, clipped
    if s is None:
        return s
    if len(s) > a["piece"]:
        s, clipped = s[:a["piece"]], True
    left -= len(s)
    return s
for m in rx.finditer(a["t"]):
    if len(out) >= a["max"] or left <= 0:
        trunc = True
        break
    out.append({"match": cut(m.group(0)), "start": m.start(), "end": m.end(), "groups": [cut(g) for g in m.groups()],
                "named": {k: cut(v) for k, v in m.groupdict().items()}})
sys.stdout.write(json.dumps({"matches": out, "truncated": trunc, "clipped": clipped}))
"""


def _child_env() -> dict:
    """Nothing from the gateway's environment reaches the child (it holds every profile's keys)."""
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8"}
