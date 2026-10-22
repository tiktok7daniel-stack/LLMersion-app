"""Runs the JavaScript unit tests (layout controller, i18n, flashcards) under Node."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_node_unit_tests_pass():
    r = subprocess.run(["node", "--test", str(ROOT / "tests" / "js" / "layout.test.mjs")],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
