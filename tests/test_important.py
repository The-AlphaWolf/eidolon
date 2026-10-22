"""Regression tests for the IMPORTANT (non-blocking) findings carried forward from the
Phase 1 + Phase 2 audit, after the nine blocking defects were repaired.

Same oracle discipline as `test_repairs.py`: every assertion is computed from the
architecture's stated rule, from the fixture's own declared timeline, or from an invariance
property — never by restating the implementation's own expression.

Each finding has at least one test that fails on the pre-repair tree; the rest are guards
that pin what must NOT change (range endpoints stay legal, genuinely different records still
accumulate, expressible actions still get a definite verdict), so a later "simplification"
cannot pass by loosening the rule instead of keeping it.
"""
from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from eidolon.minds.character import (
    CharacterState, DetectiveModel, Emotion, Personality, initial_character_state,
)
from eidolon.minds.epistemic import EpistemicState, RecallRecord, Revision
from eidolon.minds.events import (
    BeliefRevised, ComposureChange, MemoryRecall, PressureChange, SuspicionShift, TrustChange,
)
from eidolon.minds.fold import apply_character, apply_epistemic
from eidolon.minds.knowledge import propagate_knowledge
from eidolon.minds.scale import BP_MAX
from eidolon.world.case import Case
from eidolon.world.events import (
    EffActorState, EffInformationTransferred, Event, Perceptibility,
)
from eidolon.world.facts import FactIndex
from eidolon.world.interval import intersect, overlaps, ticks
from eidolon.world.perception import derive_perception
from eidolon.world.physics import Implication, check_physics
from eidolon.world.propositions import At, Did, DidNot
from eidolon.world.state import death_ticks, ordered_events, presence, world_at
from eidolon.world.timeline import (
    could_observe, could_reach, events_at, possible_window, who_was_at,
)
from tests.world.fixtures.vance import (
    ACTORS, LOCATIONS, OBJECTS, TRAVEL, _PERCEPTION_V03, _stays, vance_v03,
)

PERSONALITY = Personality(composure_base=0.5, volatility=0.2, deference=0.3, guile=0.4,
                          talkativeness=0.5, self_preservation=0.6)


# --------------------------------------------------------------- IMPORTANT-1: bp bounds
def _record(turn: int = 1) -> RecallRecord:
    return RecallRecord(turn_id=turn, cue_match_bp=5000, outcome="strong")


@pytest.mark.parametrize("bad", [-1, BP_MAX + 1, 999999, -5000])
@pytest.mark.parametrize("build", [
    lambda v: ComposureChange(new_composure_bp=v),
    lambda v: TrustChange(new_trust_detective=v),
    lambda v: SuspicionShift(new_value_bp=v),
    lambda v: PressureChange(secret_id="S1", new_value_bp=v),
    lambda v: MemoryRecall(memory_id="M1", turn_id=1, new_strength_bp=v, record=_record()),
    lambda v: BeliefRevised(belief_id="B1", new_confidence_bp=v,
                            revision=Revision(turn_id=1, old_bp=0, new_bp=0, reason="r")),
])
def test_every_bp_carrying_event_rejects_a_value_outside_the_basis_point_range(build, bad):
    """I-17: "all hashed runtime scalars are integer basis points" — §9's own code block
    pins the range at 0..10000. The event payload is where a runtime value ENTERS
    authoritative state, so it is where the range has to be enforced: the fold copies post
    values with `model_copy` (I-22) and never validates."""
    with pytest.raises(ValidationError):
        build(bad)


@pytest.mark.parametrize("bad", [-1, BP_MAX + 1])
@pytest.mark.parametrize("build", [
    lambda v: Emotion(anxiety=v),
    lambda v: Emotion(hostility=v),
    lambda v: Emotion(warmth=v),
    lambda v: DetectiveModel(estimated_suspicion_of_me=v),
    lambda v: CharacterState(actor="A", personality=PERSONALITY, composure=v),
    lambda v: CharacterState(actor="A", personality=PERSONALITY, trust_detective=v),
    lambda v: CharacterState(actor="A", personality=PERSONALITY, suspicion_of_detective=v),
    lambda v: CharacterState(actor="A", personality=PERSONALITY, suspicion={"B": v}),
    lambda v: CharacterState(actor="A", personality=PERSONALITY, verbal_pressure={"S1": v}),
    lambda v: EpistemicState(memory_strength={"M1": v}),
    lambda v: EpistemicState(belief_confidence={"B1": v}),
    lambda v: RecallRecord(turn_id=1, cue_match_bp=v, outcome="strong"),
    lambda v: Revision(turn_id=1, old_bp=v, new_bp=0, reason="r"),
    lambda v: Revision(turn_id=1, old_bp=0, new_bp=v, reason="r"),
])
def test_every_bp_state_field_rejects_a_value_outside_the_basis_point_range(build, bad):
    """The same range on the state models themselves, including the dict-valued ones —
    a bp scalar hidden behind a `dict[Key, int]` is still hashed authoritative state."""
    with pytest.raises(ValidationError):
        build(bad)


