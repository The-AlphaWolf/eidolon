"""Closed proposition schema (§4.7) + `FactIndex.truth_value` correctness.

Phase 1 exit criterion: "`truth_value` correct on a 100-proposition fixture." The oracle
below is computed directly from a hand-written tick->location table, independent of
`eidolon.world.state`/`facts` internals, so this is a real cross-check and not a tautology.
"""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, Event
from eidolon.world.facts import FactIndex
from eidolon.world.propositions import At, Fact, NotAt, Proposition
from eidolon.world.space import Location


def test_closed_schema_round_trips_through_type_adapter():
    ta = TypeAdapter(Proposition)
    p = ta.validate_python({"kind": "At", "actor": "David", "location": "Hall", "interval": (0, 5)})
    assert isinstance(p, At)
    assert ta.dump_python(p)["kind"] == "At"


def test_fact_is_frozen_and_hashable():
    p = At(actor="David", location="Hall", interval=(0, 5))
    f = Fact(id="F1", proposition=p, support=("e1",), load_bearing=True)
    assert hash(f) is not None
    with pytest.raises(Exception):
        f.load_bearing = False  # frozen: mutation must fail


def test_interval_validation_rejects_empty_and_negative():
    with pytest.raises(Exception):
        At(actor="D", location="Hall", interval=(5, 5))
    with pytest.raises(Exception):
        At(actor="D", location="Hall", interval=(5, 3))


# --- 100-proposition truth-value fixture -----------------------------------------------
# Two actors over 24 ticks across three locations; segments are hand-written and the
# expected truth values below are computed from this table directly, not from the engine.
_SEGMENTS = {
    "A": [(0, 6, "Hall"), (6, 12, "Kitchen"), (12, 18, "Study"), (18, 24, "Hall")],
    "B": [(0, 24, "Kitchen")],
}


def _loc_at(actor: str, t: int) -> str | None:
    for s, e, loc in _SEGMENTS[actor]:
        if s <= t < e:
            return loc
    return None


def _build_case() -> Case:
    actors = {"A": Actor(id="A", name="A", role="suspect"), "B": Actor(id="B", name="B", role="suspect")}
    locations = {loc: Location(id=loc, name=loc) for loc in ("Hall", "Kitchen", "Study")}
    events = []
    for actor, segs in _SEGMENTS.items():
        for i, (s, e, loc) in enumerate(segs):
            events.append(Event(id=f"stay:{actor}:{i}", kind="Stay", interval=(s, e), location=loc,
                                 actor=actor, effects=(EffActorAt(actor=actor, location=loc),)))
    return Case(id="fixture", t_investigation=24, actors=actors, locations=locations, events=tuple(events))


# Independent oracles: computed straight off `_SEGMENTS` (the fixture's own declared
# timeline), never off `FactIndex`. A tick with no covering segment means the actor is in NO
# room — §4.1 makes the CaseLog complete, so presence is total and these predicates are
# always determinate (§4.7: "Unknown arises only for `Incidental` and for attributes never
# defined"). An earlier version of these oracles reported Unknown for such ticks, which is
# what let a true `NotAt` be recorded as a refuted fact downstream.
def _oracle_at(actor: str, location: str, interval: tuple[int, int]) -> bool | None:
    return all(_loc_at(actor, t) == location for t in range(*interval))


def _oracle_not_at(actor: str, location: str, interval: tuple[int, int]) -> bool | None:
    return all(_loc_at(actor, t) != location for t in range(*interval))


def test_fact_index_100_propositions():
    case = _build_case()
    index = FactIndex(case)
    cases: list[tuple[Proposition, bool | None]] = []
    for actor in ("A", "B"):
        for location in ("Hall", "Kitchen", "Study"):
            for start in range(0, 24, 3):
                for length in (2, 5):
                    end = min(start + length, 30)
                    if end <= start:
                        continue
                    interval = (start, end)
                    cases.append((At(actor=actor, location=location, interval=interval),
                                  _oracle_at(actor, location, interval)))
                    cases.append((NotAt(actor=actor, location=location, interval=interval),
                                  _oracle_not_at(actor, location, interval)))
    assert len(cases) >= 100, f"fixture only has {len(cases)} propositions"
    mismatches = [(p, expected, got) for p, expected in cases if (got := index.truth_value(p)) != expected]
    assert not mismatches, mismatches[:5]
