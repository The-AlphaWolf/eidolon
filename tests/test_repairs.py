"""Regression tests for the nine blocking defects found in the Phase 1 + Phase 2 audit.

Every test here fails on the pre-repair tree. Oracles are deliberately *independent* of the
code under test: they are computed from the fixture's own declared timeline, from the
architecture's stated rule, or from an invariance property (shuffle the input, the output
must not move) — never by restating the implementation's own expression.
"""
from __future__ import annotations

import hashlib
import random

import pytest

from eidolon.minds.admissibility import admissibility_level
from eidolon.minds.belief import BeliefStore, form_beliefs
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.events import KnowledgeAdded
from eidolon.minds.fold import apply_epistemic
from eidolon.minds.knowledge import (
    KnowledgeEntry, KnowledgeStore, propagate_knowledge, with_overlay,
)
from eidolon.minds.provenance import (
    AdmissibilityLevel, InvestigationTold, Participated, Told, Witnessed,
)
from eidolon.minds.soundness import check_knowledge_soundness
from eidolon.world.case import Case
from eidolon.world.events import EffActorAt, EffInformationTransferred, Event
from eidolon.world.facts import FactIndex
from eidolon.world.perception import derive_perception
from eidolon.world.physics import PhysicsViolationError, check_physics
from eidolon.world.propositions import At, Did, Incidental, NotAt, Saw
from eidolon.world.state import loc_at
from tests.world.fixtures.vance import (
    ACTORS, LOCATIONS, OBJECTS, TRAVEL, _PERCEPTION_V03, _stays,
    vance_v01_negative, vance_v02_negative, vance_v03,
)

MURDER_INTERVAL = (76, 77)  # `cases/vance_v03.json`: "Attack David @Study 22:16-22:17"


def _case(events, **kw):
    return Case(id="repair", t_investigation=120, actors=ACTORS, locations=LOCATIONS,
                objects=OBJECTS, travel_edges=TRAVEL, perception_edges=_PERCEPTION_V03,
                events=tuple(events), rels=(), **kw)


def _store_digest(store: KnowledgeStore) -> str:
    """Content digest of a knowledge store, independent of entry ids and insertion order —
    so it compares what characters KNOW, not how the fold happened to number it."""
    rows = sorted(
        (e.character, e.proposition.model_dump_json(), e.source.kind, e.acquired_at,
         round(e.reliability, 6), e.is_true,
         getattr(e.source, "teller_sincere", None), getattr(e.source, "by", None))
        for e in store.all()
    )
    return hashlib.sha256(repr(rows).encode()).hexdigest()


# --------------------------------------------------------------------------- defect 1
def test_participants_hold_did_entries_for_the_events_they_took_part_in():
    """§4.8: "Participants of `e` receive `source=Participated, reliability=1.0` for the
    event's own facts." Oracle: the fixture's own event list — for every non-presence event
    with a living actor, that actor must hold a `Did` entry naming it."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    living = set(case.living_actors())

    expected = {(e.actor, e.kind, e.interval, e.location) for e in case.events
                if e.actor in living and e.kind != "Stay"}
    assert expected, "fixture has no non-presence events to check"
    for actor, kind, interval, location in expected:
        held = [e for e in store.for_character(actor)
                if e.proposition.kind == "Did" and e.proposition.action == kind
                and e.proposition.interval == interval and e.proposition.location == location]
        assert held, f"{actor} holds no Did entry for their own {kind} at {interval}"
        assert all(isinstance(e.source, Participated) and e.reliability == 1.0 for e in held)


def test_the_murderer_knows_what_he_did():
    """The concrete consequence: before the repair the store contained only At/NotAt/Saw, so
    the murderer held no entry that the murder happened — nothing for Phase 3 evidence to
    corroborate against and nothing for a deception layer to conceal."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    attack = [e for e in store.for_character("David")
              if e.proposition.kind == "Did" and e.proposition.action == "Attack"]
    assert attack, "David holds no knowledge of his own attack"
    assert attack[0].proposition.interval == MURDER_INTERVAL
    assert attack[0].proposition.object == "Glass1"
    assert attack[0].is_true is True


