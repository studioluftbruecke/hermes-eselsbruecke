"""The release step (PR #73 review X19, X20) and the two-place install rule.

- X19: every third-party component that ships in the plugin folder is named in
  THIRD_PARTY_NOTICES.md with its version, copyright line and licence text; the README's Disclosures
  name the two data files and point to the notices; plugin.js points to them.
- X20: the plugin imports no private Hermes core module except the two it cannot replace today
  (`hermes_time`, `gateway.session_finite`), each guarded with a fallback; no Python helper that
  imports Hermes internals ships outside tests/.
- AGENTS.md "Two-place install for a Desktop half": the README section "Install and update".
"""
import ast
import hashlib
import json
import re

import pytest

from esb_fakes import ROOT, sub

NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
LOCK = ROOT / "desktop" / "build" / "package-lock.json"
PRETTIER_NOTICES = ROOT / "desktop" / "build" / "node_modules" / "prettier" / "THIRD-PARTY-NOTICES.md"

# Package -> the copyright line its licence carries. Every package esbuild puts into plugin.js, plus
# esbuild itself for the module helpers it writes around them.
BUNDLED = {
    "prettier": "Copyright © James Long and contributors",
    "qrcode-generator": "Copyright (c) 2009 Kazuhiko Arase",
    "js-tiktoken": "Copyright (c) 2022 OpenAI, Shantanu Jain",
    "base64-js": "Copyright (c) 2014 Jameson Little",
    "esbuild": "Copyright (c) 2020 Evan Wallace",
}
MIT_GRANT = "Permission is hereby granted, free of charge, to any person obtaining a copy"


def _locked_version(name: str) -> str:
    return json.loads(LOCK.read_text(encoding="utf-8"))["packages"][f"node_modules/{name}"]["version"]


def _section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert match, f"README has no section '## {title}'"
    return match.group(1)


# --- X19 -------------------------------------------------------------------------------------------

def test_notices_name_every_bundled_package_with_version_copyright_and_licence_text():
    assert NOTICES.is_file(), "THIRD_PARTY_NOTICES.md is missing from the plugin folder"
    text = NOTICES.read_text(encoding="utf-8")
    for name, copyright_line in BUNDLED.items():
        version = _locked_version(name)
        assert f"{name} {version}" in text, f"{name} {version} (package-lock.json) is not named in the notices"
        assert copyright_line in text, f"{name}: its copyright line is missing"
    assert text.count(MIT_GRANT) >= len(BUNDLED), "an MIT licence text is missing"


def test_notices_carry_the_data_files_and_their_attribution():
    text = NOTICES.read_text(encoding="utf-8")
    words = ROOT / "data" / "eff_short_wordlist_1.txt"
    assert "data/eff_short_wordlist_1.txt" in text and "Electronic Frontier Foundation" in text
    assert "https://creativecommons.org/licenses/by/3.0/us/" in text
    # "unmodified" is a claim about these exact bytes: the notices name the hash it was checked against
    assert hashlib.sha256(words.read_bytes()).hexdigest() in text
    assert "data/o200k_base.json" in text and "Copyright (c) 2022 OpenAI, Shantanu Jain" in text


def test_notices_carry_prettiers_bundled_dependencies():
    text = NOTICES.read_text(encoding="utf-8")
    assert "# Licenses of bundled dependencies" in text and "## @angular/compiler@" in text
    if PRETTIER_NOTICES.is_file():  # after npm ci: the whole file, verbatim
        assert PRETTIER_NOTICES.read_text(encoding="utf-8") in text


def test_readme_disclosures_name_the_data_files_and_the_notices():
    disclosures = _section((ROOT / "README.md").read_text(encoding="utf-8"), "Disclosures")
    for needle in ("data/o200k_base.json", "data/eff_short_wordlist_1.txt", "CC BY 3.0 US", "THIRD_PARTY_NOTICES.md"):
        assert needle in disclosures, f"Disclosures do not mention {needle}"


def test_plugin_js_points_to_the_notices():
    first = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8").split("\n", 1)[0]
    assert "THIRD_PARTY_NOTICES.md" in first


# --- X20 -------------------------------------------------------------------------------------------

ACCEPTED_PRIVATE = {"hermes_time", "gateway.session_finite"}
# Modules of Hermes' published plugin API (hermes_cli/data/plugin_api.json) the plugin uses.
PUBLIC_USED = {"hermes_constants", "gateway.session_context", "gateway.config", "tools.registry", "agent.context_references"}
HERMES_PACKAGES = {"hermes_time", "hermes_cli", "gateway", "tools", "agent", "hermes_state", "cron", "plugins"}


def _plugin_modules():
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if rel.parts[0] == "tests" or "node_modules" in rel.parts:
            continue
        yield rel, ast.parse(path.read_text(encoding="utf-8"))


def _guarded(tree: ast.AST, node: ast.AST) -> bool:
    """Whether `node` sits in the body of a try whose handlers catch ImportError or Exception."""
    for parent in ast.walk(tree):
        if isinstance(parent, ast.Try) and any(node is n for stmt in parent.body for n in ast.walk(stmt)):
            caught = {ast.unparse(h.type) for h in parent.handlers if h.type is not None}
            if caught & {"ImportError", "Exception", "ModuleNotFoundError"}:
                return True
    return False


def test_no_python_helper_ships_outside_tests_and_the_runtime():
    shipped = [str(rel) for rel, _tree in _plugin_modules() if rel.parts[0] == "desktop"]
    assert shipped == [], f"Python under desktop/ ships with the plugin and is scanned as plugin code: {shipped}"


def test_private_core_imports_are_only_the_accepted_ones_and_each_is_guarded():
    found = []
    for rel, tree in _plugin_modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            else:
                continue
            for module in modules:
                if module.split(".")[0] in HERMES_PACKAGES and module not in PUBLIC_USED:
                    found.append((str(rel), module, _guarded(tree, node)))
    assert {m for _r, m, _g in found} <= ACCEPTED_PRIVATE, found
    assert all(g for _r, _m, g in found), f"unguarded private import: {[f for f in found if not f[2]]}"


def test_data_namespace_matches_hermes_rule():
    expected = "agent-plugin-eselsbruecke-" + hashlib.sha256(b"eselsbruecke").hexdigest()[:8]
    assert sub("store").namespace() == expected
    manifest = pytest.importorskip("hermes_cli.plugins_manifest")
    assert manifest._portable_data_namespace("eselsbruecke") == expected


# --- Two-place install (AGENTS.md, PR #104) --------------------------------------------------------

def test_readme_install_and_update_covers_both_places():
    section = _section((ROOT / "README.md").read_text(encoding="utf-8"), "Install and update")
    for needle in ("hermes -p <profile> plugins install https://github.com/studioluftbruecke/hermes-eselsbruecke --enable",
                   "hermes plugins install https://github.com/studioluftbruecke/hermes-eselsbruecke",
                   "hermes -p <profile> plugins update eselsbruecke", "hermes plugins update eselsbruecke",
                   "Rescan", "Agent in <profile>", "Force reinstall", "plugins list"):
        assert needle in section, f"'Install and update' lacks: {needle}"
