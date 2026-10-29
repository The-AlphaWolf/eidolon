"""§19.3 (V-3): breaker-set derivation and the cover-consistency contract."""
from __future__ import annotations

from eidolon.decision.claims import Claim, StatementStore
from eidolon.decision.context import DecisionContext
from eidolon.decision.cover_consistency import (
    MurderUniquenessCheck, check_deflection_grounding,
    check_evidence_response_coverage, check_joint_feasibility_layer0, check_monotone_concedes,
    derive_breaker_sets,
)
from eidolon.decision.secrets import CoverLayer, CoverStory, EvidenceResponse, Secret, SecretStore, Stakes
from eidolon.evidence.discovery import DiscoveryState
from eidolon.evidence.model import EvidenceStore
from eidolon.minds.belief import BeliefStore
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.knowledge import KnowledgeStore
from eidolon.world.propositions import At, DidNot
from tests.decision.fixtures.simple_cover import DAVID, build as build_simple_cover


def test_breaker_set_derived_and_evidence_response_gap_reported():
    ctx, secret = build_simple_cover()
    bsets = derive_breaker_sets(secret, 0, ctx)
    # E_trace's implication `requires=("S_clean",)`: neither item alone unlocks/breaks L0,
    # but together they do — the minimal breaker set is the PAIR (§13.3's own "{E1 + S_wash}").
    assert frozenset({"E_trace", "S_clean"}) in bsets
    assert frozenset({"E_trace"}) not in bsets

    violations = check_evidence_response_coverage(secret, 0, bsets)
    assert any(v.check == "ii" for v in violations)

    # Author the missing EvidenceResponses and re-check: the gap closes.
    fixed_secret = secret.model_copy(update={
        "evidence_responses": (EvidenceResponse(evidence="E_trace", layer=0, act="DENY_EVIDENCE"),
                                EvidenceResponse(evidence="S_clean", layer=0, act="DENY_EVIDENCE")),
    })
    violations2 = check_evidence_response_coverage(fixed_secret, 0, bsets)
    assert violations2 == []


def test_monotone_concedes_violation():
    denial = Claim(id="c0", proposition=DidNot(actor=DAVID, action="touch", object="X", interval=(0, 10)),
                    sincerity="deceptive", source="plan")
    layers = (
        CoverLayer(index=0, claims=(denial,), resolve=6000,
                   concedes=(At(actor=DAVID, location="Kitchen", interval=(0, 5)),)),
        CoverLayer(index=1, claims=(), resolve=10000, terminal="stonewall", concedes=()),  # loses a concession
    )
    secret = Secret(id="S1", owner=DAVID, kind="minor_infraction", protected=(denial.proposition,),
                     stakes=Stakes(social=0.5), cover=CoverStory(layers=layers))
    violations = check_monotone_concedes(secret)
    assert any(v.check == "iv" for v in violations)


def test_deflection_basis_must_be_owners_own_knowledge():
    from eidolon.decision.secrets import Deflection
    denial = Claim(id="c0", proposition=DidNot(actor=DAVID, action="touch", object="X", interval=(0, 10)),
                    sincerity="deceptive", source="plan")
    secret = Secret(id="S1", owner=DAVID, kind="minor_infraction", protected=(denial.proposition,),
                     stakes=Stakes(social=0.5),
                     cover=CoverStory(layers=(CoverLayer(index=0, claims=(denial,), resolve=6000, terminal="stonewall"),)),
                     deflections=(Deflection(target="Margaret", basis=("K999",)),))
    ctx = DecisionContext(case=build_simple_cover()[0].case, knowledge=KnowledgeStore(), beliefs=BeliefStore(),
                           secrets=SecretStore([secret]), evidence=EvidenceStore(), statements=StatementStore(),
                           epistemic=EpistemicState(), discovery=DiscoveryState())
    violations = check_deflection_grounding(secret, ctx)
    assert any(v.check == "iv" for v in violations)


def test_transitive_alibi_cycle_rejected_i28_t15_shape():
    """T-15's shape: three characters' layer-0 covers forming a transitive alibi cycle are
    jointly infeasible even though every PAIR is individually consistent (§13.2a)."""
    from tests.world.fixtures.vance import vance_v03
    case, _ = vance_v03()
    a_claim = Claim(id="a1", proposition=At(actor="David", location="Gazebo", interval=(60, 70)),
                     sincerity="deceptive", source="plan")
    a_claim2 = Claim(id="a2", proposition=At(actor="Margaret", location="Gazebo", interval=(60, 70)),
                      sincerity="deceptive", source="plan")
    b_claim = Claim(id="b1", proposition=At(actor="Margaret", location="Kitchen", interval=(65, 75)),
                     sincerity="deceptive", source="plan")
    b_claim2 = Claim(id="b2", proposition=At(actor="Robert", location="Kitchen", interval=(65, 75)),
                      sincerity="deceptive", source="plan")
    c_claim = Claim(id="c1", proposition=At(actor="Robert", location="Library", interval=(70, 80)),
                     sincerity="deceptive", source="plan")
    c_claim2 = Claim(id="c2", proposition=At(actor="David", location="Library", interval=(70, 80)),
                      sincerity="deceptive", source="plan")

    def secret_for(owner, claims):
        return Secret(id=f"S_{owner}", owner=owner, kind="minor_infraction", protected=(),
                       stakes=Stakes(social=0.3),
                       cover=CoverStory(layers=(CoverLayer(index=0, claims=claims, resolve=5000, terminal="stonewall"),)))

    secrets = [secret_for("David", (a_claim, c_claim2)), secret_for("Margaret", (a_claim2, b_claim)),
               secret_for("Robert", (b_claim2, c_claim))]
    ctx = DecisionContext(case=case, knowledge=KnowledgeStore(), beliefs=BeliefStore(),
                           secrets=SecretStore(secrets), evidence=EvidenceStore(), statements=StatementStore(),
                           epistemic=EpistemicState(), discovery=DiscoveryState())
    violations = check_joint_feasibility_layer0(secrets, ctx)
    assert any(v.check == "v" for v in violations)


