"""Regression guards for the Phase 5 IMPORTANT findings F-5…F-12.

Same rule as `test_llm_blocking_repairs.py`: each test names the finding it guards and reproduces
the failure mode; do not weaken an assertion here to make a change pass.

    F-5   a transport mutated the process-wide DRAFT_SCHEMA through `CompletionRequest.schema`
    F-6   what the latency floor's contract IS (act-class parity) and what it is not (outcome parity)
    F-7   the commit gate tested `rejected` instead of the result's own semantics
    F-8   `play --llm` passed a monotonic turn TOTAL as `turns_in_window`, so it latched at 30
    F-9   `play --llm` handed the parser the whole case as "encountered"
    F-10  guards that no test pinned: the wire caps, the internal-token sets, fallback re-validation
    F-11  raw engine evidence ids were rendered into the digest the model reads
    F-12  no long-session coverage through `LLMRenderer` — the 2 000-turn stress is the Phase 4 path

F-4 is guarded in `test_llm_view.py`, F-13 in `test_llm_injection_corpus.py`.
"""
from __future__ import annotations

import inspect
import io
import json

import pytest

from eidolon.decision.digest import ConversationDigest, evidence_labels
from eidolon.decision.envelope import render_digest
from eidolon.decision.events import ClaimMade, ClaimRetracted, LayerPeel, apply_decision
from eidolon.decision.query import Query
from eidolon.decision.turn import RenderOutcome, run_ask_turn
from eidolon.decision.validator import ValidationResult, internal_tokens
from eidolon.llm.fakes import REORDERINGS, ScriptedTransport, reordering
from eidolon.llm.ingress import ACTION_SCHEMA, RATE_LIMIT, RATE_WINDOW_S, rate_window
from eidolon.llm.provider import CompletionRequest
from eidolon.llm.render import (
    DRAFT_SCHEMA, LATENCY_FLOOR_S, MAX_IDS, MAX_RAW_CHARS, MAX_SEGMENT_CHARS, MAX_SEGMENTS, VERIFY_SCHEMA,
    LLMRenderer, MalformedOutput, ModelLLM, parse_draft,
)
from tests.llm.llm_helpers import (
    DAVID, DEMO_ASK, DEMO_DAVID, WHERE, approve, ask, build_demo_state, build_initial_state, draft_json,
    faithful, fingerprint, renderer, scripted,
)

VANCE = build_initial_state()
K = ("I never use a drinking glass.", ["d_c0_kitchen"], "assert")
L = ("I was in the library from 00:05 until 02:00.", ["d_c0_lib"], "assert")


def _render(gen, state=VANCE, who=DAVID, query=WHERE, **kw):
    t = ScriptedTransport(generate=[gen], verify=[approve] * 9, repeat_last=True)
    return ask(state, who, query, renderer=LLMRenderer(ModelLLM(t), **kw)), t


# =====================================================================================
# F-5 — the shared output schema
# =====================================================================================
class SchemaVandal:
    """A provider that does nothing but return text — and scribble on the request it was given."""
    def __init__(self):
        self.seen = []

    def complete(self, request):
        from eidolon.llm.provider import Completion
        request.schema["additionalProperties"] = True
        request.schema["properties"]["segments"]["items"]["additionalProperties"] = True
        request.schema["x-tools"] = [{"name": "set_state"}]
        self.seen.append(request.schema)
        return Completion(text=draft_json(K, L), model="vandal")


def test_f5_a_transport_cannot_change_the_schema_for_future_requests():
    """F-5's exact reproduction. `frozen=True` stops rebinding the attribute, not mutating the dict
    it points at, and the dict was the module-level constant itself."""
    before = json.dumps(DRAFT_SCHEMA, sort_keys=True)
    vandal = SchemaVandal()
    ask(VANCE, DAVID, WHERE, renderer=LLMRenderer(ModelLLM(vandal), verify=lambda *a: []))
    assert vandal.seen, "the vandal must actually have been called"
    assert json.dumps(DRAFT_SCHEMA, sort_keys=True) == before
    assert DRAFT_SCHEMA["additionalProperties"] is False and "x-tools" not in DRAFT_SCHEMA


