"""V-2 knowledge-soundness checker (§30 Phase 2 deliverable; I-8)."""
from __future__ import annotations

from eidolon.minds.belief import BeliefStore
from eidolon.minds.knowledge import KnowledgeEntry, KnowledgeStore, propagate_knowledge
from eidolon.minds.provenance import Absence, Inferred, Participated, Told, Witnessed
from eidolon.minds.soundness import check_knowledge_soundness
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, Event
from eidolon.world.propositions import At, NotAt
from eidolon.world.space import Location
from tests.world.fixtures.vance import vance_v03

ACTORS = {"A": Actor(id="A", name="A", role="suspect"), "B": Actor(id="B", name="B", role="suspect")}
LOCS = {"Hall": Location(id="Hall", name="Hall"), "Study": Location(id="Study", name="Study")}


def _case():
    return Case(id="c", t_investigation=20, actors=ACTORS, locations=LOCS, events=(
        Event(id="a_stay", kind="Stay", interval=(0, 20), location="Hall", actor="A",
              effects=(EffActorAt(actor="A", location="Hall"),)),
    ))


def test_v2_passes_on_vance_v03():
    """Phase 2 exit criterion (§30): "V-2 passes on vance_v03"."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    violations = check_knowledge_soundness(store, case)
    assert violations == []


def test_v2_rejects_character_claimed_to_witness_from_the_wrong_location():
    """Adversarial: a hand-constructed entry claims A witnessed something in the Study
    while A's own CaseLog presence places them in the Hall the whole time, with no
    perception edge between the rooms."""
    case = _case()
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A",
                              proposition=At(actor="B", location="Study", interval=(5, 6)),
                              source=Witnessed(event_id="fake", modality="sight", quality=0.9),
                              acquired_at=5, reliability=0.9, is_true=True))
    violations = check_knowledge_soundness(store, case)
    assert len(violations) == 1 and violations[0].rule == "V-2"


def test_v2_rejects_absence_knowledge_claimed_from_the_wrong_location():
    case = _case()  # A is in the Hall the whole time (no Study presence, no perception edge)
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A",
                              proposition=NotAt(actor="B", location="Study", interval=(5, 6)),
                              source=Absence(basis="continuous", coverage=1.0, entrances_covered=True),
                              acquired_at=5, reliability=0.5, is_true=False))
    violations = check_knowledge_soundness(store, case)
    assert len(violations) == 1


def test_v2_rejects_absence_provenance_on_a_non_notat_proposition():
    """I-34: `Absence` grounds `NotAt` ONLY — never a positive claim."""
    case = _case()
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A",
                              proposition=At(actor="A", location="Hall", interval=(0, 5)),
                              source=Absence(basis="continuous", coverage=1.0, entrances_covered=True),
                              acquired_at=0, reliability=0.5, is_true=True))
    violations = check_knowledge_soundness(store, case)
    assert len(violations) == 1 and "grounds NotAt only" in violations[0].detail


def test_v2_rejects_told_where_listener_was_never_at_the_speak_event():
    case = _case()  # only event is "a_stay"; no Speak event exists at all
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A",
                              proposition=At(actor="B", location="Study", interval=(5, 6)),
                              source=Told(by="B", speak_event_id="never_happened", teller_sincere=True),
                              acquired_at=5, reliability=0.5, is_true=True))
    violations = check_knowledge_soundness(store, case)
    assert len(violations) == 1
    assert "unknown event" in violations[0].detail


def test_v2_rejects_told_where_speak_event_exists_but_listener_absent():
    prop = At(actor="X", location="Elsewhere", interval=(5, 6))
    case = Case(id="c", t_investigation=20, actors=ACTORS, locations=LOCS, events=(
        Event(id="talk", kind="Speak", interval=(5, 6), location="Hall", actor="A"),  # B not a participant
    ))
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="B", proposition=prop,
                              source=Told(by="A", speak_event_id="talk", teller_sincere=True),
                              acquired_at=5, reliability=0.5, is_true=False))
    violations = check_knowledge_soundness(store, case)
    assert len(violations) == 1 and "not present" in violations[0].detail


def test_v2_rejects_inferred_grounding_referencing_unknown_id():
    case = _case()
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A",
                              proposition=At(actor="A", location="Hall", interval=(0, 5)),
                              source=Inferred(from_ids=("K_ghost",), rule_id="opportunity"),
                              acquired_at=0, reliability=0.5, is_true=True))
    violations = check_knowledge_soundness(store, case, BeliefStore())
    assert len(violations) == 1 and "K_ghost" in violations[0].detail


def test_v2_accepts_own_presence_and_wellformed_perception_edge_sighting():
    case = Case(id="c", t_investigation=20, actors=ACTORS,
                locations={**LOCS, "Kitchen": Location(id="Kitchen", name="Kitchen")},
                events=(
                    Event(id="a_stay", kind="Stay", interval=(0, 20), location="Kitchen", actor="A",
                          effects=(EffActorAt(actor="A", location="Kitchen"),)),
                ))
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A",
                              proposition=At(actor="A", location="Kitchen", interval=(0, 20)),
                              source=Participated(event_id="seg:A:0"), acquired_at=0, reliability=1.0, is_true=True))
    assert check_knowledge_soundness(store, case) == []