def test_murder_confession_uniqueness_pass_and_fail():
    from eidolon.decision.cover_consistency import check_murder_confession_uniqueness
    from tests.world.fixtures.vance import vance_v03
    case, _ = vance_v03()
    scene_claim = Claim(id="scene", proposition=At(actor=DAVID, location="Study", interval=(76, 77)),
                         sincerity="truthful", source="plan", grounding=("K1",))
    denial = Claim(id="c0", proposition=DidNot(actor=DAVID, action="touch", object="Glass1", interval=(0, 120)),
                    sincerity="deceptive", source="plan")
    secret = Secret(id="S_murder", owner=DAVID, kind="murder", protected=(denial.proposition,),
                     stakes=Stakes(legal=1.0),
                     cover=CoverStory(layers=(CoverLayer(index=0, claims=(denial,), resolve=1),
                                                CoverLayer(index=1, claims=(), resolve=10000, terminal="confession"))))
    from eidolon.evidence.model import DiscoverySpec, Evidence, Implication
    ev = Evidence(id="E_scene", kind="Witness", implications=(Implication(proposition=scene_claim.proposition),),
                  discovery=DiscoverySpec(action="Ask", at="Study"))
    ctx = DecisionContext(case=case, knowledge=KnowledgeStore(), beliefs=BeliefStore(),
                           secrets=SecretStore([secret]), evidence=EvidenceStore([ev]), statements=StatementStore(),
                           epistemic=EpistemicState(), discovery=DiscoveryState())
    check = MurderUniquenessCheck(murder_location="Study", murder_interval=(76, 77), candidates=("David", "Margaret"))
    fail = check_murder_confession_uniqueness(secret, 0, (frozenset({"E_scene"}),), ctx, check)
    assert fail  # Margaret has no admissible material, so she "survives" too -> not unique

    # Add material excluding Margaret: she is elsewhere, overlapping the murder window.
    margaret_ev = Evidence(id="E_margaret", kind="Witness",
                            implications=(Implication(proposition=At(actor="Margaret", location="Library",
                                                                       interval=(70, 80))),),
                            discovery=DiscoverySpec(action="Ask", at="Library"))
    ctx2 = ctx.__class__(case=ctx.case, knowledge=ctx.knowledge, beliefs=ctx.beliefs, secrets=ctx.secrets,
                          evidence=EvidenceStore([ev, margaret_ev]), statements=ctx.statements,
                          epistemic=ctx.epistemic, discovery=ctx.discovery)
    ok = check_murder_confession_uniqueness(secret, 0, (frozenset({"E_scene", "E_margaret"}),), ctx2, check)
    assert ok == []


def test_review_i6_testimony_is_filed_under_the_person_it_is_about():
    """Review I-6: a witness's statement about another suspect was filed under the witness, so it could never exclude its
    subject (survivors stayed David, Elena, Margaret, Robert when Elena's word places David out of the room)."""
    from eidolon.decision.cover_consistency import about
    from eidolon.world.propositions import At, NotAt
    assert about(NotAt(actor="David", location="Study", interval=(71, 72)), "Elena") == "David"
    assert about(At(actor="Elena", location="Hall", interval=(71, 72)), "Elena") == "Elena"


def test_review_n3_a_concession_that_contradicts_the_owners_own_word_is_a_v3_violation():
    """Phase 4 review N-3: a concession contradicting something the owner may truthfully say (and so may already have said
    as TRUTH) can never be committed - every later peel is refused. V-3 now rejects such a cover; the goldens have none."""
    from pathlib import Path
    from eidolon.decision.claims import Claim
    from eidolon.decision.cover_consistency import check_concessions_against_own_word
    from eidolon.decision.secrets import CoverStory
    from eidolon.decision.speakable import speakable
    from eidolon.solve.package import load_sealed_case
    from eidolon.solve.session import decision_context
    from eidolon.world.propositions import At
    p = load_sealed_case(str(Path(__file__).resolve().parents[2] / "cases" / "generated" / "study_party_s4.json")).package
    ctx = decision_context(p)
    secret = next(s for s in p.secrets if s.kind != "murder")
    assert check_concessions_against_own_word(secret, ctx) == []
    said = next(e for e in ctx.knowledge.for_character(secret.owner) if e.proposition.kind == "At" and speakable(
        Claim(id="k", proposition=e.proposition, sincerity="truthful", source="plan", grounding=(e.id,)),
        secret.owner, ctx.secrets, lambda s: 1 if s.id == secret.id else 0, ctx.knowledge, ctx.case))
    elsewhere = next(loc for loc in sorted(ctx.case.locations) if loc != said.proposition.location)
    bad = Claim(id="bad", proposition=At(actor=secret.owner, location=elsewhere, interval=said.proposition.interval),
                sincerity="truthful", source="plan")
    l1 = secret.cover.layers[1]
    broken = secret.model_copy(update={"cover": CoverStory(layers=(secret.cover.layers[0], l1.model_copy(
        update={"claims": l1.claims + (bad,)})) + secret.cover.layers[2:])})
    assert [x.check for x in check_concessions_against_own_word(broken, ctx)] == ["vi"]