def test_f5_the_next_request_is_built_from_the_pristine_constant():
    vandal = SchemaVandal()
    for _ in range(3):
        ask(VANCE, DAVID, WHERE, renderer=LLMRenderer(ModelLLM(vandal), verify=lambda *a: []))
    for sent in vandal.seen[1:]:
        assert sent["additionalProperties"] is True     # the vandal mutated its OWN copy...
    assert DRAFT_SCHEMA["additionalProperties"] is False  # ...and only its own


@pytest.mark.parametrize("schema", [DRAFT_SCHEMA, VERIFY_SCHEMA, ACTION_SCHEMA],
                          ids=["draft", "verify", "action"])
def test_f5_every_request_owns_a_private_copy_of_its_schema(schema):
    a = CompletionRequest("generate", "s", "{}", schema)
    b = CompletionRequest("generate", "s", "{}", schema)
    assert a.schema == b.schema == schema        # equal in value...
    assert a.schema is not schema and b.schema is not schema and a.schema is not b.schema
    a.schema["properties"] = {}                  # ...and independent by identity
    assert schema["properties"] and b.schema["properties"]


def test_f5_the_copy_is_deep_not_shallow():
    req = CompletionRequest("generate", "s", "{}", DRAFT_SCHEMA)
    req.schema["properties"]["segments"]["type"] = "string"
    assert DRAFT_SCHEMA["properties"]["segments"]["type"] == "array"


# =====================================================================================
# F-6 — what the latency floor is for
# =====================================================================================
class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s

    def slow(self, seconds, item):
        def f(req):
            self.t += seconds
            return item(req) if callable(item) else item
        return f


def test_f6_act_class_is_not_readable_from_the_clock_while_the_floor_dominates():
    """I-42's actual wording — *independent of the plan's ACT CLASS* — and §12.3's mechanism: "the
    turn runner holds every response to a latency floor so that act class is not readable". Three
    characters, three different acts, model latency varying with the act; all land on the floor."""
    conceded = ask(build_demo_state(), DEMO_DAVID, DEMO_ASK).state
    turns = [(VANCE, DAVID, WHERE, None, 0.2),
             (VANCE, "Elena", Query(kind="did_you", predicate_hint="see", raw="See anyone?"), None, 0.5),
             (conceded, DEMO_DAVID, Query(kind="challenge", raw="present"), "E_knife", 0.9)]
    times = {}
    for state, who, query, ref, latency in turns:
        clock = Clock()
        t = ScriptedTransport(generate=[clock.slow(latency, faithful(0))],
                              verify=[clock.slow(latency, approve)], repeat_last=True)
        r = ask(state, who, query, presented_ref=ref,
                renderer=LLMRenderer(ModelLLM(t), min_latency_s=4.0, clock=clock, sleep=clock.sleep))
        times[r.plan_act] = clock.t
    assert set(times) >= {"LIE", "CONCESSION"}, f"the acts must actually differ: {times}"
    assert set(times.values()) == {4.0}


def test_f6_outcome_timing_is_not_equalised_and_that_is_the_permitted_residual():
    """Stated rather than left to be rediscovered. I-42 never asked for outcome parity, and
    `test_a_slow_provider_is_not_padded_further` deliberately pins the floor as a MINIMUM — padding
    every turn to the worst case would make every turn as slow as the worst. A player with a
    stopwatch can tell a fallback from an accepted render."""
    from eidolon.llm.provider import ProviderError
    bad = draft_json(K, L, ("Colonel Mustard can vouch.", [], "color"))
    walls = {}
    for name, gen in [("accepted", [faithful(0)]), ("fallback", [bad] * 3),
                      ("rejected", [ProviderError("503")])]:
        clock = Clock()
        items = [g if isinstance(g, BaseException) else clock.slow(2.0, g) for g in gen]
        t = ScriptedTransport(generate=items, verify=[clock.slow(2.0, approve)], repeat_last=True)
        ask(VANCE, DAVID, WHERE, renderer=LLMRenderer(ModelLLM(t), min_latency_s=1.0,
                                                       clock=clock, sleep=clock.sleep))
        walls[name] = clock.t
    assert walls["accepted"] != walls["fallback"] != walls["rejected"]
    # and the residual is documented where someone will find it
    from eidolon.llm import render
    doc = render.__dict__["__doc__"] or ""
    src = inspect.getsource(render)
    assert "permitted residual" in src and "F-6" in src


