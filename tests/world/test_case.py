"""`Case` construction (§4.1/§23.1): referential integrity is checked immediately, and the
sealed case is immutable (I-4)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, Event
from eidolon.world.space import Location

ACTORS = {"David": Actor(id="David", name="David", role="suspect")}
LOCS = {"Hall": Location(id="Hall", name="Hall")}


def _valid_case() -> Case:
    events = (Event(id="e1", kind="Stay", interval=(0, 5), location="Hall", actor="David",
                     effects=(EffActorAt(actor="David", location="Hall"),)),)
    return Case(id="c", t_investigation=5, actors=ACTORS, locations=LOCS, events=events)


def test_valid_case_constructs():
    case = _valid_case()
    assert case.travel_graph is not None


@pytest.mark.parametrize("bad_event", [
    Event(id="bad1", kind="Stay", interval=(0, 1), location="Nowhere", actor="David"),
    Event(id="bad2", kind="Stay", interval=(0, 1), location="Hall", actor="Ghost"),
    Event(id="bad3", kind="Stay", interval=(0, 1), location="Hall", actor="David", participants=("Ghost",)),
    Event(id="bad4", kind="Stay", interval=(0, 1), location="Hall", actor="David", objects=("Ghost",)),
])
def test_dangling_references_are_rejected_at_construction(bad_event):
    with pytest.raises(ValidationError):
        Case(id="c", t_investigation=5, actors=ACTORS, locations=LOCS, events=(bad_event,))


def test_effect_referencing_unknown_actor_is_rejected():
    event = Event(id="e", kind="Stay", interval=(0, 1), location="Hall", actor="David",
                   effects=(EffActorAt(actor="Ghost", location="Hall"),))
    with pytest.raises(ValidationError):
        Case(id="c", t_investigation=5, actors=ACTORS, locations=LOCS, events=(event,))


def test_case_is_frozen():
    case = _valid_case()
    with pytest.raises(ValidationError):
        case.id = "other"


def test_content_hash_is_stable_and_sensitive_to_content():
    a = _valid_case()
    b = _valid_case()
    assert a.content_hash() == b.content_hash()
    events2 = (Event(id="e1", kind="Stay", interval=(0, 6), location="Hall", actor="David",
                      effects=(EffActorAt(actor="David", location="Hall"),)),)
    c = Case(id="c", t_investigation=6, actors=ACTORS, locations=LOCS, events=events2)
    assert c.content_hash() != a.content_hash()


def test_duplicate_event_ids_do_not_silently_merge():
    """Two distinct events sharing an id would corrupt provenance lookups by id; the model
    doesn't currently enforce uniqueness structurally, so this pins the current (permissive)
    behaviour and flags it for a Phase-4/7 store-level uniqueness constraint instead."""
    events = (
        Event(id="dup", kind="Stay", interval=(0, 3), location="Hall", actor="David",
              effects=(EffActorAt(actor="David", location="Hall"),)),
        Event(id="dup", kind="Stay", interval=(3, 5), location="Hall", actor="David",
              effects=(EffActorAt(actor="David", location="Hall"),)),
    )
    case = Case(id="c", t_investigation=5, actors=ACTORS, locations=LOCS, events=events)
    assert len(case.events) == 2  # both retained; id uniqueness is not (yet) an invariant here