def test_no_bystander_acquires_a_did_entry_for_an_event_they_did_not_take_part_in():
    """The knowledge boundary still holds (I-8): witnesses get `Saw`/`Heard` (rule 5), not
    the participants' own facts. Widening participation must not widen perception."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    by_event = {e.id: e for e in case.events}
    for entry in store.all():
        if entry.proposition.kind != "Did":
            continue
        event = by_event[entry.source.event_id]
        assert entry.character == event.actor or entry.character in event.participants


# --------------------------------------------------------------------------- defect 2
def test_saw_nobody_is_false_when_the_room_was_occupied():
    """`Saw(o, "nobody", L, I)` was hardcoded True. Oracle: the fixture timeline itself —
    Elena, Margaret and Robert share the Kitchen over [70,80)."""
    case, _ = vance_v03()
    index = FactIndex(case)
    others = [a for a in case.actors if a != "Elena"
              and any(loc_at(case.events, a, t) == "Kitchen" for t in range(70, 80))]
    assert others, "fixture precondition: someone else is in the Kitchen"
    assert index.truth_value(
        Saw(observer="Elena", subject="nobody", location="Kitchen",
            interval=(70, 80), identified=True)) is False


def test_saw_nobody_is_true_only_when_the_room_really_was_empty():
    case, _ = vance_v03()
    index = FactIndex(case)
    empty = all(loc_at(case.events, a, t) != "Gazebo"
                for a in case.actors if a != "Elena" for t in range(70, 80))
    assert empty, "fixture precondition: the Gazebo is empty over [70,80)"
    assert index.truth_value(
        Saw(observer="Elena", subject="nobody", location="Gazebo",
            interval=(70, 80), identified=True)) is True


# --------------------------------------------------------------------------- defect 3
def _told_chain_case():
    prop = At(actor="David", location="Study", interval=(74, 77))
    tell1 = Event(id="tell1", kind="Speak", interval=(100, 101), location="Hall", actor="David",
                  participants=("Margaret",),
                  effects=(EffInformationTransferred(from_actor="David", to_actor="Margaret",
                                                      propositions=(prop,)),))
    tell2 = Event(id="tell2", kind="Speak", interval=(102, 103), location="Hall", actor="Margaret",
                  participants=("Robert",),
                  effects=(EffInformationTransferred(from_actor="Margaret", to_actor="Robert",
                                                      propositions=(prop,)),))
    base, _ = vance_v03()
    return base.events + (tell1, tell2), prop


def test_knowledge_is_invariant_under_reordering_of_the_caselog():
    """I-5 / §4.1: the CaseLog is a set of events. Two logs with equal content must fold to
    equal knowledge. Oracle: an invariance property — shuffle the input, the digest must not
    move. Before the repair a `Told` chain folded in authoring order, so reversing two Speak
    events flipped a listener's entry between reliability 1.0/sincere and 0.0/insincere."""
    events, _ = _told_chain_case()
    baseline = _store_digest(propagate_knowledge(_case(events)))
    for seed in range(8):
        shuffled = list(events)
        random.Random(seed).shuffle(shuffled)
        assert _store_digest(propagate_knowledge(_case(shuffled))) == baseline, \
            f"knowledge changed under shuffle seed {seed}"
    assert _store_digest(propagate_knowledge(_case(tuple(reversed(events))))) == baseline


def test_a_told_chain_resolves_by_time_not_by_authoring_order():
    """The specific consequence: the second hop must inherit the first hop's reliability
    however the two Speak events happen to be ordered in the tuple."""
    events, prop = _told_chain_case()
    for ordering in (events, tuple(reversed(events))):
        store = propagate_knowledge(_case(ordering))
        robert = store.find("Robert", prop)
        assert robert is not None and robert.source.teller_sincere is True
        assert robert.reliability == 1.0


# --------------------------------------------------------------------------- defect 4
def test_propagate_knowledge_refuses_a_physically_invalid_case():
    """§4.9 + §23.1: every derivation in `minds/` reads `presence`/`loc_at` and assumes P-1.
    `check_physics` existed but nothing on the production path called it."""
    teleport = _stays("Elena", [("Study", 0, 5), ("Gazebo", 5, 120)])
    case = _case(teleport)
    assert any(v.rule == "P-2" for v in check_physics(case))
    with pytest.raises(PhysicsViolationError) as excinfo:
        propagate_knowledge(case)
    assert any(v.rule == "P-2" for v in excinfo.value.violations)


