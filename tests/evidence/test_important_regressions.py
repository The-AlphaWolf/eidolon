"""Regression tests for the eleven IMPORTANT defects found by the Phase 3 hostile audit.

Every test fails on the pre-fix code. Each guards a boundary the audit found collapsed,
and the boundaries are the six the brief names:

    PRESENT IN WORLD -> GROUNDED -> DISCOVERABLE -> DISCOVERED -> VISIBLE TO PLAYER
                                                              -> KNOWN BY CHARACTER

F-1   P-0 could not refute object/attribute/state/`Moved` claims (PRESENT IN WORLD).
F-2   the forensic-trace warrant was skipped whenever `created_by` was unset (GROUNDED).
F-3   dangling `requires` was only checked on interval-bearing implications (GROUNDED).
F-4   `known_to` was a live dict on a sealed item (I-4).
F-6   `Did`/`DidNot` ignored `location` and the `object=None` wildcard (§13.2).
F-7   `visible_to_player` was hard-coded per rule (VISIBLE TO PLAYER).
F-8   `evidence_vs_evidence` refused the planted pairing §13.1 names it for.
F-9   `Discovery.action`/`at` were never validated (DISCOVERABLE vs DISCOVERED).
F-10  `project_for_player` was not gated on discovery (DISCOVERED vs VISIBLE TO PLAYER).
F-11  a forged `DiscoveryState` was trusted by every reader.
F-13  `known_to` bound awareness to a person, not to the item (KNOWN BY CHARACTER).
"""
from __future__ import annotations

import pytest

from eidolon.evidence.contradiction import contradiction, evidence_vs_evidence
from eidolon.evidence.discovery import (
    Discovery, DiscoveryState, apply_discovery, check_discovery_state, project_for_player,
)
from eidolon.evidence.grounding import (
    check_creation_grounding, check_evidence_grounding, check_known_to_soundness,
    check_reference_integrity, check_temporal_grounding,
)
from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication
from eidolon.minds.knowledge import KnowledgeEntry, KnowledgeStore
from eidolon.minds.provenance import Participated, Witnessed
from eidolon.world.propositions import (
    At, Attr, Did, DidNot, Has, Incidental, Moved, ObjectAt, State,
)
from tests.evidence.fixtures.vance_evidence import evidence_case, evidence_case_store


def _ev(id_="EX", *, kind="Object", at="Knife", props=(), requires=(), **kw):
    return Evidence(id=id_, kind=kind,
                    implications=tuple(Implication(proposition=p, requires=requires) for p in props),
                    discovery=DiscoverySpec(action="Look", at=at), **kw)


def _rules(violations):
    return {v.rule for v in violations}


# --- F-1: PRESENT IN WORLD is checked before GROUNDED ----------------------------------
_TICK = (20, 21)  # exactly the discovery anchor, so P-9 can never be what rejects these


@pytest.mark.parametrize("prop, missing", [
    (Has(actor="Ann", object="GhostObj", interval=_TICK), "GhostObj"),
    (Has(actor="Ghost", object="Knife", interval=_TICK), "Ghost"),
    (ObjectAt(object="GhostObj", holder="Parlor", interval=_TICK), "GhostObj"),
    (ObjectAt(object="Knife", holder="Atlantis", interval=_TICK), "Atlantis"),
    (State(actor="Ghost", attr="mood", value="calm", interval=_TICK), "Ghost"),
    (Moved(actor="Ghost", from_loc="Parlor", to_loc="Cellar", t=5), "Ghost"),
    (Moved(actor="Ann", from_loc="Parlor", to_loc="Atlantis", t=5), "Atlantis"),
    (Attr(entity="Ghost", attr="hair", value="red"), "Ghost"),
    (Incidental(entity="Ghost", attr="hair", value="red"), "Ghost"),
    (Did(actor="Ghost", action="touch", object="Knife", interval=_TICK), "Ghost"),
])
def test_f1_an_implication_naming_a_nonexistent_entity_is_rejected(prop, missing):
    """`truth_value` answers Unknown for all of these — correctly, since the world settles
    nothing about entities it does not contain — so P-0 alone let every one of them pass."""
    v = check_evidence_grounding(evidence_case(), EvidenceStore([_ev(props=(prop,))]))
    assert any(missing in x.detail and x.rule == "P-6" for x in v), v