@pytest.mark.parametrize("ok", [0, 1, 5000, BP_MAX])
def test_the_endpoints_of_the_basis_point_range_are_legal(ok):
    """The bound must not be off by one at either end: 0 and 10000 are both real values
    (composure 0 = broken, 10000 = unshakeable)."""
    assert ComposureChange(new_composure_bp=ok).new_composure_bp == ok
    assert Emotion(anxiety=ok).anxiety == ok
    assert EpistemicState(memory_strength={"M1": ok}).memory_strength["M1"] == ok


def test_out_of_range_pressure_is_rejected_rather_than_silently_clamped():
    """Before the repair the fold clamped `PressureChange` to the cap and copied every other
    bp through unchecked — so one field silently rewrote a recorded outcome (against I-22)
    while the rest accepted nonsense. Rejecting at construction fixes both halves."""
    with pytest.raises(ValidationError):
        PressureChange(secret_id="S1", new_value_bp=BP_MAX + 1)
    state = initial_character_state("A", PERSONALITY)
    applied = apply_character(state, PressureChange(secret_id="S1", new_value_bp=BP_MAX))
    assert applied.verbal_pressure["S1"] == BP_MAX


def test_recall_record_carries_no_float_into_authoritative_state():
    """I-17: "no float enters authoritative state". `RecallRecord` lives inside
    `EpistemicState`, which §26.3 hashes — so its cue score is bp, not a float."""
    state = apply_epistemic(EpistemicState(),
                            MemoryRecall(memory_id="M1", turn_id=1, new_strength_bp=4000,
                                         record=_record()))
    for record in state.recall_log["M1"]:
        for name, value in record.model_dump().items():
            assert not isinstance(value, float), f"RecallRecord.{name} is a float in hashed state"


# ------------------------------------- IMPORTANT-2: duplicate append-shaped fold events
def test_replaying_a_duplicated_memory_recall_row_does_not_move_retrieval():
    """I-5: "replaying the SessionLog reproduces identical state hashes"; I-13 treats a
    duplicated row as corruption. `recall_log` is append-shaped, and `repetition_factor` is
    a function of exactly its length that multiplies `memory.score` — so before the repair
    one duplicated row raised the factor and could flip a retrieval from weak to strong.

    Oracle: an invariance property (apply the same event any number of times, the state must
    not move), plus the architecture's own §8.4 factor, not the fold's expression."""
    from eidolon.minds.memory import repetition_factor

    event = MemoryRecall(memory_id="M1", turn_id=7, new_strength_bp=4000, record=_record(7))
    once = apply_epistemic(EpistemicState(), event)
    for _ in range(5):
        replayed = apply_epistemic(once, event)
        assert replayed == once, "re-applying a recorded event moved the state"
        once = replayed
    assert len(once.recall_log["M1"]) == 1
    assert repetition_factor(once.recall_log["M1"]) == pytest.approx(1.05)


def test_genuinely_different_recalls_still_both_accumulate():
    """The dedupe must not swallow real information: two retrievals on different turns, or
    the same turn with a different outcome, are two records."""
    state = EpistemicState()
    for event in (
        MemoryRecall(memory_id="M1", turn_id=1, new_strength_bp=4000, record=_record(1)),
        MemoryRecall(memory_id="M1", turn_id=2, new_strength_bp=4000, record=_record(2)),
        MemoryRecall(memory_id="M1", turn_id=2, new_strength_bp=4000,
                     record=RecallRecord(turn_id=2, cue_match_bp=1000, outcome="weak")),
    ):
        state = apply_epistemic(state, event)
    assert len(state.recall_log["M1"]) == 3