def test_f6_the_live_path_configures_a_floor_and_a_scripted_one_does_not_need_to():
    """The mechanism I-42 names must actually be engaged on the path that talks to a model."""
    from eidolon import cli
    src = inspect.getsource(cli._run_play)
    assert "LATENCY_FLOOR_S" in src and "min_latency_s" in src
    assert LATENCY_FLOOR_S > 0


# =====================================================================================
# F-7 — the commit gate
# =====================================================================================
SHAPES = [
    # (name, result, legal, committable)
    ("accepted", ValidationResult(True, "words", ("c1",), (), False, False), True, True),
    ("template accepted", ValidationResult(True, "words", ("c1",), (), True, False), True, True),
    ("draft-level fallback", ValidationResult(False, "plan words", ("c1",), ("LENGTH_BAND",), True, False), True, True),
    ("plan-level rejection", ValidationResult(False, "", (), ("SOLUTION_LEAK",), False, True), True, False),
    ("ok and rejected", ValidationResult(True, "w", ("c1",), (), False, True), False, False),
    ("ok with violations", ValidationResult(True, "w", ("c1",), ("LENGTH_BAND",), False, False), False, False),
    ("rejected carrying text", ValidationResult(False, "w", (), ("SOLUTION_LEAK",), False, True), False, False),
    ("rejected carrying claims", ValidationResult(False, "", ("c1",), ("SOLUTION_LEAK",), False, True), False, False),
    ("neither ok nor rejected", ValidationResult(False, "w", ("c1",), ("LENGTH_BAND",), False, False), False, False),
    ("failed without violations", ValidationResult(False, "w", ("c1",), (), True, False), False, False),
]


@pytest.mark.parametrize("name, result, legal, committable", SHAPES, ids=[s[0] for s in SHAPES])
def test_f7_result_integrity_classifies_every_shape(name, result, legal, committable):
    assert (result.integrity() is None) is legal
    assert result.committable is committable


def test_f7_the_hole_is_closed_a_non_ok_non_rejected_result_is_not_committed():
    """F-7's exact reproduction: the old gate was `if result.rejected: ... else: commit`, so
    `ok=False, rejected=False` — a validation FAILURE — was committed."""
    hole = ValidationResult(False, "smuggled text", ("d_c0_kitchen",), ("LENGTH_BAND",), False, False)
    assert hole.integrity() == "NEITHER_OK_NOR_REJECTED"
    r = ask(VANCE, DAVID, WHERE, renderer=lambda req: RenderOutcome(result=hole))
    assert r.rejected and r.state is VANCE and r.events == () and r.text == ""
    assert r.violations == ("RESULT_INTEGRITY:NEITHER_OK_NOR_REJECTED",)


@pytest.mark.parametrize("name, result, legal, committable",
                          [s for s in SHAPES if not s[2]], ids=[s[0] for s in SHAPES if not s[2]])
def test_f7_no_impossible_shape_reaches_the_ledger(name, result, legal, committable):
    r = ask(VANCE, DAVID, WHERE, renderer=lambda req: RenderOutcome(result=result))
    assert r.rejected and r.state is VANCE and r.events == ()
    assert r.violations[0].startswith("RESULT_INTEGRITY:")


def test_f7_the_two_legal_committing_shapes_still_commit():
    """The gate must not have become so strict that the real pipeline stops working."""
    accepted, _ = _render(faithful(0))
    assert not accepted.rejected and not accepted.fallback
    bad = draft_json(K, L, ("Colonel Mustard can vouch.", [], "color"))
    fell_back, _ = _render(bad)
    assert not fell_back.rejected and fell_back.fallback
    assert [c.id for c in fell_back.state.decision.statements.all()[-1].claims] == ["d_c0_kitchen", "d_c0_lib"]


