"""Hermes' own checks on the plugin folder as it ships, run by tests/test_desktop_build.py
with the Python that runs Hermes and Hermes' source on PYTHONPATH:

- the Desktop admission lint (`hermes_cli.plugin_validate_desktop.desktop_surface_findings`), the rule
  `hermes plugins validate` applies to desktop/plugin.js, and its review cues
  (`desktop_review_findings`), which validate prints as warnings for the catalog reviewer;
- the install-time security scan (`tools.plugin_guard.scan_plugin`) on a copy of the plugin folder as it
  ships (without desktop/build/node_modules): verdict `safe` means no HIGH finding, so a Desktop or
  non-interactive install is not blocked. The scan reads plugin.js and data/o200k_base.json;
- the private core imports `hermes plugins validate` warns about (catalog rule 9).

These are Hermes internals, so this helper lives in tests/, which Hermes' import scan and its
runtime never load (it used to sit in desktop/build/, where the scan counted it as plugin code).

    PYTHONPATH=<hermes source> <hermes python> tests/hermes_checks.py <plugin dir>     prints one JSON line
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from hermes_cli.plugin_validate_desktop import desktop_review_findings, desktop_surface_findings
from hermes_cli.plugin_validate_private_imports import private_import_findings
from tools.plugin_guard import scan_plugin


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    bundle = (root / "desktop" / "plugin.js").read_text(encoding="utf-8")
    lint = desktop_surface_findings(bundle)
    review = desktop_review_findings(bundle)
    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / "eselsbruecke"
        shutil.copytree(root, pkg, ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache"))
        result = scan_plugin(pkg)
        private = private_import_findings(pkg)
    by = Counter((getattr(f, "severity", None), getattr(f, "pattern_id", None)) for f in result.findings)
    high = [f"{p} in {getattr(f, 'file', None)}" for f in result.findings
            for p in [getattr(f, "pattern_id", None)] if str(getattr(f, "severity", "")).lower() in ("high", "critical")]
    print(json.dumps({"lint": [{"rule": r, "line": n} for r, n in lint], "review": [{"cue": c, "line": n} for c, n in review],
                      "verdict": result.verdict, "high": high,
                      "findings": {f"{s}:{p}": n for (s, p), n in sorted(by.items(), key=str)},
                      "private_imports": private}))


if __name__ == "__main__":
    main()