def test_replaying_a_duplicated_belief_revision_row_does_not_double_the_history():
    revision = Revision(turn_id=3, old_bp=6000, new_bp=2000, reason="confronted")
    event = BeliefRevised(belief_id="B1", new_confidence_bp=2000, revision=revision)
    once = apply_epistemic(EpistemicState(), event)
    assert apply_epistemic(once, event) == once
    assert len(once.belief_revisions["B1"]) == 1
    other = BeliefRevised(belief_id="B1", new_confidence_bp=1000,
                          revision=Revision(turn_id=4, old_bp=2000, new_bp=1000, reason="evidence"))
    assert len(apply_epistemic(once, other).belief_revisions["B1"]) == 2


def test_replaying_a_duplicated_knowledge_added_row_does_not_duplicate_the_entry():
    from eidolon.minds.events import KnowledgeAdded
    from eidolon.minds.knowledge import KnowledgeEntry
    from eidolon.minds.provenance import InvestigationTold
    from eidolon.world.propositions import At

    entry = KnowledgeEntry(id="K_runtime", character="Elena",
                           proposition=At(actor="David", location="Study", interval=(74, 77)),
                           source=InvestigationTold(by_detective_turn=3), acquired_at=100,
                           reliability=0.5, is_true=True)
    once = apply_epistemic(EpistemicState(), KnowledgeAdded(entry=entry))
    assert apply_epistemic(once, KnowledgeAdded(entry=entry)) == once
    assert len(once.added_knowledge) == 1

    # ...but two DIFFERENT entries sharing one id is impossible provenance, not a duplicate:
    # `KnowledgeStore.add` rejects it and the overlay view would silently keep one. Fail closed.
    conflicting = entry.model_copy(update={"reliability": 0.9})
    with pytest.raises(ValueError):
        apply_epistemic(once, KnowledgeAdded(entry=conflicting))


def test_the_whole_epistemic_fold_is_idempotent_under_a_wholly_duplicated_log():
    """The property the store-level `action_id`/`expected_seq` guards (I-14) must also hold
    in the fold itself: folding a log twice end-to-end lands on the same state as once."""
    from eidolon.minds.events import KnowledgeAdded, MemoryCorrected
    from eidolon.minds.knowledge import KnowledgeEntry
    from eidolon.minds.provenance import InvestigationTold
    from eidolon.world.propositions import At

    log = [
        MemoryRecall(memory_id="M1", turn_id=1, new_strength_bp=4000, record=_record(1)),
        MemoryCorrected(memory_id="M1", field="interval", corrected_value=[10, 20], turn_id=1),
        BeliefRevised(belief_id="B1", new_confidence_bp=3000,
                      revision=Revision(turn_id=1, old_bp=6000, new_bp=3000, reason="r")),
        KnowledgeAdded(entry=KnowledgeEntry(
            id="K1", character="Elena", proposition=At(actor="David", location="Study", interval=(74, 77)),
            source=InvestigationTold(by_detective_turn=1), acquired_at=100, reliability=0.5, is_true=True)),
    ]

    def fold(events):
        state = EpistemicState()
        for event in events:
            state = apply_epistemic(state, event)
        return state

    assert fold(log + log) == fold(log)


# ------------------------------------------------- IMPORTANT-3: sealed-case immutability
def test_the_sealed_cases_mappings_reject_every_mutating_operation():
    """I-4: "canonical case data is immutable after validation". `ConfigDict(frozen=True)`
    only blocks attribute REBINDING — a `dict`-typed field stayed a live container, so
    `case.actors["Ghost"] = ...` succeeded on a sealed case and changed its content hash."""
    case, _ = vance_v03()
    victim = next(iter(case.actors.values()))
    mutations = [
        lambda: case.actors.__setitem__("GHOST", victim),
        lambda: case.actors.__delitem__("Elena"),
        lambda: case.actors.update({"GHOST": victim}),
        lambda: case.actors.pop("Elena"),
        lambda: case.actors.popitem(),
        lambda: case.actors.setdefault("GHOST", victim),
        lambda: case.actors.clear(),
        lambda: case.locations.__setitem__("VOID", case.locations["Hall"]),
        lambda: case.objects.__setitem__("KNIFE", case.objects["Glass1"]),
        lambda: case.actors["Elena"].static_attrs.__setitem__("sex", "Z"),
        lambda: case.objects["Glass1"].static_attrs.__setitem__("k", "v"),
        lambda: case.locations["Hall"].attributes.__setitem__("k", "v"),
        lambda: case.alias.names.__setitem__("elena", "GHOST"),
    ]
    before = case.content_hash()
    for mutate in mutations:
        with pytest.raises(TypeError):
            mutate()
    assert case.content_hash() == before


