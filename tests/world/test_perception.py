"""Perception model (§4.8). T-2/T-3 (I-34 absence gating) and T-30 (I-46 sustained
identified observation)."""
from __future__ import annotations

from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, EffActorState, Event
from eidolon.world.perception import ATTENTION_AWAKE, derive_perception
from eidolon.world.space import Location
from tests.world.fixtures.vance import vance_v01_negative, vance_v03

ACTORS = {"A": Actor(id="A", name="A", role="suspect"), "B": Actor(id="B", name="B", role="suspect")}


def _case(entrances_visible: bool, attention: str | None) -> Case:
    locations = {"L": Location(id="L", name="L", entrances_visible=entrances_visible),
                 "M": Location(id="M", name="M")}
    a_effects = [EffActorAt(actor="A", location="L")]
    if attention is not None:
        a_effects.append(EffActorState(actor="A", attr="attention", value=attention))
    events = (
        Event(id="a", kind="Stay", interval=(0, 10), location="L", actor="A", effects=tuple(a_effects)),
        Event(id="b", kind="Stay", interval=(0, 5), location="M", actor="B",
              effects=(EffActorAt(actor="B", location="M"),)),
        Event(id="b2", kind="Stay", interval=(5, 10), location="L", actor="B",
              effects=(EffActorAt(actor="B", location="L"),)),
    )
    return Case(id="c", t_investigation=10, actors=ACTORS, locations=locations, events=events)


def _notat_facts_by(observer: str, facts):
    return [f for f in facts if f.observer == observer and f.proposition.kind == "NotAt"]


def test_T2_sleeping_actor_yields_no_notat():
    case = _case(entrances_visible=True, attention="0.3")  # below ATTENTION_AWAKE
    facts = derive_perception(case)
    assert _notat_facts_by("A", facts) == []


def test_T2_awake_actor_yields_notat():
    case = _case(entrances_visible=True, attention=None)  # default: awake (1.0)
    facts = derive_perception(case)
    assert _notat_facts_by("A", facts) != []


def test_T3_uncovered_entrance_yields_no_absence_entry():
    case = _case(entrances_visible=False, attention=None)
    facts = derive_perception(case)
    assert _notat_facts_by("A", facts) == []


def test_T3_covered_entrance_reliability_below_matching_at():
    case = _case(entrances_visible=True, attention=None)
    facts = derive_perception(case)
    notat = _notat_facts_by("A", facts)
    assert notat, "expected absence facts when entrances are covered and A is awake"
    own_at = next(f for f in facts if f.observer == "A" and f.proposition.kind == "At"
                  and f.proposition.actor == "A" and f.source == "Participated")
    assert all(f.reliability < own_at.reliability for f in notat)
    assert all(f.absence is not None and f.absence.entrances_covered for f in notat)


def test_attention_awake_threshold_constant_is_reasonable():
    assert 0.0 < ATTENTION_AWAKE <= 1.0


def test_T30_sustained_identified_observation_yields_universal_at():
    """I-46: Robert's ten-minute glow sighting of Elena on the Back Steps yields universal
    `At(Elena, BackSteps, [22:05,22:15))`, not an existential `Saw`."""
    case, _ = vance_v01_negative()
    facts = derive_perception(case)
    hits = [f for f in facts if f.observer == "Robert" and f.proposition.kind == "At"
            and f.proposition.actor == "Elena" and f.proposition.location == "BackSteps"]
    assert len(hits) == 1
    fact = hits[0]
    assert fact.proposition.interval == (65, 75)  # 22:05-22:15, t0 = 21:00
    assert fact.source == "Witnessed"
    # I-46 rule 9: the observation interval is Robert's whole presence segment (Gazebo,
    # 54-81), not just the perception run (65-75).
    assert fact.obs_interval == (54, 81)
    assert fact.obs_location == "Gazebo"


def test_every_perception_fact_is_auditable_to_the_caselog():
    """Every `PerceptionFact` must trace back to something in the CaseLog (§4.1's auditability
    argument): event-perception provenance ids are literally `<EventId>@<observer>`; presence
    (own/co-presence/absence) and sustained-observation provenance are synthetic per-segment
    ids, still resolvable to a real presence segment for that actor."""
    case, _ = vance_v03()
    facts = derive_perception(case)
    event_ids = {e.id for e in case.events}
    assert facts
    for f in facts:
        for pid in f.provenance:
            if pid.startswith("seg:") or pid.startswith("see:"):
                actor = pid.split(":")[1]
                assert actor in case.actors, pid
            else:
                event_id = pid.split("@", 1)[0]
                assert event_id in event_ids, pid


def test_no_perception_edge_means_no_sighting():
    """Without a sight edge, an out-of-line-of-sight actor is never universally placed."""
    case = _case(entrances_visible=True, attention=None)
    facts = derive_perception(case)
    assert not any(f.proposition.kind == "At" and f.proposition.actor == "B" and f.observer == "A"
                   and f.source == "Witnessed" for f in facts)
