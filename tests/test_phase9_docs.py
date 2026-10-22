"""Phase 9 deliverable: documentation of prompts and constants - generated from the code, so it cannot be stale."""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

from eidolon.debug import promptdoc
from eidolon.decision.turn import CANARY
from eidolon.llm import ingress, provider, render

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "EIDOLON-PROMPTS-AND-CONSTANTS.md"


def test_the_checked_in_document_is_exactly_what_the_code_renders():
    assert DOC.read_text(encoding="utf-8") == promptdoc.render(), "regenerate: python -m eidolon.debug promptdoc"


def test_the_document_is_the_same_in_every_process():
    out = [subprocess.run([sys.executable, "-c", "from eidolon.debug import promptdoc; import hashlib; "
                           "print(hashlib.sha256(promptdoc.render().encode()).hexdigest())"], capture_output=True, text=True, cwd=ROOT,
                          env={**__import__("os").environ, "PYTHONHASHSEED": seed}).stdout for seed in ("0", "7", "31337")]
    assert out[0] == out[1] == out[2] and out[0].strip()


@pytest.mark.parametrize("prompt", [ingress.SYSTEM_PARSE, render.SYSTEM_GENERATE, render.SYSTEM_VERIFY], ids=["parse", "generate", "verify"])
def test_every_prompt_the_models_receive_is_printed_verbatim_with_the_canary_masked(prompt):
    assert prompt.replace(CANARY, "{CANARY}") in DOC.read_text(encoding="utf-8")


def test_the_canary_value_itself_is_not_in_the_document():
    assert CANARY not in DOC.read_text(encoding="utf-8")


def test_every_wire_schema_and_every_repair_template_is_in_it():
    text = DOC.read_text(encoding="utf-8")
    for schema in (ingress.ACTION_SCHEMA, render.DRAFT_SCHEMA, render.VERIFY_SCHEMA):
        assert all(f'"{k}"' in text for k in schema["properties"])
    for code in render._TEMPLATES:
        assert f"`{code}`" in text
    for marker in ingress._MARKERS:
        assert f"`{marker}`" in text
    for route in ("parse", "generate", "verify"):
        assert f"`{provider.EFFORT[route]}`" in text
    assert provider.MODEL in text and "claude-fable-5-1" in text


@pytest.mark.parametrize("name, about", promptdoc.MODULES)
def test_every_constant_defined_in_a_documented_module_is_documented(name, about):
    """Found by parsing the module's source, so a constant added tomorrow fails this test until the document is regenerated."""
    import importlib
    mod = importlib.import_module(f"eidolon.{name}")
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    names = [t.id for n in tree.body for tt in (n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AnnAssign) else [])
             for t in (tt.elts if isinstance(tt, ast.Tuple) else [tt])                         # `A, B = 1, 2` declares two constants
             if isinstance(t, ast.Name) and re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", t.id)
             and not t.id.startswith("SYSTEM_") and not t.id.endswith("_SCHEMA") and t.id != "_TEMPLATES"]
    text = DOC.read_text(encoding="utf-8")
    missing = [n for n in names if f"| `{n}` |" not in text]
    assert not missing, missing


def test_the_modules_the_document_covers_include_every_phase_9_module_that_has_constants():
    covered = {n for n, _ in promptdoc.MODULES}
    assert {"trace", "debug.slo", "debug.audit", "debug.nightly", "debug.app", "llm.render", "llm.ingress", "store", "game"} <= covered
