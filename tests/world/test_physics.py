"""Physics checker (§4.9). P-1/P-2 (incl. the corrected half-open formula, T-31), P-3/P-4/P-5,
P-9 (I-30, T-16), and the Phase 1 exit check on `vance_v03`/negative fixtures."""
from __future__ import annotations

import random

from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, EffActorState, EffObjectState, Event
from eidolon.world.physics import Implication, check_physics
from eidolon.world.propositions import State
from eidolon.world.space import Location, TravelEdge
from tests.world.fixtures.vance import vance_v01_negative, vance_v02_negative, vance_v03

ACTORS = {"David": Actor(id="David", name="David", role="suspect"),
          "Harold": Actor(id="Harold", name="Harold", role="victim")}
LOCS = {"Hall": Location(id="Hall", name="Hall"), "Study": Location(id="Study", name="Study")}
EDGES = (TravelEdge(a="Hall", b="Study", minutes=1),)


def _stay(actor, loc, s, e):
    return Event(id=f"{actor}:{loc}:{s}", kind="Stay", interval=(s, e), location=loc, actor=actor,
                 effects=(EffActorAt(actor=actor, location=loc),))


def test_T31_p2_half_open_boundary_from_worked_example():
    """§29.1's own timetable: Library until 22:03, Hall at 22:04, Kitchen at 22:05, on
    1-minute edges. The v0.3 formula (off by one) rejected this; the corrected one passes it."""
    locs = {"Library": Location(id="Library", name="Library"), "Hall": Location(id="Hall", name="Hall"),
            "Kitchen": Location(id="Kitchen", name="Kitchen")}
    edges = (TravelEdge(a="Library", b="Hall", minutes=1), TravelEdge(a="Hall", b="Kitchen", minutes=1))
    actors = {"D": Actor(id="D", name="D", role="suspect")}
    events = (_stay("D", "Library", 0, 63), _stay("D", "Hall", 64, 65), _stay("D", "Kitchen", 65, 120))
    case = Case(id="timetable", t_investigation=120, actors=actors, locations=locs, events=events, travel_edges=edges)
    assert check_physics(case) == []


def test_p2_rejects_a_gap_shorter_than_travel_time():
    events = (_stay("David", "Hall", 0, 5), _stay("David", "Study", 5, 10))
    edges = (TravelEdge(a="Hall", b="Study", minutes=2),)
    case = Case(id="c", t_investigation=10, actors=ACTORS, locations=LOCS, events=events, travel_edges=edges)
    violations = check_physics(case)
    assert any(v.rule == "P-2" for v in violations)


def test_p1_rejects_overlapping_presence():
    events = (_stay("David", "Hall", 0, 6), _stay("David", "Study", 5, 10))
    case = Case(id="c", t_investigation=10, actors=ACTORS, locations=LOCS, events=events, travel_edges=EDGES)
    assert any(v.rule == "P-1" for v in check_physics(case))


def test_p3_rejects_take_without_colocation():
    from eidolon.world.entities import Object
    objs = {"knife": Object(id="knife", name="knife", kind="weapon", initial_location="Study")}
    events = (_stay("David", "Hall", 0, 10),
              Event(id="take", kind="Take", interval=(3, 4), location="Study", actor="David", objects=("knife",)))
    case = Case(id="c", t_investigation=10, actors=ACTORS, locations=LOCS, objects=objs, events=events, travel_edges=EDGES)
    assert any(v.rule == "P-3" for v in check_physics(case))


def test_p4_rejects_action_after_death_and_missing_colocation():
    events = (
        _stay("David", "Study", 0, 10),
        _stay("Harold", "Hall", 0, 5),  # not co-located with the attacker
        Event(id="attack", kind="Attack", interval=(2, 3), location="Study", actor="David", participants=("Harold",)),
        Event(id="die", kind="Die", interval=(3, 4), location="Study", actor="Harold",
              effects=(EffActorState(actor="Harold", attr="alive", value="false"),)),
    )
    case = Case(id="c", t_investigation=10, actors=ACTORS, locations=LOCS, events=events, travel_edges=EDGES)
    rules = {v.rule for v in check_physics(case)}
    assert "P-4" in rules


def test_p5_rejects_travel_through_an_unmet_condition():
    from eidolon.world.space import Condition
    door = Condition(kind="DoorUnlocked", args=("study_door",))
    edges = (TravelEdge(a="Hall", b="Study", minutes=1, conditions=(door,)),)
    events = (_stay("David", "Hall", 0, 5), _stay("David", "Study", 5, 10))
    case = Case(id="c", t_investigation=10, actors=ACTORS, locations=LOCS, events=events, travel_edges=edges)
    # no ObjectState effect ever unlocks study_door -> condition never holds
    assert any(v.rule == "P-5" for v in check_physics(case))


