"""Evidence grounding (§5.2, P-6, P-0, P-9/I-30) — the boundary that stops Evidence
becoming a second source of truth."""
from __future__ import annotations

from eidolon.evidence.grounding import (
    check_creation_grounding, check_evidence_grounding, check_known_to_soundness,
    check_temporal_grounding, check_world_truth, established_interval, to_physics_tuples,
)
from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication
from eidolon.minds.knowledge import KnowledgeEntry, KnowledgeStore
from eidolon.minds.provenance import Participated
from eidolon.world.physics import check_physics
from eidolon.world.propositions import Did
from tests.evidence.fixtures.vance_evidence import (
    STATEMENT_INTERVALS, evidence_case, evidence_case_items, evidence_case_store,
    vance_v03_evidence,
)


def _spec(at="Knife"):
    return DiscoverySpec(action="Dust", at=at)


# --- positive: the fixtures are clean ------------------------------------------------
def test_vance_v03_evidence_table_is_fully_grounded():
    """Phase 3 exit criterion: "vance_v03 evidence table complete"."""
    case, evidence, stmt = vance_v03_evidence()
    store = EvidenceStore(evidence)
    assert check_evidence_grounding(case, store, statement_intervals=stmt) == []


def test_evidence_case_fixture_is_fully_grounded():
    case = evidence_case()
    store = evidence_case_store()
    assert check_evidence_grounding(case, store, statement_intervals=STATEMENT_INTERVALS) == []


def test_to_physics_tuples_reuses_phase1_check_physics_for_p0_and_p1_through_p5():
    """Reuse, not duplication: the bridged tuples feed the SAME `check_physics` Phase 1
    ships, and an authentic, well-formed evidence table passes it too."""
    case = evidence_case()
    store = EvidenceStore([e for e in evidence_case_items() if e.authentic])
    assert check_physics(case, to_physics_tuples(store)) == []


# --- P-6: creation grounding ----------------------------------------------------------
def test_p6_rejects_evidence_naming_an_unknown_object():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="Ghost", kind="Object", object="Nonexistent",
                                     implications=(), discovery=_spec("Nonexistent"))])
    v = check_creation_grounding(case, store)
    assert any(x.rule == "P-6" and "unknown object" in x.detail for x in v)


def test_p6_rejects_created_by_referencing_unknown_event():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Fingerprint", object="Knife",
                                     created_by="no-such-event", implications=(), discovery=_spec())])
    v = check_creation_grounding(case, store)
    assert any("unknown event" in x.detail for x in v)


def test_p6_rejects_forensic_kind_with_no_traceCreated_effect():
    case = evidence_case()  # "wipe" (Clean) touches Knife but creates no trace
    store = EvidenceStore([Evidence(id="Ghost", kind="Fingerprint", object="Knife",
                                     created_by="wipe", implications=(), discovery=_spec())])
    v = check_creation_grounding(case, store)
    assert any("no TraceCreated effect" in x.detail for x in v)


def test_p6_evidence_discovered_before_creation_is_rejected():
    """"Evidence discovered before creation": a creating event that happens AFTER
    `t_investigation` cannot have produced something already sitting in the scene."""
    case = evidence_case()  # t_investigation = 20
    from eidolon.world.entities import Object
    from eidolon.world.events import EffTraceCreated, Event
    case = case.model_copy(update={
        "objects": {**case.objects, "Later": Object(id="Later", name="a later object", kind="misc",
                                                      initial_location="Parlor")},
        "events": case.events + (
            Event(id="future-touch", kind="Use", interval=(25, 26), location="Parlor", actor="Ann",
                  objects=("Later",), effects=(EffTraceCreated(object="Later", trace_kind="fingerprint"),)),
        ),
    })
    store = EvidenceStore([Evidence(id="Ghost", kind="Fingerprint", object="Later",
                                     created_by="future-touch", implications=(), discovery=_spec("Later"))])
    v = check_creation_grounding(case, store)
    assert any("not yet discoverable" in x.detail for x in v)