def test_propagate_knowledge_refuses_a_case_with_overlapping_presence():
    overlapping = _stays("Elena", [("Kitchen", 0, 60)]) + _stays("Elena", [("Study", 30, 90)])
    with pytest.raises(PhysicsViolationError) as excinfo:
        propagate_knowledge(_case(overlapping))
    assert any(v.rule == "P-1" for v in excinfo.value.violations)


def test_the_gate_grades_the_world_not_the_evidence():
    """P-9 rejects `vance_v02_negative`'s E10 by design (T-16). That must not make the world
    itself unusable — evidence is an argument *about* the world, judged separately."""
    case, evidence = vance_v02_negative()
    assert any(v.rule == "P-9" for v in check_physics(case, evidence))
    assert propagate_knowledge(case).all()


# --------------------------------------------------------------------------- defect 5
def test_presence_predicates_are_never_unknown_over_transit_ticks():
    """§4.1 makes the CaseLog complete, so an actor on a travel edge is determinately in no
    room. Oracle: the fixture's own timeline — Robert has no segment covering ticks 7-8."""
    case, _ = vance_v03()
    index = FactIndex(case)
    assert loc_at(case.events, "Robert", 7) is None, "fixture precondition: Robert is in transit"
    assert index.truth_value(NotAt(actor="Robert", location="Kitchen", interval=(6, 9))) is True
    assert index.truth_value(At(actor="Robert", location="Kitchen", interval=(6, 9))) is False


def test_no_perception_derived_entry_is_recorded_as_refuted():
    """§6.1: knowledge "can be false? No"; §6.2 allows a false proposition only for `Told`.
    `is_true=False` therefore means REFUTED. Before the repair, Unknown collapsed into it and
    13 true `NotAt` facts in the shipping golden case were filed as refuted."""
    for build in (vance_v01_negative, vance_v02_negative, vance_v03):
        case, _ = build()
        for entry in propagate_knowledge(case).all():
            if not isinstance(entry.source, Told):
                assert entry.is_true is True, f"{entry.id}: {entry.source.kind} entry marked refuted"


def test_unknown_is_still_reachable_where_the_architecture_wants_it():
    """The repair must not delete the third truth value — §4.7 keeps it for `Incidental` and
    for attributes never defined."""
    case, _ = vance_v03()
    index = FactIndex(case)
    assert index.truth_value(Incidental(entity="Study", attr="mood", value="tense")) is None
    from eidolon.world.propositions import Attr
    assert index.truth_value(Attr(entity="Elena", attr="never_defined", value="x")) is None


# --------------------------------------------------------------------------- defect 6
def test_told_records_the_grounding_entry_it_actually_relayed():
    """I-27 computes admissibility "from that claim's `grounding` chain". The chain has to be
    a recorded edge; re-resolving the teller's entry by search can select a different one."""
    events, prop = _told_chain_case()
    store = propagate_knowledge(_case(events))
    relay = store.find("Robert", prop)
    assert relay.source.grounding_entry_id is not None
    grounding = store.get(relay.source.grounding_entry_id)
    assert grounding is not None
    assert grounding.character == relay.source.by == "Margaret"
    assert grounding.proposition == prop


def test_admissibility_walks_the_recorded_edge_and_not_the_tellers_best_entry():
    """A teller holding a second, higher-reliability entry for the same proposition must not
    silently become the grounding of a relay that named a different one."""
    prop = At(actor="David", location="Study", interval=(74, 77))
    store = KnowledgeStore([
        KnowledgeEntry(id="K_named", character="Elena", proposition=prop,
                       source=InvestigationTold(by_detective_turn=3),
                       acquired_at=100, reliability=0.4, is_true=True),
        KnowledgeEntry(id="K_unrelated", character="Elena", proposition=prop,
                       source=Witnessed(event_id="argue@Elena", modality="sight", quality=0.9),
                       acquired_at=74, reliability=0.9, is_true=True),
        KnowledgeEntry(id="K_relay", character="Margaret", proposition=prop,
                       source=Told(by="Elena", speak_event_id="argue", teller_sincere=True,
                                    grounding_entry_id="K_named"),
                       acquired_at=101, reliability=0.4, is_true=True),
    ])
    # `find` would return the higher-reliability entry; the walk must not consult it.
    assert store.find("Elena", prop).id == "K_unrelated"
    assert admissibility_level("K_named", store, BeliefStore()) == AdmissibilityLevel.L0
    assert admissibility_level("K_relay", store, BeliefStore()) == AdmissibilityLevel.L0


