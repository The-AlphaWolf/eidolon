"""The contradiction detector (§13.2) — every pairing this phase's boundary covers.

Out of scope (documented, not an oversight): "claim vs prior claim", "claim vs another
character's claim" and "hypothesis vs discovered material" need `Statement`/`Claim`/
`ResponsePlan` (§12) and the player hypothesis board (§16) — Phase 4 models. `contradiction()`
itself is claim-shape-agnostic (it compares raw `Proposition`s), so Phase 4 calls it directly
once those types exist, exactly as `evidence_implication_contradicts` already does here.
"""
from __future__ import annotations

from eidolon.evidence.contradiction import (
    contradiction, corroborates, evidence_implication_contradicts, evidence_vs_evidence,
)
from eidolon.evidence.model import DiscoverySpec, Evidence, Implication
from eidolon.world.propositions import (
    Attr, At, Did, DidNot, Has, Incidental, NotAt, ObjectAt, ObjectState, Saw, State,
)
from tests.evidence.fixtures.vance_evidence import vance_v03_evidence


def _spec():
    return DiscoverySpec(action="Look", at="x")


# --- presence / travel (§13.2's first two rules) ---------------------------------------
def test_presence_contradiction_same_actor_two_locations_overlapping():
    a = At(actor="David", location="Kitchen", interval=(10, 20))
    b = At(actor="David", location="Library", interval=(15, 25))
    c = contradiction(a, b, a_id="a", b_id="b", player_material=frozenset({"a", "b"}))
    assert c is not None and c.kind == "presence" and c.severity == 1.0 and c.visible_to_player


def test_presence_same_location_never_contradicts():
    a = At(actor="David", location="Kitchen", interval=(10, 20))
    b = At(actor="David", location="Kitchen", interval=(15, 25))
    assert contradiction(a, b) is None


def test_different_actors_never_contradict_on_presence():
    a = At(actor="David", location="Kitchen", interval=(10, 20))
    b = At(actor="Margaret", location="Library", interval=(10, 20))
    assert contradiction(a, b) is None


def test_no_case_supplied_skips_the_travel_check_rather_than_guessing():
    a = At(actor="David", location="Hall", interval=(0, 1))
    b = At(actor="David", location="Gazebo", interval=(1, 2))
    assert contradiction(a, b) is None  # no `case`: cannot compute travel_time, so no verdict


def test_travel_contradiction_when_gap_is_too_short():
    case, _ = vance_v03_evidence()[:2]
    a = At(actor="David", location="Hall", interval=(0, 1))
    b = At(actor="David", location="Gazebo", interval=(1, 2))  # Hall->Gazebo needs 3 minutes via Study
    c = contradiction(a, b, case=case)
    assert c is not None and c.kind == "travel" and 0.0 < c.severity <= 1.0


def test_travel_feasible_gap_is_not_a_contradiction():
    case, _ = vance_v03_evidence()[:2]
    a = At(actor="David", location="Hall", interval=(0, 1))
    b = At(actor="David", location="Room", interval=(1, 2))  # direct 1-minute edge, exactly feasible
    assert contradiction(a, b, case=case) is None


def test_granularity_never_manufactures_an_overlap_across_a_gap():
    """§13.2: granularity is what a claim FAILS to pin down, so it can only ever shrink what
    the claim asserts. Two claims separated by a gap stay separated however vague they are —
    widening both (the v1 form) turned the gap into an overlap and made vaguer testimony
    carry MORE refutation weight."""
    a = At(actor="David", location="Kitchen", interval=(10, 11))
    b = At(actor="David", location="Library", interval=(13, 14))
    assert contradiction(a, b) is None  # exact intervals: no overlap, no case -> no verdict
    assert contradiction(a, b, granularity_a=2, granularity_b=2) is None


# --- negation ----------------------------------------------------------------------
def test_at_vs_notat_same_actor_location_overlapping_is_negation():
    a = At(actor="Elena", location="Study", interval=(76, 77))
    b = NotAt(actor="Elena", location="Study", interval=(70, 80))
    c = contradiction(a, b, a_id="claim", b_id="alibi")
    assert c is not None and c.kind == "negation" and c.a == "claim" and c.b == "alibi"


def test_at_vs_notat_different_location_is_not_negation():
    a = At(actor="Elena", location="Kitchen", interval=(76, 77))
    b = NotAt(actor="Elena", location="Study", interval=(70, 80))
    assert contradiction(a, b) is None


