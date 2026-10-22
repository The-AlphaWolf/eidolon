"""The Phase 4 exit criterion: "playable end-to-end with TemplateLLM via CLI"."""
from __future__ import annotations

import subprocess
import sys


def test_play_end_to_end_lie_then_concession_on_evidence():
    proc = subprocess.run(
        [sys.executable, "-m", "eidolon.cli", "play"],
        input="Where were you tonight?\npresent E_knife\nquit\n",
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    assert "[LIE]" in proc.stdout
    assert "[CONCESSION]" in proc.stdout


def test_demo_state_builds_without_the_test_tree():
    """Production code (`eidolon.decision.demo`) must not import from `tests/`."""
    import ast
    from pathlib import Path
    source = Path("eidolon/decision/demo.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("tests"):
            raise AssertionError(f"demo.py imports from the test tree: {node.module}")