def test_v2_rejects_a_forged_or_dangling_grounding_edge():
    prop = At(actor="David", location="Study", interval=(74, 77))
    case, _ = vance_v03()
    dangling = KnowledgeStore([
        KnowledgeEntry(id="K1", character="Margaret", proposition=prop,
                       source=Told(by="Elena", speak_event_id="argue", teller_sincere=True,
                                    grounding_entry_id="K_does_not_exist"),
                       acquired_at=101, reliability=0.5, is_true=True),
    ])
    assert [v for v in check_knowledge_soundness(dangling, case) if "grounding" in str(v)]

    forged = KnowledgeStore([
        KnowledgeEntry(id="K_robert", character="Robert", proposition=prop,
                       source=Witnessed(event_id="argue@Robert", modality="sight", quality=0.9),
                       acquired_at=74, reliability=0.9, is_true=True),
        KnowledgeEntry(id="K2", character="Margaret", proposition=prop,
                       source=Told(by="Elena", speak_event_id="argue", teller_sincere=True,
                                    grounding_entry_id="K_robert"),  # Elena does not hold it
                       acquired_at=101, reliability=0.9, is_true=True),
    ])
    assert [v for v in check_knowledge_soundness(forged, case) if "grounding" in str(v)]


# --------------------------------------------------------------------------- defect 7
def test_the_provenance_walk_can_reach_runtime_added_knowledge():
    """AC-1/I-27: a chain running through an `InvestigationTold` entry is L0 "forever, in
    every mouth it passes through". Runtime entries live in `EpistemicState.added_knowledge`
    (§6.3), so the walk has to resolve ids across both containers or the chain dead-ends."""
    prop = At(actor="David", location="Study", interval=(74, 77))
    detective_told = KnowledgeEntry(
        id="K_runtime", character="Elena", proposition=prop,
        source=InvestigationTold(by_detective_turn=3), acquired_at=100, reliability=0.5, is_true=True)
    epistemic = apply_epistemic(EpistemicState(), KnowledgeAdded(entry=detective_told))

    sealed = KnowledgeStore([
        KnowledgeEntry(id="K_relay", character="Margaret", proposition=prop,
                       source=Told(by="Elena", speak_event_id="argue", teller_sincere=True,
                                    grounding_entry_id="K_runtime"),
                       acquired_at=101, reliability=0.5, is_true=True),
    ])
    assert sealed.get("K_runtime") is None, "sealed store must not absorb runtime knowledge (I-4)"

    view = with_overlay(sealed, epistemic)
    assert view.get("K_runtime") is not None
    assert admissibility_level("K_runtime", view, BeliefStore()) == AdmissibilityLevel.L0
    assert admissibility_level("K_relay", view, BeliefStore()) == AdmissibilityLevel.L0
    # the view is derived, never written back — no second source of truth
    assert sealed.get("K_runtime") is None
    assert len(sealed.all()) == 1


# --------------------------------------------------------------------------- defect 8
def _belief_inputs():
    """Three `At` beliefs about one actor whose conflict relation is NOT transitive:
    A overlaps B, B overlaps C, A and C do not overlap."""
    props = {
        "A": At(actor="David", location="Hall", interval=(0, 10)),
        "B": At(actor="David", location="Study", interval=(8, 20)),
        "C": At(actor="David", location="Hall", interval=(18, 30)),
    }
    rel = {"A": 0.65, "B": 0.95, "C": 0.75}
    return [
        KnowledgeEntry(id=f"K{k}", character="Elena", proposition=props[k],
                       source=Witnessed(event_id="argue@Elena", modality="sight", quality=rel[k]),
                       acquired_at=0, reliability=rel[k], is_true=True)
        for k in ("A", "B", "C")
    ]