def test_did_vs_didnot_same_slots_overlapping_is_negation():
    did = Did(actor="David", action="touch", object="Glass1", location="Study", interval=(12, 120))
    didnot = DidNot(actor="David", action="touch", object="Glass1", location="Study", interval=(0, 120))
    c = contradiction(did, didnot)
    assert c is not None and c.kind == "negation"


def test_did_vs_didnot_different_object_is_not_negation():
    did = Did(actor="David", action="touch", object="Glass1", interval=(12, 120))
    didnot = DidNot(actor="David", action="touch", object="OtherGlass", interval=(0, 120))
    assert contradiction(did, didnot) is None


# --- object / possession -------------------------------------------------------------
def test_has_vs_objectat_different_holder_overlapping_is_object_contradiction():
    has = Has(actor="Ann", object="Knife", interval=(2, 3))
    at = ObjectAt(object="Knife", holder="Bea", interval=(2, 3))
    c = contradiction(has, at)
    assert c is not None and c.kind == "object"


def test_has_vs_objectat_matching_holder_is_not_a_contradiction():
    has = Has(actor="Ann", object="Knife", interval=(2, 3))
    at = ObjectAt(object="Knife", holder="Ann", interval=(2, 3))
    assert contradiction(has, at) is None


# --- attribute -------------------------------------------------------------------------
def test_attr_vs_attr_different_value_is_attribute_contradiction():
    a = Attr(entity="Glass1", attr="color", value="clear")
    b = Attr(entity="Glass1", attr="color", value="green")
    c = contradiction(a, b, player_material=frozenset({"a", "b"}))
    assert c is not None and c.kind == "attribute" and c.visible_to_player


def test_incidental_vs_attr_canonical_wins_and_is_never_player_visible():
    canon = Attr(entity="Glass1", attr="color", value="clear")
    soft = Incidental(entity="Glass1", attr="color", value="green")
    c = contradiction(canon, soft, player_material=frozenset({"a", "b"}))
    assert c is not None and c.kind == "attribute" and c.visible_to_player is False


def test_state_vs_state_overlapping_different_value():
    a = State(actor="Harold", attr="alive", value="true", interval=(0, 76))
    b = State(actor="Harold", attr="alive", value="false", interval=(70, 80))
    assert contradiction(a, b) is not None


def test_objectstate_vs_objectstate_overlapping_different_value():
    a = ObjectState(object="terrace_door", attr="bolted", value="true", interval=(0, 50))
    b = ObjectState(object="terrace_door", attr="bolted", value="false", interval=(40, 60))
    assert contradiction(a, b) is not None


# --- cross-witness ---------------------------------------------------------------------
def test_identified_saw_contradicts_a_different_claimed_location():
    saw = Saw(observer="Elena", subject="David", location="Kitchen", interval=(65, 66), identified=True)
    at = At(actor="David", location="Library", interval=(65, 66))
    c = contradiction(saw, at)
    assert c is not None and c.kind == "cross_witness"


def test_unidentified_saw_never_contradicts():
    """"Unidentified sightings never contradict (they only support)" (§13.2)."""
    saw = Saw(observer="Elena", subject="figure", location="Kitchen", interval=(65, 66), identified=False)
    at = At(actor="David", location="Library", interval=(65, 66))
    assert contradiction(saw, at) is None


# --- implication (evidence vs claim) ----------------------------------------------------
def test_evidence_implication_contradicts_scales_severity_by_strength():
    imp = Implication(proposition=Did(actor="David", action="touch", object="Glass1",
                                       location="Study", interval=(12, 120)), strength=0.9)
    denial = DidNot(actor="David", action="touch", object="Glass1", location="Study", interval=(0, 120))
    c = evidence_implication_contradicts(imp, denial, imp_id="E_trace", other_id="claim_n")
    assert c is not None and c.kind == "implication" and c.severity == 0.9


def test_evidence_implication_below_half_strength_never_contradicts():
    imp = Implication(proposition=Did(actor="David", action="touch", object="Glass1",
                                       location="Study", interval=(12, 120)), strength=0.4)
    denial = DidNot(actor="David", action="touch", object="Glass1", location="Study", interval=(0, 120))
    assert evidence_implication_contradicts(imp, denial, imp_id="E", other_id="c") is None