def test_p5_allows_travel_once_condition_is_met():
    from eidolon.world.space import Condition
    from eidolon.world.entities import Object
    door = Condition(kind="DoorUnlocked", args=("study_door",))
    edges = (TravelEdge(a="Hall", b="Study", minutes=1, conditions=(door,)),)
    objs = {"study_door": Object(id="study_door", name="study door", kind="door", initial_location="Study")}
    events = (
        _stay("David", "Hall", 0, 5),
        Event(id="unlock", kind="Use", interval=(2, 3), location="Hall", actor="David", objects=("study_door",),
              effects=(EffObjectState(object="study_door", attr="locked", value="false"),)),
        _stay("David", "Study", 5, 10),
    )
    case = Case(id="c", t_investigation=10, actors=ACTORS, locations=LOCS, objects=objs, events=events, travel_edges=edges)
    assert check_physics(case) == []


def test_T16_p9_rejects_ungrounded_implication_interval():
    imp = Implication(proposition=State(actor="David", attr="drunk", value="true", interval=(0, 10)),
                       requires=(), created_at=(9, 10))
    case = Case(id="c", t_investigation=10, actors=ACTORS, locations=LOCS,
                events=(_stay("David", "Hall", 0, 10),), travel_edges=EDGES)
    assert any(v.rule == "P-9" for v in check_physics(case, [("E1", imp)]))


def test_p9_accepts_implication_with_requires_regardless_of_grounding():
    imp = Implication(proposition=State(actor="David", attr="drunk", value="true", interval=(0, 10)),
                       requires=("some_statement",), created_at=None)
    case = Case(id="c", t_investigation=10, actors=ACTORS, locations=LOCS,
                events=(_stay("David", "Hall", 0, 10),), travel_edges=EDGES)
    assert check_physics(case, [("E1", imp)]) == []


# --- Phase 1 exit criterion -------------------------------------------------------------
def test_vance_v03_check_physics_is_clean_including_p9():
    case, evidence = vance_v03()
    assert check_physics(case, evidence) == []


def test_vance_v01_negative_is_physics_clean():
    """v01's defect is solver-level (collusion), not physics."""
    case, evidence = vance_v01_negative()
    assert check_physics(case, evidence) == []


def test_vance_v02_negative_fails_p9_on_e10():
    """§29.1: E10 (bolted terrace door) is observed only at t_investigation and asserted
    over the whole evening with no `requires` — P-9/I-30 must reject it."""
    case, evidence = vance_v02_negative()
    violations = check_physics(case, evidence)
    assert any(v.rule == "P-9" and "E10" in v.detail for v in violations)


# --- property test (§28.3: "physics vs brute force", T-31) -----------------------------
def test_property_p2_matches_independent_gap_computation():
    """A tiny 3-node graph with hand-computed pairwise distances, checked against
    `check_physics` over many random single-actor two-segment timelines."""
    dist = {("Hall", "Study"): 2, ("Study", "Hall"): 2, ("Hall", "Kitchen"): 1, ("Kitchen", "Hall"): 1,
            ("Study", "Kitchen"): 3, ("Kitchen", "Study"): 3}
    locs = {n: Location(id=n, name=n) for n in ("Hall", "Study", "Kitchen")}
    edges = (TravelEdge(a="Hall", b="Study", minutes=2), TravelEdge(a="Hall", b="Kitchen", minutes=1),
             TravelEdge(a="Study", b="Kitchen", minutes=3))
    rng = random.Random(1234)
    for _ in range(200):
        l1, l2 = rng.sample(list(locs), 2)
        s1 = rng.randint(0, 20)
        e1 = s1 + rng.randint(1, 5)
        gap = rng.randint(1, 5)  # gap 0 would force overlap at the shared boundary tick (P-1, not P-2)
        s2 = e1 - 1 + gap
        e2 = s2 + rng.randint(1, 5)
        if e2 <= s2:
            continue
        events = (_stay("David", l1, s1, e1), _stay("David", l2, s2, e2))
        case = Case(id="c", t_investigation=e2 + 1, actors={"David": Actor(id="David", name="David", role="suspect")},
                    locations=locs, events=events, travel_edges=edges)
        violations = check_physics(case)
        expected_ok = gap >= dist[(l1, l2)]
        got_ok = not any(v.rule == "P-2" for v in violations)
        assert got_ok == expected_ok, (l1, l2, s1, e1, s2, e2, gap, violations)