def test_f1_p0_now_refutes_a_false_placement_of_a_real_unmoved_object():
    """The knife is canonically in the Parlor and no event ever moves it, so
    `world_at().object_at` has no entry for it. Reading that absence as "no opinion" made
    every claim about an untouched object Unknown, and an authentic item could put the
    murder weapon in the wrong room."""
    case = evidence_case()
    store = EvidenceStore([_ev(props=(ObjectAt(object="Knife", holder="Cellar", interval=_TICK),))])
    assert "P-0" in _rules(check_evidence_grounding(case, store))
    truthful = EvidenceStore([_ev(props=(ObjectAt(object="Knife", holder="Parlor", interval=_TICK),))])
    assert check_evidence_grounding(case, truthful) == []


def test_f1_planted_evidence_is_exempt_from_p0_but_never_from_reference_integrity():
    """A forgery is designed to be FALSE; it is never about things that do not exist."""
    case = evidence_case()
    false_but_real = _ev(props=(ObjectAt(object="Knife", holder="Cellar", interval=_TICK),),
                          authentic=False, planted_by="plant")
    assert "P-0" not in _rules(check_evidence_grounding(case, EvidenceStore([false_but_real])))
    unreal = _ev(props=(ObjectAt(object="GhostObj", holder="Cellar", interval=_TICK),),
                  authentic=False, planted_by="plant")
    assert check_reference_integrity(case, EvidenceStore([unreal])) != []


# --- F-2: a trace has a cause even when the cause is not pinned ------------------------
def test_f2_a_trace_with_no_created_by_still_needs_a_cause_somewhere_in_the_log():
    """§5.2: "no evidence exists without a cause". Leaving `created_by` unset is legitimate
    (forensics under-determine WHICH handling left the mark) but cannot excuse the item from
    having a cause at all — the Letter is never marked by any event."""
    case = evidence_case()
    v = check_creation_grounding(case, EvidenceStore([
        _ev(kind="Fingerprint", object="Letter", location_at_investigation="Cellar", at="Letter")]))
    assert any("evidence without a cause" in x.detail for x in v), v


def test_f2_an_unpinned_trace_on_a_marked_object_is_accepted():
    """The knife IS marked by the `grip` event, so an unpinned print on it is grounded."""
    case = evidence_case()
    v = check_creation_grounding(case, EvidenceStore([
        _ev(kind="Fingerprint", object="Knife", location_at_investigation="Parlor")]))
    assert not [x for x in v if "evidence without a cause" in x.detail]


def test_f2_a_non_trace_kind_never_needs_a_trace_effect():
    """A document's existence needs no forensic act on it — the rule must not over-fire."""
    case = evidence_case()
    v = check_creation_grounding(case, EvidenceStore([
        _ev(kind="Document", object="Letter", location_at_investigation="Cellar", at="Letter")]))
    assert not [x for x in v if "evidence without a cause" in x.detail]


# --- F-3: forged provenance is caught on every implication, not just timed ones ---------
@pytest.mark.parametrize("prop", [
    Attr(entity="Ann", attr="alibi", value="ironclad"),
    Moved(actor="Ann", from_loc="Parlor", to_loc="Cellar", t=5),
    Incidental(entity="Ann", attr="mood", value="calm"),
])
def test_f3_a_dangling_requires_is_rejected_on_interval_free_implications(prop):
    """The check used to sit below the `interval is None` guard, so an implication over a
    proposition with no interval could name a `requires` id resolving to nothing at all."""
    v = check_temporal_grounding(evidence_case(), EvidenceStore([
        _ev(props=(prop,), requires=("totally-made-up",))]))
    assert any("forged or dangling provenance" in x.detail for x in v), v