def _incompatible(a, b) -> bool:
    """Independent oracle: two `At` propositions about one actor are incompatible when they
    put them in different rooms over overlapping ticks (§4.9 P-1). Written from the rule, not
    from `belief._conflicts`."""
    if not (a.kind == b.kind == "At" and a.actor == b.actor):
        return False
    if a.location == b.location:
        return False
    return a.interval[0] < b.interval[1] and b.interval[0] < a.interval[1]


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 0, 1), (1, 2, 0), (2, 1, 0), (0, 2, 1)])
def test_form_beliefs_never_returns_a_logically_incompatible_set(order):
    """§6.4 rule 5. Conflict is not transitive, so evicting one incumbent per candidate could
    leave two beliefs that clash with each other but not with the winner."""
    case, _ = vance_v03()
    entries = _belief_inputs()
    store = KnowledgeStore([entries[i] for i in order])
    result = form_beliefs("Elena", store, case, FactIndex(case))
    clashing = [(x.proposition, y.proposition)
                for i, x in enumerate(result.beliefs) for y in result.beliefs[i + 1:]
                if _incompatible(x.proposition, y.proposition)]
    assert clashing == [], f"incompatible beliefs kept together: {clashing}"


def test_belief_formation_is_independent_of_store_insertion_order():
    case, _ = vance_v03()
    entries = _belief_inputs()
    index = FactIndex(case)
    seen = set()
    for order in ((0, 1, 2), (2, 0, 1), (1, 2, 0), (2, 1, 0)):
        result = form_beliefs("Elena", KnowledgeStore([entries[i] for i in order]), case, index)
        seen.add(tuple(sorted(b.proposition.model_dump_json() for b in result.beliefs)))
    assert len(seen) == 1, "belief set depends on insertion order"


def test_compatible_observations_of_the_same_room_are_both_kept():
    """Rule 5 resolves contradictions; it must not suppress a belief that merely says
    something else. Two overlapping sightings of one actor in ONE room are compatible —
    exactly what co-presence plus sustained sighting produce for the same person."""
    case, _ = vance_v03()
    props = [At(actor="David", location="Hall", interval=(0, 10)),
             At(actor="David", location="Hall", interval=(5, 15))]
    store = KnowledgeStore([
        KnowledgeEntry(id=f"K{i}", character="Elena", proposition=p,
                       source=Witnessed(event_id="argue@Elena", modality="sight", quality=0.9),
                       acquired_at=0, reliability=0.9, is_true=True)
        for i, p in enumerate(props)
    ])
    result = form_beliefs("Elena", store, case, FactIndex(case))
    assert {b.proposition.interval for b in result.beliefs} == {(0, 10), (5, 15)}
    assert result.suppressed == ()


def test_every_actors_beliefs_on_the_golden_case_are_mutually_consistent():
    case, _ = vance_v03()
    store, index = propagate_knowledge(case), FactIndex(case)
    for actor in case.living_actors():
        beliefs = form_beliefs(actor, store, case, index).beliefs
        for i, x in enumerate(beliefs):
            for y in beliefs[i + 1:]:
                assert not _incompatible(x.proposition, y.proposition), (actor, x.proposition, y.proposition)


# --------------------------------------------------------------------------- defect 9
@pytest.mark.parametrize("build", [vance_v01_negative, vance_v02_negative, vance_v03])
def test_authored_evidence_is_not_refuted_by_the_world_it_describes(build):
    """A case's own implications must not contradict its own CaseLog. Without this check
    "authored wrong" is indistinguishable from "deliberately planted" once Phase 3 arrives."""
    case, evidence = build()
    index = FactIndex(case)
    refuted = [eid for eid, imp in evidence if index.truth_value(imp.proposition) is False]
    assert refuted == [], f"{case.id}: implications refuted by the canonical world: {refuted}"


def test_a_refuted_implication_is_reported():
    from eidolon.world.physics import Implication
    case, _ = vance_v03()
    lie = Implication(At(actor="David", location="Gazebo", interval=MURDER_INTERVAL),
                      created_at=MURDER_INTERVAL)
    assert FactIndex(case).truth_value(lie.proposition) is False
    assert any(v.rule == "P-0" for v in check_physics(case, [("E_false", lie)]))


