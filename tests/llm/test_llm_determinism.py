"""Determinism across the LLM path (I-5, I-6, I-22): the decision state a scripted-LLM session
produces is identical across processes with different hash seeds, and independent of which wording
the model chose. Only the wording (`Statement.text`) may differ.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRIPT = textwrap.dedent('''
    import hashlib, json, sys
    from tests.llm.llm_helpers import *
    from eidolon.decision.query import Query

    def norm(x):
        if hasattr(x, "model_dump"):
            x = x.model_dump()
        if isinstance(x, dict):
            return {str(k): norm(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
        if isinstance(x, (set, frozenset)):
            return sorted((norm(v) for v in x), key=repr)
        if isinstance(x, (list, tuple)):
            return [norm(v) for v in x]
        return x

    style = int(sys.argv[1])
    state = build_demo_state()
    plan = [(DEMO_ASK, None), (Query(kind="challenge", raw="p"), "E_knife"), (DEMO_ASK, None),
            (Query(kind="opinion", raw="What do you make of it?"), None)]
    for i, (q, ref) in enumerate(plan):
        gen = [faithful(style + i)] if i != 2 else ["not json"]          # turn 2: the model fails, the template speaks
        t = scripted(gen, repeat_last=True)
        state = ask(state, DEMO_DAVID, q, presented_ref=ref, renderer=renderer(t)).state
    decisions = norm({
        "statements": [(s.id, s.turn, s.act, [c.id for c in s.claims], s.retracted_by, s.query_hash) for s in state.decision.statements.all()],
        "peels": state.decision.layer_peels, "characters": state.characters, "epistemic": state.epistemic,
        "discovery": state.discovery, "turn": state.turn_counter})
    words = [s.text for s in state.decision.statements.all()]
    print(hashlib.sha256(json.dumps(decisions, sort_keys=True, default=str).encode()).hexdigest(),
          hashlib.sha256(json.dumps(words).encode()).hexdigest())
''')


def _run(seed: str, style: int) -> tuple[str, str]:
    out = subprocess.run([sys.executable, "-c", SCRIPT, str(style)], cwd=ROOT, capture_output=True, text=True, timeout=120,
                         env={"PYTHONHASHSEED": seed, "PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert out.returncode == 0, out.stderr
    decisions, words = out.stdout.split()
    return decisions, words


def test_decision_state_is_identical_across_processes_and_hash_seeds():
    runs = [_run(seed, 0) for seed in ("1", "2", "3")]
    assert len({d for d, _ in runs}) == 1          # same decisions...
    assert len({w for _, w in runs}) == 1          # ...and, with a scripted model, the same words


def test_decision_state_is_independent_of_the_models_wording_only_the_words_differ():
    (d0, w0), (d1, w1), (d2, w2) = (_run("1", s) for s in (0, 1, 2))
    assert d0 == d1 == d2
    assert len({w0, w1, w2}) == 3