def test_p6_interacted_rejects_actor_not_present_at_the_named_event():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Knife",
                                     interacted=(("Bea", "grip"),),  # grip's actor is Ann
                                     implications=(), discovery=_spec())])
    v = check_creation_grounding(case, store)
    assert any("were not actor or participant" in x.detail for x in v)


def test_p6_location_at_investigation_must_match_canonical_world():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Knife",
                                     location_at_investigation="Cellar",  # Knife is in Parlor
                                     implications=(), discovery=_spec())])
    v = check_creation_grounding(case, store)
    assert any("!= canonical" in x.detail for x in v)


def test_p6_authentic_evidence_must_not_carry_planted_by():
    """"Altered evidence being treated as authentic": authored inconsistency, caught."""
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Knife", authentic=True,
                                     planted_by="plant", implications=(), discovery=_spec())])
    v = check_creation_grounding(case, store)
    assert any("must not carry planted_by" in x.detail for x in v)


def test_p6_planted_evidence_needs_planted_by():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Knife", authentic=False,
                                     implications=(), discovery=_spec())])
    v = check_creation_grounding(case, store)
    assert any("needs planted_by" in x.detail for x in v)


def test_p6_planted_by_must_reference_a_plant_event():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Knife", authentic=False,
                                     planted_by="grip",  # a Use event, not Plant
                                     implications=(), discovery=_spec())])
    v = check_creation_grounding(case, store)
    assert any("not Plant" in x.detail for x in v)


# --- P-0: world truth, restricted to authentic evidence --------------------------------
def test_p0_rejects_an_authentic_implication_the_world_refutes():
    """"Evidence contradicting canonical world truth" — for AUTHENTIC evidence, rejected."""
    case = evidence_case()
    forged = Evidence(id="E1", kind="Document", object="Letter", authentic=True, created_at=(8, 9),
                       implications=(Implication(proposition=Did(actor="Bea", action="Write",
                                                                  object="Letter", location="Cellar",
                                                                  interval=(8, 9))),),
                       discovery=_spec("Letter"))
    v = check_world_truth(case, EvidenceStore([forged]))
    assert any(x.rule == "P-0" for x in v)


def test_p0_exempts_planted_evidence_from_world_truth():
    """The same forged claim, `authentic=False`: not flagged — planted evidence being
    world-false is the point (§5.2), not an authoring error."""
    case = evidence_case()
    store = EvidenceStore([e for e in evidence_case_items() if e.id == "E_letter"])
    assert check_world_truth(case, store) == []


def test_p0_bridge_via_check_physics_does_not_know_about_authenticity():
    """Contrast: the raw Phase 1 `check_physics` bridge has no authenticity concept, so it
    DOES flag the planted item — which is exactly why `check_evidence_grounding`'s own
    `check_world_truth` (authenticity-aware) exists on top of it rather than replacing it."""
    case = evidence_case()
    store = EvidenceStore([e for e in evidence_case_items() if e.id == "E_letter"])
    v = check_physics(case, to_physics_tuples(store))
    assert any(x.rule == "P-0" for x in v)


# --- P-9/I-30: deep temporal grounding --------------------------------------------------
def test_established_interval_is_just_the_discovery_pin_with_no_requires_or_created_at():
    store = EvidenceStore()
    imp = Implication(proposition=Did(actor="Ann", action="touch", interval=(0, 20)))
    assert established_interval(imp, store, t_investigation=20) == (20, 21)


def test_established_interval_unions_created_at_and_requires_into_one_hull():
    """`E_fp_wide` requires both `S_wipe` (an opaque statement interval) and `E_fp` (a real
    `Evidence` whose OWN `created_at` is (2,3)) — the hull is every resolvable contribution,
    convex-hulled with the always-present discovery pin (20,21)."""
    store = evidence_case_store()
    imp = store.get("E_fp_wide").implications[0]
    hull = established_interval(imp, store, t_investigation=20,
                                 statement_intervals=STATEMENT_INTERVALS,
                                 self_created_at=store.get("E_fp_wide").created_at)
    assert hull == (2, 21)  # E_fp's created_at (2,3) ∪ S_wipe (5,6) ∪ discovery pin (20,21)


