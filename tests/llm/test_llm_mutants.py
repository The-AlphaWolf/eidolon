"""§28.2 / Phase 5 exit: `MutantLLM` catch rate is 100% per violation class.

Classes flagged deterministic must be caught with a verifier that approves EVERYTHING (the point
of AC-8 / I-36: a label or a cooperative verifier cannot route content past the deterministic
layer). Classes that need a semantic judgement are caught by the verifier and only by it — the
test states that openly rather than pretending otherwise.
"""
from __future__ import annotations

import json

import pytest

from eidolon.decision.claims import Claim, Statement, StatementStore
from eidolon.decision.digest import ConversationDigest
from eidolon.decision.envelope import PersonaSlot, build_envelope
from eidolon.decision.llm import render_claim
from eidolon.decision.strategy import DeliveryDirective, ResponsePlan
from eidolon.decision.validator import validate_draft, verify_segments
from eidolon.llm.fakes import MUTATIONS, MutantLLM, ScriptedTransport
from eidolon.llm.render import ModelLLM
from eidolon.world.propositions import At, Solution
from tests.llm.llm_helpers import DAVID, build_initial_state

STATE = build_initial_state()
CASE = STATE.case
BLIND = lambda d, e, c: []                     # a verifier that approves everything

CLAIMS = (Claim(id="d_c0_kitchen", proposition=STATE.secrets.get("S_murder_david").cover.layers[0].claims[0].proposition,
                sincerity="deceptive", source="plan"),
          Claim(id="d_c0_lib", proposition=At(actor=DAVID, location="Library", interval=(5, 120)),
                sincerity="deceptive", source="plan"))
PLAN = ResponsePlan(act="LIE", claims=CLAIMS, delivery=DeliveryDirective("composed"))
ENV = build_envelope(PLAN, persona=PersonaSlot(), digest=ConversationDigest(character=DAVID, turns=0), query_text="?")

# Independent of the code under test: the violation each class must raise (or None: only a verifier sees it).
EXPECT = {
    "unknown_entity": "UNKNOWN_ENTITY", "known_unpermitted_entity": "UNKNOWN_ENTITY",
    "protected_fact": "CLAIM_ID_NOT_IN_ENVELOPE", "out_of_envelope_time": "TIME_SLOT_MISMATCH",
    "meta_text": "FORBIDDEN_VOCAB", "confession": "SELF_DISCLOSURE", "untagged_assertion": "UNTAGGED_ASSERTION",
    "slot_mismatch": "SLOT_MISMATCH", "nonverbal_leak": "NONVERBAL_LEAK",
    "assertion_mislabelled_color": "COLOR_CARRIES_CONTENT", "color_names_location": "COLOR_CARRIES_CONTENT",
    "color_names_time": "COLOR_CARRIES_CONTENT", "claim_omitted": "PLAN_CLAIM_OMITTED", "canary_leak": "CANARY_LEAK",
    "sincerity_label": "INTERNAL_TOKEN_LEAK", "length_fingerprint": "LENGTH_BAND",
    "tense_negation_inversion": None, "unreferenced_implicature": None,
}
DETERMINISTIC = sorted(n for n, (_, det) in MUTATIONS.items() if det)
SEMANTIC = sorted(n for n, (_, det) in MUTATIONS.items() if not det)


def _validate(draft, verify=BLIND, plan=PLAN, env=ENV, statements=StatementStore()):
    return validate_draft(draft, env, plan, DAVID, CASE, statements, ctx=STATE.ctx(), canary="EIDOLON-SESSION-CANARY", verify=verify)


def _mutant(name):
    return MutantLLM(name).generate(ENV, CASE, DAVID)


def test_every_class_in_the_architecture_has_a_mutant():
    """§28.2's list, including the three added in v0.3."""
    assert set(EXPECT) == set(MUTATIONS)
    assert {"assertion_mislabelled_color", "color_names_location", "color_names_time"} <= set(MUTATIONS)
    assert len(MUTATIONS) >= 18


def test_the_faithful_draft_is_accepted_so_a_mutant_failure_is_the_mutations_doing():
    from eidolon.decision.llm import TemplateLLM
    assert _validate(TemplateLLM().generate(ENV, CASE, DAVID), verify=verify_segments).ok


@pytest.mark.parametrize("name", DETERMINISTIC)
def test_class_is_caught_by_the_deterministic_checks_alone(name):
    draft = _mutant(name)
    result = _validate(draft)                              # blind verifier
    assert result.ok is False
    assert any(v.startswith(EXPECT[name]) for v in result.violations), (name, result.violations)
    assert result.text == " ".join(render_claim(c, CASE) for c in PLAN.claims)   # the deterministic render, never the mutant
    assert set(result.claim_ids) <= {c.id for c in PLAN.claims}
    assert not result.rejected and result.fallback          # a renderer failure: the plan itself was fine


@pytest.mark.parametrize("name", DETERMINISTIC)
def test_class_is_caught_by_the_default_pipeline_too(name):
    assert _validate(_mutant(name), verify=verify_segments).ok is False