def test_f3_a_resolvable_requires_on_an_interval_free_implication_is_accepted():
    anchor = _ev("ANCHOR")
    target = _ev("T", props=(Attr(entity="Ann", attr="alibi", value="ironclad"),), requires=("ANCHOR",))
    assert check_temporal_grounding(evidence_case(), EvidenceStore([anchor, target])) == []


# --- F-4: a sealed item is sealed all the way down (I-4) -------------------------------
def test_f4_known_to_cannot_be_mutated_after_construction():
    ev = _ev(known_to={"Ann": "K1"})
    with pytest.raises(TypeError):
        ev.known_to["Mallory"] = "K_FORGED"
    for mutate in (lambda d: d.update({"Mallory": "X"}), lambda d: d.pop("Ann"),
                   lambda d: d.setdefault("Mallory", "X"), lambda d: d.clear()):
        with pytest.raises(TypeError):
            mutate(ev.known_to)
    assert dict(ev.known_to) == {"Ann": "K1"}


def test_f4_known_to_still_reads_compares_and_round_trips():
    ev = _ev(known_to={"Ann": "K1"})
    assert ev.known_to["Ann"] == "K1" and list(ev.known_to) == ["Ann"]
    assert Evidence.model_validate_json(ev.model_dump_json()) == ev


# --- F-6: Did/DidNot slot semantics ----------------------------------------------------
def test_f6_a_denial_about_another_location_is_not_a_contradiction():
    """False positive: `location` is a slot of both propositions and was never compared."""
    assert contradiction(
        Did(actor="X", action="touch", object="O", location="Kitchen", interval=(10, 20)),
        DidNot(actor="X", action="touch", object="O", location="Study", interval=(10, 20))) is None


def test_f6_a_blanket_denial_contradicts_a_specific_act():
    """Missed contradiction, and it is §13.3's own shape: "I never touched anything" against
    a forensic implication that David touched Glass1. `FactIndex._tv_Did` already reads an
    unfilled `object` as "any object"; the detector now agrees."""
    did = Did(actor="David", action="touch", object="Glass1", location="Study", interval=(12, 120))
    for denial in (DidNot(actor="David", action="touch", interval=(0, 120)),
                   DidNot(actor="David", action="touch", object=None, location="Study", interval=(0, 120))):
        c = contradiction(did, denial)
        assert c is not None and c.kind == "negation"
        assert contradiction(denial, did) is not None       # order-independent


def test_f6_an_existential_assertion_does_not_contradict_a_specific_denial():
    """The wildcard is directional: "I touched something" is compatible with "I did not
    touch Glass1" — the something may have been another object."""
    assert contradiction(Did(actor="X", action="touch", interval=(10, 20)),
                          DidNot(actor="X", action="touch", object="Glass1", interval=(10, 20))) is None


def test_f6_did_didnot_honours_granularity_like_at_notat():
    assert contradiction(Did(actor="X", action="touch", object="O", interval=(10, 20)),
                          DidNot(actor="X", action="touch", object="O", interval=(40, 50)),
                          granularity_a=30, granularity_b=30) is None


# --- F-7: visibility is a fact about the player -----------------------------------------
def test_f7_visibility_requires_both_sides_in_the_players_material():
    a = At(actor="X", location="Study", interval=(10, 20))
    b = At(actor="X", location="Kitchen", interval=(15, 25))
    assert contradiction(a, b, a_id="E1", b_id="E2").visible_to_player is False   # unknown -> closed
    assert contradiction(a, b, a_id="E1", b_id="E2",
                          player_material=frozenset()).visible_to_player is False
    assert contradiction(a, b, a_id="E1", b_id="E2",
                          player_material=frozenset({"E1"})).visible_to_player is False  # one side only
    assert contradiction(a, b, a_id="E1", b_id="E2",
                          player_material=frozenset({"E1", "E2"})).visible_to_player is True