def test_a_frozen_case_still_reads_serializes_and_round_trips_like_a_dict():
    """The seal must not change the read API — every subsystem indexes `case.actors[id]`."""
    case, _ = vance_v03()
    assert case.actors["Elena"].name == "Elena Ruiz"
    assert dict(case.actors) == {k: v for k, v in case.actors.items()}
    assert set(case.locations) == set(case.locations.keys())
    reloaded = Case.model_validate_json(case.model_dump_json())
    assert reloaded == case and reloaded.content_hash() == case.content_hash()
    with pytest.raises(TypeError):
        reloaded.actors.__setitem__("GHOST", next(iter(case.actors.values())))


def test_a_default_constructed_case_is_frozen_too():
    """Pydantic does not validate DEFAULTS, so an empty `= {}` default stayed mutable even
    after the field type was frozen — the seal has to hold on a case that omits the field."""
    empty = Case(id="empty", t_investigation=1)
    for mapping in (empty.actors, empty.locations, empty.objects, empty.alias.names):
        with pytest.raises(TypeError):
            mapping.__setitem__("x", "y")


# --------------------------------------------- IMPORTANT-4: content_hash canonicalization
def _rebuild(case: Case, **overrides) -> Case:
    fields = {name: getattr(case, name) for name in Case.model_fields}
    return Case(**(fields | overrides))


def test_content_hash_is_invariant_under_caselog_order():
    """§4.1: "the CaseLog is a *set* of events". I-4 verifies the hash on load, so two cases
    with equal content must hash equal — otherwise the check reports tampering whenever the
    events were serialized in a different order. Oracle: an invariance property."""
    case, _ = vance_v03()
    baseline = case.content_hash()
    for seed in range(8):
        shuffled = list(case.events)
        random.Random(seed).shuffle(shuffled)
        assert _rebuild(case, events=tuple(shuffled)).content_hash() == baseline, seed
    assert _rebuild(case, events=tuple(reversed(case.events))).content_hash() == baseline


def test_content_hash_is_invariant_under_mapping_and_graph_order():
    """Dict insertion order and the order of the unordered graph/attitude tuples are not
    case content either."""
    case, _ = vance_v03()
    baseline = case.content_hash()
    reordered = _rebuild(
        case,
        actors=dict(reversed(list(case.actors.items()))),
        locations=dict(reversed(list(case.locations.items()))),
        objects=dict(reversed(list(case.objects.items()))),
        travel_edges=tuple(reversed(case.travel_edges)),
        perception_edges=tuple(reversed(case.perception_edges)),
        rels=tuple(reversed(case.rels)),
    )
    assert reordered.content_hash() == baseline


@pytest.mark.parametrize("field,value", [
    ("id", "tampered"),
    ("t_investigation", 121),
])
def test_content_hash_still_detects_a_real_change(field, value):
    """Canonicalisation must not blunt the tamper detection it exists to serve (I-4)."""
    case, _ = vance_v03()
    assert _rebuild(case, **{field: value}).content_hash() != case.content_hash()


def test_content_hash_detects_a_changed_event_and_a_dropped_one():
    case, _ = vance_v03()
    baseline = case.content_hash()
    assert _rebuild(case, events=case.events[:-1]).content_hash() != baseline
    attack = next(e for e in case.events if e.kind == "Attack")
    moved = tuple(e.model_copy(update={"location": "Gazebo"}) if e is attack else e for e in case.events)
    assert _rebuild(case, events=moved).content_hash() != baseline


# ------------------------------------------- IMPORTANT-5: dead-character perception (P-4)
def _kill(actor: str, t: int) -> Event:
    """The CaseLog's own death marker (§4.9 P-4): `ActorState(actor, "alive", "false")`."""
    return Event(id=f"die:{actor}", kind="Die", interval=(t, t + 1), location="Kitchen", actor=actor,
                 effects=(EffActorState(actor=actor, attr="alive", value="false"),))