def test_golden_fixtures_keep_their_intended_physics_verdicts():
    """v01/v03 clean; v02 retains exactly its one deliberate P-9 negative (T-16)."""
    v01, ev01 = vance_v01_negative()
    v03, ev03 = vance_v03()
    assert check_physics(v01, ev01) == []
    assert check_physics(v03, ev03) == []
    v02, ev02 = vance_v02_negative()
    assert [v.rule for v in check_physics(v02, ev02)] == ["P-9"]


# --------------------------------------------------------------------------- absence (I-34)
def test_absence_knowledge_stops_where_attention_stops():
    """§4.8.7 / I-34: attention must hold at `ATTENTION_AWAKE` *throughout* the claimed
    window, and the window is the maximal sub-interval over which it did. Sampling attention
    once at the segment start made a character who dozed off a perfect absence witness for
    the rest of the hour — the v0.2 defect I-34 was written to prevent."""
    from eidolon.world.events import EffActorState
    awake = Event(id="s0", kind="Stay", interval=(0, 10), location="Kitchen", actor="Elena",
                  effects=(EffActorAt(actor="Elena", location="Kitchen"),
                           EffActorState(actor="Elena", attr="attention", value="1.0")))
    asleep = Event(id="s1", kind="Stay", interval=(10, 60), location="Kitchen", actor="Elena",
                   effects=(EffActorAt(actor="Elena", location="Kitchen"),
                            EffActorState(actor="Elena", attr="attention", value="0.3")))
    case = _case((awake, asleep) + tuple(_stays("Margaret", [("Hall", 0, 60)])))
    absences = [f for f in derive_perception(case) if f.source == "Absence" and f.observer == "Elena"]
    assert absences, "precondition: Elena is awake long enough to derive some absence"
    for f in absences:
        assert f.proposition.interval[1] <= 10, \
            f"absence claimed over {f.proposition.interval} but Elena was asleep from t=10"


def test_absence_reliability_stays_below_the_observers_own_presence_entry():
    """I-34: `r` strictly below the corresponding `At` the same actor holds."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    for entry in store.all():
        if entry.source.kind != "Absence":
            continue
        own = [e for e in store.for_character(entry.character)
               if e.proposition.kind == "At" and e.proposition.actor == entry.character
               and e.proposition.location == entry.proposition.location]
        if own:
            assert entry.reliability < max(e.reliability for e in own)


# --------------------------------------------------------------------------- cross-cutting
def test_full_pipeline_replay_is_deterministic_across_a_serialization_boundary():
    """I-5: replay reproduces identical state. Crosses a real boundary — the case is dumped
    to JSON, reloaded, and re-folded — rather than folding the same list twice in-process."""
    case, _ = vance_v03()
    reloaded = Case.model_validate_json(case.model_dump_json())
    assert reloaded.content_hash() == case.content_hash()
    assert _store_digest(propagate_knowledge(reloaded)) == _store_digest(propagate_knowledge(case))

    index = FactIndex(reloaded)
    store = propagate_knowledge(reloaded)
    for actor in reloaded.living_actors():
        a = form_beliefs(actor, store, case, index).beliefs
        b = form_beliefs(actor, store, reloaded, index).beliefs
        assert [x.proposition for x in a] == [x.proposition for x in b]


def test_knowledge_entries_still_round_trip():
    from pydantic import TypeAdapter
    case, _ = vance_v03()
    entries = propagate_knowledge(case).all()
    adapter = TypeAdapter(list[KnowledgeEntry])
    assert adapter.validate_json(adapter.dump_json(entries)) == entries


def test_v2_soundness_still_holds_on_the_whole_golden_pipeline():
    case, _ = vance_v03()
    store, index = propagate_knowledge(case), FactIndex(case)
    beliefs = BeliefStore()
    for actor in case.living_actors():
        for b in form_beliefs(actor, store, case, index).beliefs:
            beliefs.add(b)
    assert check_knowledge_soundness(store, case, beliefs) == []


def test_the_sealed_case_is_untouched_by_the_whole_pipeline():
    """I-4."""
    case, _ = vance_v03()
    before = case.content_hash()
    store, index = propagate_knowledge(case), FactIndex(case)
    for actor in case.living_actors():
        form_beliefs(actor, store, case, index)
    assert case.content_hash() == before
