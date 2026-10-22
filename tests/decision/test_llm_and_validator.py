"""§14/§28.2: `TemplateLLM` and the deterministic half of the validator pipeline."""
from __future__ import annotations

from eidolon.decision.claims import Claim, StatementStore
from eidolon.decision.digest import ConversationDigest
from eidolon.decision.envelope import PersonaSlot, build_envelope
from eidolon.decision.llm import Draft, Segment, TemplateLLM, render_claim
from eidolon.decision.strategy import DeliveryDirective, ResponsePlan
from eidolon.decision.validator import validate_draft
from eidolon.world.propositions import At, DidNot, entities
from tests.world.fixtures.vance import vance_v03
from eidolon.decision.context import DecisionContext
from eidolon.decision.secrets import SecretStore
from eidolon.evidence.discovery import DiscoveryState
from eidolon.evidence.model import EvidenceStore
from eidolon.minds.belief import BeliefStore
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.knowledge import KnowledgeStore

CASE, _ = vance_v03()
# §14.2(e) reads the speaker's knowledge; these plans are David's own first-person claims.
CTX = DecisionContext(case=CASE, knowledge=KnowledgeStore(), beliefs=BeliefStore(), secrets=SecretStore(),
                      evidence=EvidenceStore(), statements=StatementStore(), epistemic=EpistemicState(),
                      discovery=DiscoveryState())


def _plan_and_envelope(claim_kind="At"):
    if claim_kind == "At":
        prop = At(actor="David", location="Library", interval=(5, 60))
    else:
        prop = DidNot(actor="David", action="touch", object="Glass1", interval=(0, 120))
    claim = Claim(id="c1", proposition=prop, sincerity="deceptive", source="plan")
    plan = ResponsePlan(act="LIE", claims=(claim,), delivery=DeliveryDirective(tone="composed"))
    digest = ConversationDigest(character="David", turns=1)
    envelope = build_envelope(plan, persona=PersonaSlot(), digest=digest)
    return plan, envelope


def test_template_llm_produces_faithful_tagged_segments():
    plan, envelope = _plan_and_envelope()
    draft = TemplateLLM().generate(envelope, CASE, "David")
    assert len(draft.segments) == 1
    seg = draft.segments[0]
    assert seg.claim_ids == ("c1",)
    assert "library" in seg.text


def test_validator_accepts_faithful_template_output():
    plan, envelope = _plan_and_envelope()
    draft = TemplateLLM().generate(envelope, CASE, "David")
    result = validate_draft(draft, envelope, plan, "David", CASE, StatementStore(), ctx=CTX)
    assert result.ok is True
    assert result.claim_ids == ("c1",)


def test_untagged_assertion_caught_deterministically_i36():
    plan, envelope = _plan_and_envelope()
    bad_draft = Draft(segments=(Segment(text="I was somewhere.", claim_ids=(), kind="assert"),))
    result = validate_draft(bad_draft, envelope, plan, "David", CASE, StatementStore(), ctx=CTX)
    assert result.ok is False
    assert any("UNTAGGED_ASSERTION" in v for v in result.violations)


def test_color_segment_naming_a_location_is_caught_i36_t14():
    """T-14's shape: a `color` segment naming a location is caught by the deterministic
    check alone, no LLM/verifier involved."""
    plan, envelope = _plan_and_envelope()
    bad_draft = Draft(segments=(
        Segment(text=render_claim(plan.claims[0], CASE), claim_ids=("c1",), kind="assert"),
        Segment(text="The Library always smelled of dust.", claim_ids=(), kind="color"),
    ))
    result = validate_draft(bad_draft, envelope, plan, "David", CASE, StatementStore(), ctx=CTX)
    assert result.ok is False
    assert any("COLOR_CARRIES_CONTENT" in v for v in result.violations)


def test_mislabelled_assertion_as_color_still_caught_i36_t13():
    """T-13's shape: an assertion mislabelled `kind="color"` is caught by the deterministic
    slot check, with no verifier needed — the label buys no exemption (AC-8)."""
    plan, envelope = _plan_and_envelope()
    bad_draft = Draft(segments=(
        Segment(text=render_claim(plan.claims[0], CASE), claim_ids=(), kind="color"),
    ))
    result = validate_draft(bad_draft, envelope, plan, "David", CASE, StatementStore(), ctx=CTX)
    assert result.ok is False
    assert any("COLOR_CARRIES_CONTENT" in v for v in result.violations)