def _witness_dies_case() -> Case:
    """Elena watches the Kitchen all evening and is killed at t=30. Margaret walks in at
    t=60 — thirty minutes after Elena is dead."""
    events = (_stays("Elena", [("Kitchen", 0, 120)])
              + _stays("Margaret", [("Hall", 0, 60), ("Kitchen", 60, 120)])
              + [_kill("Elena", 30)])
    return Case(id="witness_dies", t_investigation=120, actors=ACTORS, locations=LOCATIONS,
                objects=OBJECTS, travel_edges=TRAVEL, perception_edges=_PERCEPTION_V03,
                events=tuple(events), rels=())


def test_a_dead_witness_perceives_nothing_after_the_tick_they_die():
    """§4.9 P-4 makes death a CaseLog fact. Before the repair, eligibility was read off
    `Actor.role`, so an actor whose role was "witness" or "suspect" kept perceiving after
    being killed. Oracle: the fixture's own death tick."""
    case = _witness_dies_case()
    assert death_ticks(case.events)["Elena"] == 30
    for fact in derive_perception(case):
        if fact.observer != "Elena":
            continue
        interval = getattr(fact.proposition, "interval", None)
        assert fact.obs_interval[1] <= 30, f"{fact.id}: observed over {fact.obs_interval}, dead from t=30"
        if interval is not None:
            assert interval[1] <= 30, f"{fact.id}: {fact.proposition} claimed past death"


def test_a_corpse_does_not_witness_the_arrival_it_could_not_have_seen():
    """The concrete consequence: Margaret enters the Kitchen at t=60, thirty minutes after
    Elena dies. A dead Elena must hold no co-presence fact about her."""
    case = _witness_dies_case()
    saw_margaret = [f for f in derive_perception(case)
                    if f.observer == "Elena" and getattr(f.proposition, "actor", None) == "Margaret"
                    and f.proposition.kind == "At"]
    assert saw_margaret == []


def test_a_corpse_supplies_no_absence_alibi():
    """The sharpest form: `Absence` provenance is the fairness spine (I-34) — it is what
    makes "X was never in this room" testimony. A dead observer must not keep certifying
    an empty room for the rest of the evening."""
    case = _witness_dies_case()
    for fact in derive_perception(case):
        if fact.observer == "Elena" and fact.source == "Absence":
            assert fact.proposition.interval[1] <= 30, \
                f"{fact.id}: corpse vouches for {fact.proposition.interval}"


def test_the_victim_knows_their_own_evening_up_to_the_moment_they_die():
    """The other half of the same defect: `living_actors()` excluded the victim for the
    WHOLE case, so Harold — alive for 76 of 120 ticks, and the only other person in the room
    when he was killed — contributed no knowledge at all."""
    case, _ = vance_v03()
    death = death_ticks(case.events)["Harold"]
    entries = propagate_knowledge(case).for_character("Harold")
    assert entries, "the victim was alive for most of the evening and perceived nothing"
    assert all(e.acquired_at < death for e in entries)
    assert any(e.proposition.kind == "At" and e.proposition.actor == "Harold"
               and e.proposition.location == "Study" for e in entries)
    # ...but nothing about his own death, and nothing at all past it.
    assert not [e for e in entries
                if e.proposition.kind == "Did" and e.proposition.action in ("Die", "Attack")]


def test_living_actors_is_decided_by_the_caselog_not_by_the_authored_role():
    """`Actor.role` is narrative metadata; §4.1 makes the CaseLog authoritative. A suspect
    killed mid-evening cannot be interrogated at `t_investigation` whatever their role says."""
    case = _witness_dies_case()
    assert "Elena" not in case.living_actors(), "a dead witness is still in the interrogation pool"
    assert "Margaret" in case.living_actors()
    # The role filter is retained as well: a victim with no Die event stays excluded.
    unkilled, _ = vance_v03()
    no_death = _rebuild(unkilled, events=tuple(e for e in unkilled.events if e.id != "die"))
    assert "Harold" not in no_death.living_actors()


