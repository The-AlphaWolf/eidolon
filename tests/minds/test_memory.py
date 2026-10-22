"""§8: encoding/decay/distortion (generation, pure) and retrieval (runtime, pure)."""
from __future__ import annotations

from eidolon.minds.belief import form_beliefs
from eidolon.minds.epistemic import EpistemicState, RecallRecord
from eidolon.minds.knowledge import propagate_knowledge
from eidolon.minds.memory import (
    RETRIEVE_STRONG, RETRIEVE_WEAK, CueSet, Memory, cue_overlap, encode_memories,
    memory_granularity, repetition_factor, retrieve, score,
)
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, Event, Perceptibility
from eidolon.world.facts import FactIndex
from eidolon.world.space import Location
from tests.world.fixtures.vance import vance_v03


def test_memory_granularity_buckets_by_strength():
    assert memory_granularity(8000) == 5
    assert memory_granularity(5000) == 15
    assert memory_granularity(1000) == 30


def test_cue_overlap_jaccard_and_empty_cues_never_match():
    a = CueSet(entities=("X",), location="Hall", topic_tags=("at",))
    b = CueSet(entities=("X",), location="Hall", topic_tags=("saw",))
    assert 0.0 < cue_overlap(a, b) < 1.0
    assert cue_overlap(a, a) == 1.0
    assert cue_overlap(a, CueSet()) == 0.0


def test_repetition_factor_rises_and_caps():
    assert repetition_factor(()) == 1.0
    ten_records = tuple(RecallRecord(turn_id=i, cue_match_bp=10000, outcome="strong") for i in range(10))
    assert repetition_factor(ten_records) == 1.3  # 1.0 + 0.05*10 = 1.5, capped 1.3


def test_encode_memories_bundles_witnessed_event_into_one_episodic_memory():
    """A bystander witnessing a real event forms one episodic memory anchored to it,
    not one memory per belief (§8.2 "each KnowledgeEntry/Belief cluster anchored on an
    event")."""
    actors = {"Actor": Actor(id="Actor", name="Actor", role="suspect"),
              "Witness": Actor(id="Witness", name="Witness", role="suspect")}
    locations = {"Hall": Location(id="Hall", name="Hall")}
    events = (
        Event(id="w_stay", kind="Stay", interval=(0, 20), location="Hall", actor="Witness",
              effects=(EffActorAt(actor="Witness", location="Hall"),)),
        Event(id="a_stay", kind="Stay", interval=(0, 20), location="Hall", actor="Actor",
              effects=(EffActorAt(actor="Actor", location="Hall"),)),
        Event(id="argue", kind="Speak", interval=(5, 6), location="Hall", actor="Actor",
              perceptibility=Perceptibility(sight=1.0, sound=1.0, identifies_voice=True)),
    )
    case = Case(id="c", t_investigation=20, actors=actors, locations=locations, events=events)
    store = propagate_knowledge(case)
    result = form_beliefs("Witness", store, case, FactIndex(case))
    memories = encode_memories("Witness", list(result.beliefs), store, case)
    episodic = [m for m in memories if m.kind == "episodic" and m.episode == "argue"]
    assert len(episodic) == 1
    assert len(episodic[0].content) >= 1  # bundles every belief anchored on `argue`


def test_encode_memories_covers_every_belief_exactly_once():
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    fi = FactIndex(case)
    for actor in case.living_actors():
        beliefs = list(form_beliefs(actor, store, case, fi).beliefs)
        memories = encode_memories(actor, beliefs, store, case)
        covered = [bid for m in memories for bid in m.content]
        assert sorted(covered) == sorted(b.id for b in beliefs)
        assert len(covered) == len(set(covered))  # no belief bundled twice


def test_strength_never_exceeds_salience_and_both_are_bounded_bp():
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    fi = FactIndex(case)
    for actor in case.living_actors():
        beliefs = list(form_beliefs(actor, store, case, fi).beliefs)
        for m in encode_memories(actor, beliefs, store, case):
            assert 0 <= m.strength_0 <= m.salience <= 10000  # decay only weakens (§8.3)


def test_retrieve_strong_vs_weak_vs_none_thresholds():
    cues = CueSet(entities=("X",), location="Hall", time_bucket="b0", topic_tags=("at",))
    strong_mem = Memory(id="M1", character="A", kind="semantic", content=("B1",), encoded_at=0,
                         salience=9000, strength_0=9000, cues=cues)
    weak_mem = Memory(id="M2", character="A", kind="semantic", content=("B2",), encoded_at=0,
                       salience=3500, strength_0=3500, cues=cues)
    none_mem = Memory(id="M3", character="A", kind="semantic", content=("B3",), encoded_at=0,
                       salience=9000, strength_0=9000, cues=CueSet())  # no cue overlap at all
    epistemic = EpistemicState()
    result = retrieve([strong_mem, weak_mem, none_mem], epistemic, cues)
    assert result.strong == ("M1",)
    assert result.weak == ("M2",)
    assert "M3" not in result.strong and "M3" not in result.weak
    assert score(strong_mem, epistemic, cues) >= RETRIEVE_STRONG
    assert RETRIEVE_WEAK <= score(weak_mem, epistemic, cues) < RETRIEVE_STRONG


def test_retrieval_is_pure_and_deterministic():
    """Same `(memories, epistemic, cues)` in -> byte-identical result out, every time
    (§8.4: "retrieval at runtime is a pure function")."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    fi = FactIndex(case)
    beliefs = list(form_beliefs("Elena", store, case, fi).beliefs)
    memories = encode_memories("Elena", beliefs, store, case)
    cues = CueSet(entities=("David",), location="Study", topic_tags=("at",))
    epistemic = EpistemicState()
    r1 = retrieve(memories, epistemic, cues)
    r2 = retrieve(memories, epistemic, cues)
    assert r1 == r2


def test_retrieval_monotone_in_epistemic_strength():
    """Raising `memory_strength` in the overlay (post-decay) never lowers a score — the
    same monotonicity the corroboration/weight machinery relies on elsewhere."""
    cues = CueSet(entities=("X",), location="Hall", topic_tags=("at",))
    mem = Memory(id="M1", character="A", kind="semantic", content=("B1",), encoded_at=0,
                 salience=9000, strength_0=4000, cues=cues)
    low = EpistemicState(memory_strength={"M1": 2000})
    high = EpistemicState(memory_strength={"M1": 8000})
    assert score(mem, low, cues) <= score(mem, high, cues)


def test_time_compression_distortion_shifts_recalled_interval_within_bound():
    """§8.7: `time_compression` shift <= 20 minutes, only on memories with strength < 0.6."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    fi = FactIndex(case)
    distorted = 0
    for actor in case.living_actors():
        beliefs = list(form_beliefs(actor, store, case, fi).beliefs)
        for m in encode_memories(actor, beliefs, store, case):
            for d in m.distortions:
                distorted += 1
                assert d.cause == "time_compression" and d.field == "interval"
                true_iv, recalled_iv = d.true_value, d.recalled_value
                shift = abs(recalled_iv[0] - true_iv[0])
                assert 1 <= shift <= 20
                assert m.strength_0 < 6000
    assert distorted > 0  # the rule actually fires on vance_v03, not just typed and unused