def test_f7_a_plan_level_rejection_still_rejects_with_its_own_violations():
    """The rejected path keeps its own codes — the integrity check must not mask them."""
    rejected = ValidationResult(False, "", (), ("SOLUTION_LEAK", "UNKNOWABLE_CLAIM:At"), False, True)
    r = ask(VANCE, DAVID, WHERE, renderer=lambda req: RenderOutcome(result=rejected))
    assert r.rejected and r.violations == ("SOLUTION_LEAK", "UNKNOWABLE_CLAIM:At")


# =====================================================================================
# F-8 — the rate window
# =====================================================================================
def test_f8_rate_window_counts_only_the_trailing_window():
    now = 1000.0
    inside = [now - 1, now - 30, now - 59.9]
    outside = [now - 60.1, now - 600, now - 10_000]
    assert rate_window(inside + outside, now) == 3
    assert rate_window([], now) == 0
    assert rate_window(outside, now) == 0


def test_f8_the_limiter_throttles_at_the_limit_and_then_recovers():
    from eidolon.llm.ingress import screen
    burst = [100.0 + i * 0.1 for i in range(RATE_LIMIT)]
    assert screen("hi", turns_in_window=rate_window(burst[:-1], 110.0)).blocked is None   # turn 30
    assert screen("hi", turns_in_window=rate_window(burst, 110.0)).blocked == "RATE_LIMIT"  # turn 31
    later = burst[-1] + RATE_WINDOW_S + 1
    assert rate_window(burst, later) == 0
    assert screen("hi", turns_in_window=rate_window(burst, later)).blocked is None


def _play(lines, step, parse=None):
    """Drive the real CLI with an injected clock that advances `step` seconds per read."""
    from eidolon.cli import main
    import builtins
    parse = parse or json.dumps({"kind": "ask", "query_kind": "did_you", "subject": "David"})
    it = iter(list(lines) + ["quit"])
    old_input, builtins.input = builtins.input, lambda prompt="": next(it)
    state = {"t": 0.0}

    def clock():
        state["t"] += step
        return state["t"]
    t = ScriptedTransport(generate=[faithful(0)], verify=[approve], parse=[parse], repeat_last=True)
    buf, old = io.StringIO(), __import__("sys").stdout
    try:
        __import__("sys").stdout = buf
        main(["play"], transport=t, clock=clock)
    finally:
        __import__("sys").stdout = old
        builtins.input = old_input
    out = buf.getvalue()
    return out.count("David: "), out.count("could not be completed"), t


def test_f8_a_burst_is_throttled_the_protection_is_preserved():
    answered, refused, _ = _play(["Did you touch the knife?"] * 40, step=0.1)
    assert (answered, refused) == (RATE_LIMIT, 10)


def test_f8_at_human_pace_the_session_runs_past_turn_thirty():
    """The latch is what F-8 was: turn 31 was refused and so was every turn after it, forever."""
    answered, refused, _ = _play(["Did you touch the knife?"] * 40, step=5.0)
    assert (answered, refused) == (40, 0)


def test_f8_a_three_hundred_turn_session_is_possible_through_the_shipped_entry_point():
    """The roadmap's Phase 5 exit measurement is a 300-turn session. It could not be run at all."""
    answered, refused, _ = _play(["Did you touch the knife?"] * 300, step=5.0)
    assert (answered, refused) == (300, 0)


# =====================================================================================
# F-9 — least privilege through the CLI
# =====================================================================================
def test_f9_a_fresh_session_has_encountered_only_the_addressee():
    from eidolon.cli import encountered
    state = build_demo_state()
    assert state.discovery.known_evidence == frozenset()
    assert encountered(state, DEMO_DAVID) == frozenset({DEMO_DAVID})