def test_f7_an_engine_only_pairing_stays_hidden_even_when_both_sides_are_held():
    """§4.7/§14.4: `Incidental` vs `Attr` is an authoring check, never notebook tension."""
    c = contradiction(Attr(entity="Glass1", attr="color", value="clear"),
                       Incidental(entity="Glass1", attr="color", value="green"),
                       a_id="E1", b_id="E2", player_material=frozenset({"E1", "E2"}))
    assert c is not None and c.visible_to_player is False


# --- F-8: the planted pairing §13.1 names ----------------------------------------------
def test_f8_planted_versus_authentic_tension_is_reported():
    """§13.1: "evidence vs evidence | planted-evidence tension; validator". Gating on
    authenticity silenced the unmasking material §19.5 requires every planted item to have."""
    authentic = _ev("E1", props=(At(actor="Ann", location="Parlor", interval=(2, 3)),))
    planted = _ev("E2", props=(At(actor="Ann", location="Cellar", interval=(2, 3)),),
                   authentic=False, planted_by="plant")
    assert len(evidence_vs_evidence(authentic, planted)) == 1
    assert len(evidence_vs_evidence(planted, authentic)) == 1


def test_f8_the_v1_authoring_check_is_still_expressible_by_the_caller():
    both = [_ev("E1", props=(At(actor="Ann", location="Parlor", interval=(2, 3)),)),
            _ev("E2", props=(At(actor="Ann", location="Cellar", interval=(2, 3)),))]
    v1 = [c for c in evidence_vs_evidence(*both) if both[0].authentic and both[1].authentic]
    assert len(v1) == 1


def test_f8_authenticity_never_leaks_through_the_contradiction():
    planted = _ev("E2", props=(At(actor="Ann", location="Cellar", interval=(2, 3)),),
                   authentic=False, planted_by="plant")
    authentic = _ev("E1", props=(At(actor="Ann", location="Parlor", interval=(2, 3)),))
    for c in evidence_vs_evidence(authentic, planted):
        assert "plant" not in c.explanation and "authentic" not in c.explanation
        assert set(c.model_dump()) == {"a", "b", "kind", "severity", "explanation", "visible_to_player"}


# --- F-9: the Discovery event must describe a discovery this item admits ----------------
def test_f9_the_wrong_action_is_rejected():
    store = evidence_case_store()
    state = DiscoveryState(held_items=frozenset({"kit"}))
    with pytest.raises(ValueError, match="requires 'Dust'"):
        apply_discovery(state, Discovery(evidence_id="E_fp", turn=1, action="Look", at="Knife"), store)


