"""JSON and YAML formatting and conversion for `eselsbruecke_format` and the page's formatter (one
engine for both, constraint 8). JSON uses the stdlib; YAML uses ruamel.yaml, a core Hermes
dependency. Parse errors carry line and column (1-based).

Markdown, TypeScript, JavaScript, CSS and HTML are formatted by Prettier inside the Desktop page;
this engine answers them with `not_here` and says where they are (D2 recommendation b).
"""
from __future__ import annotations

import io
import json
from typing import Any

LANGS = ("json", "yaml")
DESKTOP_ONLY = ("markdown", "typescript", "javascript", "css", "scss", "html")
MAX_TEXT = 500_000
MAX_ALIAS_EXPANSION = 100_000  # values plus string characters that YAML aliases may add when written as JSON
MAX_INDENT = 8


class FormatError(ValueError):
    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.line = line
        self.column = column


def _yaml():
    try:
        from ruamel.yaml import YAML
    except ImportError as exc:
        raise FormatError("ruamel.yaml is not installed (it ships with Hermes)") from exc
    y = YAML(typ="rt")
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 4096
    y.preserve_quotes = True
    return y


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FormatError(f"JSON: {exc.msg}", exc.lineno, exc.colno) from exc


def _parse_yaml(text: str) -> Any:
    y = _yaml()
    try:
        return y.load(text)
    except Exception as exc:  # ruamel raises several classes; all carry problem_mark when it knows
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        line = mark.line + 1 if mark is not None else None
        col = mark.column + 1 if mark is not None else None
        problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        raise FormatError(f"YAML: {problem}", line, col) from exc


def _dump_yaml(data: Any) -> str:
    buf = io.StringIO()
    _yaml().dump(data, buf)
    return buf.getvalue()


def _plain(data: Any) -> Any:
    """ruamel's round-trip types to plain JSON types (keeps order).

    YAML aliases share one loaded node, and JSON has no references, so every alias is written out in
    full. A 333-byte alias bomb used to become 25.6 MB in 2.6 s (X12). Each shared node (a container, or
    a string over 64 characters; shorter ones may be interned by Python anyway) is converted once; every
    later reference to it adds its size (values plus string characters) to a budget, and past
    MAX_ALIAS_EXPANSION the conversion stops. A container that contains itself is refused."""
    done: dict[int, tuple[Any, int]] = {}
    busy: set[int] = set()
    spent = 0

    def again(key: int) -> tuple[Any, int]:
        nonlocal spent
        plain, size = done[key]
        spent += size
        if spent > MAX_ALIAS_EXPANSION:
            raise FormatError(f"YAML: aliases expand past {MAX_ALIAS_EXPANSION} values and characters; "
                              "JSON cannot share them, so this document is refused")
        return plain, size

    def walk(node: Any) -> tuple[Any, int]:
        key = id(node)
        if key in done:
            return again(key)
        if isinstance(node, (dict, list, tuple)):
            if key in busy:
                raise FormatError("YAML: a recursive alias (a node that contains itself) has no JSON form")
            busy.add(key)
            size = 1
            if isinstance(node, dict):
                plain = {}
                for k, v in node.items():
                    plain[str(k)], n = walk(v)
                    size += n + len(str(k))
            else:
                plain = []
                for v in node:
                    p, n = walk(v)
                    plain.append(p)
                    size += n
            busy.discard(key)
            done[key] = (plain, size)
            return plain, size
        if isinstance(node, bool) or node is None or isinstance(node, (int, float)):
            return node, 1
        text = node.isoformat() if hasattr(node, "isoformat") else str(node)
        if len(text) > 64:
            done[key] = (text, 1 + len(text))
        return text, 1 + len(text)

    return walk(data)[0]


def _check(text: Any) -> str:
    if not isinstance(text, str):
        raise FormatError("text must be a string")
    if len(text) > MAX_TEXT:
        raise FormatError(f"text is longer than {MAX_TEXT} characters")
    return text


def _indent(indent: Any) -> int:
    """0 means compact JSON; a request can ask for at most MAX_INDENT spaces (X12: 100000 was accepted)."""
    if isinstance(indent, bool) or not isinstance(indent, int) or not 0 <= indent <= MAX_INDENT:
        raise FormatError(f"indent must be a whole number from 0 to {MAX_INDENT}")
    return indent


def format_text(text: str, lang: str, indent: int = 2, sort_keys: bool = False) -> dict:
    text = _check(text)
    indent = _indent(indent)
    lang = (lang or "").lower()
    if lang in DESKTOP_ONLY:
        return {"ok": False, "error": "not_here",
                "message": f"{lang} is formatted by Prettier on the Formatter page in Hermes Desktop; this tool "
                           "formats JSON and YAML."}
    if lang == "json":
        data = _parse_json(text)
        out = json.dumps(data, indent=indent or None, ensure_ascii=False, sort_keys=sort_keys)
        return {"ok": True, "lang": "json", "text": out + "\n", "changed": out + "\n" != text}
    if lang == "yaml":
        data = _parse_yaml(text)
        out = _dump_yaml(data)
        return {"ok": True, "lang": "yaml", "text": out, "changed": out != text}
    raise FormatError(f"lang must be one of {', '.join(LANGS)} (and {', '.join(DESKTOP_ONLY)} on the Desktop page)")


def convert(text: str, source: str, target: str, indent: int = 2) -> dict:
    text = _check(text)
    indent = _indent(indent)
    source, target = (source or "").lower(), (target or "").lower()
    if {source, target} != {"json", "yaml"}:
        raise FormatError("convert goes json -> yaml or yaml -> json")
    if source == "json":
        data = _parse_json(text)
        return {"ok": True, "lang": "yaml", "text": _dump_yaml(data)}
    data = _plain(_parse_yaml(text))
    return {"ok": True, "lang": "json", "text": json.dumps(data, indent=indent or None,
                                                            ensure_ascii=False) + "\n"}


def guess(text: str) -> str:
    s = text.lstrip() if isinstance(text, str) else ""
    return "json" if s[:1] in ("{", "[") else "yaml"