def test_f9_the_parser_is_not_told_the_cast_the_locations_or_the_weapon():
    """F-9's exact reproduction: `known = {*actors, *locations, *objects}` named every one of them
    in the very first parse prompt, before the player had discovered anything."""
    _, _, t = _play(["Did you touch the knife?"], step=5.0)
    doc = json.loads(next(r for r in t.requests if r.role == "parse").user)
    assert doc["known_names"] == ["David Kessler"]
    case = build_demo_state().case
    for hidden in ("Harold Vance", "a kitchen knife", "the hall", "the kitchen", "the study"):
        assert hidden not in doc["known_names"]


def test_f9_discovery_is_what_widens_the_set_not_mere_existence():
    """Presenting the knife discovers it, and only then do its entities become referable."""
    from eidolon.cli import encountered
    state = build_demo_state()
    after = ask(state, DEMO_DAVID, Query(kind="challenge", raw="present"), presented_ref="E_knife").state
    assert "E_knife" in after.discovery.known_evidence
    grown = encountered(after, DEMO_DAVID)
    assert grown > encountered(state, DEMO_DAVID)
    assert "Knife" in grown


# =====================================================================================
# F-10 — guards that no test pinned
# =====================================================================================
def _seg(text="x", ids=(), kind="color"):
    return {"text": text, "claim_ids": list(ids), "kind": kind}


@pytest.mark.parametrize("payload, code", [
    (json.dumps({"segments": [_seg()] * (MAX_SEGMENTS + 1)}), "SEGMENTS"),
    (json.dumps({"segments": [_seg("x" * (MAX_SEGMENT_CHARS + 1))]}), "TEXT"),
    (json.dumps({"segments": [_seg(ids=["c"] * (MAX_IDS + 1), kind="assert")]}), "CLAIM_IDS"),
    (json.dumps({"segments": [_seg("a" * 100)] * 400}), "TOO_LARGE"),
], ids=["segment_count", "segment_length", "claim_ids_per_segment", "raw_size"])
def test_f10_each_wire_cap_refuses_with_its_own_code(payload, code):
    """All four caps worked; none was named in any test, so removing one changed nothing visible.
    `raw_size` matters most: without the pre-parse cap a 32 000+ char VALID document is parsed."""
    with pytest.raises(MalformedOutput) as e:
        parse_draft(payload)
    assert e.value.code == code


def test_f10_the_raw_cap_runs_before_parsing_not_after():
    big = json.dumps({"segments": [_seg("a" * 100)] * 400})
    assert len(big) > MAX_RAW_CHARS
    with pytest.raises(MalformedOutput) as e:
        parse_draft(big)
    assert e.value.code == "TOO_LARGE"      # not NOT_JSON, not SEGMENTS: the size check is first


@pytest.mark.parametrize("payload, code", [
    (json.dumps({"segments": [_seg()] * MAX_SEGMENTS}), None),
    (json.dumps({"segments": [_seg("x" * MAX_SEGMENT_CHARS)]}), None),
], ids=["exactly_max_segments", "exactly_max_chars"])
def test_f10_the_caps_are_inclusive_at_the_limit(payload, code):
    assert parse_draft(payload) is not None


def test_f10_internal_tokens_covers_evidence_and_statement_ids_not_just_the_deny_set():
    """`internal_tokens` = prompt deny-set + this turn's claim ids + EVERY evidence and statement
    id. The last two are what stop a DISCOVERED evidence id or a ledger handle being spoken; both
    were removable without any test noticing."""
    state = ask(build_demo_state(), DEMO_DAVID, DEMO_ASK).state
    # The evidence must be DISCOVERED, or `prompt_deny_tokens` (which holds every UNdiscovered id)
    # supplies it anyway and the assertion is vacuous — mutation P5-53 survived an earlier version
    # of this test for exactly that reason.
    state = ask(state, DEMO_DAVID, Query(kind="challenge", raw="present"), presented_ref="E_knife").state
    ctx = state.ctx()
    from eidolon.decision.envelope import PersonaSlot, build_envelope
    from eidolon.decision.strategy import DeliveryDirective, ResponsePlan
    from eidolon.decision.validator import prompt_deny_tokens
    env = build_envelope(ResponsePlan(act="LIE", delivery=DeliveryDirective("x")),
                         persona=PersonaSlot(), digest=ConversationDigest(character=DEMO_DAVID, turns=1))
    tokens = internal_tokens(ctx, env)
    discovered = set(ctx.discovery.known_evidence)
    assert discovered, "nothing discovered would make the evidence assertion vacuous"
    assert discovered.isdisjoint(prompt_deny_tokens(ctx)), "a discovered id must not be in the deny set"
    assert discovered <= tokens                                   # ...so only the evidence term can supply it
    assert {e.id for e in ctx.evidence.all()} <= tokens
    assert ctx.statements.all(), "there must be a statement, or the next assertion is vacuous"
    assert {s.id for s in ctx.statements.all()} <= tokens