def test_a_dead_listener_is_not_told_anything():
    """The other half of IMPORTANT-5: perception is not the only way information reaches a
    character. `Told` is gated on the listener being present at the `Speak` event — it also
    has to be gated on their being alive to hear it (§4.9 P-4). Oracle: the fixture's own
    death tick against an `InformationTransferred` effect aimed at the corpse."""
    case = _witness_dies_case()
    proposition = At(actor="Margaret", location="Hall", interval=(0, 60))
    posthumous = Event(id="tell_corpse", kind="Speak", interval=(70, 71), location="Kitchen",
                       actor="Margaret", participants=("Elena",),
                       effects=(EffInformationTransferred(from_actor="Margaret", to_actor="Elena",
                                                          propositions=(proposition,)),))
    before_death = Event(id="tell_living", kind="Speak", interval=(10, 11), location="Kitchen",
                         actor="Margaret", participants=("Elena",),
                         effects=(EffInformationTransferred(from_actor="Margaret", to_actor="Elena",
                                                            propositions=(proposition,)),))
    # `Margaret` has to be in the Kitchen to speak there; give her a matching timeline.
    events = (tuple(_stays("Elena", [("Kitchen", 0, 120)]))
              + tuple(_stays("Margaret", [("Kitchen", 0, 120)]))
              + (_kill("Elena", 30), posthumous, before_death))
    case = _rebuild(case, events=events)
    assert death_ticks(case.events)["Elena"] == 30

    told = [e for e in propagate_knowledge(case).for_character("Elena")
            if e.source.kind == "Told"]
    assert told, "the living listener must still be told what she heard at t=10"
    assert all(e.source.speak_event_id == "tell_living" for e in told), \
        "a corpse was told something at t=70"


def test_perception_derivation_is_independent_of_actor_dict_order():
    """`content_hash` is now order-invariant, so two cases that hash equal must derive equal
    perception — including the synthetic fact ids, which are assigned in iteration order."""
    case, _ = vance_v03()
    reordered = _rebuild(case, actors=dict(reversed(list(case.actors.items()))))
    assert reordered.content_hash() == case.content_hash()
    assert derive_perception(reordered) == derive_perception(case)


# ---------------------------------------------- IMPORTANT-6: section 4.10 timeline API
def test_section_4_10_names_seven_entry_points_and_all_seven_exist():
    """§4.10 "Timeline query API (used by every other subsystem)" lists seven functions.
    Only `presence` was implemented. `information_reach` returns a `minds/` model, so it
    lives on `KnowledgeStore` — §23.1 forbids `world/` naming a `KnowledgeEntry`."""
    import eidolon.world as world
    from eidolon.minds.knowledge import KnowledgeStore

    for name in ("presence", "who_was_at", "could_reach", "could_observe",
                 "possible_window", "events_at"):
        assert callable(getattr(world, name, None)), f"section 4.10 {name} missing from eidolon.world"
    assert callable(getattr(KnowledgeStore, "information_reach", None))


def test_who_was_at_matches_the_fixtures_own_timeline():
    """Oracle: `_TIMELINE_V03` as declared in the fixture — David is in the Study 74-77 and
    Harold from t=5; nobody else is there during the murder window."""
    case, _ = vance_v03()
    assert who_was_at(case, "Study", (74, 78)) == {"David": (74, 77), "Harold": (74, 78)}
    assert who_was_at(case, "Gazebo", (76, 80)) == {}
    for actor, window in who_was_at(case, "Kitchen", (70, 75)).items():
        assert 70 <= window[0] < window[1] <= 75, actor


def test_who_was_at_agrees_with_presence_for_every_room_and_actor():
    """An invariance property against the derivation §4.10 projects, not against itself."""
    case, _ = vance_v03()
    window = (40, 90)
    for location in case.locations:
        found = who_was_at(case, location, window)
        for actor in case.actors:
            visits = [intersect(seg, window) for seg, loc in presence(case.events, actor)
                      if loc == location and intersect(seg, window)]
            assert found.get(actor) == (visits[0] if visits else None), (location, actor)


def test_events_at_returns_exactly_the_overlapping_events_in_canonical_order():
    case, _ = vance_v03()
    found = events_at(case, "Study", (74, 78))
    assert {e.id for e in found} == {e.id for e in case.events
                                     if e.location == "Study" and overlaps(e.interval, (74, 78))}
    assert [e.id for e in found] == [e.id for e in ordered_events(tuple(found))]
    assert events_at(case, "Study", (0, 1)) == []