def test_p9_rejects_an_implication_wider_than_its_established_interval():
    """§29.1's own E10 shape: an interval asserted over the whole evening with nothing to
    establish it — "a bolted door observed at t_investigation with no requires establishes
    only [t_investigation, t_investigation+1) and may not be used to constrain the murder
    window"."""
    case = evidence_case()
    store = EvidenceStore([Evidence(id="Overclaim", kind="Object", object="Knife",
                                     implications=(Implication(proposition=Did(
                                         actor="Ann", action="touch", object="Knife",
                                         location="Parlor", interval=(0, 20))),),
                                     discovery=_spec())])
    v = check_temporal_grounding(case, store)
    assert len(v) == 1 and v[0].rule == "P-9"


def test_p9_rejects_a_dangling_requires_reference_as_forged_provenance():
    """"Evidence with forged provenance": a `requires` id that resolves to nothing."""
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Fingerprint", object="Knife",
                                     implications=(Implication(proposition=Did(
                                         actor="Ann", action="touch", object="Knife",
                                         location="Parlor", interval=(0, 20)),
                                         requires=("ghost-id",)),),
                                     discovery=_spec())])
    v = check_temporal_grounding(case, store)
    assert any("unresolved reference" in x.detail for x in v)


def test_p9_ignores_implications_whose_proposition_carries_no_interval():
    case = evidence_case()
    from eidolon.world.propositions import Attr
    store = EvidenceStore([Evidence(id="E1", kind="Document",
                                     implications=(Implication(proposition=Attr(
                                         entity="Letter", attr="color", value="cream")),),
                                     discovery=_spec("Letter"))])
    assert check_temporal_grounding(case, store) == []


def test_p9_evidence_referencing_another_evidence_with_no_created_at_contributes_nothing():
    """A `requires` id that IS a real `Evidence` but has no `created_at` of its own is not a
    forged reference — it is simply uninformative, and the hull still falls back to the
    discovery pin (and any other resolvable requirement)."""
    case = evidence_case()
    uninformative = Evidence(id="Vague", kind="Object", object="Knife", implications=(),
                              discovery=_spec())
    dependent = Evidence(id="E1", kind="Fingerprint", object="Knife",
                          implications=(Implication(proposition=Did(
                              actor="Ann", action="touch", object="Knife",
                              location="Parlor", interval=(20, 21)), requires=("Vague",)),),
                          discovery=_spec())
    store = EvidenceStore([uninformative, dependent])
    assert check_temporal_grounding(case, store) == []  # (20,21) fits the discovery pin alone


# --- known_to soundness: "evidence discovered by an impossible observer" ---------------
def test_known_to_rejects_a_dangling_knowledge_entry_reference():
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Knife",
                                     known_to={"Ann": "K9999"}, implications=(), discovery=_spec())])
    v = check_known_to_soundness(store, KnowledgeStore())
    assert any("unknown KnowledgeEntry" in x.detail for x in v)


def test_known_to_rejects_a_knowledge_entry_belonging_to_someone_else():
    entry = KnowledgeEntry(id="K1", character="Bea", proposition=Did(actor="Ann", action="touch",
                                                                       object="Knife", interval=(2, 3)),
                            source=Participated(event_id="grip"), acquired_at=2, reliability=1.0, is_true=True)
    knowledge = KnowledgeStore([entry])
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Knife",
                                     known_to={"Ann": "K1"},  # K1 belongs to Bea, not Ann
                                     implications=(), discovery=_spec())])
    v = check_known_to_soundness(store, knowledge)
    assert any("belongs to Bea" in x.detail for x in v)


def test_check_evidence_grounding_includes_known_to_check_only_when_knowledge_is_supplied():
    case = evidence_case()
    store = EvidenceStore([Evidence(id="E1", kind="Object", object="Knife",
                                     known_to={"Ann": "K9999"}, implications=(), discovery=_spec())])
    assert check_evidence_grounding(case, store) == []  # no `knowledge` -> check skipped
    assert check_evidence_grounding(case, store, knowledge=KnowledgeStore()) != []
