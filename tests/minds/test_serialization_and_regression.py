"""Serialization round-trip, deterministic replay, and the Phase 2 exit criteria that name
`vance_v03` directly: V-2 passes, every §7.1 query answers from indexes, the sealed case is
byte-identical after a long run of epistemic churn."""
from __future__ import annotations

import hashlib

from eidolon.minds.belief import BeliefStore, form_beliefs
from eidolon.minds.character import CharacterState, Personality, initial_character_state
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.events import (
    ComposureChange, EmotionalDelta, MindsEvent, SuspicionShift, TrustChange,
)
from eidolon.minds.fold import apply_character, apply_epistemic, build_memory_recall_event
from eidolon.minds.knowledge import KnowledgeEntry, propagate_knowledge
from eidolon.minds.memory import Memory, encode_memories
from eidolon.minds.soundness import check_knowledge_soundness
from eidolon.world.facts import FactIndex
from eidolon.world.propositions import At
from eidolon.world.state import death_ticks, loc_at
from pydantic import TypeAdapter
from tests.world.fixtures.vance import vance_v03

PERSONALITY = Personality(composure_base=0.6, volatility=0.2, deference=0.5, guile=0.3,
                           talkativeness=0.5, self_preservation=0.4)


def test_v2_passes_on_vance_v03_full_pipeline():
    """§30 Phase 2 exit: "V-2 passes on vance_v03" — run the whole pipeline, not just
    propagation, since belief/memory formation must not introduce unsound entries."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    fi = FactIndex(case)
    beliefs = BeliefStore()
    for actor in case.living_actors():
        for b in form_beliefs(actor, store, case, fi).beliefs:
            beliefs.add(b)
    assert check_knowledge_soundness(store, case, beliefs) == []


def test_section_7_1_queries_all_answered_from_indexes():
    """§30 Phase 2 exit: "all §7.1 queries answered from indexes"."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    fi = FactIndex(case)
    beliefs = BeliefStore()
    memories_by_actor: dict[str, list[Memory]] = {}
    for actor in case.living_actors():
        result = form_beliefs(actor, store, case, fi)
        for b in result.beliefs:
            beliefs.add(b)
        memories_by_actor[actor] = encode_memories(actor, list(result.beliefs), store, case)

    # Each query is checked against a value derived from the case, not against a type.
    # (`isinstance(x, object)` — as an earlier version of this test used — is true of every
    # value in Python and asserted nothing.)

    # "who knows it?" — Harold is in the Study from t=5, so everyone co-present there knows
    # it; nobody who was elsewhere does. Oracle: the fixture's own timeline.
    prop = At(actor="Harold", location="Study", interval=(70, 71))
    knowers = store.knowers(prop)
    for character, entry in knowers.items():
        assert entry.character == character and entry.proposition == prop
        assert loc_at(case.events, character, 70) == "Study"

    # "why/how?", "when?", "reliable?", "told vs witnessed vs inferred?" — take Elena's own
    # presence entry, whose values the architecture fixes exactly (§4.8 rule 1).
    own = next(e for e in store.for_character("Elena")
               if e.proposition.kind == "At" and e.proposition.actor == "Elena")
    assert own.source.kind == "Participated"
    assert own.reliability == 1.0
    assert own.acquired_at == own.proposition.interval[0]
    assert loc_at(case.events, "Elena", own.acquired_at) == own.proposition.location

    # "do they believe it?" — reliability 1.0 clears §6.4 rule 1's 0.6 threshold, so a belief
    # must exist and must carry that entry as its grounds.
    belief = beliefs.belief_for("Elena", own.proposition)
    assert belief is not None
    assert own.id in belief.grounds
    assert beliefs.belief_for("Elena", At(actor="Elena", location="Gazebo", interval=(0, 5))) is None

    # "do they remember it?" — every belief lands in exactly one memory (§8.2).
    in_memory = {bid for m in memories_by_actor["Elena"] for bid in m.content}
    assert belief.id in in_memory


def test_case_byte_identical_after_a_long_run_of_epistemic_churn():
    """§30 Phase 2 exit: "the sealed case is byte-identical after a 200-turn session
    (nothing mutates it)". Simulated with 200 rounds of fold/retrieval activity."""
    case, _ = vance_v03()
    before = case.content_hash()
    store = propagate_knowledge(case)
    fi = FactIndex(case)
    beliefs = list(form_beliefs("Elena", store, case, fi).beliefs)
    memories = encode_memories("Elena", beliefs, store, case)
    estate = EpistemicState()
    cstate = initial_character_state("Elena", PERSONALITY)
    for turn in range(200):
        if memories:
            m = memories[turn % len(memories)]
            estate = apply_epistemic(estate, build_memory_recall_event(
                m.id, turn_id=turn, current_strength_bp=m.strength_0, cue_match=0.5, outcome="weak"))
        cstate = apply_character(cstate, ComposureChange(new_composure_bp=(turn * 37) % 10000))
        cstate = apply_character(cstate, EmotionalDelta(new_emotion=cstate.emotion))
    assert case.content_hash() == before