def test_could_reach_agrees_with_the_travel_graph_the_physics_checker_uses():
    """§4.10 "travel + presence" — §4.9 P-2's rule asked as a query. Oracle: the fixture's
    declared timeline plus the declared travel graph, computed by hand here.

    `_TIMELINE_V03`: David is in the Hall 73-74 and the Study 74-77; Robert is in the Gazebo
    50-65 and on the 3-minute Gazebo->BackSteps edge until 67."""
    case, _ = vance_v03()
    assert could_reach(case, "David", "Study", 74)       # he is there at 74
    assert not could_reach(case, "David", "Hall", 74)    # in the Study; Study->Hall costs 1
    assert not could_reach(case, "Robert", "BackSteps", 66)  # left the Gazebo at 64; edge is 3
    assert could_reach(case, "Robert", "BackSteps", 67)      # arrives at 67
    assert could_reach(case, "Robert", "Gazebo", 66)         # still on the edge out of it
    assert not could_reach(case, "David", "Study", -1)   # no placement at or before the deadline


def test_could_reach_honours_an_explicit_from_state():
    case, _ = vance_v03()
    state = world_at(case.events, 50)
    assert could_reach(case, "Robert", "Study", 60, from_state=state)
    assert not could_reach(case, "Robert", "Study", 50, from_state=state)


def test_could_observe_agrees_with_the_perception_facts_actually_derived():
    """The strongest available oracle: §4.8's own output. If `could_observe` says an actor
    could perceive an event, `derive_perception` must have emitted a fact for that pairing,
    and vice versa — the two must not be able to disagree."""
    case, _ = vance_v03()
    facts = derive_perception(case)
    for event in case.events:
        if event.actor is None:
            continue
        witnessed = {f.observer for f in facts
                     if f.source == "Witnessed" and f.provenance == (f"{event.id}@{f.observer}",)}
        for actor in case.actors:
            if actor == event.actor or actor in event.participants:
                continue
            reachable, quality, modality = could_observe(case, actor, event)
            assert reachable == (actor in witnessed), (event.id, actor, quality, modality)
            assert (modality is not None) == reachable


def test_could_observe_reports_participation_for_the_people_in_the_event():
    case, _ = vance_v03()
    attack = next(e for e in case.events if e.kind == "Attack")
    assert could_observe(case, "David", attack) == (True, 1.0, "participation")
    assert could_observe(case, "Harold", attack) == (True, 1.0, "participation")


def test_could_observe_gives_a_dead_actor_no_access():
    """Consistent with IMPORTANT-5: the §4.10 query and §4.8's derivation share one rule."""
    case = _witness_dies_case()
    late = Event(id="late", kind="Speak", interval=(60, 62), location="Kitchen", actor="Margaret",
                 perceptibility=Perceptibility(sight=1.0, sound=1.0))
    case = _rebuild(case, events=case.events + (late,))
    assert could_observe(case, "Elena", late) == (False, 0.0, None)


def test_possible_window_excludes_every_tick_another_witness_refutes():
    """§4.10: "gaps where presence is unconstrained... where a lie is *not* refuted". Oracle:
    the perception facts themselves — no returned tick may be covered by another actor's
    fact placing this actor elsewhere or certifying their absence from the room."""
    case, _ = vance_v03()
    facts = derive_perception(case)
    for actor in case.actors:
        for location in ("Study", "Gazebo", "Kitchen"):
            free = {t for window in possible_window(case, actor, location) for t in ticks(window)}
            for fact in facts:
                if fact.observer == actor:
                    continue
                prop = fact.proposition
                elsewhere = (prop.kind == "At" and prop.actor == actor and prop.location != location)
                denied = (prop.kind == "NotAt" and prop.actor == actor and prop.location == location)
                if elsewhere or denied:
                    assert not (free & set(ticks(prop.interval))), (actor, location, prop)


def test_possible_window_is_a_disjoint_ordered_cover_inside_the_case_clock():
    case, _ = vance_v03()
    for actor in case.actors:
        windows = possible_window(case, actor, "Study")
        for window in windows:
            assert 0 <= window[0] < window[1] <= case.t_investigation
        for earlier, later in zip(windows, windows[1:]):
            assert earlier[1] < later[0], "windows must be disjoint and ordered"


def test_possible_window_keeps_a_window_where_the_actor_really_was_unseen():
    """David is genuinely in the Gazebo 37-59 and nobody is positioned to see it, so that
    stretch must survive as a usable cover window."""
    case, _ = vance_v03()
    windows = possible_window(case, "David", "Gazebo")
    assert any(w[0] <= 37 and 59 <= w[1] for w in windows), windows