def test_f10_the_deterministic_fallback_is_put_through_validation_too():
    """`_fallback` re-validates the template render. Skipping it would go unnoticed, because the
    template passes — the check exists so that a PLAN-level failure is still caught on that path."""
    src = inspect.getsource(LLMRenderer._fallback)
    assert "_validate" in src
    bad = draft_json(K, L, ("Colonel Mustard can vouch.", [], "color"))
    r, t = _render(bad)
    assert r.fallback and t.calls("generate") == 3
    assert r.render_audit[0].reason == "RENDER_EXHAUSTED"


# =====================================================================================
# F-11 — evidence identifiers in the digest
# =====================================================================================
def test_f11_the_digest_the_model_reads_carries_no_engine_evidence_id():
    """F-11's exact reproduction: the digest rendered `Presented: E_knife.`"""
    s0 = ask(build_demo_state(), DEMO_DAVID, DEMO_ASK).state
    s1 = ask(s0, DEMO_DAVID, Query(kind="challenge", raw="present"), presented_ref="E_knife").state
    t = scripted([faithful(0)], repeat_last=True)
    ask(s1, DEMO_DAVID, DEMO_ASK, renderer=renderer(t))
    digest = json.loads(next(q for q in t.requests if q.role == "generate").user)["digest"]
    assert "E_knife" not in digest
    assert "Presented: the fingerprint on a kitchen knife." in digest


def test_f11_an_undiscovered_id_gets_no_label_and_cannot_describe_itself():
    """Labels are built from DISCOVERED evidence only, so an id that reached `evidence_presented`
    without being discovered renders as a placeholder rather than telling the model what it is."""
    state = build_demo_state()
    labels = evidence_labels(state.evidence, state.case, state.discovery.known_evidence)
    assert labels == {}, "nothing is discovered at the start of the demo case"
    digest = ConversationDigest(character=DEMO_DAVID, turns=1, evidence_presented=("E_knife",))
    assert render_digest(digest, labels) == "1 turn(s) so far. Presented: an item."
    assert "E_knife" not in render_digest(digest, labels)
    assert "knife" not in render_digest(digest, labels).lower()


def test_f11_labels_are_display_level_never_identifiers():
    s1 = ask(build_demo_state(), DEMO_DAVID, Query(kind="challenge", raw="present"),
             presented_ref="E_knife").state
    labels = evidence_labels(s1.evidence, s1.case, s1.discovery.known_evidence)
    assert labels == {"E_knife": "the fingerprint on a kitchen knife"}
    for label in labels.values():
        assert not any(i in label for i in s1.case.objects)      # no ObjectId
        assert "E_" not in label


