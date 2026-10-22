"""§19.5/I-27/I-35/I-37: claim- and evidence-level admissibility, corroboration and the
collusion graph. Exercises the same invariants T-4/T-5/T-11 name (owner Phase 6/5 for the
full solver-level fixtures), as the Phase 4 infrastructure those tests will be built on.
"""
from __future__ import annotations

from eidolon.decision.admissibility import (
    CollusionGraph, claim_admissibility, claim_apparent_admissibility, confrontee_knows_false,
    evidence_admissibility, evidence_apparent_admissibility,
)
from eidolon.decision.claims import Claim
from eidolon.decision.secrets import Secret, SecretStore, Stakes, CoverStory
from eidolon.minds.belief import Belief, BeliefStore
from eidolon.minds.knowledge import KnowledgeEntry, KnowledgeStore
from eidolon.minds.provenance import AdmissibilityLevel, Witnessed
from eidolon.world.propositions import At
from eidolon.world.entities import Actor
from eidolon.world.propositions import Rel

ANN, BEA, CAL = "Ann", "Bea", "Cal"


def _entry(eid, character, prop, event_id, reliability=0.8) -> KnowledgeEntry:
    return KnowledgeEntry(id=eid, character=character, proposition=prop,
                           source=Witnessed(event_id=event_id, modality="sight", quality=reliability),
                           acquired_at=0, reliability=reliability, is_true=True)


def test_corroboration_promotes_l1_to_l2_when_independent():
    prop = At(actor=CAL, location="Study", interval=(10, 20))
    k1 = _entry("K1", ANN, prop, "evA")
    k2 = _entry("K2", BEA, prop, "evB")
    knowledge = KnowledgeStore([k1, k2])
    beliefs = BeliefStore()
    secrets = SecretStore()
    collusion = CollusionGraph(edges=frozenset())

    claim = Claim(id="c1", proposition=prop, sincerity="truthful", source="plan", grounding=("K1",))
    assert claim_admissibility(claim, ANN, knowledge, beliefs, secrets, collusion) == AdmissibilityLevel.L2


def test_collusion_blocks_corroboration_i37():
    """Two claims corroborating each other, from LOVERS, stay L1 — I-37's "connectivity, not
    adjacency": a direct `Rel` edge between the two speakers is the same defect the v0.1
    golden case failed on."""
    prop = At(actor=CAL, location="Gazebo", interval=(10, 20))
    k1 = _entry("K1", ANN, prop, "evA")
    k2 = _entry("K2", BEA, prop, "evB")
    knowledge = KnowledgeStore([k1, k2])
    beliefs = BeliefStore()
    secrets = SecretStore()
    collusion = CollusionGraph(edges=frozenset({frozenset({ANN, BEA})}))

    claim = Claim(id="c1", proposition=prop, sincerity="truthful", source="plan", grounding=("K1",))
    assert claim_admissibility(claim, ANN, knowledge, beliefs, secrets, collusion) == AdmissibilityLevel.L1


def test_transitive_collusion_component_not_just_adjacency():
    """A-B corroborate, B-C are lovers: A and C sit in the SAME collusion component even
    though there is no direct A-C edge (§19.5: "connectivity, not adjacency")."""
    graph = CollusionGraph(edges=frozenset({frozenset({ANN, BEA}), frozenset({BEA, CAL})}))
    assert graph.connected(ANN, CAL)


def test_own_protected_fact_is_always_l0():
    prop = At(actor=ANN, location="Kitchen", interval=(0, 10))
    secret = Secret(id="S1", owner=ANN, kind="minor_infraction", protected=(prop,),
                     stakes=Stakes(social=0.5), cover=CoverStory(layers=()))
    secrets = SecretStore([secret])
    knowledge = KnowledgeStore([_entry("K1", ANN, prop, "evA")])
    beliefs = BeliefStore()
    collusion = CollusionGraph(edges=frozenset())
    claim = Claim(id="c1", proposition=prop, sincerity="deceptive", source="plan", grounding=("K1",))
    assert claim_admissibility(claim, ANN, knowledge, beliefs, secrets, collusion) == AdmissibilityLevel.L0


def test_confrontee_knows_false_zeroes_apparent_weight_i35():
    prop_false = At(actor=ANN, location="Kitchen", interval=(0, 10))
    true_belief_prop = At(actor=ANN, location="Study", interval=(0, 10))
    beliefs = BeliefStore([Belief(id="B1", character=ANN, proposition=true_belief_prop,
                                   confidence_0=8000, grounds=(), formed_at=0, is_true=True)])
    assert confrontee_knows_false(prop_false, ANN, beliefs) is True

    knowledge = KnowledgeStore([_entry("K1", ANN, prop_false, "evA")])
    secrets = SecretStore()
    collusion = CollusionGraph(edges=frozenset())
    claim = Claim(id="c1", proposition=prop_false, sincerity="truthful", source="plan", grounding=("K1",))
    assert claim_apparent_admissibility(claim, ANN, ANN, knowledge, beliefs, secrets, collusion) == AdmissibilityLevel.L0


def test_evidence_planted_is_l0_true_but_l3_apparent_i35():
    from tests.evidence.fixtures.vance_evidence import evidence_case_items
    planted = next(e for e in evidence_case_items() if not e.authentic)
    beliefs = BeliefStore()
    assert evidence_admissibility(planted) == AdmissibilityLevel.L0
    assert evidence_apparent_admissibility(planted, "Ann", beliefs) == AdmissibilityLevel.L3


def test_evidence_authentic_is_l3_both_ways():
    from tests.evidence.fixtures.vance_evidence import evidence_case_items
    authentic = next(e for e in evidence_case_items() if e.authentic)
    beliefs = BeliefStore()
    assert evidence_admissibility(authentic) == AdmissibilityLevel.L3
    assert evidence_apparent_admissibility(authentic, "Ann", beliefs) == AdmissibilityLevel.L3