def test_information_reach_answers_who_could_know_a_proposition_by_t():
    """§4.10 `information_reach(proposition, t) -> {actor: KnowledgeEntry}`. Oracle: the
    store's own entries filtered by the architecture's stated rule ("who could know p by t"),
    i.e. `acquired_at <= t` — never a value read back out of the method."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    proposition = At(actor="David", location="Study", interval=(74, 77))
    everyone = store.knowers(proposition)
    assert everyone, "fixture precondition: someone knows David was in the Study"
    earliest = min(e.acquired_at for e in everyone.values())

    assert store.information_reach(proposition, earliest - 1) == {}
    assert store.information_reach(proposition, case.t_investigation) == everyone
    for t in (earliest, earliest + 1, 100):
        assert store.information_reach(proposition, t) == {
            a: e for a, e in everyone.items() if e.acquired_at <= t}


# --------------------------------- IMPORTANT-7: Did.action outside the closed EventKind
def test_an_action_the_schema_cannot_express_is_unknown_not_refuted():
    """`FactIndex` settles `Did` by matching against event kinds. An action it has no
    entailment rule for is something the world cannot EXPRESS, not something it refutes —
    §4.7 reserves Unknown for exactly that ("attributes never defined"). Before the repair
    it came back False, and `DidNot` compounded it (`not None` is `True`).

    ADR-22 closed `Did.action` to the `ActionKind` vocabulary, so such an action can no
    longer be constructed normally (see `tests/world/test_actions.py`). The property still
    has to hold on the paths that bypass validation — `model_construct` here, and a future
    ADR adding a vocabulary member without its entailment row."""
    case, _ = vance_v03()
    index = FactIndex(case)
    unexpressible = Did.model_construct(kind="Did", actor="David", action="frobnicate",
                                        object="Glass1", location="Study", interval=(12, 120))
    assert index.truth_value(unexpressible) is None
    assert index.truth_value(DidNot.model_construct(
        kind="DidNot", actor="David", action="frobnicate", object=None, target_actor=None,
        location=None, interval=(12, 120))) is None


def test_an_unexpressible_action_is_not_reported_as_contradicted_by_the_world():
    """The consequence that matters: P-0 flags an implication the world REFUTES, which is
    how "authored wrong" stays distinguishable from "deliberately planted" in Phase 3. An
    action the schema cannot settle must not be filed as a contradiction."""
    case, _ = vance_v03()
    unexpressible = Implication(
        Did.model_construct(kind="Did", actor="David", action="frobnicate", object="Glass1",
                            target_actor=None, location="Study", interval=(12, 120)),
        requires=("clean@Elena",))
    assert [v for v in check_physics(case, [("E_x", unexpressible)]) if v.rule == "P-0"] == []
    # ...while an action the schema CAN name and the world does refute is still reported.
    refuted = Implication(Did(actor="Elena", action="Attack", location="Study", interval=(76, 77)),
                          created_at=(76, 77))
    assert [v for v in check_physics(case, [("E_false", refuted)]) if v.rule == "P-0"]


@pytest.mark.parametrize("action", ["Attack", "Clean", "Speak", "Die", "Move", "touch"])
def test_every_expressible_action_still_gets_a_definite_verdict(action):
    """The repair must not turn the whole predicate Unknown: an action in the `ActionKind`
    vocabulary is still settled True or False by the complete CaseLog (§4.1)."""
    case, _ = vance_v03()
    index = FactIndex(case)
    for actor in case.actors:
        verdict = index.truth_value(Did(actor=actor, action=action, interval=(0, 120)))
        assert verdict in (True, False), (actor, action, verdict)
        assert index.truth_value(DidNot(actor=actor, action=action, interval=(0, 120))) is (not verdict)


def test_the_golden_cases_own_did_facts_are_all_still_true():
    """Regression floor: every `Did` the perception model derives from the CaseLog must stay
    definitely True — the repair only touches actions the schema cannot name."""
    case, _ = vance_v03()
    index = FactIndex(case)
    derived = [f.proposition for f in derive_perception(case) if f.proposition.kind == "Did"]
    assert derived, "fixture precondition: the case derives some Did facts"
    for proposition in derived:
        assert index.truth_value(proposition) is True, proposition
