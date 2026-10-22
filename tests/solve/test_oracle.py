"""The DP (`world.feasibility._search`), the arrival-jump oracle and exhaustive enumeration must
agree. Three implementations of one question: a disagreement is a bug in one of them."""
import pytest
from hypothesis import given, settings, strategies as st

from eidolon.solve.oracle import brute_feasible, check_walk, oracle_feasible
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.feasibility import _search
from eidolon.world.space import Location, TravelEdge

# a tiny house: A -1- B -2- C  (B is the only way between A and C)
TINY = Case(id="tiny", t_investigation=7, actors={"x": Actor(id="x", name="x", role="suspect")},
            locations={k: Location(id=k, name=k) for k in "ABC"},
            travel_edges=(TravelEdge(a="A", b="B", minutes=1), TravelEdge(a="B", b="C", minutes=2)))
T = TINY.t_investigation
STARTS = [(L, 0) for L in "ABC"]


def all_three(blocked, forced, exist, goal=None):
    dp = _search(TINY, T, STARTS, blocked, forced, exist, goal)[0]
    orc = oracle_feasible(TINY, T, blocked, forced, exist, STARTS, goal)
    bru = brute_feasible(TINY, T, blocked, forced, exist, STARTS, goal)
    return dp, orc, bru


cell = st.tuples(st.sampled_from("ABC"), st.integers(0, T - 1))


@settings(max_examples=40, deadline=None)
@given(blocked=st.sets(cell, max_size=6),
       forced=st.dictionaries(st.integers(0, T - 1), st.sampled_from("ABC"), max_size=4),
       exist=st.lists(st.sets(cell, min_size=1, max_size=3), max_size=2),
       goal=st.sampled_from([None, "A", "C"]))
def test_dp_oracle_and_brute_force_agree(blocked, forced, exist, goal):
    dp, orc, bru = all_three(blocked, forced, exist, goal)
    assert dp == orc == bru


def test_travel_semantics_fixed_points():
    # A at 0 and C at 2 is impossible (A->B 1, B->C 2 = 3 minutes); C at 3 is possible
    assert all_three(set(), {0: "A", 2: "C"}, [])[:2] == (False, False)
    assert all_three(set(), {0: "A", 3: "C"}, [])[:2] == (True, True)


def test_tail_cannot_stay_put_on_a_blocked_tick():
    # C at 0 and 2 with (C,1) blocked: staying is blocked, the only round trip takes 4 minutes (Hypothesis counterexample)
    assert all_three({("C", 1)}, {0: "C", 2: "C"}, []) == (False, False, False)


def test_a_walk_may_drift_in_transit_straight_after_its_last_visit():
    # the only existential is met on the LAST tick, so nothing needs the actor to stand anywhere before it: an oracle whose
    # tail loop starts a tick late (mutant TK3, Phase 8 review H8-N10) rejects this and, in the verifier, valid proofs
    assert all_three(set(), {}, [{("A", T - 1)}]) == (True, True, True)


ISO = Case(id="iso", t_investigation=3, actors={"x": Actor(id="x", name="x", role="suspect")},       # C has no travel edge
           locations={k: Location(id=k, name=k) for k in "ABC"}, travel_edges=(TravelEdge(a="A", b="B", minutes=1),))


@pytest.mark.xfail(strict=True, reason="H8-X2, NON-BLOCKING and open: the DP cannot leave a room with no travel edge; the oracle "
                                       "and brute force still drift out of it. No generated case has such a room. Fix, then drop this marker.")
def test_known_divergence_a_room_with_no_exit_cannot_be_left():
    starts, args = [(L, 0) for L in "ABC"], ({("C", 1)}, {0: "C"}, [])         # in C at tick 0, C barred at tick 1
    dp = _search(ISO, 3, starts, *args, None)[0]
    assert dp is False
    assert oracle_feasible(ISO, 3, *args, starts, None) == brute_feasible(ISO, 3, *args, starts, None) == dp


def test_dp_witness_paths_validate():
    ok, path = _search(TINY, T, STARTS, set(), {0: "A", 4: "C"}, [{("B", 2)}])
    assert ok and check_walk(TINY, [loc for loc, _ in path], set(), {0: "A", 4: "C"}, [{("B", 2)}])


def test_walk_checker_rejects_teleport_and_forced_transit():
    assert not check_walk(TINY, ["A", "C"] + ["C"] * 5, set(), {}, [])
    assert not check_walk(TINY, ["A", "~", "C", "C", "C", "C", "C"], set(), {1: "A"}, [])


# a house with a THREE-minute edge: transit-state bookkeeping differs for d >= 3 (d - 2 ticks in transit)
LONG = Case(id="long", t_investigation=8, actors={"x": Actor(id="x", name="x", role="suspect")},
            locations={k: Location(id=k, name=k) for k in "ABC"},
            travel_edges=(TravelEdge(a="A", b="B", minutes=1), TravelEdge(a="B", b="C", minutes=3)))


def test_three_minute_edge_semantics_agree_across_dp_oracle_and_brute_force():
    starts = [(L, 0) for L in "ABC"]
    for forced, want in (({0: "B", 2: "C"}, False), ({0: "B", 3: "C"}, True), ({0: "A", 3: "C"}, False), ({0: "A", 4: "C"}, True)):
        dp = _search(LONG, 8, starts, set(), forced, [])[0]
        assert dp == oracle_feasible(LONG, 8, set(), forced, [], starts) == brute_feasible(LONG, 8, set(), forced, [], starts) == want
