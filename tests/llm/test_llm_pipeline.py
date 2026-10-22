"""The render pipeline end to end (§12.1 stages 7-11, §14): free wording accepted, bounded repair,
deterministic fallback, fail-closed, and — the point of Phase 5 — that the model's words never
change what the engine decided. The reference for "what the engine decided" is the Phase 4
`TemplateLLM` path, a separate implementation.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from eidolon.decision.claims import Claim, Statement, StatementStore
from eidolon.decision.digest import ConversationDigest
from eidolon.decision.envelope import PersonaSlot, build_envelope
from eidolon.decision.events import ClaimMade, ClaimRetracted, LayerPeel, apply_decision
from eidolon.decision.query import Query
from eidolon.decision.strategy import DeliveryDirective, ResponsePlan
from eidolon.decision.validator import canonical_text
from eidolon.decision.turn import CANARY, RenderRequest
from eidolon.llm.fakes import ScriptedTransport
from eidolon.llm.provider import Completion, ProviderError, ProviderRefusal, ProviderTimeout
from eidolon.llm.render import LLMRenderer, ModelLLM, PlayerTurn, player_view
from eidolon.world.propositions import At
from tests.llm.llm_helpers import (
    DAVID, DEMO_ASK, DEMO_DAVID, ELENA, MARGARET, WHERE, approve, ask, build_demo_state, build_initial_state,
    draft_json, faithful, fingerprint, reject_all, renderer, scripted,
)

STATE = build_initial_state()
BASE = ask(STATE, DAVID, WHERE)          # Phase 4 reference: LIE, template text
TEMPLATE_TEXT = BASE.text

GOOD = "GOOD"  # placeholder: replaced by `faithful()`
INVENTED = draft_json(("I never use a drinking glass.", ["d_c0_kitchen"], "assert"),
                      ("I was in the library from 00:05 until 02:00.", ["d_c0_lib"], "assert"),
                      ("Colonel Mustard can vouch for me.", [], "color"))


def _run(gen, verify=None, *, state=STATE, who=DAVID, query=WHERE, repeat_last=False, **kw):
    t = scripted(gen, verify, repeat_last=repeat_last)
    return ask(state, who, query, renderer=renderer(t, **kw)), t


# ---- accepted -----------------------------------------------------------------------------
@pytest.mark.parametrize("style", [0, 1, 2])
def test_free_wording_is_accepted_with_one_generation_and_one_verification(style):
    r, t = _run([faithful(style)])
    audit = r.render_audit[0]
    assert (audit.outcome, [a.outcome for a in audit.attempts]) == ("accepted", ["accepted"])
    assert (t.calls("generate"), t.calls("verify")) == (1, 1)
    assert r.rejected is False and r.fallback is False


def test_the_text_the_player_sees_is_the_models_and_the_claims_committed_are_the_plans():
    r, _ = _run([faithful(0)])
    assert r.text.startswith("Well, I never use a drinking glass.") and r.text != TEMPLATE_TEXT
    stmt = r.state.decision.statements.all()[-1]
    assert stmt.text == r.text
    assert [c.id for c in stmt.claims] == [c.id for c in BASE.state.decision.statements.all()[-1].claims] == ["d_c0_kitchen", "d_c0_lib"]


# ---- determinism: the words vary, the decisions do not ------------------------------------
def test_engine_decisions_are_identical_whatever_the_wording():
    texts = set()
    for style in (0, 1, 2):
        r, _ = _run([faithful(style)])
        assert r.plan_act == BASE.plan_act == "LIE"
        assert fingerprint(r.state) == fingerprint(BASE.state)
        assert [type(e).__name__ for e in r.events] == [type(e).__name__ for e in BASE.events]
        texts.add(r.text)
    assert len(texts) == 3


def test_a_multi_turn_session_with_a_concession_decides_identically_on_both_paths():
    """Ask, present the knife (peel + concession), ask again. Wording differs per turn and per path;
    act, claims, peels, retractions, character and epistemic state must not."""
    script = [(DEMO_ASK, None), (Query(kind="challenge", raw="present"), "E_knife"), (DEMO_ASK, None)]
    ref = live = build_demo_state()
    for i, (q, ref_id) in enumerate(script):
        ref = ask(ref.state if hasattr(ref, "state") else ref, DEMO_DAVID, q, presented_ref=ref_id)
        t = scripted([faithful(i)], repeat_last=True)
        live = ask(live.state if hasattr(live, "state") else live, DEMO_DAVID, q, presented_ref=ref_id, renderer=renderer(t))
        assert (live.plan_act, live.rejected) == (ref.plan_act, ref.rejected)
        assert fingerprint(live.state) == fingerprint(ref.state)
    assert ref.state.decision.layer_peels and live.state.decision.layer_peels == ref.state.decision.layer_peels
    assert live.render_audit[0].outcome == "accepted"


def test_fallback_turns_decide_identically_too():
    """A session in which the model fails every third turn: the engine's state matches the all-template run turn for turn."""
    queries = [WHERE, Query(kind="did_you", predicate_hint="kitchen", raw="Were you in the kitchen?"),
               Query(kind="opinion", raw="What do you make of it?"), WHERE, Query(kind="smalltalk", raw="Nice house.")] * 3
    ref, live = STATE, STATE
    for i, q in enumerate(queries):
        ref = ask(ref, DAVID, q).state
        gen = [ProviderRefusal("x")] * 3 if i % 3 == 2 else [faithful(i)]
        r = ask(live, DAVID, q, renderer=renderer(scripted(gen, repeat_last=True)))
        live = r.state
        assert not r.rejected
        assert fingerprint(live) == fingerprint(ref)


