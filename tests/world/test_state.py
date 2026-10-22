"""`world_at`/`presence` (§4.6) and replay determinism (I-5) at the world-model level:
folding the same CaseLog twice yields byte-identical state."""
from __future__ import annotations

from eidolon.world.events import EffActorAt, EffActorState, EffObjectState, Event
from eidolon.world.state import attention_at, loc_at, presence, world_at
from tests.world.fixtures.vance import vance_v03


def _events():
    return (
        Event(id="e1", kind="Stay", interval=(0, 5), location="Hall", actor="David",
              effects=(EffActorAt(actor="David", location="Hall"),)),
        Event(id="e2", kind="Stay", interval=(5, 10), location="Study", actor="David",
              effects=(EffActorAt(actor="David", location="Study"), EffActorState(actor="David", attr="attention", value="0.7"))),
        Event(id="e3", kind="Use", interval=(6, 7), location="Study", actor="David",
              effects=(EffObjectState(object="glass", attr="dirty", value="true"),)),
    )


def test_presence_merges_touching_segments_and_reports_gaps():
    evs = _events()
    assert presence(evs, "David") == [((0, 5), "Hall"), ((5, 10), "Study")]
    assert loc_at(evs, "David", 4) == "Hall"
    assert loc_at(evs, "David", 5) == "Study"
    assert loc_at(evs, "David", 20) is None


def test_world_at_actorat_is_inprogress_other_effects_wait_for_completion():
    evs = _events()
    mid = world_at(evs, 6)  # e2 (ends 10) is still in progress; e3 (ends 7) also in progress
    assert mid.actor_at == {"David": "Study"}
    assert mid.object_state == {}  # e3 hasn't completed yet
    done = world_at(evs, 7)  # e3 completed at t=7
    assert done.object_state == {"glass": {"dirty": "true"}}


def test_attention_defaults_to_awake_when_unstated():
    evs = _events()
    assert attention_at(evs, "David", 2) == 1.0   # e1 states no attention -> default
    assert attention_at(evs, "David", 6) == 0.7    # e2 states attention explicitly
    assert attention_at(evs, "David", 50) == 0.0   # not present anywhere


def test_replay_determinism_on_vance_v03():
    """I-5's world-model half: folding the same CaseLog twice reproduces identical state."""
    case, _ = vance_v03()
    for t in (0, 12, 76, 77, 119):
        a = world_at(case.events, t)
        b = world_at(case.events, t)
        assert a == b
        assert hash(a.model_dump_json()) == hash(b.model_dump_json())
    for actor in case.actors:
        assert presence(case.events, actor) == presence(case.events, actor)


def test_case_serialization_round_trip_preserves_semantics():
    """§23.5/I-4-adjacent: a sealed case must survive JSON round-tripping unchanged."""
    from eidolon.world.case import Case

    case, _ = vance_v03()
    dumped = case.model_dump_json()
    restored = Case.model_validate_json(dumped)
    assert restored.content_hash() == case.content_hash()
    assert presence(restored.events, "David") == presence(case.events, "David")
