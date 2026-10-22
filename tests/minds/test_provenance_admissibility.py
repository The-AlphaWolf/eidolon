"""§19.5/I-27: admissibility as a pure function of a grounding chain, minimum over the
chain, InvestigationTold poisoning any chain it appears in."""
from __future__ import annotations

import pytest

from eidolon.minds.admissibility import admissibility_level, apparent_admissibility
from eidolon.minds.belief import Belief, BeliefStore
from eidolon.minds.knowledge import KnowledgeEntry, KnowledgeStore
from eidolon.minds.provenance import (
    AdmissibilityLevel, Background, Inferred, InvestigationTold, Participated, Told, Witnessed,
    level_below,
)
from eidolon.world.propositions import At


def _entry(id_, character, source, prop=None):
    return KnowledgeEntry(id=id_, character=character, proposition=prop or At(actor="X", location="Hall", interval=(0, 5)),
                           source=source, acquired_at=0, reliability=0.8, is_true=True)


def test_level_below_steps_down_and_floors_at_l0():
    assert level_below(AdmissibilityLevel.L3) == AdmissibilityLevel.L2
    assert level_below(AdmissibilityLevel.L2) == AdmissibilityLevel.L1
    assert level_below(AdmissibilityLevel.L1) == AdmissibilityLevel.L0
    assert level_below(AdmissibilityLevel.L0) == AdmissibilityLevel.L0


def test_witnessed_participated_background_are_l1_uncorroborated():
    store = KnowledgeStore()
    beliefs = BeliefStore()
    for kind_id, source in [
        ("K1", Witnessed(event_id="e1", modality="sight", quality=0.8)),
        ("K2", Participated(event_id="e2")),
        ("K3", Background(background_kind="layout")),
    ]:
        store.add(_entry(kind_id, "Elena", source))
    for kid in ("K1", "K2", "K3"):
        assert admissibility_level(kid, store, beliefs) == AdmissibilityLevel.L1


def test_investigation_told_is_always_l0():
    store = KnowledgeStore()
    store.add(_entry("K1", "Elena", InvestigationTold(by_detective_turn=3)))
    assert admissibility_level("K1", store, BeliefStore()) == AdmissibilityLevel.L0


def test_investigation_told_poisons_inferred_chain():
    """I-27/AC-1: a claim laundered through a witness who was told it by the detective
    stays L0 forever, "in every mouth it passes through"."""
    store = KnowledgeStore()
    store.add(_entry("K_seed", "Elena", InvestigationTold(by_detective_turn=1)))
    store.add(_entry("K_derived", "Elena", Inferred(from_ids=("K_seed",), rule_id="consistency")))
    assert admissibility_level("K_derived", store, BeliefStore()) == AdmissibilityLevel.L0


def test_told_is_one_step_below_tellers_own_level():
    prop = At(actor="X", location="Hall", interval=(0, 5))
    store = KnowledgeStore()
    store.add(_entry("K_teller", "Robert", Witnessed(event_id="e1", modality="sight", quality=0.8), prop))
    store.add(_entry("K_listener", "Elena", Told(by="Robert", speak_event_id="talk1", teller_sincere=True), prop))
    assert admissibility_level("K_teller", store, BeliefStore()) == AdmissibilityLevel.L1
    assert admissibility_level("K_listener", store, BeliefStore()) == AdmissibilityLevel.L0  # L1 - 1


def test_told_with_no_grounded_teller_entry_is_l0():
    """The teller asserted something they have no knowledge entry for at all — an
    ungrounded/fabricated claim, structurally indistinguishable from a lie (§6.4 rule 3)."""
    prop = At(actor="X", location="Hall", interval=(0, 5))
    store = KnowledgeStore()
    store.add(_entry("K_listener", "Elena", Told(by="Robert", speak_event_id="talk1", teller_sincere=False), prop))
    assert admissibility_level("K_listener", store, BeliefStore()) == AdmissibilityLevel.L0


def test_inferred_takes_minimum_over_from_ids():
    store = KnowledgeStore()
    store.add(_entry("K_hi", "Elena", Witnessed(event_id="e1", modality="sight", quality=0.9)))
    store.add(_entry("K_lo", "Elena", InvestigationTold(by_detective_turn=1)))
    store.add(_entry("K_inf", "Elena", Inferred(from_ids=("K_hi", "K_lo"), rule_id="opportunity")))
    assert admissibility_level("K_inf", store, BeliefStore()) == AdmissibilityLevel.L0


def test_belief_grounds_recurse_through_knowledge_store():
    prop = At(actor="X", location="Hall", interval=(0, 5))
    store = KnowledgeStore()
    store.add(_entry("K1", "Elena", InvestigationTold(by_detective_turn=1), prop))
    beliefs = BeliefStore()
    beliefs.add(Belief(id="B1", character="Elena", proposition=prop, confidence_0=8000,
                        grounds=("K1",), formed_at=0, is_true=True))
    assert admissibility_level("B1", store, beliefs) == AdmissibilityLevel.L0


def test_cyclic_grounding_resolves_to_l0_not_infinite_recursion():
    beliefs = BeliefStore()
    prop_a = At(actor="A", location="Hall", interval=(0, 5))
    prop_b = At(actor="B", location="Hall", interval=(0, 5))
    beliefs.add(Belief(id="B1", character="Elena", proposition=prop_a, confidence_0=8000,
                        grounds=("B2",), formed_at=0, is_true=True))
    beliefs.add(Belief(id="B2", character="Elena", proposition=prop_b, confidence_0=8000,
                        grounds=("B1",), formed_at=0, is_true=True))
    assert admissibility_level("B1", KnowledgeStore(), beliefs) == AdmissibilityLevel.L0


def test_unknown_grounding_id_raises():
    with pytest.raises(KeyError):
        admissibility_level("nope", KnowledgeStore(), BeliefStore())


def test_apparent_admissibility_matches_true_level_at_phase2_scope():
    """Documented Phase 2 scope: `apparent_admissibility` diverges from `admissibility_level`
    only for planted evidence / confrontee-knows-false claims (Evidence/Claim, Phase 3-4),
    neither of which exists yet — the two must agree until then."""
    store = KnowledgeStore()
    store.add(_entry("K1", "Elena", Witnessed(event_id="e1", modality="sight", quality=0.8)))
    beliefs = BeliefStore()
    assert apparent_admissibility("K1", store, beliefs) == admissibility_level("K1", store, beliefs)