def test_replaying_the_recorded_events_rebuilds_the_same_decision_state_i22():
    """The fold applies recorded outcomes only; it never re-runs the renderer, the strategy or the model."""
    state, events = build_demo_state(), []
    for i, (q, ref_id) in enumerate([(DEMO_ASK, None), (Query(kind="challenge", raw="p"), "E_knife"), (DEMO_ASK, None)]):
        r = ask(state, DEMO_DAVID, q, presented_ref=ref_id, renderer=renderer(scripted([faithful(i)], repeat_last=True)))
        state = r.state
        events += [e for e in r.events if isinstance(e, (ClaimMade, LayerPeel, ClaimRetracted))]
    folded = build_demo_state().decision
    for e in events:
        folded = apply_decision(folded, e)
    assert [(s.id, s.text, tuple(c.id for c in s.claims), s.retracted_by) for s in folded.statements.all()] == \
           [(s.id, s.text, tuple(c.id for c in s.claims), s.retracted_by) for s in state.decision.statements.all()]
    assert folded.layer_peels == state.decision.layer_peels


def test_a_model_that_drops_the_concession_cannot_stop_it_being_voiced():
    """The engine recorded the peel; a draft that omits the conceded claim is repaired, then the template speaks it."""
    s0 = ask(build_demo_state(), DEMO_DAVID, DEMO_ASK).state
    omit = draft_json(("Well, that is all I have to say about it.", [], "color"))
    r = ask(s0, DEMO_DAVID, Query(kind="challenge", raw="p"), presented_ref="E_knife",
            renderer=renderer(scripted([omit], repeat_last=True)))
    assert r.plan_act == "CONCESSION" and r.fallback is True and not r.rejected
    assert "did touch a kitchen knife" in r.text
    assert r.state.decision.layer_peels


def test_default_path_is_unchanged_and_carries_no_audit():
    assert BASE.render_audit == () and BASE.fallback is False


# ---- repair -------------------------------------------------------------------------------
def test_a_bad_draft_is_repaired_once_and_the_bad_draft_is_never_shown():
    r, t = _run([INVENTED, faithful(0)])
    audit = r.render_audit[0]
    assert [a.outcome for a in audit.attempts] == ["repair", "accepted"]
    assert "Mustard" not in r.text and audit.attempts[0].violations[0].startswith("UNKNOWN_ENTITY[2]")
    assert (t.calls("generate"), t.calls("verify")) == (2, 1)   # only the draft that survived is verified
    first, second = (json.loads(q.user) for q in t.requests if q.role == "generate")
    assert first["revise"] == []
    # F-2: the feedback names the SEGMENT and nothing else. It used to render the violation's
    # detail ("remove the reference to Colonel, Mustard"), which for a guessed real entity became
    # that entity's canonical display name.
    assert second["revise"] == ["Segment 2: it names something that is not in names; remove that reference and keep everything else."]
    assert "Mustard" not in second["revise"][0] and "Colonel" not in second["revise"][0]