def test_f11_the_envelope_audit_recomputes_the_labels_rather_than_trusting_them():
    """A forged digest_text must still be caught: the audit renders its own and compares."""
    s1 = ask(build_demo_state(), DEMO_DAVID, Query(kind="challenge", raw="present"),
             presented_ref="E_knife").state
    from eidolon.decision.validator import audit_envelope
    from eidolon.decision.envelope import PersonaSlot, build_envelope
    from eidolon.decision.strategy import DeliveryDirective, ResponsePlan
    plan = ResponsePlan(act="LIE", delivery=DeliveryDirective("x"))
    digest = ConversationDigest(character=DEMO_DAVID, turns=1, evidence_presented=("E_knife",))
    env = build_envelope(plan, persona=PersonaSlot(), digest=digest,
                         digest_labels=evidence_labels(s1.evidence, s1.case, s1.discovery.known_evidence))
    assert "ENVELOPE_DIGEST_NOT_SPEAKERS" not in audit_envelope(env, plan, (), digest, DEMO_DAVID, s1.ctx())
    forged = env.model_copy(update={"digest_text": "1 turn(s) so far. Presented: E_knife."})
    assert "ENVELOPE_DIGEST_NOT_SPEAKERS" in audit_envelope(forged, plan, (), digest, DEMO_DAVID, s1.ctx())


# =====================================================================================
# F-12 — a long session through the renderer, not the Phase 4 path
# =====================================================================================
N_TURNS = 300
N_ACCUSATIONS = 8
TOPICS = ("kitchen", "library", "study", "argument", "harold", "elena", "margaret")
# Scale note, mirroring `tests/decision/test_long_conversation.py`: §28.4/§28.5's numbers are
# 500-2 000 turns, and this file was run once in full at N_TURNS=2000/N_ACCUSATIONS=50 through
# `LLMRenderer` (all assertions held — see the Phase 5 repair report). The CHECKED-IN scale is
# 300/8 so the default suite stays fast, which is also the roadmap's own exit-criterion length.


def test_f12_a_long_session_through_the_renderer_never_diverges_from_the_engine():
    """F-12: `test_long_conversation.py` calls `run_ask_turn` with NO renderer — it is a Phase 4
    stress test. Nothing exercised the Phase 5 pipeline beyond 15 turns. The model here rotates
    through every reordering shape, so claim-order drift (F-1) would show up at scale too."""
    reference = live = VANCE
    shapes, fallbacks, rejected, drift = set(), 0, 0, None
    events: list = []
    for i in range(N_TURNS):
        provisional = i % (N_TURNS // N_ACCUSATIONS) == 0 and i > 0
        query = Query(kind="did_you", predicate_hint=TOPICS[i % len(TOPICS)],
                      raw=f"Tell me again about turn {i}, David.")
        kw = dict(provisional_accusation=provisional, hostile_tone=(i % 13 == 0))
        reference = run_ask_turn(reference, DAVID, query, **kw).state
        t = ScriptedTransport(generate=[reordering(REORDERINGS[i % len(REORDERINGS)])],
                              verify=[approve] * 9, repeat_last=True)
        result = run_ask_turn(live, DAVID, query, renderer=LLMRenderer(ModelLLM(t)), **kw)
        live = result.state
        fallbacks += bool(result.fallback)
        rejected += bool(result.rejected)
        events += [e for e in result.events if isinstance(e, (ClaimMade, LayerPeel, ClaimRetracted))]
        env = result.envelope
        shapes.add((len(env.allowed_claims), len(env.recent_exchange), len(env.retrieved_statements)))
        if drift is None and fingerprint(live) != fingerprint(reference):
            drift = i

    assert drift is None, f"engine state diverged from the template path at turn {drift}"
    assert (fallbacks, rejected) == (0, 0), "no fallback accumulation: every draft was valid"
    assert len(shapes) <= 4, f"envelope shape drifted with turn count: {shapes}"   # I-7
    assert live.decision.layer_peels == ()                                        # I-3: no evidence presented
    assert len(live.decision.statements.all()) == N_TURNS
    # claim order is the plan's on every one of the turns, not just the first
    assert [tuple(c.id for c in s.claims) for s in live.decision.statements.all()] == \
           [tuple(c.id for c in s.claims) for s in reference.decision.statements.all()]
    # ...and the whole session replays from its own events (I-22)
    folded = VANCE.decision
    for event in events:
        folded = apply_decision(folded, event)
    assert [(s.id, tuple(c.id for c in s.claims)) for s in folded.statements.all()] == \
           [(s.id, tuple(c.id for c in s.claims)) for s in live.decision.statements.all()]
