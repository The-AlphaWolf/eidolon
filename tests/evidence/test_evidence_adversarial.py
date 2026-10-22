"""Adversarial suite (§28.4 pattern, applied to Phase 3): each test names one specific
attack on the evidence/discovery boundary and asserts it is caught, not merely tolerated.
Most individual mechanisms are also unit-tested in `test_grounding.py`/`test_discovery.py`;
this file is the consolidated "attack list" the task's own acceptance gate names.
"""
from __future__ import annotations

import pytest

from eidolon.evidence.discovery import Discovery, DiscoveryState, apply_discovery
from eidolon.evidence.grounding import check_evidence_grounding
from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication
from eidolon.minds.knowledge import KnowledgeStore
from eidolon.world.propositions import Did
from tests.evidence.fixtures.vance_evidence import evidence_case, evidence_case_store


def _spec():
    return DiscoverySpec(action="Look", at="x")


def test_evidence_asserting_a_nonexistent_event():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", created_by="no-such-event",
                                     implications=(), discovery=_spec())])
    v = check_evidence_grounding(case, store)
    assert any("unknown event" in x.detail for x in v)


def test_evidence_referencing_impossible_objects():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Unicorn",
                                     implications=(), discovery=_spec())])
    v = check_evidence_grounding(case, store)
    assert any("unknown object" in x.detail for x in v)


def test_evidence_discovered_before_creation():
    """The creating event lies strictly after `t_investigation`: not yet in the world the
    player is investigating."""
    case = evidence_case()
    from eidolon.world.entities import Object
    from eidolon.world.events import EffTraceCreated, Event
    case = case.model_copy(update={
        "objects": {**case.objects, "Later": Object(id="Later", name="a later object", kind="misc",
                                                      initial_location="Parlor")},
        "events": case.events + (
            Event(id="future", kind="Use", interval=(25, 26), location="Parlor", actor="Ann",
                  objects=("Later",), effects=(EffTraceCreated(object="Later", trace_kind="fingerprint"),)),
        ),
    })
    store = EvidenceStore([Evidence(id="E1", kind="Fingerprint", object="Later", created_by="future",
                                     implications=(), discovery=_spec())])
    v = check_evidence_grounding(case, store)
    assert any("not yet discoverable" in x.detail for x in v)


def test_evidence_discovered_by_an_impossible_observer():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", known_to={"Ann": "K404"},
                                     implications=(), discovery=_spec())])
    v = check_evidence_grounding(case, store, knowledge=KnowledgeStore())
    assert any("unknown KnowledgeEntry" in x.detail for x in v)


def test_evidence_with_forged_provenance():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Fingerprint", object="Knife",
                                     implications=(Implication(proposition=Did(
                                         actor="Ann", action="touch", object="Knife",
                                         location="Parlor", interval=(0, 20)),
                                         requires=("forged-ref",)),),
                                     discovery=_spec())])
    v = check_evidence_grounding(case, store)
    assert any("forged or dangling provenance" in x.detail for x in v)


def test_two_evidence_items_sharing_a_source_are_not_independent():
    from eidolon.evidence.contradiction import corroborates
    from eidolon.world.propositions import At
    p = At(actor="Ann", location="Parlor", interval=(2, 3))
    e1 = Evidence(id="E1", kind="Object", created_by="grip",
                  implications=(Implication(proposition=p),), discovery=_spec())
    e2 = Evidence(id="E2", kind="Object", created_by="grip",
                  implications=(Implication(proposition=p),), discovery=_spec())
    assert corroborates(e1, e2, p) is False


def test_duplicated_evidence_pretending_to_be_independent():
    """A `requires` cycle — each names the other — is the model's shape of "duplicated
    evidence dressed up as two sources"."""
    from eidolon.evidence.contradiction import corroborates
    from eidolon.world.propositions import At
    p = At(actor="Ann", location="Parlor", interval=(2, 3))
    e1 = Evidence(id="E1", kind="Object", created_by="grip",
                  implications=(Implication(proposition=p, requires=("E2",)),), discovery=_spec())
    e2 = Evidence(id="E2", kind="Object", created_by="wipe",
                  implications=(Implication(proposition=p, requires=("E1",)),), discovery=_spec())
    assert corroborates(e1, e2, p) is False


def test_altered_evidence_being_treated_as_authentic():
    """Authored inconsistency: `authentic=True` with `planted_by` set — caught, never
    silently accepted as "authentic"."""
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", authentic=True, planted_by="plant",
                                     implications=(), discovery=_spec())])
    v = check_evidence_grounding(case, store)
    assert any("inconsistent" in x.detail for x in v)


def test_evidence_contradicting_canonical_world_truth():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Document", object="Letter", authentic=True,
                                     created_at=(8, 9),
                                     implications=(Implication(proposition=Did(
                                         actor="Bea", action="Write", object="Letter",
                                         location="Cellar", interval=(8, 9))),),
                                     discovery=_spec())])
    v = check_evidence_grounding(case, store)
    assert any(x.rule == "P-0" for x in v)


def test_discovery_occurring_through_an_invalid_path():
    store = evidence_case_store()
    with pytest.raises(ValueError):
        apply_discovery(DiscoveryState(), Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife"), store)


def test_malformed_evidence_reliability_out_of_range_is_rejected_at_construction():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Evidence(id="E1", kind="Object", reliability=42.0, implications=(), discovery=_spec())