def test_repair_feedback_says_what_was_written_never_why():
    r, t = _run([INVENTED, faithful()])
    fb = json.loads([q for q in t.requests if q.role == "generate"][1].user)["revise"]
    blob = " ".join(fb).lower()
    for why in ("because", "not allowed", "forbidden", "secret", "does not know", "doesn't know", "unknown", "leak", "murder"):
        assert why not in blob


def test_repair_is_bounded_and_then_the_template_speaks_the_same_plan():
    r, t = _run([INVENTED], repeat_last=True)
    audit = r.render_audit[0]
    assert audit.outcome == "fallback" and len(audit.attempts) == 3 and t.calls("generate") == 3
    assert t.calls("verify") == 0                       # the verifier never saw a draft that failed a deterministic check
    assert r.fallback is True and r.text == TEMPLATE_TEXT and fingerprint(r.state) == fingerprint(BASE.state)


@pytest.mark.parametrize("repairs", [0, 1, 2, 5])
def test_generation_calls_are_bounded_by_max_repairs(repairs):
    r, t = _run([INVENTED], repeat_last=True, max_repairs=repairs)
    assert t.calls("generate") == 1 + repairs and r.fallback


# ---- fail closed: timeout, provider error, verifier failure -------------------------------
def _assert_untouched(r, state=STATE):
    assert r.rejected is True and r.text == "" and r.events == () and r.state is state
    assert r.state.turn_counter == state.turn_counter and fingerprint(r.state) == fingerprint(state)


def test_generation_timeout_rejects_the_turn_and_does_not_retry_silently():
    r, t = _run([ProviderTimeout("slow")])
    _assert_untouched(r)
    assert r.violations == ("PROVIDER_TIMEOUT",) and t.calls("generate") == 1
    assert r.render_audit[0].outcome == "rejected" and r.render_audit[0].reason == "PROVIDER_TIMEOUT"


def test_provider_error_rejects_the_turn():
    r, t = _run([ProviderError("503")])
    _assert_untouched(r)
    assert r.violations == ("PROVIDER_ERROR",) and t.calls("generate") == 1


def test_a_timeout_during_repair_rejects_and_the_earlier_bad_draft_is_not_shown():
    r, t = _run([INVENTED, ProviderTimeout("slow")])
    _assert_untouched(r)
    assert "Mustard" not in r.text and t.calls("generate") == 2


def test_verifier_timeout_fails_closed_even_though_the_draft_was_fine():
    r, _ = _run([faithful()], verify=[ProviderTimeout("slow")])
    _assert_untouched(r)
    assert r.violations == ("PROVIDER_TIMEOUT",)


def test_verifier_malformed_output_fails_closed():
    for bad, code in [("not json", "NOT_JSON"), ('{"segments": []}', "VERIFIER_FIELDS"),
                      (json.dumps({"segments": [], "unreferenced_assertions": []}), "VERIFIER_SHAPE")]:
        r, _ = _run([faithful()], verify=[bad])
        _assert_untouched(r)
        assert r.violations == (f"VERIFIER_MALFORMED:{code}",)


def test_verifier_verdict_with_the_wrong_shape_fails_closed():
    def wrong(req):
        return json.dumps({"unreferenced_assertions": [], "segments": [
            {"index": 5, "asserts_exactly": True, "extra_assertions": [], "modality": "actual"}] * 2})
    r, _ = _run([faithful()], verify=[wrong])
    _assert_untouched(r)
    assert r.violations == ("VERIFIER_MALFORMED:VERIFIER_VERDICT",)


def test_verifier_objection_triggers_repair_and_the_stricter_of_two_providers_wins():
    r, t = _run([faithful(0), faithful(1)], verify=[reject_all, approve])
    assert [a.outcome for a in r.render_audit[0].attempts] == ["repair", "accepted"]
    assert r.render_audit[0].attempts[0].violations[0].startswith("ASSERTS_NOT_EXACTLY")
    r2, t2 = _run([faithful()], verify=[reject_all], repeat_last=True)
    assert r2.fallback and r2.text == TEMPLATE_TEXT and t2.calls("verify") == 3