def test_replay_from_a_serialized_log_reproduces_identical_state():
    """I-5: `state = fold(case, session_events)`, and replaying the SessionLog reproduces
    identical state hashes.

    An earlier version of this test folded one in-memory list twice in the same process and
    compared the results — which cannot fail unless `apply_character` is nondeterministic
    within a process, and so tested nothing about replay. This crosses the boundary replay
    actually crosses: the log is serialized, reloaded through the discriminated union, and
    re-folded from a freshly built initial state; the resulting state is compared by content
    hash, not by object identity.
    """
    adapter = TypeAdapter(list[MindsEvent])
    events: list[MindsEvent] = [ComposureChange(new_composure_bp=v) for v in (1000, 5000, 2500, 9999, 100)]
    events += [TrustChange(new_trust_detective=v) for v in (7000, 3000)]
    events += [SuspicionShift(target="David", new_value_bp=6100)]

    live = initial_character_state("A", PERSONALITY)
    for ev in events:
        live = apply_character(live, ev)

    reloaded_log = adapter.validate_json(adapter.dump_json(events))
    replayed = initial_character_state("A", PERSONALITY)  # fresh state, not the same object
    for ev in reloaded_log:
        replayed = apply_character(replayed, ev)

    def state_hash(s: CharacterState) -> str:
        return hashlib.sha256(s.model_dump_json().encode()).hexdigest()

    assert state_hash(replayed) == state_hash(live)
    assert replayed.composure == 100 and replayed.trust_detective == 3000
    assert replayed.suspicion["David"] == 6100


def test_knowledge_entry_serialization_round_trips():
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    entry = store.all()[0]
    dumped = entry.model_dump_json()
    restored = KnowledgeEntry.model_validate_json(dumped)
    assert restored == entry


def test_character_state_serialization_round_trips():
    state = initial_character_state("Elena", PERSONALITY)
    state = apply_character(state, ComposureChange(new_composure_bp=4242))
    restored = CharacterState.model_validate_json(state.model_dump_json())
    assert restored == state


def test_epistemic_state_serialization_round_trips():
    state = EpistemicState()
    state = apply_epistemic(state, build_memory_recall_event("M1", turn_id=1, current_strength_bp=6000,
                                                                cue_match=0.7, outcome="strong"))
    restored = EpistemicState.model_validate_json(state.model_dump_json())
    assert restored == state


def test_minds_event_union_round_trips_through_the_discriminated_type():
    """Every `SessionEventKind` payload survives a dump/load cycle through the shared
    `MindsEvent` discriminated union (needed for real persistence in Phase 7)."""
    adapter = TypeAdapter(MindsEvent)
    ev = ComposureChange(new_composure_bp=3333)
    restored = adapter.validate_json(adapter.dump_json(ev))
    assert restored == ev


def test_knowledge_store_round_trips_the_full_vance_v03_cast():
    """A coarser round-trip: every entry produced for the whole cast survives dump/load,
    proposition discriminated union included (§4.7's closed schema, exercised broadly)."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    adapter = TypeAdapter(list[KnowledgeEntry])
    restored = adapter.validate_json(adapter.dump_json(store.all()))
    assert restored == store.all()


def test_vance_v03_knowledge_table_matches_hand_expectations():
    """§28.7's "`vance_v03` knowledge tables match hand expectations", pinned against the
    case's own known facts (§29.1/the golden-case fixture docstring): David is alone with
    Harold in the Study for the murder interval (76-77), so his own presence there is
    certain first-hand knowledge; the victim knows his own evening up to the tick he dies
    (t=76) and nothing after it.

    This test previously asserted `store.for_character("Harold") == []` — that the victim
    observes nothing at all — because observer eligibility was read off `Actor.role`
    instead of off the CaseLog's own death marker. Harold was alive from t=0 to t=76; his
    knowledge of that stretch is real and the murderer's cover story has to survive it."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)

    from eidolon.world.interval import contains
    david_at_study = next((e for e in store.for_character("David") if e.proposition.kind == "At"
                            and e.proposition.actor == "David" and e.proposition.location == "Study"
                            and contains(e.proposition.interval, (76, 77))), None)
    assert david_at_study is not None
    assert david_at_study.source.kind == "Participated" and david_at_study.reliability == 1.0
    assert david_at_study.is_true is True

    # The victim perceives while alive and stops at the tick he dies (§4.9 P-4's own
    # `alive=false` marker; `cases/vance_v03.json` puts the attack at 22:16-22:17 = t 76-77).
    harold = store.for_character("Harold")
    assert harold, "the victim was alive for 76 of 120 ticks and must know his own evening"
    death_tick = death_ticks(case.events)["Harold"]
    assert death_tick == 76
    for entry in harold:
        assert entry.acquired_at < death_tick, f"{entry.id}: acquired at/after death"
        interval = getattr(entry.proposition, "interval", None)
        if interval is not None:
            assert interval[1] <= death_tick, f"{entry.id}: {entry.proposition} extends past death"
    # ...and he holds his own presence in the Study, where he was killed.
    assert any(e.proposition.kind == "At" and e.proposition.actor == "Harold"
                and e.proposition.location == "Study" for e in harold)

    # Every living suspect knows their OWN whereabouts at the murder tick to some degree
    # (own presence is always Participated, reliability 1.0) — the epistemic floor no
    # character falls below for their own timeline.
    for actor in case.living_actors():
        own_entries = [e for e in store.for_character(actor)
                       if e.proposition.kind == "At" and e.proposition.actor == actor and e.source.kind == "Participated"]
        assert own_entries, f"{actor} has no first-hand knowledge of their own presence"