@pytest.mark.parametrize("name", ["assertion_mislabelled_color", "color_names_location", "color_names_time"])
def test_the_three_v03_classes_never_depend_on_the_verifier(name):
    """T-13/T-14: caught by the deterministic checks even when the verifier approves everything, and the verifier is never asked."""
    called = []
    result = _validate(_mutant(name), verify=lambda *a: called.append(1) or [])
    assert not result.ok and called == []


def _scripted_verifier(verdicts):
    t = ScriptedTransport(verify=[json.dumps(verdicts)])
    return ModelLLM(t).verify


def test_tense_negation_inversion_needs_the_verifier():
    draft = _mutant("tense_negation_inversion")
    assert draft.segments[0].text == "I did use a drinking glass." and "I was not in the library" in draft.segments[1].text
    assert _validate(draft, verify=BLIND).ok is True        # nothing deterministic can see a polarity flip in-slot...
    assert _validate(draft, verify=verify_segments).ok is False   # ...the template path's re-render equality does
    verdicts = {"unreferenced_assertions": [], "segments": [
        {"index": 0, "asserts_exactly": False, "extra_assertions": [], "modality": "actual"},
        {"index": 1, "asserts_exactly": False, "extra_assertions": [], "modality": "actual"}]}
    result = _validate(draft, verify=_scripted_verifier(verdicts))
    assert not result.ok and any(v.startswith("ASSERTS_NOT_EXACTLY[0]") for v in result.violations)


def test_unreferenced_implicature_needs_the_verifier():
    draft = _mutant("unreferenced_implicature")
    assert _validate(draft, verify=BLIND).ok is True         # the documented residual: least privilege is the defense (§33.3)
    verdicts = {"unreferenced_assertions": [], "segments": [
        {"index": 0, "asserts_exactly": True, "extra_assertions": [], "modality": "actual"},
        {"index": 1, "asserts_exactly": True, "extra_assertions": [], "modality": "actual"},
        {"index": 2, "asserts_exactly": True, "extra_assertions": ["implies someone is untrustworthy"], "modality": "actual"}]}
    result = _validate(draft, verify=_scripted_verifier(verdicts))
    assert not result.ok and any(v.startswith("EXTRA_ASSERTION[2]") for v in result.violations)


def test_catch_rate_is_one_hundred_percent_per_class():
    caught = {n: (not _validate(_mutant(n), verify=verify_segments).ok) for n in DETERMINISTIC}
    assert all(caught.values()), [n for n, c in caught.items() if not c]


# ---- plan-level classes (the PLAN is the mutant; no rendering can fix them) ----------------
def _plan_env(plan):
    return plan, build_envelope(plan, persona=PersonaSlot(), digest=ConversationDigest(character=DAVID, turns=1), query_text="?")


def _faithful(env):
    from eidolon.decision.llm import TemplateLLM
    return TemplateLLM().generate(env, CASE, DAVID)


def test_contradiction_with_a_prior_claim_and_a_jointly_infeasible_set_reject_the_turn():
    prior = Claim(id="prior", proposition=At(actor=DAVID, location="Kitchen", interval=(0, 20)), sincerity="truthful", source="plan")
    new = Claim(id="new", proposition=At(actor=DAVID, location="Study", interval=(0, 20)), sincerity="deceptive", source="plan")
    plan, env = _plan_env(ResponsePlan(act="LIE", claims=(new,), delivery=DeliveryDirective("x")))
    store = StatementStore([Statement(id="S1", turn=1, speaker=DAVID, text="t", claims=(prior,), act="LIE")])
    result = _validate(_faithful(env), plan=plan, env=env, statements=store)
    assert result.rejected and result.claim_ids == () and {"JOINTLY_INFEASIBLE"} <= set(result.violations)
    assert any(v.startswith("CONTRADICTS_PRIOR") for v in result.violations)


def test_hypothetical_stated_as_actual_rejects_the_turn():
    c = Claim(id="h", proposition=At(actor=DAVID, location="Study", interval=(0, 20)), sincerity="truthful", source="plan", modality="actual")
    plan, env = _plan_env(ResponsePlan(act="HYPOTHETICAL", claims=(c,), delivery=DeliveryDirective("imagines")))
    result = _validate(_faithful(env), plan=plan, env=env)
    assert result.rejected and "HYPOTHETICAL_STATED_AS_ACTUAL" in result.violations


def test_a_solution_in_the_plan_outside_a_confession_rejects_the_turn():
    sol = Claim(id="sol", proposition=Solution(murderer=DAVID, method="bookend", location="Study", interval=(71, 72), motive_kind="money"),
                sincerity="truthful", source="plan")
    plan, env = _plan_env(ResponsePlan(act="LIE", claims=(sol,), delivery=DeliveryDirective("x")))
    result = _validate(_faithful(env), plan=plan, env=env)
    assert result.rejected and "SOLUTION_LEAK" in result.violations and result.claim_ids == ()