@pytest.mark.parametrize("verdict, code", [
    ({"extra_assertions": ["he was seen leaving"]}, "EXTRA_ASSERTION[0]"),
    ({"modality": "hypothetical"}, "MODALITY_MISMATCH[0]"),
    ({"modality": "reported"}, "MODALITY_MISMATCH[0]"),
])
def test_verifier_findings_become_draft_level_violations(verdict, code):
    def v(req):
        segs = [{"index": s["index"], "asserts_exactly": True, "extra_assertions": [], "modality": "actual",
                 **(verdict if s["index"] == 0 else {})} for s in json.loads(req.user)["segments"]]
        return json.dumps({"unreferenced_assertions": [], "segments": segs})
    r, _ = _run([faithful()], verify=[v], repeat_last=True)
    assert r.fallback and code in r.render_audit[0].attempts[0].violations


def test_unreferenced_assertions_reported_by_the_verifier_are_violations():
    def v(req):
        segs = [{"index": s["index"], "asserts_exactly": True, "extra_assertions": [], "modality": "actual"}
                for s in json.loads(req.user)["segments"]]
        return json.dumps({"unreferenced_assertions": ["implies he was there"], "segments": segs})
    r, _ = _run([faithful()], verify=[v], repeat_last=True)
    assert r.fallback and "UNREFERENCED_ASSERTION" in r.render_audit[0].attempts[0].violations


# ---- refusal and malformed output ---------------------------------------------------------
def test_refusal_is_a_renderer_failure_asked_again_then_the_template_speaks():
    r, t = _run([ProviderRefusal("policy")], repeat_last=True)
    assert r.fallback and r.text == TEMPLATE_TEXT and t.calls("generate") == 3
    assert {a.outcome for a in r.render_audit[0].attempts} == {"refused"}


def test_refusal_then_a_good_draft_is_accepted():
    r, _ = _run([ProviderRefusal("policy"), faithful()])
    assert [a.outcome for a in r.render_audit[0].attempts] == ["refused", "accepted"] and not r.fallback


@pytest.mark.parametrize("payload", [
    "```json\n{}\n```", "not json at all", '{"segments": [', '{"segments": {}}', '["segments"]', "null", "",
    '{"segments": [{"text": "x"}]}', '{"segments": [{"text": 1, "claim_ids": [], "kind": "color"}]}',
    '{"segments": [{"text": "x", "claim_ids": "c1", "kind": "assert"}]}',
    '{"segments": [{"text": "x", "claim_ids": [], "kind": "shout"}]}',
    Completion(text="", stop_reason="max_tokens"),
])
def test_malformed_output_is_repaired_then_falls_back_and_nothing_malformed_is_shown(payload):
    r, t = _run([payload], repeat_last=True)
    assert r.fallback and r.text == TEMPLATE_TEXT and fingerprint(r.state) == fingerprint(BASE.state)
    assert {a.outcome for a in r.render_audit[0].attempts} == {"malformed"}
    assert t.calls("verify") == 0


# ---- plan-level failures are not repairable -----------------------------------------------
def _contradicted_request():
    prior = Claim(id="old", proposition=At(actor="David", location="Study", interval=(5, 10)), sincerity="deceptive", source="plan")
    new = Claim(id="new", proposition=At(actor="David", location="Kitchen", interval=(5, 10)), sincerity="deceptive", source="plan")
    plan = ResponsePlan(act="LIE", claims=(new,), delivery=DeliveryDirective("composed"))
    statements = StatementStore([Statement(id="s0", turn=0, speaker="David", text="prior", claims=(prior,), act="LIE")])
    env = build_envelope(plan, persona=PersonaSlot(), digest=ConversationDigest(character="David", turns=1), query_text="?")
    return RenderRequest(env, plan, "David", STATE.case, statements, STATE.ctx(), frozenset(), CANARY, frozenset())


def test_a_plan_that_contradicts_the_record_is_rejected_not_repaired_and_never_falls_back():
    t = scripted([faithful()], repeat_last=True)
    out = renderer(t)(_contradicted_request())
    assert out.result.rejected and out.result.text == "" and out.result.claim_ids == ()
    assert "CONTRADICTS_PRIOR:old" in out.result.violations
    assert t.calls("generate") == 1 and out.audit[0].outcome == "rejected" and out.audit[0].reason == "PLAN_LEVEL"


# ---- latency floor (I-42) -----------------------------------------------------------------
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
            if isinstance(item, BaseException):
                raise item
            return item(req) if callable(item) else item
        return f


