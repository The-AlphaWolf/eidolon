"""Shared scaffolding for the Phase 5 tests. Oracles here are independent of the code under test:
expected values come from running the SAME turn through the Phase 4 `TemplateLLM` path (a separate
implementation) or from hand-written tables, never from the renderer being tested.
"""
from __future__ import annotations

import json

from eidolon.decision.demo import DAVID as DEMO_DAVID, build_demo_state
from eidolon.decision.query import Query
from eidolon.decision.turn import run_ask_turn
from eidolon.llm.fakes import ScriptedTransport
from eidolon.llm.render import LLMRenderer, ModelLLM
from tests.decision.fixtures.vance_walkthrough import DAVID, ELENA, MARGARET, build_initial_state

__all__ = ["DAVID", "ELENA", "MARGARET", "DEMO_DAVID", "build_initial_state", "build_demo_state",
           "faithful", "approve", "reject_all", "draft_json", "scripted", "renderer", "ask", "fingerprint",
           "WHERE", "DEMO_ASK"]

WHERE = Query(kind="where", raw="Where were you at ten?")
DEMO_ASK = Query(kind="did_you", raw="Did you touch the knife?")


def draft_json(*segments: tuple[str, list[str], str]) -> str:
    return json.dumps({"segments": [{"text": t, "claim_ids": ids, "kind": k} for t, ids, k in segments]})


def faithful(style: int = 0):
    """A well-behaved model that words things freely. Reads only what a real model would see."""
    def gen(request) -> str:
        claims = json.loads(request.user)["claims"]
        if not claims:
            return draft_json(("I really cannot say.", [], "color"))
        pre, post = [("Well, ", ""), ("", " That is all."), ("", "")][style % 3]
        return draft_json(*((f"{pre}{c['content']}{post}", [c["id"]], "assert") for c in claims))
    return gen


def approve(request) -> str:
    """A verifier oracle that agrees with the tagging, using its own modality table."""
    doc = json.loads(request.user)
    return json.dumps({"unreferenced_assertions": [], "segments": [
        {"index": s["index"], "asserts_exactly": True, "extra_assertions": [],
         "modality": "actual"}
        for s in doc["segments"]]})


def reject_all(request) -> str:
    doc = json.loads(request.user)
    return json.dumps({"unreferenced_assertions": [], "segments": [
        {"index": s["index"], "asserts_exactly": False, "extra_assertions": [], "modality": "actual"}
        for s in doc["segments"]]})


def scripted(generate=(), verify=None, *, repeat_last: bool = False, parse=()) -> ScriptedTransport:
    return ScriptedTransport(generate=generate, verify=[approve] * 8 if verify is None else verify,
                             parse=parse, repeat_last=repeat_last)


def renderer(transport, **kw) -> LLMRenderer:
    return LLMRenderer(ModelLLM(transport), **kw)


def ask(state, who, query, **kw):
    return run_ask_turn(state, who, query, **kw)


def fingerprint(state):
    """Everything the engine decides, with all wording removed."""
    return (tuple((s.id, s.turn, s.speaker, s.act, tuple(c.id for c in s.claims), s.retracted_by, s.query_hash,
                   s.layer_scope) for s in state.decision.statements.all()),
            state.decision.layer_peels, state.characters, state.epistemic, state.discovery, state.turn_counter)