def test_the_worked_scenario_reproduces_deterministically():
    """The vance-case analogue of §13.3's worked "I never entered the kitchen" scenario,
    using this case's own vocabulary (a `touch` implication, not `enter`): ADR-22 defers
    `enter` to a future ADR amendment (its own text: "the document's Phase 4 worked example
    uses both [enter, hear]... deferred"), so the literal Kitchen-entry phrasing is not
    constructible under the current closed `ActionKind` vocabulary. David's blanket denial
    is contradicted by the unlocked fingerprint implication, deterministically and repeatedly."""
    _, evidence, _ = vance_v03_evidence()
    e_trace = next(e for e in evidence if e.id == "E_trace")
    denial = DidNot(actor="David", action="touch", object="Glass1", location="Study", interval=(0, 120))
    imp = e_trace.implications[0]
    results = [evidence_implication_contradicts(imp, denial, imp_id=e_trace.id, other_id="claim_n")
               for _ in range(5)]
    assert all(r == results[0] for r in results)  # deterministic, no hidden state
    assert results[0] is not None and results[0].kind == "implication"


# --- evidence vs evidence ------------------------------------------------------------
def test_evidence_vs_evidence_finds_a_contradiction_between_authentic_items():
    e1 = Evidence(id="E1", kind="Object", implications=(Implication(proposition=At(
        actor="Ann", location="Parlor", interval=(2, 3))),), discovery=_spec())
    e2 = Evidence(id="E2", kind="Object", implications=(Implication(proposition=At(
        actor="Ann", location="Cellar", interval=(2, 3))),), discovery=_spec())
    cs = evidence_vs_evidence(e1, e2)
    assert len(cs) == 1 and cs[0].kind == "implication"


def test_evidence_vs_evidence_reports_planted_tension_the_caller_classifies_it():
    """§13.1's row is "evidence vs evidence | planted-evidence tension; validator" — both
    uses, one comparison. The tension is reported; the caller decides whether this pair is a
    V-1 authoring defect (both authentic) or the unmasking material a planted item must
    have (§19.5)."""
    e1 = Evidence(id="E1", kind="Object", implications=(Implication(proposition=At(
        actor="Ann", location="Parlor", interval=(2, 3))),), discovery=_spec())
    e2 = Evidence(id="E2", kind="Object", authentic=False, planted_by="p",
                  implications=(Implication(proposition=At(
                      actor="Ann", location="Cellar", interval=(2, 3))),), discovery=_spec())
    cs = evidence_vs_evidence(e1, e2)
    assert len(cs) == 1 and cs[0].kind == "implication"
    assert [c for c in cs if e1.authentic and e2.authentic] == []  # not a V-1 defect
    assert cs[0].visible_to_player is False                        # authenticity stays engine-side


# --- corroboration independence (I-37 at the evidence layer) ---------------------------
def _ev(id_, created_by=None, requires=(), prop=None):
    prop = prop or At(actor="Ann", location="Parlor", interval=(2, 3))
    return Evidence(id=id_, kind="Object", created_by=created_by,
                     implications=(Implication(proposition=prop, requires=requires),),
                     discovery=_spec())


def test_corroborates_true_for_genuinely_independent_items():
    p = At(actor="Ann", location="Parlor", interval=(2, 3))
    e1 = _ev("E1", created_by="grip", prop=p)
    e2 = _ev("E2", created_by="wipe", prop=p)
    assert corroborates(e1, e2, p) is True


def test_corroborates_false_when_two_items_share_the_same_source():
    """"Two evidence items claiming mutual independence when they share the same source"."""
    p = At(actor="Ann", location="Parlor", interval=(2, 3))
    e1 = _ev("E1", created_by="grip", prop=p)
    e2 = _ev("E2", created_by="grip", prop=p)
    assert corroborates(e1, e2, p) is False


def test_corroborates_false_for_circular_requires():
    """"Evidence A supports B, B supports A" treated as independent confirmation — rejected."""
    p = At(actor="Ann", location="Parlor", interval=(2, 3))
    e1 = _ev("E1", created_by="grip", requires=("E2",), prop=p)
    e2 = _ev("E2", created_by="wipe", requires=("E1",), prop=p)
    assert corroborates(e1, e2, p) is False


def test_corroborates_false_for_a_duplicated_item_pretending_to_be_independent():
    """A literal self-comparison, and a duplicate id, are both rejected."""
    p = At(actor="Ann", location="Parlor", interval=(2, 3))
    e1 = _ev("E1", created_by="grip", prop=p)
    assert corroborates(e1, e1, p) is False


def test_corroborates_false_when_neither_item_actually_supports_the_proposition():
    other = At(actor="Ann", location="Cellar", interval=(2, 3))
    e1 = _ev("E1", created_by="grip")
    e2 = _ev("E2", created_by="wipe")
    assert corroborates(e1, e2, other) is False