@pytest.mark.parametrize("name", ["accepted", "fallback", "rejected", "timeout"])
def test_every_outcome_takes_the_same_floor_so_speed_does_not_tell_the_act(name):
    clock = Clock()
    gens = {"accepted": [clock.slow(0.3, faithful())], "fallback": [clock.slow(0.3, INVENTED)] * 3,
            "rejected": [clock.slow(0.3, ProviderError("x"))], "timeout": [clock.slow(0.3, ProviderTimeout("x"))]}
    t = ScriptedTransport(generate=gens[name], verify=[approve])
    r = ask(STATE, DAVID, WHERE, renderer=LLMRenderer(ModelLLM(t), min_latency_s=2.0, clock=clock, sleep=clock.sleep))
    assert clock.t == pytest.approx(2.0)


def test_a_slow_provider_is_not_padded_further():
    clock = Clock()
    t = ScriptedTransport(generate=[clock.slow(5.0, faithful())], verify=[approve])
    ask(STATE, DAVID, WHERE, renderer=LLMRenderer(ModelLLM(t), min_latency_s=2.0, clock=clock, sleep=clock.sleep))
    assert clock.t == pytest.approx(5.0)


# ---- audit --------------------------------------------------------------------------------
def test_audit_records_every_call_without_the_prompts():
    r, t = _run([INVENTED, faithful()])
    audit = r.render_audit[0]
    assert [(c.role, c.effort) for c in audit.calls] == [("generate", "medium"), ("generate", "medium"), ("verify", "low")]
    assert all(len(c.prompt_hash) == 16 and c.stop_reason == "end_turn" for c in audit.calls)
    assert [c.prompt_hash for c in audit.calls] == [q.prompt_hash for q in t.requests]
    blob = json.dumps(dataclasses.asdict(audit), default=str)
    for prompt_text in ("player_query", "Where were you at ten", "SYSTEM", "Session token"):
        assert prompt_text not in blob


def test_audit_keeps_every_draft_for_the_trace():
    r, _ = _run([INVENTED, faithful()])
    a0, a1 = r.render_audit[0].attempts
    assert "Mustard" in a0.draft.segments[2].text and a1.draft is not None


# ---- the player's view --------------------------------------------------------------------
def test_player_view_is_text_and_ok_only():
    assert {f.name for f in dataclasses.fields(PlayerTurn)} == {"text", "ok"}


def test_a_fallback_is_indistinguishable_from_a_model_render_to_the_player():
    """I-12: fallback renders are marked in the trace, never to the player."""
    fb, _ = _run([INVENTED], repeat_last=True)
    ok, _ = _run([faithful(2)])
    assert fb.fallback and not ok.fallback
    pf, po = player_view(fb), player_view(ok)
    assert type(pf) is type(po) and pf.ok is po.ok is True
    assert set(dataclasses.asdict(pf)) == set(dataclasses.asdict(po))


def test_rejected_turn_projects_to_the_out_of_world_retry_only():
    r, _ = _run([ProviderTimeout("x")])
    assert player_view(r) == PlayerTurn(text="", ok=False)


def test_player_projection_carries_no_engine_field_or_value():
    for gen, kw in [([faithful(1)], {}), ([INVENTED], {"repeat_last": True})]:
        r, _ = _run(gen, **kw)
        blob = json.dumps(dataclasses.asdict(player_view(r)))
        for engine in ("LIE", "plan_act", "violations", "fallback", "d_c0", "claim", "sincerity", "S_murder", "audit"):
            assert engine not in blob


# ---- equal length (I-42, I-35, §22.3) ------------------------------------------------------
def _plan_over(prop, act, sincerity):
    return ResponsePlan(act=act, claims=(Claim(id="c1", proposition=prop, sincerity=sincerity, source="plan"),),
                        delivery=DeliveryDirective("same"))


def _req(plan, query="?"):
    env = build_envelope(plan, persona=PersonaSlot(), digest=ConversationDigest(character="David", turns=0), query_text=query)
    return RenderRequest(env, plan, "David", STATE.case, STATE.decision.statements, STATE.ctx(), frozenset(), CANARY, frozenset())


LONG = "It has been a long and wearying evening for everyone in this house, and I would rather not dwell on it. " * 3


def test_the_length_band_is_the_same_for_a_lie_and_a_truth_about_the_same_proposition():
    prop = At(actor="David", location="Library", interval=(5, 60))
    windows = set()
    for act, sinc in (("LIE", "deceptive"), ("TRUTH", "truthful"), ("SINCERE_FALSE", "sincere_false")):
        t = scripted([faithful()])
        out = renderer(t)(_req(_plan_over(prop, act, sinc)))
        assert out.result.ok
        doc = json.loads(t.requests[0].user)
        windows.add((doc["min_chars"], doc["max_chars"]))
    assert windows == {(0, 199)}


