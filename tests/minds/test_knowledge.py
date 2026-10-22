"""§6.2-6.3, §7.1: `propagate_knowledge` folds Phase 1 perception into `KnowledgeEntry`,
plus `Told` from `InformationTransferred` effects. `is_true` is the FactIndex annotation."""
from __future__ import annotations

from eidolon.minds.knowledge import KnowledgeStore, propagate_knowledge
from eidolon.minds.provenance import Absence, Participated, Told, Witnessed
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, EffInformationTransferred, Event
from eidolon.world.propositions import At
from eidolon.world.space import Location, TravelEdge
from tests.world.fixtures.vance import vance_v03

ACTORS = {"A": Actor(id="A", name="A", role="suspect"), "B": Actor(id="B", name="B", role="suspect")}
LOCS = {"L": Location(id="L", name="L"), "M": Location(id="M", name="M")}
# A one-minute link, so a case in which an actor actually moves L <-> M is
# physically valid (P-2/P-5) rather than merely unchecked.
TRAVEL = (TravelEdge(a="L", b="M", minutes=1),)


def test_propagate_knowledge_on_vance_v03_produces_own_presence_and_copresence_entries():
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    assert store.all()
    elena_entries = store.for_character("Elena")
    assert any(isinstance(e.source, Participated) for e in elena_entries)
    assert any(isinstance(e.source, Witnessed) and e.source.modality == "co-presence" for e in elena_entries)
    assert any(isinstance(e.source, Absence) for e in elena_entries)


def test_is_true_matches_fact_index():
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    for e in store.all():
        if e.source.kind in ("Witnessed", "Participated"):
            # every perception-derived entry reports a proposition that actually happened
            assert e.is_true is True


def test_knowers_returns_best_entry_per_character():
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    prop = At(actor="Harold", location="Study", interval=(70, 71))
    knowers = store.knowers(prop)
    for character, entry in knowers.items():
        assert entry.proposition == prop
        assert entry.character == character


def test_find_returns_highest_reliability_match():
    store = KnowledgeStore()
    from eidolon.minds.knowledge import KnowledgeEntry
    prop = At(actor="X", location="L", interval=(0, 5))
    store.add(KnowledgeEntry(id="K1", character="A", proposition=prop,
                              source=Participated(event_id="e1"), acquired_at=0, reliability=0.3, is_true=True))
    store.add(KnowledgeEntry(id="K2", character="A", proposition=prop,
                              source=Witnessed(event_id="e2", modality="sight", quality=0.9),
                              acquired_at=0, reliability=0.9, is_true=True))
    best = store.find("A", prop)
    assert best.id == "K2"


def test_told_knowledge_from_information_transferred_when_listener_present():
    told_prop = At(actor="X", location="Elsewhere", interval=(50, 60))
    case = Case(id="c", t_investigation=20, actors=ACTORS, locations=LOCS, events=(
        Event(id="a_stay", kind="Stay", interval=(0, 20), location="L", actor="A",
              effects=(EffActorAt(actor="A", location="L"),)),
        Event(id="b_stay", kind="Stay", interval=(0, 20), location="L", actor="B",
              effects=(EffActorAt(actor="B", location="L"),)),
        Event(id="talk", kind="Speak", interval=(5, 6), location="L", actor="A", participants=("B",),
              effects=(EffInformationTransferred(from_actor="A", to_actor="B", propositions=(told_prop,)),)),
    ))
    store = propagate_knowledge(case)
    told_entries = [e for e in store.for_character("B") if isinstance(e.source, Told)]
    assert len(told_entries) == 1
    assert told_entries[0].source.by == "A"
    assert told_entries[0].source.speak_event_id == "talk"
    # A has no grounded entry for `told_prop` (it never happened near A) -> fabricated,
    # insincere, zero reliability (documented §6.4-rule-3 policy).
    assert told_entries[0].source.teller_sincere is False
    assert told_entries[0].reliability == 0.0
    assert told_entries[0].is_true is False  # `told_prop` never happened in this case


def test_told_knowledge_propagates_tellers_reliability_when_grounded():
    """A tells B something A actually witnessed: B's entry inherits A's own reliability
    for that exact proposition (not a flat trust-only number), and is marked sincere."""
    seen_prop = At(actor="C", location="M", interval=(0, 3))
    actors = dict(ACTORS, C=Actor(id="C", name="C", role="witness"))
    # A is in M for [0,3) and only then in L — the earlier version of this fixture ALSO gave
    # A a Stay in L over [0,20), putting one actor in two rooms at once (P-1). It went
    # unnoticed because nothing enforced physics at the world -> minds boundary; it does now.
    case = Case(id="c", t_investigation=20, actors=actors, locations=LOCS,
                travel_edges=TRAVEL, events=(
        Event(id="b_stay", kind="Stay", interval=(0, 20), location="L", actor="B",
              effects=(EffActorAt(actor="B", location="L"),)),
        Event(id="c_stay", kind="Stay", interval=(0, 3), location="M", actor="C",
              effects=(EffActorAt(actor="C", location="M"),)),
        Event(id="a_at_m", kind="Stay", interval=(0, 3), location="M", actor="A",
              effects=(EffActorAt(actor="A", location="M"),)),
        Event(id="a_back", kind="Move", interval=(3, 20), location="L", actor="A",
              effects=(EffActorAt(actor="A", location="L"),)),
        Event(id="talk", kind="Speak", interval=(10, 11), location="L", actor="A", participants=("B",),
              effects=(EffInformationTransferred(from_actor="A", to_actor="B", propositions=(seen_prop,)),)),
    ))
    store = propagate_knowledge(case)
    a_entry = store.find("A", seen_prop)
    assert a_entry is not None and a_entry.source.kind == "Witnessed"
    b_told = next(e for e in store.for_character("B") if isinstance(e.source, Told))
    assert b_told.source.teller_sincere is True
    assert b_told.reliability == a_entry.reliability


def test_told_is_not_emitted_when_listener_was_not_present():
    """I-8: no entry is fabricated for a listener who was not at the speak event — a
    structural prevention of impossible provenance, not a post-hoc rejection."""
    told_prop = At(actor="X", location="Elsewhere", interval=(50, 60))
    actors = dict(ACTORS, C=Actor(id="C", name="C", role="witness"))
    case = Case(id="c", t_investigation=20, actors=actors, locations=LOCS, events=(
        Event(id="a_stay", kind="Stay", interval=(0, 20), location="L", actor="A",
              effects=(EffActorAt(actor="A", location="L"),)),
        Event(id="c_stay", kind="Stay", interval=(0, 20), location="M", actor="C",  # elsewhere, not present
              effects=(EffActorAt(actor="C", location="M"),)),
        Event(id="talk", kind="Speak", interval=(5, 6), location="L", actor="A",
              effects=(EffInformationTransferred(from_actor="A", to_actor="C", propositions=(told_prop,)),)),
    ))
    store = propagate_knowledge(case)
    assert [e for e in store.for_character("C") if isinstance(e.source, Told)] == []


def test_duplicate_entry_id_rejected():
    import pytest
    from eidolon.minds.knowledge import KnowledgeEntry
    store = KnowledgeStore()
    prop = At(actor="X", location="L", interval=(0, 5))
    e = KnowledgeEntry(id="K1", character="A", proposition=prop, source=Participated(event_id="e1"),
                        acquired_at=0, reliability=1.0, is_true=True)
    store.add(e)
    with pytest.raises(ValueError):
        store.add(e)