def test_slot_mismatch_different_location_caught():
    plan, envelope = _plan_and_envelope()
    bad_draft = Draft(segments=(
        Segment(text="I was in the kitchen the whole time.", claim_ids=("c1",), kind="assert"),
    ))
    result = validate_draft(bad_draft, envelope, plan, "David", CASE, StatementStore(), ctx=CTX)
    assert result.ok is False
    assert any("SLOT_MISMATCH" in v for v in result.violations)


def test_unauthorized_claim_id_is_a_leak():
    plan, envelope = _plan_and_envelope()
    rogue_claim = Claim(id="rogue", proposition=At(actor="David", location="Study", interval=(76, 77)),
                         sincerity="truthful", source="plan")
    bad_draft = Draft(segments=(Segment(text=render_claim(rogue_claim, CASE), claim_ids=("rogue",), kind="assert"),))
    result = validate_draft(bad_draft, envelope, plan, "David", CASE, StatementStore(), ctx=CTX)
    assert result.ok is False
    assert any("UNAUTHORIZED_CLAIM" in v for v in result.violations)


def test_contradiction_with_standing_claim_caught_unless_concession():
    prop = At(actor="David", location="Library", interval=(5, 60))
    claim = Claim(id="c_new", proposition=DidNot(actor="David", action="touch", object="Glass1", interval=(0, 120)),
                  sincerity="deceptive", source="plan")
    contradicting_prior = Claim(id="c_old", proposition=At(actor="David", location="Study", interval=(5, 10)),
                                 sincerity="deceptive", source="plan")
    from eidolon.decision.claims import Statement
    statements = StatementStore([Statement(id="s0", turn=0, speaker="David", text="prior",
                                            claims=(contradicting_prior,), act="LIE")])
    # A new claim about touching a glass doesn't itself contradict a prior At(Study) claim,
    # so build a genuinely conflicting pair for this test:
    new_at = Claim(id="c_new2", proposition=At(actor="David", location="Kitchen", interval=(5, 10)),
                    sincerity="deceptive", source="plan")
    plan = ResponsePlan(act="LIE", claims=(new_at,), delivery=DeliveryDirective())
    digest = ConversationDigest(character="David", turns=1)
    envelope = build_envelope(plan, persona=PersonaSlot(), digest=digest)
    draft = TemplateLLM().generate(envelope, CASE, "David")
    result = validate_draft(draft, envelope, plan, "David", CASE, statements, ctx=CTX)
    assert result.ok is False
    assert any("CONTRADICTS_PRIOR" in v for v in result.violations)

    concession_plan = ResponsePlan(act="CONCESSION", claims=(new_at,), delivery=DeliveryDirective(), retracts=True)
    envelope2 = build_envelope(concession_plan, persona=PersonaSlot(), digest=digest)
    draft2 = TemplateLLM().generate(envelope2, CASE, "David")
    # §14.2(f): the waiver holds "when plan.act ∈ {CONCESSION, CORRECTION} and the contradicted
    # claims ⊆ plan.retracts" — a concession that retracts s0 may contradict it...
    result2 = validate_draft(draft2, envelope2, concession_plan, "David", CASE, statements, ctx=CTX,
                             retracting=frozenset({"s0"}))
    assert result2.ok is True
    # ...one that leaves s0 standing may not (the pre-repair blanket waiver accepted this).
    result3 = validate_draft(draft2, envelope2, concession_plan, "David", CASE, statements, ctx=CTX)
    assert result3.rejected is True and result3.claim_ids == ()


def test_fallback_used_when_validation_fails():
    plan, envelope = _plan_and_envelope()
    bad_draft = Draft(segments=(Segment(text="nonsense", claim_ids=(), kind="assert"),))
    result = validate_draft(bad_draft, envelope, plan, "David", CASE, StatementStore(), ctx=CTX)
    assert result.fallback is True
    assert result.text  # dull-but-valid fallback text, never the failed draft (I-12)
    assert "kitchen" not in result.text.lower() or "library" in result.text.lower()