def test_a_long_reply_for_a_deceptive_plan_and_a_short_one_for_an_honest_plan_are_both_out_of_band():
    """The fingerprint attack: verbose when lying, terse when honest. Both are held to the canonical band."""
    prop = At(actor="David", location="Library", interval=(5, 60))
    long_lie = draft_json(("I was in the library from 00:05 until 01:00. " + LONG, ["c1"], "assert"))
    for act, sinc in (("LIE", "deceptive"), ("TRUTH", "truthful")):
        t = scripted([long_lie], repeat_last=True)
        out = renderer(t)(_req(_plan_over(prop, act, sinc)))
        assert out.result.fallback and out.audit[0].attempts[0].violations == ("LENGTH_BAND[1!=0]",)


def test_a_reply_shorter_than_the_canonical_band_is_also_rejected():
    many = ResponsePlan(act="LIE", claims=tuple(
        Claim(id=f"c{i}", proposition=At(actor="David", location="Library", interval=(10 * i + 1, 10 * i + 9)),
              sincerity="deceptive", source="plan") for i in range(6)), delivery=DeliveryDirective("x"))
    assert len(canonical_text(_req(many).envelope, STATE.case)) >= 200
    curt = draft_json(*((f"I was in the library from {t1} until {t2}.", [f"c{i}"], "assert")
                        for i, (t1, t2) in enumerate([("00:01", "00:09"), ("00:11", "00:19"), ("00:21", "00:29"),
                                                       ("00:31", "00:39"), ("00:41", "00:49"), ("00:51", "00:59")])))
    ok = renderer(scripted([curt]))(_req(many))
    assert ok.result.ok                                     # the same words at the canonical length are accepted
    short = draft_json(*((f"I was in the library then.", [f"c{i}"], "assert") for i in range(6)))
    out = renderer(scripted([short], repeat_last=True))(_req(many))
    assert out.audit[0].attempts[0].violations[0].startswith("LENGTH_BAND[0!=1]")
    assert out.result.fallback


def test_accepted_texts_for_lie_and_truth_land_in_the_same_band():
    prop = At(actor="David", location="Library", interval=(5, 60))
    from eidolon.decision.validator import length_band
    bands = set()
    for act, sinc in (("LIE", "deceptive"), ("TRUTH", "truthful")):
        for style in (0, 1, 2):
            out = renderer(scripted([faithful(style)]))(_req(_plan_over(prop, act, sinc)))
            assert out.result.ok and not out.result.fallback
            bands.add(length_band(len(out.result.text)))
    assert bands == {0}


# ---- retries never mutate anything --------------------------------------------------------
def test_failed_attempts_leave_the_callers_state_untouched():
    before = fingerprint(STATE)
    for gen in ([INVENTED], [ProviderTimeout("x")], [ProviderRefusal("x")], ["nope"]):
        _run(gen, repeat_last=True)
    assert fingerprint(STATE) == before


@pytest.mark.parametrize("verifier_says, accepted", [("actual", True), ("negated", True), ("hypothetical", False), ("reported", False)])
def test_modality_is_compared_by_class_polarity_is_not_a_mismatch(verifier_says, accepted):
    """A claim asserted as its NEGATION ("I was not in...") and a DidNot claim ("I never...") are both
    'asserted'; a model may label either polarity. Only asserted-vs-hypothetical-vs-reported can mismatch;
    a polarity flip is `asserts_exactly`'s job."""
    neg = ResponsePlan(act="LIE", claims=(Claim(id="c1", proposition=At(actor="David", location="Library", interval=(5, 60)),
                                                 modality="negated", sincerity="deceptive", source="plan"),),
                       delivery=DeliveryDirective("x"))
    def verdict(req):
        return json.dumps({"unreferenced_assertions": [], "segments": [
            {"index": s["index"], "asserts_exactly": True, "extra_assertions": [], "modality": verifier_says}
            for s in json.loads(req.user)["segments"]]})
    out = renderer(scripted([faithful()], [verdict], repeat_last=True))(_req(neg))
    assert (out.audit[0].outcome == "accepted") is accepted
    if not accepted:
        assert out.audit[0].attempts[0].violations == ("MODALITY_MISMATCH[0]",)