def test_f9_the_wrong_location_is_rejected():
    store = evidence_case_store()
    state = DiscoveryState(held_items=frozenset({"kit"}))
    with pytest.raises(ValueError, match="found at 'Knife'"):
        apply_discovery(state, Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Atlantis"), store)


def test_f9_the_matching_event_is_still_accepted_and_stays_idempotent():
    store = evidence_case_store()
    state = DiscoveryState(held_items=frozenset({"kit"}))
    good = Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife")
    once = apply_discovery(state, good, store)
    assert once.known_evidence == frozenset({"E_fp"})
    assert apply_discovery(once, good, store) == once


# --- F-10: DISCOVERED is upstream of VISIBLE TO PLAYER ----------------------------------
def test_f10_an_undiscovered_item_projects_to_nothing():
    store = evidence_case_store()
    assert project_for_player(store.get("E_letter"), DiscoveryState()) is None
    assert project_for_player(store.get("E_letter"),
                              DiscoveryState(known_evidence=frozenset({"E_fp"}))) is None


def test_f10_a_discovered_item_projects_and_its_unlocks_follow_the_same_state():
    store = evidence_case_store()
    ev = store.get("E_fp_wide")   # implication requires ("S_wipe", "E_fp")
    found = DiscoveryState(known_evidence=frozenset({"E_fp_wide"}))
    assert project_for_player(ev, found).unlocked == ()
    both = DiscoveryState(known_evidence=frozenset({"E_fp_wide", "E_fp"}),
                           known_statements=frozenset({"S_wipe"}))
    assert project_for_player(ev, both).unlocked == tuple(i.proposition for i in ev.implications)


# --- F-11: a hand-built DiscoveryState is checkable --------------------------------------
def test_f11_a_forged_discovery_state_is_reported_unsound():
    store = evidence_case_store()
    assert check_discovery_state(DiscoveryState(known_evidence=frozenset({"GHOST"})), store)
    # E_fp_wide requires EvidenceFound(E_fp); holding it alone is not a reachable state.
    assert check_discovery_state(DiscoveryState(known_evidence=frozenset({"E_fp_wide"})), store)


def test_f11_a_state_the_fold_could_have_produced_is_sound():
    store = evidence_case_store()
    state = DiscoveryState(held_items=frozenset({"kit"}))
    for e in (Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife"),
              Discovery(evidence_id="E_fp_wide", turn=2, action="Dust", at="Knife")):
        state = apply_discovery(state, e, store)
    assert check_discovery_state(state, store) == []
    assert check_discovery_state(DiscoveryState(), store) == []


# --- F-13: awareness is bound to the ITEM, not merely to a person ------------------------
def _knowledge():
    about_knife = KnowledgeEntry(id="K1", character="Ann", proposition=Has(
        actor="Ann", object="Knife", interval=(2, 3)), source=Participated(event_id="grip"),
        acquired_at=2, reliability=1.0, is_true=True)
    unrelated = KnowledgeEntry(id="K2", character="Ann", proposition=At(
        actor="Ann", location="Parlor", interval=(0, 20)), source=Witnessed(
        event_id="stay:Ann:0", modality="co-presence", quality=1.0),
        acquired_at=0, reliability=1.0, is_true=True)
    return KnowledgeStore([about_knife, unrelated])


def test_f13_an_entry_unrelated_to_the_item_is_rejected():
    """Any entry of that actor's used to satisfy the field, so a `known_to` sealed at
    generation silently REBOUND to an unrelated proposition whenever positional knowledge
    ids shifted. The binding is now checked against the item itself."""
    ev = _ev(object="Knife", known_to={"Ann": "K2"})
    v = check_known_to_soundness(EvidenceStore([ev]), _knowledge(), evidence_case())
    assert any("is not about this item" in x.detail for x in v), v


def test_f13_an_entry_about_the_items_object_or_its_events_is_accepted():
    """Two sound bindings: the entry's proposition names the item's object, or its
    provenance names an event the item itself traces to (here Ann's `grip`, carried on
    `interacted` — she handled the thing, so she knows it exists)."""
    by_object = _ev("E1", object="Knife", known_to={"Ann": "K1"})
    by_event = _ev("E2", object="Letter", at="Letter", interacted=(("Ann", "grip"),),
                    known_to={"Ann": "K1"})
    store = EvidenceStore([by_object, by_event])
    v = check_known_to_soundness(store, _knowledge(), evidence_case())
    assert [x for x in v if "is not about this item" in x.detail] == []


def test_f13_an_unknown_actor_is_rejected():
    ev = _ev(object="Knife", known_to={"Mallory": "K1"})
    v = check_known_to_soundness(EvidenceStore([ev]), _knowledge(), evidence_case())
    assert any("unknown actor" in x.detail for x in v), v


def test_f13_the_referential_checks_still_hold():
    store = EvidenceStore([_ev(object="Knife", known_to={"Ann": "K404"})])
    assert any("unknown KnowledgeEntry" in x.detail
               for x in check_known_to_soundness(store, _knowledge(), evidence_case()))
    store = EvidenceStore([_ev(object="Knife", known_to={"Bea": "K1"})])
    assert any("belongs to Ann" in x.detail
               for x in check_known_to_soundness(store, _knowledge(), evidence_case()))
